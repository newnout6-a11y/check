# language: Python 3.12+, file: config.py, target: Windows 11
# Sprint 5: единый конфиг порогов и констант пайплайна.
# Всё, что раньше было размазано по файлам магическими числами.

# --- Stripe (первоисточник — менять ЗДЕСЬ) ---
STRIPE_API_VERSION = "2026-08-26.dahlia"   # актуальный месячный релиз Dahlia (сентябрь 2026); endive (2026-09-30) — major, потребует аудита
# Соль сборки stripe.js. Обновляется скриптом: python scratch/refresh_stripe_salt.py --write
# (--check вернёт exit 1, если значение разошлось с живым бандлом js.stripe.com/v3).
STRIPE_JS_BUILD = "f0a6d7cfcd"
CHROME_IMPERSONATE = "edge101"   # устарело: см. pick_impersonate() ниже

# --- D-30: ротация TLS-отпечатка ---------------------------------------------
# chrome120 и новее (120/124/131) систематически режутся: Cloudflare отдаёт 429
# на витринах, DuckDuckGo отдаёт 202 с пустой выдачей. Проверено боем 2026-08-31
# на 4 доменах и 6 поисковых отпечатках. chrome116 и старше, весь Safari,
# Firefox, Edge и Tor проходят. firefox120 нестабилен (падает) — исключён.
#
# В 2026 году добавлены актуальные профили Chromium 136-146, Safari 18.4/26.0,
# Firefox 135-147 из curl_cffi 0.15.0; устаревшие chrome99-110 удалены.
IMPERSONATIONS = (
    # Chromium (2025-2026)
    "chrome136", "chrome142", "chrome145", "chrome146", "chrome133a", "chrome131_android",
    # Safari / WebKit (macOS & iOS)
    "safari184", "safari184_ios", "safari260", "safari260_ios", "safari18_0", "safari17_2_ios", "safari17_0",
    # Firefox / Gecko
    "firefox147", "firefox144", "firefox135", "firefox133",
    # Windows-native & privacy
    "edge101", "edge99", "tor145",
    # Proven fallback
    "chrome116",
)


def pick_impersonate() -> str:
    """Случайный отпечаток из рабочего пула. Случайность важна: пул, долбящий
    одним и тем же следом синхронно, снова ловит 429 — просто позже."""
    import random
    return random.choice(IMPERSONATIONS)

# --- SetupIntent / WooCommerce cooldown & Session Pacing ---
SETUP_COOLDOWN_MIN = 8.1           # минимальная задержка между add-payment-method на одной сессии
SETUP_COOLDOWN_MAX = 9.0           # верхняя граница с джиттером (спасает от "retried_too_soon")
SESSION_PACING_MIN = 8.1           # унифицированная пауза для rate-limited эндпоинтов
SESSION_PACING_MAX = 9.0


def setup_cooldown_delay() -> float:
    """Джиттерная пауза 8.1 - 9.0с между картами для защиты от кулдауна WooCommerce."""
    import random
    return round(random.uniform(SETUP_COOLDOWN_MIN, SETUP_COOLDOWN_MAX), 2)


def session_pacing_delay(min_delay: float = SESSION_PACING_MIN, max_delay: float = SESSION_PACING_MAX) -> float:
    """Возвращает равномерно распределённую случайную задержку с джиттером (8.1 - 9.0с по умолчанию)
    для rate-limited e-commerce эндпоинтов и защиты от anti-spam tripwires."""
    import random
    return round(random.uniform(min_delay, max_delay), 2)


# --- PaymentIntent vector (Фаза 2) ---
MAX_PI_AMOUNT_CENTS = 10000        # выше — CHARGE_RISK, не подтверждаем ($100)
MAX_CONFIRMS_PER_SECRET = 20       # бюджет подтверждений на один client_secret

# --- Donor pool / scanner ---
DONOR_FAIL_LIMIT = 3               # подряд идущих отказов до выброса донора
GATE_TTL_HOURS = 72                # донор без подтверждения N часов -> из пула
STALE_AFTER_HOURS = 24             # ... сначала пометка STALE
RESCAN_INTERVAL_HOURS = 24         # очередь domains.db

# --- Verdict taxonomy (план §6.2 + реальные исходы трёх поверхностей) ---
VERDICTS = [
    "APPROVED", "APPROVED@HOLD", "APPROVED@PAID", "APPROVED@CVV", "APPROVED@CCN",
    "DECLINED", "DECLINED@DO_NOT_HONOR", "DECLINED@FRAUD", "DECLINED@STOLEN",
    "INVALID", "EXPIRED", "WRONG_CVC", "RESTRICTED",
    "TEST_MODE", "RATE_LIMITED", "RETRY", "PI_MINTED", "PI_PENDING",
    "3DS_REQUIRED", "3DS_FRICTIONLESS", "3DS_CHALLENGE", "3DS_REDIRECT",
    "SESSION_EXPIRED", "SESSION_CANCELED",
    # Внутренние исходы антибот-челленджа Radar (gate_client.verify_intent_challenge).
    # В таксономии, иначе любой путь через coerce_verdict давал UNKNOWN без возврата
    # кредита (аудит 2026-09, M-06 / G-10).
    "CHALLENGE_FAILED", "CHALLENGE_BURNED",
    "UNKNOWN", "ERROR",
]
HIT_VERDICTS = {"APPROVED", "APPROVED@HOLD", "APPROVED@PAID", "APPROVED@CVV", "APPROVED@CCN"}
VERDICT_ICONS = {
    "APPROVED": "✅", "APPROVED@HOLD": "🟡", "APPROVED@PAID": "💰",
    "APPROVED@CVV": "✅", "APPROVED@CCN": "✅",
    "DECLINED": "❌", "DECLINED@DO_NOT_HONOR": "❌", "DECLINED@FRAUD": "🚫", "DECLINED@STOLEN": "🚨",
    "INVALID": "⚠️", "EXPIRED": "⌛", "WRONG_CVC": "⚠️", "RESTRICTED": "⛔",
    "TEST_MODE": "🧪", "RATE_LIMITED": "🐢", "RETRY": "🔁", "PI_MINTED": "🪙",
    "PI_PENDING": "🧾",
    "3DS_REQUIRED": "🔒", "3DS_FRICTIONLESS": "✅", "3DS_CHALLENGE": "🔐",
    "3DS_REDIRECT": "↪️",
    "SESSION_EXPIRED": "⌛", "SESSION_CANCELED": "🚫",
    "CHALLENGE_FAILED": "🔐", "CHALLENGE_BURNED": "🔥",
    "UNKNOWN": "❔",
    "ERROR": "💥",
}


def coerce_verdict(verdict: str) -> str:
    """Страховка таксономии: вердикт вне VERDICTS сводится к ближайшему классу.

    Порядок: технические сбои витрины/цели -> ERROR (возврат кредита + фолл-троу)
    -> точное совпадение -> базовый класс по префиксу (DECLINED@{ЧТО-ТО}
    -> DECLINED) -> UNKNOWN.
    """
    v = (verdict or "").strip()
    # Сбои витрины/цели (не свойство карты) обязаны быть ERROR
    if v in ("GUEST_CHECKOUT_DISABLED", "GUEST_CHECKOUT_OFF", "CAPTCHA_CHECKOUT",
             "NO_PM_SLUG", "PM_SLUG_MISSING", "NO_PRODUCT_UNDER_CAP", "NO_PRODUCTS",
             "ADD_ITEM_NO_JSON", "VARIATION_REQUIRED", "CHARGE_RISK",
             "OUT_OF_STOCK", "CART_EMPTY", "CHECKPOINT_DENIED",
             # Технические исходы, которые раньше уходили в UNKNOWN и не возвращали кредит:
             # провал челленджа, невалидный линк, исключение движка, провал пайплайна.
             "CHALLENGE_FAILED", "CHALLENGE_BURNED",
             "INVALID_URL", "EXCEPTION", "FAILED"):
        return "ERROR"
    if v in VERDICTS:
        return v
    base = v.split("@", 1)[0].strip()
    if base in VERDICTS:
        return base
    return "UNKNOWN"


def is_hit(verdict: str) -> bool:
    return verdict in HIT_VERDICTS


# Вердикты, при которых бот ВОЗВРАЩАЕТ кредит: сбой движка (ERROR) и смерть
# цели/сессии (SESSION_*). Это свойство цели, а не карты — пользователь не
# должен платить за мёртвый линк/донора. Всё остальное (включая DECLINED и
# любые 3DS_*) — честный результат проверки карты.
REFUNDABLE_VERDICTS = {"ERROR", "SESSION_EXPIRED", "SESSION_CANCELED"}

# Состояния пайплайна /hit (execute_hit). Это НЕ вердикты карты: держим отдельным полем,
# чтобы терминальный статус прогона не подменял таксономию (аудит 2026-09, G-10).
PIPELINE_STATES = ("SUCCESS", "COMPLETED", "PARTIAL", "FAILED")

# 3DS Method notification URL. Прежний хардкод https://hooks.stripe.com/3ds2/fingerprint/complete
# отдаёт 404 (проверено боем 2026-09-12), а живой маршрут того же семейства — /3d_secure_2/...
# (200 ОК). Пока значение берётся из ответа Stripe, но дефолт обязан быть живым.
THREE_DS_METHOD_NOTIFICATION_URL = "https://hooks.stripe.com/3d_secure_2/hosted/complete"

# Сколько страниц /products.json обходить при поиске самого дешёвого варианта:
# эндпоинт отдаёт максимум 250 товаров на страницу без пагинации, у крупных каталогов
# дешёвые позиции лежат дальше первой страницы (аудит 2026-09, G-28).
SHOPIFY_CATALOG_PAGES = 3

# Известные НЕПУБЛИЧНЫЕ эндпоинты Stripe, на которых стоит боевой контур. В API-референсе
# их нет (docs.stripe.com отдаёт 404), но маршруты живы и отвечают 401 без ключа. Начал
# отдавать 404 — Stripe убрал маршрут: это сломанный контур, а не отказ карты.
UNDOCUMENTED_ENDPOINTS = {
    "/v1/payment_pages/{cs}": "Stripe Checkout hosted pages (чтение сессии)",
    "/v1/payment_pages/{cs}/confirm": "Stripe Checkout hosted pages (подтверждение)",
    "/v1/payment_intents/{pi}/verify_challenge": "Radar hCaptcha Enterprise challenge",
    "/v1/confirmation_tokens": "ConfirmationToken из pk (документирован только клиентский путь)",
    "/v1/3ds2/authenticate": "3DS2 из эпохи Sources API (официально деприкейтнут)",
}


def is_refundable(verdict: str) -> bool:
    """ERROR или смерть цели/сессии: кредит возвращается, фолл-троу продолжается."""
    return coerce_verdict(verdict) in REFUNDABLE_VERDICTS


def icon(verdict: str) -> str:
    return VERDICT_ICONS.get(verdict, "·")
