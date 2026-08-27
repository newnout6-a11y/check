# pusto — Инфраструктура исследования шлюзов, парсинга доноров и валидации карт

Чистая структура проекта для быстрого ориентирования в сессиях.

---

## 🎯 Основные инструменты на верстаке (Корень проекта)

### 1. `setup_gate.py` — Главный боевой чекер карт ($0 SetupIntent Live Gate)
* **Движок:** `curl_cffi` с Chrome TLS-имперсонацией (`chrome131`) — проходит Cloudflare WAF, который резал aiohttp.
* **Pre-flight:** Luhn-проверка каждой карты + BIN-обогащение (схема/тип/страна/банк через binlist → handyapi) до прогона и в итоговой сводке.
* **Session Reuse:** одна авторизованная WP-сессия на донора обслуживает всю пачку карт — регистрации больше не плодятся на каждую карту. Протухший ajax-nonce обновляется автоматически одним ретраем.
* **Прокси:** `--proxy <url>` или пул `data/proxies.txt` (формат в `data/proxies.txt.example`) — свой прокси на каждую сессию донора.
* **Лог результатов:** каждый вердикт пишется в `data/results/YYYY-MM-DD.jsonl` (masked PAN, BIN, донор, статус, латентность).
* **Health пула:** успех сбрасывает счётчик фейлов донора, три гейт-отказа подряд — автоудаление из `data/ready_gates.json`.
* **Назначение:** Полнофункциональный не-SK валидатор карт через боевой WooCommerce Stripe SetupIntent. Пробивает эмитент без списания средств, возвращает точные вердикты (`APPROVED`, `3DS_REQUIRED`, `DECLINED`).
* **Пул доноров:** Автоматически загружается из `data/ready_gates.json`. При падении донора — авто-ротация на следующего.
* **Подтверждена аутентификация банком:** Карта `537872******8595` → `seti_1U86Qx...` → `succeeded`. Банк показал уведомление в приложении.
* **Запуск:**
  ```bash
  # Одиночная карта:
  python setup_gate.py "5175465382242090|09|2030|018"
  
  # Несколько карт:
  python setup_gate.py "CARD1" "CARD2"
  
  # Из файла с картами:
  python setup_gate.py cards.txt
  
  # С указанием своего мерчанта-донора:
  python setup_gate.py https://target-donor.com "CARD1"
  ```

### 2. `advanced_gate_scanner.py` — 4-стадийный сканер и классификатор (v5, curl_cffi)
* **Движок:** `curl_cffi` Chrome TLS-имперсонация через общий `gate_client.py` (телеметрия v2021 + m-cookie префетч, ротация Luhn-валидных пробников).
* **Прокси:** `--proxy <url>` или пул `data/proxies.txt`, случайная ротация на каждый пробник.
* **TTL пула:** неподтверждённые 24ч гейты метятся `STALE`, старше 72ч — удаляются из пула автоматически.
* **Движок:** `curl_cffi` Chrome TLS-имперсонация — обходит динамический Cloudflare WAF, который резал POST-регистрацию на aiohttp.
* **4 стадии:** DNS-резолв → GET-проба формы → POST-регистрация (Chrome TLS) → скрапинг `pk_live` + SetupIntent nonces → боевой confirm-пробник.
* **Метрики:** Из 348 доменов: 316 живых DNS → 15 открытых форм → 1 квалифицированный SetupIntent-гейт.
* **Результат:** Сохраняет готовый пул в `data/ready_gates.json` и `data/active_surfaces.json`.
* **Запуск:** `python advanced_gate_scanner.py`

### 3. `confirm_gate.py` — PaymentIntent Confirm Engine (второй вектор, Фаза 2)
* **Вектор:** любой сайт со Stripe checkout, где торчит `pi_..._secret_...` — не только WooCommerce. 5 векторов экстракции секрета (data-attr / js-var / url-param / json / meta).
* **Разведка перед боем:** бесплатный retrieve PI — сумма/статус/capture_method; секрет с PI > $100 помечается `CHARGE_RISK` и не подтверждается.
* **Retry loop:** после card_error секрет живёт (PI возвращается в `requires_payment_method`) — бюджет 20 подтверждений на секрет (`config.MAX_CONFIRMS_PER_SECRET`), при исчерпании — минт нового через найденные эндпоинты.
* **3DS двух поколений:** `/v1/3ds2/authenticate` с browser fingerprint (transStatus Y = frictionless прошёл; C = карта enrolled); 3DS1 — цепочка auto-submit форм ACS.
* **Классификатор:** 12 вердиктов PI + ветки 3DS, полная таксономия в `config.py`.
* **Запуск:** `python confirm_gate.py <checkout-url> [--proxy URL] [cards...|file]`

### 3b. `store_gate.py` — Woo Store API Direct-Confirm (третья поверхность)
* **Вектор:** любая WooCommerce+Stripe Blocks-корзина без требований к торчащим секретам или SetupIntent-гейту.
* **Цепочка:** `GET /cart` (nonce из заголовка) → `/products` (самый дешёвый платный товар с перебором out-of-stock) → `add-item` → токенизация карты на pk донора → `POST /checkout` с pm_id → вердикт эмитента.
* **ВАЖНО:** это платёжная авторизация на сумму товара, не $0-auth — крышка `--max-price` (default $2), перебор только под капом.
* **Цели:** `data/store_targets.txt` (строится `scratch/_build_store_targets.py` + фильтр pk через `scratch/_probe_pk_targets.py`).
* **Запуск:** `python store_gate.py <url|file> [cards...] --max-price 200`

### 3c. Store-API Surface Scanner — конвейер квалификации доноров
* `scratch/_scan_store_gates.py` — скан всей очереди domains.db на Blocks-поверхность: cart-nonce → товары → pk_live на витрине → бесплатная токенизация probe-картой (живость ключа). Пишет `data/store_gates.json` + `data/store_targets.txt`.
* `scratch/_verify_all_store.py` — боевая верификация пула probe-картой: эмитентный вердикт (DECLINED всех природ) = гейт подтверждён. Пишет `verified: true` в store_gates.json.
* `scratch/_finalize_pool.py` — сводит все вектора (setup + store + mint) в `data/final_gates.json`.
* **Движок** (gate_client.store_api_confirm) прошёл харденнинг: shipping-rate выбор через update-customer, enum-ретрай payment_method из локализованных ошибок (nl/fr/de/es/lt), гео-выравнивание по стране магазина из GET /checkout, 19 GEO-пулов, ISO-3166-2/short-state ретраи, address_2-ретрай, одноразовый nonce-рефреш на каждой мутации, парс client_secret из base64-redirect.
* **Результат:** пул вырос с 1 донора до **12** (1 setup + 11 store с эмитентным вердиктом).


* **Назначение:** Собирает живые доменные имена магазинов через топики форумов плагинов (Stripe, Subscriptions, GiveWP, Paid Memberships Pro, Tutor LMS, LifterLMS и др.).
* **Результат:** SQLite-пул `data/domains.db` (+ txt-экспорт для совместимости).
* **Запуск:** `python harvest_donors.py`

### 5. `unified_harvester.py` — Единый конвейер добычи → `data/domains.db`
* Три полосы: форумы (напрямую), два доркера (подпроцессами), manual-цели (`data/probe_targets.txt`).
* SQLite-очередь: INSERT OR IGNORE, приоритетные полосы (forum=1, woo=2, dork=3), due-for-scan после `config.RESCAN_INTERVAL_HOURS`, writeback результатов скана.
* **Запуск:** `python unified_harvester.py [--forum-only] [--pages N]`

### 6. `bot/` — Telegram-бот поверх движков (Sprint 4)
* Pyrogram async, плагинные гейты (`bot/gates/*.py`, контракт `async def gate(cc,mm,yy,cvv)->tuple`): `setupwoo`, `storegate`, `piconfirm`, `braintreenvbv`.
* **Мультигейт `/chk` (Фаза 5.2):** авто-выбор лучшей поверхности (setupwoo → storegate → piconfirm → braintreenvbv) или форс конкретного гейта первым аргументом.
* Экономика: credits/premium, одноразовые ключи `/genkey` → `/key`, антиспам, статистика на юзера.
* **Запуск:** `PUSTO_BOT_TOKEN=... python -m bot.main`

### 7. `Braintree VBV Lookup Gate` (Фаза 5.1)
* `$0` токенизация карты через Braintree client_api (client_token/fingerprint) или GraphQL (tokenization_key); вердикт по `cvvResponseCode`: M/S = карта жива, N = WRONG_CVC; 3DS-поля при наличии (enrolled/liabilityShifted).
* Ключи скрапятся сканером (`BRAINTREE_KEY`) в `data/braintree_targets.txt`.

---

## 🧬 Sprint 1 — Evasion Hardening (Фаза 1, в движке)
* **Серверные Radar-ID:** beacon POST к `m.stripe.com/6` — сервер минтует muid/guid/sid (формат uuid+6hex) прямо в JSON-ответе; uuid4 остался только fallback'ом.
* **hcaptcha radar token:** wallet-config (Origin обязателен `https://js.stripe.com`) → checksiteconfig → `P1_`-токен → поле `radar_options[hcaptcha_token]` в токенизации.
* **Гео-адаптация:** пулы US/GB/AU/CA/DE/FR, billing выравнивается по BIN карты.
* **wc_order_attribution_*** — 11 полей аналитики Woo в confirm-body.
* **ctoken groundwork** — regex'ы Confirmation Tokens уже в `scrape_gate`.

---

## 📁 Структура каталогов

```
pusto/
├── setup_gate.py              # 🔥 Главный валидатор карт ($0 SetupIntent Gate)
├── confirm_gate.py            # 💳 PaymentIntent Confirm Engine (второй вектор)
├── advanced_gate_scanner.py   # 🔍 4-стадийный сканер, очередь из domains.db
├── gate_client.py             # ⚙️ Общий движок: nonces, телеметрия, identity, PI/3DS, Store API
├── config.py                  # 🎛️ Пороги, TTL, таксономия вердиктов (17 классов)
├── proxy_manager.py           # 🕵️ Пул прокси: валидация, sticky на донора, health-файл
├── domains_store.py           # 🗄️ SQLite-хранилище доменов (очередь сканов)
├── unified_harvester.py       # 🌐 Конвейер добычи: форумы + доркеры + manual → db
├── harvest_donors.py          # Форумная полоса (58 слагов WordPress.org)
├── store_gate.py              # 🛒 Store API direct-confirm (третья поверхность)
├── bot/                       # 🤖 TG-бот: pyrogram, гейты-плагины, credits/premium
│   ├── main.py                #    команды /chk /mass /bin /gates /stats /me /key ...
│   ├── gates/                 #    контракт: async gate(cc,mm,yy,cvv)->tuple
│   ├── db.py                  #    SQLite юзеров и ключей активации
│   └── utils/formatter.py     #    вывод карточек: Card/BIN/Gate/Status/Detail/Latency
├── data/
│   ├── domains.db             # SQLite-пул доменов с очередью сканирования
│   ├── ready_gates.json       # Пул SetupIntent-доноров (+метрики EMA)
│   ├── store_gates.json       # Пул Store-API поверхностей + верификация
│   ├── final_gates.json       # 🔥 Сводный пул всех векторов (setup+store+mint)
│   ├── braintree_targets.txt  # Braintree-цели (ключи со сканера)
│   ├── proxy_health.json      # Живость/латентность прокси между прогонами
│   ├── results/               # JSONL-логи вердиктов по дням
│   └── proxies.txt.example    # Формат пула прокси (реальный в git не идёт)
├── scratch/                   # Рабочие инструменты и прототипы
│   ├── _scan_store_gates.py   # Store-API surface scanner (квалификация)
│   ├── _verify_all_store.py   # Боевая верификация store-пула probe-картой
│   ├── _finalize_pool.py      # Свод пула → final_gates.json
│   ├── _scan_pi_gates.py      # PI-confirm surface scanner (секреты на страницах)
│   ├── dork_harvester.py      # DDG+Yahoo+Bing+AOL, пагинация → domains.db
│   └── deep_dorker.py         # Глубокие дорки по TLD и нишам → domains.db
├── archive/                   # Архив: старые пробы + debug-2026-08-27 (одноразовая отладка)
└── research/                  # Заметки и разборы экосистемы
```

---

## ⚡ Команды

```bash
# Проверить карту на боевом шлюзе (пул из data/ready_gates.json):
python setup_gate.py "CARD|MM|YY|CVC"

# Проверить через PaymentIntent-вектор (страница с торчащим client_secret):
python confirm_gate.py https://target-checkout.com "CARD|MM|YY|CVC"

# Собрать домены всеми полосами в domains.db:
python unified_harvester.py

# Отсканировать очередь из db и обновить пул доноров:
python advanced_gate_scanner.py

# Юнит-тесты движка:
$env:PYTHONPATH='.'; python scratch/_test_gate_client.py

# TG-бот (токен от @BotFather):
$env:PUSTO_BOT_TOKEN='...'; python -m bot.main
```

## Проверено

| Дата | Карта | Донор | Вердикт | Поверхность |
|---|---|---|---|---|
| 2026-08-25 | `537872******8595` | blackbeltprotein.com.au | **APPROVED** | SetupIntent |
| 2026-08-25 | `442019******2053` | blackbeltprotein.com.au | DECLINED incorrect_number | SetupIntent |
| 2026-08-25 | `516499******7375` | blackbeltprotein.com.au | DECLINED card_declined | SetupIntent |
| 2026-08-25 | `517546******2090` | blackbeltprotein.com.au | DECLINED card_declined | SetupIntent |
| 2026-08-27 | probe (Luhn) | thimpress.com | DECLINED card_declined | Store API |
| 2026-08-27 | probe (Luhn) | rocketgeek.com | DECLINED card_declined | Store API |
| 2026-08-27 | probe (Luhn) | essexmonastery.com | DECLINED (gateway) | Store API |
| 2026-08-27 | probe (Luhn) | madatshop.com | DECLINED (DE) | Store API |
| 2026-08-27 | probe (Luhn) | themakersclub.it | DECLINED incorrect_number (IT) | Store API |
| 2026-08-27 | probe (Luhn) | tricolistica.com | DECLINED card_declined (ES) | Store API |
| 2026-08-27 | probe (Luhn) | cherryarts.org | DECLINED processing failed | Store API |
| 2026-08-27 | probe (Luhn) | pianowizardacademy.com | DECLINED card_declined | Store API |
| 2026-08-27 | probe (Luhn) | theposhpundit.co.uk | DECLINED (gateway) | Store API |

Верифицированный пул доноров: `data/final_gates.json` (12 гейтов: 1 setup + 11 store).
