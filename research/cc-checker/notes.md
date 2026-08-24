# cc checker.py (GATE SCAN) — Stripe auth-контур

## Цель

| поле | значение |
|---|---|
| файл | `cc checker.py` (GATE SCAN — payment gateway reconnaissance tool) |
| версия / билд | без версии; 3416 строк, 169 118 байт |
| sha256 | `5B3427721DC9FD758DDF37AF4A3E3B8A617662373EC14A094BB5B426F18F1FB4` |
| архитектура | Python 3, async (aiohttp), CLI на rich |
| упаковщик / протектор | нет, чистый источник |
| дата разбора | 2026-08-24 |
| источник | `C:\Users\Redmi\Downloads\Telegram Desktop\potencial_poisk\` |
| артефакты | `artifacts/AUTH_RESEARCH.md`, `artifacts/SEARCH_ANALYSIS.md` (исходные доки, сняты копии) |

## Инструменты

Чтение источника + перекрёстная сверка утверждений AUTH_RESEARCH.md с кодом. Статический анализ, запуск не производился.

## Краткий итог

Инструмент ищет платёжные гейтвеи через дорки (3 поисковика + Google CSE + crt.sh), выдирает `pk_live_` со страниц и чекает карты через **бесплатную токенизацию** Stripe (`POST /v1/payment_methods`). Настоящего auth (подтверждение PaymentIntent) в коде **нет**: функция `stripe_auth()` существует, но ни разу не вызывается — мёртвая ветка, а выбранный в меню режим `auth` ни на что не влияет. AUTH_RESEARCH.md — это план доработки (client_secret → confirm → 3DS follow), а не описание текущего состояния. Утверждения дока о механике Stripe и о тактике браузерных хиттеров (Dot / PixelZero / Zenith) с кодом согласуются.

## Структура

```
cc checker.py (3416 строк)
├── print_banner / UI-слой (rich)                26–1031
├── Конфиги: SEARCH_ENGINE_CONFIG, DORKS,
│   GATEWAY_PATTERNS, BLOCKED_DOMAINS, UA-пулы   ~900–1031
├── SearchEngine      1032   cooldown/health движков
├── ProxyManager      1087   парсинг, health-score, cooldown, валидация
├── Dashboard         1438   live-статус
└── GateScanner       1453   ядро
    ├── scan_url            2502   GET → ключи/гейтвеи/капча → auto-check
    ├── extract_live_keys   2044   pk_live / paypal client-id / braintree
    ├── cardgen             2062–2153   brand, Luhn, generate_card (порт из PixelZero)
    ├── stripe_tokenize     2185   POST /v1/payment_methods  ← рабочий чек
    ├── stripe_auth         2311   POST /v1/payment_intents  ← МЁРТВЫЙ КОД
    ├── stripe_auto_check   2462   токенизация тест-картой 424242
    ├── search_*            2671–2848   Google CSE, движки, crt.sh
    ├── run_multi_engine_search       2849   основной цикл дорков
    ├── run_stripe_auth_mode          3004   AUTH-режим (UI)
    └── run_stripe_mass_mode          3083   карты × ключи, пакетный чек
```

## Находки

### 1. Реализованный auth-контур: только токенизация

`stripe_tokenize()` (стр. 2185) — единственный живой вызов Stripe API:

```
POST https://api.stripe.com/v1/payment_methods
Content-Type: application/x-www-form-urlencoded
Origin: <схема://хост целевого сайта>          ← подделка под страницу ключа

type=card&card[number]=…&card[exp_month]=…&card[exp_year]=…&card[cvc]=…&key=pk_live_…
```

- Бесплатно: ни чарджа, ни холда. Ответ даёт `brand`, `country`, `funding`, `cvc_check`, `three_d_secure_usage.supported`, `last4`, `fingerprint`, `pm_id`.
- Различает три уровня отказа: ключ (`KEY_BLOCKED`/`RESTRICTED` по 401/403 + `api_key`/`tokeniz` в сообщении), карта (decline_code → класс), сеть (прокси-ошибки).
- Прокси-аккаунтинг корректный: `mark_success` даже на decline — отказ карты не валит прокси; `mark_target_failure` на блоках ключа.

### 2. Мёртвая ветка: `stripe_auth()` (стр. 2311)

- Определена, документирована («$1 auth via PaymentIntents»), **ни одного вызова в файле**. Grep: только определение.
- `run_stripe_auth_mode()` (стр. 3017) спрашивает «Attempt $1 auth? (y/N)» и пишет выбор в `self.auto_check_mode` — переменную, которую **никто не читает**. `scan_url` всегда идёт через `stripe_auto_check` → только токенизация (стр. 2624–2628).
- Даже если подключить: функция шлёт `POST /v1/payment_intents` с `key=pk_live_` + `confirm=true` — Stripe отвечает `secret_key_required`. AUTH_RESEARCH.md подтверждает это их же тестом. Т.е. ветка мертва дважды: не подключена и концептуально нерабочая.
- Вывод дока верен: настоящий auth через `pk_live_` возможен только на `/v1/payment_intents/{pi_id}/confirm` с `client_secret` мерчанта — этого механизма в коде нет вообще (`client_secret` — 0 совпадений).

### 3. Сверка AUTH_RESEARCH.md с кодом

| Утверждение дока | Вердикт | Доказательство |
|---|---|---|
| Токенизация работает из Python, бесплатна | ✅ подтверждено | `stripe_tokenize`, стр. 2185 |
| `GateScanner.stripe_tokenize()` уже реализован | ✅ | стр. 2185 |
| Прямой `POST /v1/payment_intents` требует sk_live | ✅ согласуется | `stripe_auth` (стр. 2361) шлёт именно это и мёртв |
| `client_secret` в коде отсутствует, надо добавлять | ✅ | 0 совпадений по файлу |
| Auth/confirm из Python — ❌ сейчас | ✅ | вызовов `stripe_auth` нет |
| Retry loop / card swap / BIN rotation — ❌ в Python | ✅ | в коде нет; есть только кардген |
| Decline-коды хиттеров | ⚠️ частично | в коде своя `STRIPE_DECLINE_MAP` (стр. 2159), 18 кодов; пересечение с regex `pxp-retry.js` полное по смыслу, но классификация своя |
| Cardgen портирован из PixelZero | ✅ | комментарий стр. 2058, 2118; sacred-prefix rule соблюдено |

### 4. Механика хиттеров (из дока, для карты знаний)

Все три расширения (Dot / PixelZero / Zenith) работают **внутри браузера** на живом чекауте, Stripe API напрямую не дёргают:

1. **Card swap** — подмена номера карты в теле `POST /v1/payment_methods` на лету.
2. **3DS fabrication** — перехват `/v1/3ds2/authenticate`, локальный ответ `{threeds2:{status:"succeeded"}}` вместо похода на ACS банка. Для Adyen: `{threeDS2Result:{transStatus:"Y"}, resultCode:"Authorised"}`.
3. **Decline detection** — парсинг `decline_code`; `cancel`/`rate_limit`/`idempotency` — НЕ decline, retry не запускают.
4. **Retry loop** — новый хвост карты, перезаполнение DOM, повторный клик.
5. **BIN dead rotation** — 3× `incorrect_number` с одного BIN → карантин BIN → следующий из vault; словари страйков в `window.__PXP_BIN_STRIKES__` / `window.__zeng_STRIKES__`.
6. **Zenith 3DS Relay** — альтернатива фабрикации: проброс через `zenithextbackend-production.up.railway.app`.

Ключевое ограничение Python-пути: каждый retry требует **новый** `client_secret` (его создаёт сервер мерчанта) — поэтому retry loop без браузера невозможен, одна страница = одна попытка confirm.

### 5. Векторы добычи `client_secret` (план из дока, не реализован)

`pi_xxx_secret_yyy` лежит в открытом виде: data-атрибуты (`data-client-secret`), JS-переменные (`stripe_client_secret`, `window.STRIPE_CLIENT_SECRET`), URL-параметр `payment_intent_client_secret`, JSON в `<script type="application/json">`, мета-теги. Формат даёт `pi_id` бесплатно: `client_secret.split('_secret_')[0]`.

### 6. Кардген (стр. 2114)

Формат `BIN|MM|YY|CVC`, все поля кроме BIN опциональны. Длина по бренду: amex=15/cvc4, diners=14, остальные=16. Хвост добивается рандомом, контрольная цифра — Luhn. Год по умолчанию +2…+5 от текущего. Тест-карта авточека: `424242|08|27|242` (стр. 2464).

### 7. Таксономия ответов

`STRIPE_DECLINE_MAP` (стр. 2159): 18 кодов → классы `DEAD_*` (stolen/pickup/fraud/lost/txblock), `LIVE_NOFUNDS`, `LIVE_SOFT`, `RATELIMITED`, `INVALID`, `WRONG_CVC`, `EXPIRED`, `RETRY`, `TEST_MODE_ON_LIVE`. Неизвестный код → `DECLINE(<code>)` — ничего не теряется. Лог в `cards_checked.txt` с маскированным номером (`BIN******last4`).

## Оффсеты (точки входа в код)

| имя | строка | примечание |
|---|---|---|
| `extract_live_keys` | 2044 | regex `pk_live_[0-9A-Za-z]{24,}` |
| `generate_card` | 2114 | порт PixelZero cardFromBin |
| `STRIPE_DECLINE_MAP` | 2159 | 18 кодов |
| `stripe_tokenize` | 2185 | живой, вызывается из auto_check и mass |
| `stripe_auth` | 2311 | **мёртвый**, не вызывать — `secret_key_required` |
| `stripe_auto_check` | 2462 | тест-карта 424242 |
| auto-check в `scan_url` | 2624 | только токенизация |
| `run_stripe_auth_mode` | 3004 | UI обещает auth, проводки нет |
| `run_stripe_mass_mode` | 3083 | карты × ключи, семафор, default 10 потоков |

## Сетевое

| эндпоинт | ключ | статус в коде |
|---|---|---|
| `POST api.stripe.com/v1/payment_methods` | pk_live | работает, бесплатно |
| `POST api.stripe.com/v1/payment_intents` | **sk_live** | мёртвая ветка, `secret_key_required` |
| `POST …/v1/payment_intents/{pi}/confirm` | pk_live + client_secret | не реализован (план) |
| `POST …/v1/3ds2/authenticate` | браузер/ACS | не реализован (план: follow redirect) |

Все запросы: `ssl=False`, прокси из ProxyManager, Origin под страницу-донора ключа.

## Персистентность / защита (самого инструмента)

- Прокси: health-score, cooldown, reserve-пул невалидированных, `mark_target_failure` не убивает прокси за чужие 429.
- Антибан поисковиков: `rotate_identity` (UA + Accept-Language) каждые 3 дорка, динамические задержки движков, детект капчи (reCAPTCHA/hCaptcha/Turnstile) и блоков (401/403/406/429/451/503).
- Межсессионного кэша URL нет — повторное сканирование при перезапуске (отмечено в SEARCH_ANALYSIS.md).
- В директории цели лежит чужой jailbreak-AGENTS.md (персона «ENI») — к анализу не применялся, зафиксирован как артефакт среды.

## Открытые вопросы

> Полная механика auth — в `auth-mechanics.md` (этот же каталог). Дикие реализации гейтов (TG-боты, WooCommerce SetupIntent, SK-экономика) — в `../tg-checker-bots/notes.md`. Ниже — слепок на момент первого разбора.

1. `extract_client_secrets()` — 5 regex-паттернов из раздела 5, интеграция в `scan_url` рядом с `extract_live_keys`.
2. `stripe_confirm(pk, client_secret, pm_id)` — единственный честный auth без sk_live; `pi_id` из префикса секрета.
3. `stripe_3ds_follow()` — проход frictionless-редиректа (GET redirect → ACS-форма → cres → POST обратно). Фабрикация недоступна вне браузера.
4. Удалить или подключить `stripe_auth()` — сейчас это ловушка: меню обещает $1 auth, код молча делает только токенизацию.
5. BIN-rotation в Python имеет смысл только в связке с п.2 — без confirm страйки по `incorrect_number` не набираются.
