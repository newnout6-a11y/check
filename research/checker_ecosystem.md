# CC CHECKER ECOSYSTEM RESEARCH
# ================================

## TIER LIST (по качеству/сложности)

### S-TIER: Закрытые/обфусцированные
- Evelyn Checker — элита, закрытый код, Stripe Auth + Radar emulation
- STRIPECHARGED (KianSantang777) — zlib+exec обфускация, anti-debug (frida/pydevd/gettrace), non-SK, proxyless
- MeduzaV3 (KianSantang777) — мульти-гейт (Stripe/Braintree/многие API), 39 stars, обфусцирован
- RavenPRO (SmSystems01) — Stripe+Braintree, cloudscraper+httpx+aiohttp+pycryptodome, main.py закрыт

### A-TIER: Открытый код, рабочие
- StripeChecker-V2 (walterwhite-69) — ПОЛНЫЙ ИСХОДНИК ПОЛУЧЕН. ThreadPoolExecutor, faker, random telemetry
- SDMN_CheckerBot (iamNVN) — PHP, 544 stars, 609 forks, Telegram бот, /ss /sm /schk команды
- goonkenya/cc-checker-free-gates — мульти: Stripe+Braintree+PayPal+Cybersource

### B-TIER: Базовые/учебные  
- SK_CC_Checker (phccoder) — PHP web, 4 SK API, генератор, Telegram forwarding
- switchblade-cc (lightningpriest) — PHP Telegram, 48 stars
- LXDZCL/stripechk — dollar pre-auth, no SK

## АРХИТЕКТУРА StripeChecker-V2 (единственный полный исходник)

ДОНОР: dilaboards.com (хардкод)
FLOW:
1. GET /add-payment-method/ → извлечь register-nonce + pk (publishable key)
2. POST register с faker.email() → извлечь createAndConfirmSetupIntentNonce  
3. POST api.stripe.com/v1/payment_methods → card data + random muid/guid/sid + pk
4. POST wc-ajax=wc_stripe_create_and_confirm_setup_intent → pm + nonce
5. response.success = true → LIVE, false → DEAD

КЛЮЧЕВЫЕ ТЕХНИКИ:
- Random telemetry: muid/guid/sid генерируются каждый раз
- payment_user_agent: "stripe.js/c1fbe29896; stripe-js-v3; payment-element; deferred-intent"
- client_attribution_metadata: elements_session, merchant_integration_source=elements
- Stripe API version: 2024-06-20
- faker для email при регистрации

## ANTI-DEBUG в STRIPECHARGED
- sys.gettrace() проверка (debugger detection)
- argv сканирование: pyinst, pydevd, frida, trace, hook, uncompyle, decompile
- PYTHONINSPECT env check
- sys.setrecursionlimit(100000000)
- Весь код в zlib.decompress(bytes.fromhex(...)) → exec()

## ТИПЫ ГЕЙТОВ

1. SK-BASED: требует sk_live_ ключ. Прямые вызовы Stripe API. Ключ горит быстро.
2. NON-SK (WooCommerce donor): через publishable key магазина. SetupIntent flow. Устойчивее.
3. CHARGE: реальный -29 charge через PaymentIntent. Деньги снимаются.
4. AUTH ONLY:  SetupIntent confirm. Проверка без списания. НАША МОДЕЛЬ.

## СРАВНЕНИЕ С НАШИМ setup_gate.py

НАШ подход vs StripeChecker-V2:
- МЫ: curl_cffi (TLS impersonation) | ОНИ: requests (без TLS spoof)
- МЫ: async | ОНИ: ThreadPoolExecutor  
- МЫ: динамический донор пул | ОНИ: хардкод dilaboards.com
- МЫ: нет telemetry spoof | ОНИ: random muid/guid/sid ← НУЖНО ВНЕДРИТЬ
- МЫ: нет client_attribution | ОНИ: full metadata ← НУЖНО ВНЕДРИТЬ

## ЧТО НУЖНО ДОБАВИТЬ В НАШ КОД

1. TELEMETRY SPOOFING (из StripeChecker-V2):
   muid = random 8-digit + "-0000-0000-0000"
   sid = random 8-digit + "-0000-0000-0000"  
   guid = random 8-digit + "-0000-0000-0000"
   
2. CLIENT ATTRIBUTION METADATA:
   client_session_id = "src_" + random 16 alphanum
   merchant_integration_source = "elements"
   merchant_integration_subtype = "payment-element"
   payment_intent_creation_flow = "deferred"
   
3. PAYMENT_USER_AGENT строка:
   "stripe.js/VERSION; stripe-js-v3/VERSION; payment-element; deferred-intent"

4. ANTI-RADAR (из research Evelyn):
   m.stripe.com/6 cookie flow — fingerprint cookie перед confirm

5. STRIPE API VERSION: обновить до 2024-06-20 или свежее

## КЛЮЧЕВЫЕ GITHUB REPOS

| Repo | Stars | Lang | Тип |
|------|-------|------|-----|
| iamNVN/SDMN_CheckerBot | 544 | PHP | Telegram bot, SK+Auth |
| OshekharO/MASS-CC-CHECKER | 353 | PHP | Web mass checker |
| skylar69-wtf/CC-CHECKERS-API | 123 | PHP | Multi-gateway API |
| mat1520/telegram-bot-cc-checker | 94 | PHP | Telegram bot |
| Plasmonix/CC-Checker | 83 | PHP | Stripe no-SK |
| KianSantang777/CVV-checkers | 66 | Python | Stripe Merchant gates |
| KianSantang777/MeduzaV3 | 39 | Python | Multi-API obfuscated |
| blacknetid/CC-CHECKER-CLIV5.5 | 32 | Python | CLI bulk checker |
| walterwhite-69/StripeChecker-V2 | 21 | Python | CLI, FULL SOURCE |
| KianSantang777/BraintreeCHK | 15 | Python | Braintree VBV |

## YOUTUBE/TELEGRAM КАНАЛЫ

- Gateway Maker (830 subs) — @diwazz, team_falcone, StripePy lib tutorials
- @RarxGod — Stripe Auth + Braintree tutorials  
- SmSystems — RavenPRO premium tools

## ВЫВОД

Наш проект архитектурно ВЫШЕ большинства открытых решений (async, curl_cffi, 
динамический донор пул). Но не хватает: telemetry spoofing, client attribution
metadata, и m.stripe.com cookie flow. Это то что отличает S-tier (Evelyn) от 
остальных. Внедрение этих 3 компонентов = переход на уровень элиты.
