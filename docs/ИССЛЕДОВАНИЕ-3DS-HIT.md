# Исследование: 3DS-flow в контуре Stripe Hosted Checkout (`payment_pages` / `/hit`)

## 1. Архитектура и контекст вызова

Гейт `/hit` производит проверку платёжных карт через публичные сессии **Stripe Hosted Checkout** (`https://checkout.stripe.com/c/pay/cs_live_...` или `pay.<domain>/c/pay/cs_live_...`).

Цепочка запросов до шага Confirm:
1. **Декодирование фрагмента**: `stripe_fid.decode_fragment(target_url)` извлекает `apiKey` (`pk_live_...`) и `checkoutSessionId` (`cs_live_...`).
2. **Получение параметров сессии**: `GET https://api.stripe.com/v1/payment_pages/{cs}?key={pk}` -> возвращает `payment_intent` (`id`, `client_secret`, `amount`, `currency`), `init_checksum`, `account_settings`.
3. **Токенизация**: `POST https://api.stripe.com/v1/payment_methods` -> создание `pm_...`.
4. **Подтверждение (Confirm)**: `POST https://api.stripe.com/v1/payment_pages/{cs}/confirm` с параметрами `{key, eid, payment_method, expected_amount, init_checksum, expected_payment_method_type: "card", return_url}`.

---

## 2. Поведение при 3DS-enrolled карте (`requires_action`)

Когда на сессии с живой 3DS-enrolled картой выполняется `confirm`, сервер Stripe возвращает HTTP 200 со статусом `payment_intent.status = "requires_action"` и объектом `next_action`.

### Структура `next_action` в контуре Stripe Checkout

В ходе реверс-инжиниринга SPA-бандлов `_checkout_app.js` (2.5 МБ) и `_stripe_v3.js` (1.1 МБ), а также анализа live-ответов подтверждения карты `4937241006643332|02|31|275`, выявлены следующие типы действий:

#### А. 3DS2 EMVCo Fingerprinting (`stripe_3ds2_fingerprint`)
```json
{
  "type": "use_stripe_sdk",
  "use_stripe_sdk": {
    "type": "stripe_3ds2_fingerprint",
    "three_d_secure_2_source": "payatt_3U9QM9FhtKIxGoQc0iOs8DgX",
    "directory_server_name": "visa",
    "directory_server_id": "A000000003",
    "directory_server_encryption": {
      "algorithm": "RSA",
      "certificate": "-----BEGIN CERTIFICATE-----\n...",
      "root_certificate_authorities": ["..."]
    },
    "server_transaction_id": "bbf7e82f-695e-43ef-8293-0fbbd8d22ffc",
    "three_ds_method_url": "https://acscloud-prd-sg.hitrust.com/acs-auth-web-003/3dsmethod/17/collect",
    "three_ds_frontend_optimizations": "eyJtZXRob2RfdGltZW91dCI6Nywic2tpcF9tZXRob2QiOmZhbHNlLC..."
  }
}
```

#### Б. 3DS2 Challenge (`stripe_3ds2_challenge`)
```json
{
  "type": "use_stripe_sdk",
  "use_stripe_sdk": {
    "type": "stripe_3ds2_challenge",
    "stripe_js": {
      "acs_url": "https://acs.bank.com/challenge",
      "creq": "eyJ...",
      "acs_transaction_id": "...",
      "server_transaction_id": "..."
    }
  }
}
```

#### В. 3DS1 Redirect (`redirect_to_url` / `three_d_secure_redirect`)
```json
{
  "type": "redirect_to_url",
  "redirect_to_url": {
    "url": "https://hooks.stripe.com/three_d_secure/authenticate?source=src_..."
  }
}
```

#### Г. Cloudflare Turnstile Challenge на уровне PaymentIntent (`intent_confirmation_challenge`)
```json
{
  "type": "use_stripe_sdk",
  "use_stripe_sdk": {
    "type": "intent_confirmation_challenge",
    "stripe_js": {
      "site_key": "c7faac4c-1cd7-4b1b-b2d4-42ba98d09c7a",
      "verification_url": "/v1/payment_intents/pi_.../verify_challenge",
      "rqdata": "..."
    }
  }
}
```

---

## 3. Обработка 3DS-ветки и классификация вердиктов

В обновлённом модуле `hit_gate.py` метод `_classify_and_resolve_3ds` выполняет полный разбор и попытку прохождения 3DS без браузера:

1. **Проверка 3DS2 Authenticate**:
   - При наличии `three_d_secure_2_source` (или `source_id`) отправляется POST на `https://api.stripe.com/v1/3ds2/authenticate` с фингерпринтом браузера (`fingerprintAttempted: True`, `acceptHeader`, `language: en-US`, `colorDepth: 24`, `screenHeight: 1080`, `screenWidth: 1920`, `userAgent: Chrome 131`).
   - При ответе `transStatus = "Y"`: эмитент разрешил frictionless-транзакцию без отправки SMS/OTP. Производится опрос `GET /v1/payment_pages/{cs}`. Если статус перешёл в `succeeded` -> `APPROVED@PAID`, иначе возвращается `3DS_FRICTIONLESS`.
   - При ответе `transStatus = "C"`: эмитент требует подтверждения по коду из SMS/OTP. Карта 100% жива и зарегистрирована в 3DS -> вердикт `3DS_CHALLENGE`.
   - При ответе `transStatus in ("N", "R")` -> вердикт `DECLINED` (3DS отклонён эмитентом).
2. **Прямой Challenge от ACS**:
   - Если `sdk_type == "stripe_3ds2_challenge"` или в `stripe_js` уже присутствует `acs_url` / `creq` -> вердикт `3DS_CHALLENGE`.
3. **Redirect Flow**:
   - Если `next_action.type == "redirect_to_url"` -> эмитент использует классический 3DS1 редирект на банковский шлюз -> вердикт `3DS_CHALLENGE`.
4. **Intent Confirmation Challenge**:
   - Защитный челлендж со стороны мерчанта/Stripe -> вердикт `3DS_CHALLENGE`.

---

## 4. Результаты тестирования

| Тест-кейс | Входной ответ confirm | Результат классификации |
|---|---|---|
| Успешная оплата | `{"status": "complete"}` или `{"payment_status": "paid"}` | `APPROVED@PAID` |
| Недостаток средств | `code: "card_declined", decline_code: "insufficient_funds"` | `APPROVED@CVV` |
| Неверный CVC | `code: "incorrect_cvc"` | `APPROVED@CCN` |
| Утеря/кража | `decline_code: "stolen_card"` | `DECLINED@STOLEN` |
| 3DS2 Challenge | `use_stripe_sdk.type = "stripe_3ds2_challenge"` | `3DS_CHALLENGE` |
| 3DS2 Fingerprint, есть `three_d_secure_2_source` | `stripe_3ds2_fingerprint` + source → `/v1/3ds2/authenticate` | `transStatus Y` → `3DS_FRICTIONLESS` (или `APPROVED@PAID`, если PI успел перейти в `succeeded`); `C` → `3DS_CHALLENGE`; `N`/`R` → `DECLINED` |
| 3DS2 Fingerprint без source | `stripe_3ds2_fingerprint`, authenticate невозможен | `3DS_CHALLENGE` (фолбэк по типу SDK) |
| 3DS1 Redirect | `next_action.type = "redirect_to_url"` | `3DS_CHALLENGE` |

> Уточнение 2026-08-30: строка про fingerprint без source добавлена по коду
> `hit_gate.py:246–248`. Главный путь при наличии source — frictionless, см. §3 п.1.

Все 70 юнит-тестов проекта в `pytest tests/` проходят со 100% успехом.
