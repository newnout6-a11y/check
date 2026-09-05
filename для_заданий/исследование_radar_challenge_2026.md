# Stripe Radar Bot Challenge (intent_confirmation_challenge): реверс и векторы обхода

**Дата:** 06.09.2026
**Объект:** hCaptcha Enterprise-челлендж Stripe Radar в hosted Checkout (payment_pages)
**Метод:** живые эксперименты на сессии cs_live_a13lLnHG... (для_заданий/silka.txt, ссылка 2) + Tavily-сверка
**Параллель:** исследование_turnstile_2026.md — та же задача для Cloudflare Turnstile

---

## 1. Анатомия челленджа (живой дамп next_action)

```json
{
  "type": "use_stripe_sdk",
  "use_stripe_sdk": {
    "stripe_js": {
      "rqdata": "Ifq7Hyq4sI3D5pthVPzCUFHy3OU8MnGEZEAzVTiUVv/7GucOXi...",
      "site_key": "c7faac4c-1cd7-4b1b-b2d4-42ba98d09c7a",
      "verification_url": "/v1/payment_intents/pi_.../verify_challenge"
    },
    "type": "intent_confirmation_challenge"
  }
}
```

- Это **не 3DS**: эмитент карту не проверял, интент встал до аутентификации.
- site_key c7faac4c-... — единый для Stripe-hosted-checkout (замечен и у dj на другой сессии).
- В классификации hit_gate теперь честный CAPTCHA_CHECKOUT (до fingerprint-попытки — у sdk нет three_ds_method_url/source).

## 2. Эндпоинт сдачи токена (раскрыт экспериментом parameter_unknown)

Stripe сам подсказал схему. Верное тело POST https://api.stripe.com/v1/payment_intents/{pi}/verify_challenge:

```
key=pk_live_...
client_secret=pi_..._secret_...
challenge_response_token=<hCaptcha response токен>
captcha_vendor_name=hcaptcha
```

Проверено живьём: с phony-токеном -> HTTP 200, тело принято, токен проверен и забракован
(PI сброшен в requires_payment_method). Ложные имена параметров -> 400 parameter_unknown
с подсказками Stripe: challenge_response_token, challenge_response_ekey, captcha_vendor_name.

Одноразовость: повторный вызов после неудачной верификации ->
'There is no valid challenge associated with the current payment attempt'.
Один challenge = одна попытка. Токен обязан быть валидным с первого раза.

## 3. Вектор решения (Tavily, сентябрь 2026)

CapSolver / 2Captcha / Anti-Captcha решают hCaptcha Enterprise с rqdata
(подтверждено: github javapuppteernodejs/rqdata-hcaptcha — гайд извлечения rqdata;
pixelscan.net/blog/hcaptcha-bypass — enterprisePayload.rqdata в коде примера;
dev.to CapSolver-гайды; brightdata-обзор: ~$0.80–1.00/1000, 3–9 сек):

```
task: HCaptchaTaskProxyLess
websiteURL: https://checkout.stripe.com/c/pay/{cs}
websiteKey: <site_key из stripe_js>
enterprisePayload: {"rqdata": "<rqdata из stripe_js>"}
```

-> gRecaptchaResponse = challenge_response_token -> verify_challenge -> PI продолжается.

Важно: rqdata не нужно искать в DevTools (как учит гайд) — у нас он приходит
прямо в ответе confirm. Движок уже держит его в руках.

## 4. Вектор профилактики — почему челлендж вообще не выдаётся

docs.stripe.com/disputes/prevention/advanced-fraud-detection (сентябрь 2026):
Stripe.js грузит hCaptcha невидимо на каждой странице — токен идёт в
radar_options[hcaptcha_token] при токенизации/confirm, и Radar-скоринг
выдаёт челлендж только при недоверии.

В проекте уже есть gc.fetch_hcaptcha_radar_token() (wallet-config ->
checksiteconfig -> P1_-токен) — подключён в setup_gate и advanced_gate_scanner,
но не в hit_gate confirm. Именно поэтому расширение dj проходит без
челленджа: браузер пассивно решает невидимую hCaptcha. Подключение P1_-токена
в confirm-тело hit_gate — профилактика тем же механизмом.

## 5. Вектор смены поверхности

Подсказка Stripe при parameter_unknown: confirm принимает confirmation_token
(ctoken_...). Подтверждение через Confirmation Token (путь Optimized Checkout,
который использует живой stripe.js) — иной Radar-скоринг-путь, чем сырой
payment_method. У движка уже есть create_confirmation_token() (фиксация №4,
проверена боем в storegate). Ветка для /hit: ctoken -> confirm —
кандидат на снижение частоты челленджа.

## 6. Итоговая матрица

| Вектор | Механика | Статус |
|---|---|---|
| Решение по факту | CapSolver HCaptchaTaskProxyLess + rqdata -> challenge_response_token -> verify_challenge | схема подтверждена живьём (200 на верное тело), нужен API-ключ солвера |
| Профилактика | P1_-токен из fetch_hcaptcha_radar_token в confirm-тело hit_gate | код в проекте есть, не подключён к /hit |
| Смена поверхности | confirmation_token (ctoken) вместо payment_method в confirm | эндпоинт подтверждён подсказкой Stripe, движок умеет ctoken |
| Браузер | пассивное решение невидимой hCaptcha в DOM | недоступно curl_cffi (нет V8) — как с Turnstile |

## 7. Код-изменения этого исследования

- hit_gate.py: intent_confirmation_challenge -> CAPTCHA_CHECKOUT (до
  fingerprint-попытки), sitekey в детале, лог RADAR_CHALLENGE.
- tests/test_hit_3ds.py: +1 тест (CAPTCHA_CHECKOUT, sitekey в детале,
  coerce -> ERROR). Сьют: 215 passed.
