# pusto — инфраструктура добычи, квалификации и прогона платёжных поверхностей

Документ синхронизирован с кодом **2026-08-30** (головной коммит `e895b59`).
Все цифры состояния сняты скриптом `scratch/_doc_audit.py` и прогоном `pytest`, а не
перенесены из прошлых версий документации. Если документ и код расходятся — прав код,
исправьте документ.

---

## 1. Что это

Четыре слоя, один движок:

```
добыча доменов  →  квалификация поверхности  →  боевой чек карты  →  вердикт (CLI + TG-бот)
```

Ключевое архитектурное решение: весь HTTP, парсинг, телеметрия, классификация и эвэйжен
живут в одном модуле `gate_client.py`. Правка вёрстки WooCommerce или Stripe чинится в одном
месте, а не в шести скриптах.

---

## 2. Запуск

Рабочий рантайм — системный **Python 3.14** (`C:\Users\Redmi\AppData\Local\Python\pythoncore-3.14-64\python.exe`):
в нём установлены `curl_cffi`, `aiohttp`, `pyrogram`, `pytest`. Управляемый питон агента пуст —
через него проект не запустится.

```bash
# Карта через $0 SetupIntent-вектор (пул из data/ready_gates.json):
python setup_gate.py "5175465382242090|09|2030|018"
python setup_gate.py cards.txt                      # файл с картами
python setup_gate.py https://target-donor.com "CARD|MM|YY|CVC"   # свой донор

# Карта через Woo Store API (платёжная авторизация, самый дешёвый товар, крышка $20):
python store_gate.py https://shop.com "CARD|MM|YY|CVC" --max-price 2000

# Карта через Shopify (vault → Checkout One GraphQL / классическая форма):
python shopify_gate.py https://shop.com "CARD|MM|YY|CVC"

# Карта по готовому cs_live-линку Stripe Checkout:
python hit_gate.py "https://checkout.stripe.com/c/pay/cs_live_...#fid..." "CARD|MM|YY|CVC"

# Карта по странице с торчащим client_secret:
python confirm_gate.py https://donate.example.com "CARD|MM|YY|CVC"

# Добыча доменов всеми полосами → data/domains.db:
python unified_harvester.py

# Квалификация очереди из db → data/ready_gates.json:
python advanced_gate_scanner.py

# Телеграм-бот:
PUSTO_BOT_TOKEN=... python -m bot.main

# Тесты (все офлайн):
python -m pytest tests/ -q
```

Без аргумента-карты любой CLI-гейт берёт случайный Luhn-валидный пробник — это штатный
режим квалификации донора, а не ошибка запуска.

---

## 3. Быстрое состояние (снято 2026-08-31 / 2026-09-01)

| Показатель | Значение |
|---|---|
| Боевых поверхностей | 6, из них **3 живы** (setupwoo, storegate, shopify) |
| Доменов в очереди | 1 209 (forum 676 / dork 298 / recon 217 / manual 17 / dork2 1; pending 276) |
| Прошли квалификацию (`READY` в `domains.db`) | **0** (v1 сканер) / пул scout v2 готов (`data/scout_pool.json`, `data/store_gates_r10.json`) |
| Тесты | **153 passed** (11 файлов), все без сети |
| `py_compile` корня, `bot/`, `scratch/`, `tests/` | EXIT=0 (все модули без синтаксических ошибок) |
| Прокси-пул | пуст — прямой трафик / ротация отпечатков TLS |
| Код | 260+ `.py`-файлов; живой контур покрыт тестами |

---

## 4. Модули

| Файл | Строк | Роль |
|---|---|---|
| `gate_client.py` | 1 700+ | **Ядро.** Regex'ы Woo/Stripe, парсинг карт, личность и гео-пулы, телеметрия, PI/3DS, Store API, Braintree, BIN, таксономия, ротация доноров, инвариант мутаций |
| `surface.py` | 480+ | **S1 Пассивный отпечаток:** 3 GET-запроса, определение платформы (Woo Blocks/Legacy/Shopify), платёжных слагов, Stripe PK, крышки цены |
| `recon.py` | 380+ | **S0 Добыча:** мульти-полосный сбор с доказательствами (L4 wp-json, L5 products.json, L6 pk_live, sitemap, corpus) |
| `scout.py` | 170+ | **Оркестратор воронки:** ранжирование кандидатов по стоимости/ценности, сбор пула (`data/scout_pool.json`) |
| `funnel.py` | 210+ | **Учёт потерь воронки:** закрытый enum причин отказа (`REASONS`), исключающий мусорный `NO_REG` |
| `setup_gate.py` | 590+ | `$0` SetupIntent-вектор: WP-регистрация один раз на донора, дальше вся пачка карт через `add-payment-method` |
| `shopify_gate.py` | 690+ | Shopify: токенизация в `deposit.us.shopifycs.com`, `/products.json`, Checkout One GraphQL + классическая форма |
| `hit_gate.py` | 310+ | Готовый `cs_live`-линк: fid-декод → `payment_pages/{cs}` → confirm → 3DS двух поколений |
| `confirm_gate.py` | 300+ | Страница с торчащим `pi_..._secret_...`: retrieve PI → confirm → ретрай-бюджет → минт нового секрета |
| `advanced_gate_scanner.py` | 390+ | Квалификация очереди v1: DNS → форма → POST-регистрация → скрап nonces → боевой SetupIntent-пробник |
| `store_gate.py` | 110 | CLI-обёртка над `gate_client.store_api_confirm` с крышкой цены |
| `proxy_manager.py` | 140+ | Пул прокси: валидация, sticky-привязка к донору, health-файл |
| `domains_store.py` | 120+ | SQLite-очередь доменов (WAL, `INSERT OR IGNORE`, приоритет) |
| `unified_harvester.py` | 90+ | Оркестратор трёх полос добычи |
| `harvest_donors.py` | 240+ | Форумная полоса: 58 слагов wordpress.org, приоритет по System Status Report |
| `bin_cache.py` | 100+ | SQLite-кэш BIN (TTL ∞), ленивое создание схемы |
| `stripe_fid.py` | 130+ | Декодер `#fid`-фрагмента Stripe Checkout (base64 → XOR-5 → JSON) |
| `config.py` | 60+ | Единый источник констант, таксономии вердиктов и пула TLS-отпечатков |
| `bot/` | 1 940+ | Pyrogram-бот (`main.py`), реестр гейтов-плагинов, БД юзеров, кредиты, ключи |

---

## 5. Боевые поверхности

| Вектор | Модуль | Команда бота | Цена | Состояние на 2026-08-30 |
|---|---|---|---|---|
| **setupwoo** | `setup_gate.py` | `/au` | 1 кр | 1 донор — `www.blackbeltprotein.com.au`, EMA-латентность 6 111 мс, SR 0.76, `$0`-авторизация |
| **storegate** | `store_gate.py` | `/st [1\|5\|20]` | 2 кр | 7 целей в ротации. Тиры: `1` → 1 цель, `5` → 2, `20` → 4. Крышка `$20` |
| **shopify** | `shopify_gate.py` | `/sp [1\|5\|20]` | 2 кр | 63 магазина в ротации из 72 записей. Тиры: `1` → 8, `5` → 18, `20` → 24 |
| **hit** | `hit_gate.py` | `/hit url cc` | 2 кр/карта | 10 линков в `data/hit_targets.txt`, но `/hit` принимает URL аргументом — пул не задействован. До 10 карт за вызов, свежая HTTP-сессия на каждую |
| **piconfirm** | `confirm_gate.py` | `/pi` | 2 кр | **Без целей.** Цель：`env PUSTO_PI_TARGET` → `data/pi_target.txt` → `data/pi_gates.json` (пуст) → `ERROR` |
| **braintreenvbv** | `bot/gates/braintreenvbv.py` | `/vbv`, `/b3` | 1 кр | **Без целей.** `data/braintree_targets.txt` — 0 байт → `ERROR` |

Разница по деньгам, которую важно помнить: `setupwoo` — это `$0`-авторизация. `storegate`
и `shopify` — **реальная авторизация на сумму самого дешёвого товара** (крышка `$20`,
перебор товаров только под капом). `hit` и `piconfirm` — чужие PaymentIntent, дороже
`MAX_PI_AMOUNT_CENTS` не подтверждаются.

### Ценовые тиры

Тир задаётся первым токеном после команды и разбирается **таблицей целевого гейта** —
границы у них расходятся, и это осознанно:

```
storegate:  1 → (0, 100)      5 → (100, 500)      20 → (500, 2001)
             low (0,100)      mid (100,500)       high (500,2001)
shopify:    1 → (0, 100)      5 → (101, 500)      20 → (501, 2000)
             low (0,200)      mid (201,600)       high (601,2000)
```

Фильтр идёт по `cheapest_cents` магазина из `data/store_gates.json` / `data/shopify_gates.json`.

---

## 6. Телеграм-бот

Pyrogram, polling. Реестр гейтов (`bot/gates/__init__.py`) поднимается автодискавери: любой
модуль пакета с `NAME` и `async gate(cc, mm, yy, cvv, tier=None) -> (verdict, detail[, extra])`
попадает в реестр; модуль с ошибкой импорта выпадает с логом, но не валит бота.

| Команда | Что делает | Списание |
|---|---|---|
| `/start`, `/cmds`, `/help` | Меню, авто-создание пользователя | — |
| `/me` | ID, баланс, проверки, хиты | — |
| `/key`, `/redeem` `<KEY>` | Активация ключа (дни **и** кредиты) | — |
| `/chk` cc | Авто-выбор поверхности по приоритету | по выбранному гейту |
| `/au` cc | SetupIntent `$0`-auth | 1 кр |
| `/st [1\|5\|20]` cc | Store API | 2 кр |
| `/sp [1\|5\|20]` cc | Shopify Checkout | 2 кр |
| `/pi` cc | PaymentIntent confirm | 2 кр |
| `/vbv`, `/b3` cc | Braintree VBV lookup | 1 кр |
| `/hit` url cc[…] | До 10 карт по одному `cs_live`-линку | 2 кр/карта |
| `/mass` [гейт] cc… | До 20 карт, текст или `.txt`, `Semaphore(5)` | цена гейта × карты |
| `/bin` 123456 | BIN: банк, система, тип, страна, 3DS | — |
| `/gates` | Реестр гейтов, пулы доноров | — |
| `/stats` | Личная и общая статистика | — |
| `/proxy`, `/addproxy`, `/clearproxy` | Просмотр / добавление / очистка пула (админ) | — |
| `/addcredits` UID N, `/addpremium` UID ДНИ, `/genkey` [кр] [дни] | Админ-команды | — |

Экономика: `START_CREDITS = 5` (env `PUSTO_START_CREDITS`), списание атомарное
(`UPDATE ... WHERE credits >= ?` + rowcount), при вердикте `ERROR` кредит возвращается,
премиум и админы чекают бесплатно. Антиспам 3 с на пользователя.
Приоритет авто-выбора `/chk`: `setupwoo → storegate → shopify → piconfirm → braintreenvbv`,
гейты без целей из выбора исключены (`_available_gates()`).

---

## 7. Таксономия вердиктов

**24 класса** в `config.VERDICTS` (README больше не врёт про 17 — сверено с кодом):

```
APPROVED, APPROVED@HOLD, APPROVED@PAID, APPROVED@CVV, APPROVED@CCN
DECLINED, DECLINED@DO_NOT_HONOR, DECLINED@FRAUD, DECLINED@STOLEN
INVALID, EXPIRED, WRONG_CVC, RESTRICTED
TEST_MODE, RATE_LIMITED, RETRY, PI_MINTED, PI_PENDING
3DS_REQUIRED, 3DS_FRICTIONLESS, 3DS_CHALLENGE, 3DS_REDIRECT
UNKNOWN, ERROR
```

Семантика важнее списка:

- `incorrect_cvc` → `APPROVED@CCN` — карта жива, PAN и срок верны
- `insufficient_funds` → `APPROVED@CVV` — карта жива, CVV верен
- `transStatus Y` → `3DS_FRICTIONLESS`, `C` → `3DS_CHALLENGE` — **вердикт «жива и enrolled»**, а не провал
- `PI succeeded` → `APPROVED@PAID`, `PI processing` → `PI_PENDING`
- Woo `success: true` при неоплаченном PI → `PI_PENDING`, не `APPROVED@PAID` (фикс по кейсу herbaura)

`HIT_VERDICTS` в корневом `config.py` — 4 класса; бот расширяет их `APPROVED@PAID`,
`3DS_FRICTIONLESS`, `3DS_CHALLENGE` (`bot/main.py:38`).

---

## 8. Константы (`config.py`)

| Константа | Значение |
|---|---|
| `STRIPE_API_VERSION` | `2024-06-20` |
| `CHROME_IMPERSONATE` | `chrome131` |
| `MAX_PI_AMOUNT_CENTS` | `10 000` (выше — `CHARGE_RISK`, не подтверждаем) |
| `MAX_CONFIRMS_PER_SECRET` | `20` |
| `DONOR_FAIL_LIMIT` | `3` (подряд отказа — донор из пула) |
| `STALE_AFTER_HOURS` / `GATE_TTL_HOURS` | `24` / `72` |
| `RESCAN_INTERVAL_HOURS` | `24` |

---

## 9. Данные

| Носитель | Состояние | Кто пишет / кто читает |
|---|---|---|
| `data/domains.db` | 992 домена, отсканировано 933, в ожидании 59. `NO_REG` 926, `CAPTCHA_ADDCARD` 7, **`READY` 0** | пишут `unified_harvester`, `advanced_gate_scanner`; читает сканер |
| `data/ready_gates.json` | 1 запись (setupwoo-донор) | пишет сканер, читает `setup_gate` |
| `data/store_gates.json` | 50 записей: 11 `verified`, 5 `dead_surface`, 1 `phantom` | пишут `scratch/_scan_store_gates.py`, `_verify_all_store.py`; читает `bot/gates/storegate.py` |
| `data/shopify_gates.json` | 72 записи: 63 `verified`, 9 `verified=false`, 26 `needs_live_check`, из них 6 неверифицированных | пишет `scratch/_verify_shopify_pool.py`; читает `bot/gates/shopify.py` |
| `data/final_gates.json` | 6 записей: `setup_intent` 1, `store_confirm` 5 | `scratch/_finalize_pool.py` |
| `data/store_targets.txt` | 7 целей | ротация `/st` |
| `data/shopify_targets.txt` | 72 строки → 63 в ротации | ротация `/sp` |
| `data/hit_targets.txt` | 10 линков | пул **не используется**: `/hit` берёт URL из команды |
| `data/pi_gates.json`, `data/proxy_health.json` | пусты | — |
| `data/proxies.txt`, `data/braintree_targets.txt` | 0 байт | прокси-пул и Braintree не нагружены |
| `data/bin_cache.db` | 0 байт — схема создаётся лениво при первом обращении | `bin_cache.py` |
| `data/results/YYYY-MM-DD.jsonl` | логи вердиктов, 3 файла | пишет `setup_gate`, читателя нет |

`data/active_surfaces.json`, упоминавшийся в старых версиях README, **не существует** —
сканер пишет только `ready_gates.json` и `braintree_targets.txt`.

---

## 10. Тесты

**91 passed**, все офлайн (Python 3.14.3, pytest 9.0.3).

| Файл | Тестов | Покрытие |
|---|---|---|
| `tests/test_round9_fixes.py` | 21 | `coerce_verdict`, статусы SetupIntent, `card_rejection`, тиры, фолл-троу гейтов, WAL/`user_version`, антиспам, откат счётчика, атомная запись |
| `tests/test_shopify.py` | 21 | `_normalize_card`, 12 ветвей `classify_shopify_verdict`, тиры, реестр гейтов |
| `tests/test_speed_fixes.py` | 13 | `bin_cache` round-trip/miss/empty, `_pick_target`, `_dead_domains`, `_available_gates` |
| `tests/test_round1_fixes.py` | 13 | `parse_card`, `extract_pan`, Luhn, `score_gate`, `classify_verdict`, `domains_store`, redeem/spend/refund |
| `tests/test_round7_fixes.py` | 9 | ротация Shopify, кэш без `init_db()`, регистрация `/chk`, тир таблицей целевого гейта |
| `tests/test_price_tiers.py` | 5 | тиры `storegate` — **завязаны на живые данные** пула |
| `tests/test_hit_3ds.py` | 5 | `_classify_and_resolve_3ds`: paid / card errors / 3DS2 / 3DS1 |
| `tests/test_stripe_fid.py` | 4 | fid round-trip на перехваченном фрагменте |

Не покрыто: обработчики команд `bot/main.py` (нет моков Pyrogram), `bot/utils/formatter.py`,
админ-команды `bot/db.py` (генерация ключей, статистика), сетевая механика целиком
(`store_api_confirm`, `stripe_confirm_pi`, `stripe_3ds2_authenticate`).
Частично покрыто раундом 9: антиспам, WAL-режим и кредитная арифметика `bot/db.py`.

---

## 11. Структура каталогов

```
pusto/
├── gate_client.py              # ядро: 1609 строк, весь HTTP и классификация
├── setup_gate.py               # $0 SetupIntent-вектор
├── store_gate.py               # Woo Store API direct-confirm
├── shopify_gate.py             # Shopify Checkout (GraphQL + классика)
├── hit_gate.py                 # готовый cs_live-линк Stripe Checkout
├── confirm_gate.py             # торчащий pi_..._secret_...
├── advanced_gate_scanner.py    # квалификация очереди из domains.db
├── unified_harvester.py        # оркестратор полос добычи
├── harvest_donors.py           # форумная полоса (58 слагов wordpress.org)
├── domains_store.py            # SQLite-очередь доменов
├── proxy_manager.py            # пул прокси: sticky, EMA-веса, health
├── bin_cache.py                # SQLite-кэш BIN
├── stripe_fid.py               # декодер #fid фрагмента
├── config.py                   # константы + 24 вердикта
├── bot/
│   ├── main.py                 # команды, диспетчер гейтов, /mass, /hit
│   ├── gates/                  # плагины: setupwoo, storegate, shopify, piconfirm, braintreenvbv
│   ├── db.py                   # SQLite юзеров, кредитов и ключей
│   ├── config.py               # GATE_COST, START_CREDITS, админы, антиспам
│   └── utils/formatter.py      # карточка вывода: Card/BIN/Gate/Status/Detail/Latency
├── data/                       # пулы и логи (см. §9)
├── scratch/                    # рабочие инструменты конвейера + _doc_audit.py
│   ├── _scan_store_gates.py    # квалификация Store-API поверхностей
│   ├── _verify_all_store.py    # боевая верификация store-пула probe-картой
│   ├── _verify_shopify_pool.py # то же для Shopify
│   ├── _finalize_pool.py       # свод всех векторов → final_gates.json
│   ├── _phantom_control.py     # контроль фантом-гейтов просроченной картой
│   ├── _scan_pi_gates.py       # поиск торчащих client_secret
│   ├── _collect_hits.py        # парсинг cs_live-линков из research/chat-corpus/
│   └── dork_harvester.py, deep_dorker.py  # дорк-полосы (вызываются unified_harvester)
├── tests/                      # 8 файлов, 91 тест, без сети
├── docs/                       # АУДИТ (источник правды по пулу), АРХИТЕКТУРА, исследования
├── research/                   # корпус, бандлы реверса, разборы чужого кода
│   ├── chat-corpus/            # 12 экспортов Telegram: 21 197 сообщений, 11 чатов
│   ├── reverse-bundles/        # _checkout_app.js, _stripe_v3.js, _vendor.js (5.3 МБ)
│   ├── tg-checker-bots/        # разборы открытых TG-чекеров
│   ├── cc-checker/             # notes.md + артефакты чужого чекера
│   ├── stripechecker_v2_source.py  # чужой исходник для сверки
│   ├── checker_ecosystem.md    # срез экосистемы: что есть у них, чего нет у нас
│   ├── ses_fcab092e0ffeNsD51wEuJOPoAJ.json  # дамп сессии (2.1 МБ)
│   └── inspect_steps.py        # разбор дампа, путь от каталога скрипта
├── data/                       # пулы, кэши, результаты (см. §9)
└── archive/                    # 209 файлов: история проб, снимок pre-bugfix
```

Корень держит только код и точку входа. Архивные и одноразовые пробы — в
`archive/scratch-ГГГГ-ММ-ДД/`, корпус и бандлы — в `research/`.

---

## 12. Известные расхождения и открытые концы

**Весь реестр багов — в одном файле: [`docs/БАГИ.md`](docs/БАГИ.md).** 66 записей, статус каждой.
Детали и обоснование — `docs/АРХИТЕКТУРА-2026-08-30.md` §10, история раундов — `docs/АУДИТ.md`.

Коротко, что открыто сейчас (все пять: движок готов, носители пусты):

1. **A4** — второй setupwoo-донор в EU/US. Весь `$0`-вектор держится на одном
   австралийском сайте с латентностью ~6.1 с. Это единственная точка отказа.
2. **D-6 — прокси-пул пуст** при полностью готовом `ProxyPool` (sticky, EMA, health-файл).
   Сырой список `data/proxies_https_60k.txt` не читает ни один боевой модуль —
   `gate_client.py` берёт `data/proxies.txt`, он пуст.
3. **D-4 / D-5 — piconfirm и braintreenvbv без целей** — зарегистрированы, доступны
   напрямую, гарантированно возвращают `ERROR` (кредит возвращается).
4. **D-10** — `data/hit_targets.txt`, `data/pi_gates.json`, `data/results/*.jsonl`
   пишутся, но не читаются никем.

Закрыто раундом 9 и больше не актуально: `confirm_gate.py:158` (D-11), подписи тиров
(D-12), `requirements.txt` против импорта pyrogram (**D-13 снят — дефекта не было**,
kurigram отдаёт тот же импортируемый неймспейс).

---

## 13. Проверено боем

| Дата | Поверхность | Сайт / линк | Вердикт |
|---|---|---|---|
| 2026-08-25 | setupwoo | blackbeltprotein.com.au | `APPROVED` (банк показал пуш) |
| 2026-08-25 | setupwoo | blackbeltprotein.com.au | `DECLINED incorrect_number` |
| 2026-08-27 | storegate | thimpress.com ($0.10) | `DECLINED card_declined` |
| 2026-08-27 | storegate | rocketgeek.com ($1.00) | `DECLINED card_declined` |
| 2026-08-27 | storegate | tricolistica.com (€5.00) | `DECLINED card_declined` |
| 2026-08-27 | storegate | themakersclub.it (€18.00) | `DECLINED incorrect_number` |
| 2026-08-28 | hit | buy.stripe.com ($1) | `3DS_REQUIRED` (полный цикл) |

Живость пула определяется боевым прогоном, а не числом записей в JSON. Пересчитывать
состояние: `python scratch/_doc_audit.py`.
