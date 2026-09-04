# pusto — инфраструктура добычи, квалификации и прогона платёжных поверхностей

> Все исторические и противоречивые документы убраны. `README.md` и `AGENTS.md` — единственный состав документации проекта; README сверен с кодом пофайлово. Полный тестовый сьют: **196 passed** (Python 3.14).

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

# Добыча доменов: форумная полоса (58 слагов wordpress.org) + manual-цели + доркеры → data/domains.db:
python unified_harvester.py              # --forum-only — без доркеров; --pages N — глубина форумов

# Квалификация очереди из db → data/ready_gates.json (DNS → форма → регистрация → боевой пробник):
python advanced_gate_scanner.py

# Конвейер раунда 10 (S0→S2): дорки → пассивный отпечаток → роутинг → data/scout_pool.json:
python scout.py --queries 14 --delay 5 --concurrency 12 --reset
python scout.py --only-report            # сводка воронки и пула без новой добычи

# Слои конвейера по отдельности:
python recon.py --dork --max-queries 12 --delay 6   # S0: дорки DDG (+ --corpus/--crtsh/--file/--db)
python surface.py example.com                       # S1: пассивный отпечаток (домен или файл со списком)
python funnel.py                                    # отчёт воронки: где умирают кандидаты

# Тесты (все офлайн):
python -m pytest tests/ -q
```

Телеграм-бот — отдельным блоком, это PowerShell, а не bash:

```powershell
$env:PUSTO_BOT_TOKEN = "ТОКЕН"; python -m bot.main
# без токена бот стартует по сессии bot/pusto_bot.session, если файл существует
```

Без аргумента-карты любой CLI-гейт берёт случайный Luhn-валидный пробник — это штатный
режим квалификации донора, а не ошибка запуска. Все карточные CLI принимают `--proxy URL`;
`store_gate.py` и `shopify_gate.py` вместо одиночного URL берут и файл со списком целей.

---

## 3. Быстрое состояние (актуально на сентябрь 2026)

| Показатель | Значение |
|---|---|
| Боевых поверхностей | 6 (`storegate`, `shopify`, `setupwoo`, `hit`, `piconfirm`, `braintreenvbv`) |
| Пул мерчантов | **185 целей в файлах** → **179 в живой ротации** (79 Store API после отсева мёртвых из 85 в `store_targets.txt` + 100 Shopify в `shopify_targets.txt`) + 1 ready gate |
| Прокси-пул | Пул в `data/proxies.txt` (SOCKS5/HTTP/SOCKS4, приоритет SOCKS5 2.0x) — в файле только узлы, подтверждённые последней валидацией; число живых волатильно и меняется от прогона к прогону (мгновенный срез — `data/proxy_health.json` и `/proxy`); фоновая авто-чистка каждые 15 минут в работающем боте |
| Консольное логирование | Централизованный real-time движок `pusto_logger.py` (ANSI/UTF-8 бейджи по всем слоям) |
| Тесты | **196 passed** (все офлайн; покрыт весь офлайн-контур — сетевая механика и хендлеры бота вне сьюта, см. §10) |
| `py_compile` корня, `bot/`, `scratch/`, `tests/` | EXIT=0 (все модули без синтаксических ошибок) |
| Интерфейс бота | Интерактивные меню Pyrogram, типографика Mathematical Unicode, парсинг карт vs прокси |

### Прокси-механика (`proxy_manager.py`)

```python
weight = ((1000.0 / max(latency_ms, 20)) ** 2) * proto_mult / (1.0 + fail_count * 2.0)
```

- протокольный множитель: SOCKS5 **2.0x** (чистый TCP-туннель без HTTP-заголовков), HTTP/HTTPS 1.0x, SOCKS4 0.8x
- выбор взвешенный среди ТОП-35% самых быстрых живых узлов; 3 страйка — узел мёртв
- `pick_proxy()` берёт только подтверждённые `alive`-узлы из `data/proxy_health.json`; проверенных нет → `None` (безопасное прямое подключение)
- при блокировке Cloudflare на мерчанте (`no Nonce`, `403`, `curl 97/7/28`): прокси штрафуется, запрос повторяется напрямую или через резервный узел — чек пользователя не срывается из-за сбоя прокси

---

## 4. Модули

| Файл | Строк | Роль |
|---|---|---|
| `gate_client.py` | 1 980+ | **Ядро.** Regex'ы Woo/Stripe, парсинг карт, личность и гео-пулы, телеметрия, PI/3DS, Store API, Braintree, BIN, таксономия, ротация доноров, инвариант мутаций |
| `surface.py` | 480+ | **S1 Пассивный отпечаток:** 3 обязательных GET (витрина, products.json, /cart) + до 4 условных для Woo, ни одной мутации; определение платформы (Woo Blocks/Legacy/Shopify), платёжных слагов, Stripe PK, крышки цены |
| `recon.py` | 380+ | **S0 Добыча:** мульти-полосный сбор с доказательствами — дорки DDG с ротацией поисковых отпечатков, crt.sh, майнинг TG-корпуса, файл, очередь из domains.db |
| `scout.py` | 170+ | **Оркестратор воронки:** ранжирование кандидатов по стоимости/ценности, сбор пула (`data/scout_pool.json`) |
| `funnel.py` | 210+ | **Учёт потерь воронки:** закрытый enum причин отказа (`REASONS`), исключающий мусорный `NO_REG` |
| `setup_gate.py` | 590+ | `$0` SetupIntent-вектор: WP-регистрация один раз на донора, дальше вся пачка карт через `add-payment-method` |
| `shopify_gate.py` | 690+ | Shopify: токенизация в `deposit.us.shopifycs.com`, `/products.json`, Checkout One GraphQL + классическая форма |
| `hit_gate.py` | 310+ | Готовый `cs_live`-линк: fid-декод → `payment_pages/{cs}` → confirm → 3DS двух поколений |
| `confirm_gate.py` | 300+ | Страница с торчащим `pi_..._secret_...`: retrieve PI → confirm → ретрай-бюджет → минт нового секрета |
| `advanced_gate_scanner.py` | 390+ | Квалификация очереди v1: DNS → форма → POST-регистрация → скрап nonces → боевой SetupIntent-пробник |
| `store_gate.py` | 110 | CLI-обёртка над `gate_client.store_api_confirm` с крышкой цены |
| `proxy_manager.py` | 200+ | Пул прокси: валидация (80 воркеров), sticky-привязка к донору (в CLI `setup_gate`), health-файл, 3 страйка |
| `domains_store.py` | 120+ | SQLite-очередь доменов (WAL, `INSERT OR IGNORE`, приоритет) |
| `unified_harvester.py` | 90+ | Оркестратор трёх полос добычи |
| `harvest_donors.py` | 240+ | Форумная полоса: 58 слагов wordpress.org, приоритет по System Status Report |
| `bin_cache.py` | 100+ | SQLite-кэш BIN (TTL ∞), ленивое создание схемы |
| `stripe_fid.py` | 130+ | Декодер `#fid`-фрагмента Stripe Checkout (base64 → XOR-5 → JSON) |
| `pusto_logger.py` | 280+ | **Центральный консольный логгер:** Windows Virtual Terminal, ANSI/UTF-8, бейджи `[TG]` `[HTTP]` `[STRIPE]` `[GATE]` `[RESULT]` по всем слоям, адаптер стандартного `logging` |
| `config.py` | 60+ | Единый источник констант, таксономии вердиктов и пула TLS-отпечатков |
| `bot/` | 3 570+ | Pyrogram-бот (`main.py` 1 890+), реестр гейтов-плагинов, интерактивные клавиатуры (`keyboards.py`), БД юзеров, кредиты, ключи, карточный форматтер с переводом ответов эмитентов |

---

## 5. Боевые поверхности

| Вектор | Модуль | Команда бота | Цена | Состояние на сентябрь 2026 |
|---|---|---|---|---|
| **setupwoo** | `setup_gate.py` | `/au` | 1 кр | 1 донор — `www.blackbeltprotein.com.au`, EMA-латентность 6 111 мс, SR 0.76, `$0`-авторизация |
| **storegate** | `store_gate.py` | `/st [1\|5\|20]` | 2 кр | 85 целей в `data/store_targets.txt` → 79 в живой ротации (отсев dead/phantom); verified 26 из 63 записей в `store_gates.json`. Крышка `$20` |
| **shopify** | `shopify_gate.py` | `/sp [1\|5\|20]` | 2 кр | 100 магазинов в живой ротации; из 142 записей `shopify_gates.json` — 133 verified, 9 убиты боем |
| **hit** | `hit_gate.py` | `/hit url cc` | 2 кр/карта | 10 линков в `data/hit_targets.txt`, но `/hit` принимает URL аргументом — пул не задействован. До 10 карт за вызов, свежая HTTP-сессия на каждую |
| **piconfirm** | `confirm_gate.py` | `/pi` | 2 кр | **Без целей.** Цель: `env PUSTO_PI_TARGET` → `data/pi_target.txt` → `data/pi_gates.json` (пуст) → `ERROR` |
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

Фильтр идёт по `cheapest_cents` магазина из `data/store_gates.json` / `data/shopify_gates.json`. Тир `all` (Auto в меню) — фильтр цены отключён, действует общий кап `$20`.

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
| `/chk` cc | Авто-выбор поверхности по приоритету с фолл-троу: при `ERROR` движка чек уходит следующему живому гейту цепочки | по выбранному гейту |
| `/au` cc | SetupIntent `$0`-auth | 1 кр |
| `/st [1\|5\|20]` cc | Store API | 2 кр |
| `/sp [1\|5\|20]` cc | Shopify Checkout | 2 кр |
| `/pi` cc | PaymentIntent confirm | 2 кр |
| `/vbv`, `/b3` cc | Braintree VBV lookup | 1 кр |
| `/hit` url cc[…] | До 10 карт по одному `cs_live`-линку | 2 кр/карта |
| `/mass` [гейт] cc… | До 20 карт free (100 premium / 10 000 admin), текст или `.txt`, `Semaphore(5/10)` | цена гейта × карты |
| `/bin` 123456 | BIN: банк, система, тип, страна, 3DS | — |
| `/gates` | Реестр гейтов, пулы доноров | — |
| `/stats` | Личная и общая статистика | — |
| `/proxy` | Проверка и чистка пула (валидация до 500 узлов, медиана пинга) — доступна всем | — |
| `/addproxy`, `/clearproxy` | Добавление (текст/`.txt`) / очистка пула — админ | — |
| `/addcredits` UID N, `/addpremium` UID ДНИ, `/genkey` [кр] [дни] | Админ-команды | — |
| *без команды:* карта в чат | Чек выбранным шлюзом и тиром; список карт → массовый чек; ровно 6 цифр → автоматический BIN-lookup | по шлюзу |
| *без команды:* `.txt` файл | Список карт → массовый чек; прокси-лист (по имени или структуре) → валидация и пул (админ) | по шлюзу |

Экономика: `START_CREDITS = 5` (env `PUSTO_START_CREDITS`), списание атомарное
(`UPDATE ... WHERE credits >= ?` + rowcount), при вердикте `ERROR` кредит возвращается,
премиум и админы чекают бесплатно. Антиспам 3 с на пользователя.
Приоритет авто-выбора `/chk`: `storegate → setupwoo → shopify → piconfirm → braintreenvbv`,
гейты без целей из выбора исключены (`_available_gates()`).

### База данных (`bot/db.py`)

SQLite (`bot/bot_users.db`), режим WAL, схема **v2** (версия в `PRAGMA user_version`, миграции `_MIGRATIONS`):
- `users`: `user_id`, `username`, `credits`, `total_checks`, `hits`, `premium_until`, `banned`, `last_cmd_ts`, `selected_gate` (DEFAULT `'chk'`), `selected_tier` (DEFAULT `'1'`)
- `keys`: `key`, `days`, `credits`, `used_by`, `used_at` — одноразовые, несут дни **и** кредиты одновременно

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
- `transStatus Y` → `3DS_FRICTIONLESS`, `C` → `3DS_CHALLENGE` — **вердикт «жива и enrolled»**, а не провал; в hit при `Y` с успешным опросом PI вердикт эскалирует до `APPROVED@PAID`
- `PI succeeded` → `APPROVED@PAID` в hit и storegate, чистый `APPROVED` в piconfirm-классификаторе; `PI processing` → `PI_PENDING` во всех движках
- Woo `success: true` при неоплаченном PI → `PI_PENDING`, не `APPROVED@PAID` (фикс по кейсу herbaura)

`HIT_VERDICTS` в корневом `config.py` — 4 класса; бот расширяет их `APPROVED@PAID`,
`3DS_FRICTIONLESS`, `3DS_CHALLENGE` (`bot/main.py:68`).

---

## 8. Константы (`config.py`)

| Константа | Значение |
|---|---|
| `STRIPE_API_VERSION` | `2026-03-25.dahlia` — актуальная стабильная версия API Stripe 2026 года |
| `STRIPE_JS_BUILD` | `eb42eea6af` — живой билд stripe.js v3 (сентябрь 2026): подставляется в `payment_user_agent` телеметрии и `v`-параметр hcaptcha |
| `CHROME_IMPERSONATE` | `edge101` — нативный Windows-профиль (устраняет p0f TCP mismatch TTL=128); fallback для `surface._FALLBACK_IMP` |
| `IMPERSONATIONS` | Пул из 22 актуальных профилей `curl_cffi 0.15.0` (Chromium 133a-146, Safari 18.4/26.0, Firefox 135-147, Edge 99/101, Tor 145); устаревшие `chrome99`-`chrome110` удалены |
| `MAX_PI_AMOUNT_CENTS` | `10 000` (выше — `CHARGE_RISK`, не подтверждаем) |
| `MAX_CONFIRMS_PER_SECRET` | `20` |
| `DONOR_FAIL_LIMIT` | `3` (подряд отказа — донор из пула) |
| `STALE_AFTER_HOURS` / `GATE_TTL_HOURS` | `24` / `72` |
| `RESCAN_INTERVAL_HOURS` | `24` |

---

## 9. Данные

| Носитель | Состояние | Кто пишет / кто читает |
|---|---|---|
| `data/domains.db` | 1 229 доменов, отсканировано 933 (NO_REG 926, CAPTCHA_ADDCARD 7, **READY 0**), в ожидании 296 | пишут `unified_harvester`, `recon`/`scout` (квалифицированных priority 1, мёртвых priority 3), `advanced_gate_scanner`; читают сканер, `surface`, `recon`, `scout` |
| `data/scout_pool.json` | **190 записей** — пул конвейера S0→S2: woo_blocks 83 / shopify 100 / woo_legacy 7; маршруты setupwoo 10, storegate 86, shopify 100 | пишет `scout.py`; читают `scout --only-report` и scratch-квалификаторы |
| `data/probe_targets.txt` | 17 строк — ручные manual-цели | пишется руками; читают `unified_harvester` (manual-полоса) и сканер (fallback) |
| `data/harvested_domains.txt`, `dork_harvested.txt` | по 992 строки — txt-экспорт пула из domains.db | пишут `harvest_donors` и доркеры через `unified_harvester`; читает сканер как fallback при пустой db |
| `data/ready_gates.json` | 1 запись (setupwoo-донор) | пишут сканер и `setup_gate` (EMA success_rate/латентность, captcha-флаг, выброс при 3 фейлах); читает `setup_gate` |
| `data/store_gates.json` | 63 записи (расширенная база Store API с ценами каталогов) | пишут `scratch/_scan_store_gates.py`, `_verify_all_store.py`; читает `bot/gates/storegate.py` |
| `data/shopify_gates.json` | 142 записи чекаутов Shopify | пишет `scratch/_verify_shopify_pool.py`; читает `bot/gates/shopify.py` |
| `data/final_gates.json` | 6 записей: `setup_intent` 1, `store_confirm` 5 | пишет `scratch/_finalize_pool.py`; читает бот-монитор `/gates` |
| `data/store_targets.txt` | 85 целей (79 в живой ротации после отсева мёртвых) | пишут `scratch/_scan_store_gates.py`, `_build_store_targets.py`; ротация `/st` (WooCommerce Store API) |
| `data/shopify_targets.txt` | 100 целей в живой ротации | ротация `/sp` (Shopify Checkout One) |
| `data/hit_targets.txt` | 10 линков | пул **не используется**: `/hit` берёт URL из команды |
| `data/proxy_health.json` | живой срез: латентность, ошибки, флаг `alive` по каждому узлу | пишет `proxy_manager` при каждой валидации; читает `pick_proxy()` |
| `data/proxies.txt` | активный пул (SOCKS5/HTTP/SOCKS4); число живых волатильно — мгновенный срез в доке не фиксируется | авто-валидация каждые 15 мин в работающем боте; читает `gate_client.pick_proxy()` |
| `data/braintree_targets.txt` | 0 байт | цели Braintree не нагружены |
| `data/bin_cache.db` | 0 байт — схема создаётся лениво при первом обращении | `bin_cache.py` |
| `data/results/YYYY-MM-DD.jsonl` | логи вердиктов, 5 файлов | пишет `setup_gate`, читателя нет |

`data/active_surfaces.json`, упоминавшийся в старых версиях README, **не существует** —
сканер пишет только `ready_gates.json` и `braintree_targets.txt`.

---

## 10. Тесты

**196 passed** (16 файлов), все офлайн (Python 3.14, pytest 9.0.3).

| Файл | Тестов | Покрытие |
|---|---|---|
| `tests/test_round10_funnel.py` | 32 | воронка чекаута, корзина, токенизация, обработка ошибок шлюзов |
| `tests/test_round10_recon.py` | 30 | рекон доменов, обнаружение Store API/Shopify/UPE, эвристики |
| `tests/test_round9_fixes.py` | 21 | `coerce_verdict`, статусы SetupIntent, `card_rejection`, тиры, фолл-троу гейтов, WAL/`user_version`, антиспам, откат счётчика, атомная запись |
| `tests/test_shopify.py` | 21 | `_normalize_card`, 12 ветвей `classify_shopify_verdict`, тиры, реестр гейтов |
| `tests/test_bot_interactive.py` | 13 | интерактивные inline-меню бота, переключение шлюзов и тиров цены, фильтрация ввода |
| `tests/test_round1_fixes.py` | 13 | `parse_card`, `extract_pan`, Luhn, `score_gate`, `classify_verdict`, `domains_store`, redeem/spend/refund |
| `tests/test_speed_fixes.py` | 13 | `bin_cache` round-trip/miss/empty, `_pick_target`, `_dead_domains`, `_available_gates` |
| `tests/test_round7_fixes.py` | 9 | ротация Shopify, кэш без `init_db()`, регистрация `/chk`, тир таблицей целевого гейта |
| `tests/test_audit_fixes.py` | 8 | обогащённый BIN lookup без NameError, санитизация вывода, граничные случаи |
| `tests/test_proxy_priority.py` | 6 | взвешенный выбор SOCKS5/HTTP/SOCKS4, штрафы, fallback на прямое подключение |
| `tests/test_round10_fixes.py` | 6 | изоляция парсинга карт и прокси, регрессионные фиксы регулярных выражений |
| `tests/test_stripe_ctoken.py` | 5 | Stripe Confirmation Tokens (`ctoken_...`), dual-payload Store API, изоляция параметров |
| `tests/test_turnstile.py` | 5 | экстракция параметров Cloudflare Turnstile (контейнеры, wrapper, скриптовый рендер, фоллбэки) |
| `tests/test_hit_3ds.py` | 5 | `_classify_and_resolve_3ds`: paid / card errors / 3DS2 / 3DS1 |
| `tests/test_price_tiers.py` | 5 | тиры `storegate` — фильтрация товаров по ценовым диапазонам |
| `tests/test_stripe_fid.py` | 4 | fid round-trip на перехваченном фрагменте |

Покрыты: ядро классификации, эвристики рекона, воронки чекаута, тиры, ротация, скоринг прокси, валидация карт, атомарная БД, интерактивные меню и роутинг сообщений Telegram-бота. Внешняя сеть при запуске тестового сьюта отключена — тесты полностью детерминированы.

---

## 11. Структура каталогов

```
pusto/
├── gate_client.py              # ядро: 1985 строк, весь HTTP и классификация
├── setup_gate.py               # $0 SetupIntent-вектор
├── store_gate.py               # Woo Store API direct-confirm
├── shopify_gate.py             # Shopify Checkout (GraphQL + классика)
├── hit_gate.py                 # готовый cs_live-линк Stripe Checkout
├── confirm_gate.py             # торчащий pi_..._secret_...
├── advanced_gate_scanner.py    # квалификация очереди из domains.db
├── unified_harvester.py        # оркестратор полос добычи
├── harvest_donors.py           # форумная полоса (58 слагов wordpress.org)
├── scout.py                    # оркестратор S0→S2 → data/scout_pool.json
├── surface.py                  # S1: пассивный отпечаток поверхностей
├── recon.py                    # S0: полосы добычи (дорки/crt.sh/corpus)
├── funnel.py                   # учёт потерь воронки: причины отказов
├── domains_store.py            # SQLite-очередь доменов
├── proxy_manager.py            # пул прокси: sticky, EMA-веса, health
├── bin_cache.py                # SQLite-кэш BIN
├── stripe_fid.py               # декодер #fid фрагмента
├── pusto_logger.py             # центральный ANSI-логгер (бейджи по слоям)
├── config.py                   # константы + 24 вердикта
├── рабочий_файл.md             # журнал завершённых задач (обновляет агент по команде)
├── bot/
│   ├── main.py                 # команды, диспетчер гейтов, /mass, /hit
│   ├── keyboards.py            # inline-клавиатуры меню и мониторов
│   ├── gates/                  # плагины: setupwoo, storegate, shopify, piconfirm, braintreenvbv
│   ├── db.py                   # SQLite юзеров, кредитов и ключей
│   ├── config.py               # GATE_COST, START_CREDITS, админы, антиспам
│   └── utils/formatter.py      # карточка вывода: Card/BIN/Gate/Status/Detail/Latency
├── scratch/                    # рабочие инструменты конвейера + _doc_audit.py
│   ├── _scan_store_gates.py    # квалификация Store-API поверхностей
│   ├── _verify_all_store.py    # боевая верификация store-пула probe-картой
│   ├── _verify_shopify_pool.py # то же для Shopify
│   ├── _finalize_pool.py       # свод всех векторов → final_gates.json
│   ├── _phantom_control.py     # контроль фантом-гейтов просроченной картой
│   ├── _scan_pi_gates.py       # поиск торчащих client_secret
│   ├── _collect_hits.py        # парсинг cs_live-линков из TG-экспортов (пул уже собран в data/hit_targets.txt)
│   ├── dork_harvester.py, deep_dorker.py  # дорк-полосы (вызываются unified_harvester)
│   └── verify_proxies.py       # валидация прокси-пула из data/proxies.txt
├── tests/                      # 16 файлов, 196 тестов, без сети
└── data/                       # пулы, кэши, результаты (см. §9)
```

Корень держит код, точку входа и рабочий журнал. Исторические пробы (archive/) и
исследовательский корпус (research/) удалены при чистке сентября 2026 — боевой
контур от них не зависел (сверено кодом и полным прогоном тестов).

---

## 12. Известные расхождения и открытые концы

**Источник правды — код; этот README сверен с ним пофайлово и поддерживается единственным.**

Текущие открытые векторы и направления:

1. **A4** — второй setupwoo-донор в EU/US. Весь `$0`-вектор держится на одном
   австралийском сайте с латентностью ~6.1 с. Это единственная точка отказа.
2. **D-4 / D-5 — piconfirm и braintreenvbv без постоянных целей** — зарегистрированы, доступны
   напрямую, при отсутствии целей возвращают `ERROR` с возвратом кредита на баланс.
3. **D-10 — носители-сироты**: `data/hit_targets.txt` (10 линков) не читается никем —
   `/hit` берёт URL аргументом; `data/pi_gates.json` пуст. связать пулы с движком
   или сделать их полноценным источником целей.

Закрыто в текущей версии движка (не переоткрывать):
- **D-6 (прокси-пул)** — пул развёрнут, механика в §3; **D-11 / D-12** — тиры и
  вердикты согласованы (§5, §7); интерактивный бот — §6, сьют — §10.
- **Хардкод `chrome131` и аудит 2026** (закрыто 2026-09-04): хардкоды устранены
  (`bot/gates/braintreenvbv.py`, `scratch/dork_harvester.py`, `scratch/deep_dorker.py` переведены
  на `config.pick_impersonate()`, userAgent обновлен до Chrome/136), guard-тест расширен
  на 12 модулей; Stripe обновлен до `2026-03-25.dahlia` и билда `eb42eea6af`.

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
| 2026-09-03 | setupwoo | blackbeltprotein.com.au | `DECLINED` — контроль живости донора: `battle_result: LIVE`, харнесс исправен |
| 2026-09-04 | storegate | tricolistica.com (€5.00) | `DECLINED` — probe-прогон: полный цикл (cart→add-item 201→tokenize→checkout), испанский отказ эмитента |
| 2026-09-04 | storegate | tricolistica.com (€5.00) | `DECLINED` — боевой прогон 2026: Stripe Dahlia `2026-03-25.dahlia` (соль `eb42eea6af`) + Chromium TLS 2026, токенизация `pm_1UC2Rt...` 200, чекаут 400 |
| 2026-09-04 | setupwoo | blackbeltprotein.com.au | `DECLINED` — боевой прогон 2026: прямой запуск direct, сессия открыта, SetupIntent подтвержден, вердикт эмитента |
| 2026-09-04 | storegate | tricolistica.com (€5.00) | `DECLINED` — боевой прогон: Stripe Confirmation Token flow (`pm_1UC2pK...` 200 -> `ctoken_1UC2pK...` 200 -> checkout 400) |

Живость пула определяется боевым прогоном, а не числом записей в JSON. Пересчитывать
состояние: `python scratch/_doc_audit.py`.
