# language: Python 3.12+, file: config.py, target: Windows 11
# Sprint 5: единый конфиг порогов и констант пайплайна.
# Всё, что раньше было размазано по файлам магическими числами.

# --- Stripe (первоисточник — менять ЗДЕСЬ) ---
STRIPE_API_VERSION = "2026-03-25.dahlia"
STRIPE_JS_BUILD = "eb42eea6af"
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
    "UNKNOWN", "ERROR",
]
HIT_VERDICTS = {"APPROVED", "APPROVED@HOLD", "APPROVED@CVV", "APPROVED@CCN"}
VERDICT_ICONS = {
    "APPROVED": "✅", "APPROVED@HOLD": "🟡", "APPROVED@PAID": "💰",
    "APPROVED@CVV": "✅", "APPROVED@CCN": "✅",
    "DECLINED": "❌", "DECLINED@DO_NOT_HONOR": "❌", "DECLINED@FRAUD": "🚫", "DECLINED@STOLEN": "🚨",
    "INVALID": "⚠️", "EXPIRED": "⌛", "WRONG_CVC": "⚠️", "RESTRICTED": "⛔",
    "TEST_MODE": "🧪", "RATE_LIMITED": "🐢", "RETRY": "🔁", "PI_MINTED": "🪙",
    "PI_PENDING": "🧾",
    "3DS_REQUIRED": "🔒", "3DS_FRICTIONLESS": "✅", "3DS_CHALLENGE": "🔐",
    "3DS_REDIRECT": "↪️", "UNKNOWN": "❔",
    "ERROR": "💥",
}


def coerce_verdict(verdict: str) -> str:
    """Страховка таксономии: вердикт вне VERDICTS сводится к ближайшему классу.

    Порядок: точное совпадение → базовый класс по префиксу (DECLINED@{ЧТО-ТО}
    → DECLINED) → UNKNOWN. Сырая строка наружу не выходит НИКОГДА: она остаётся
    без иконки, не попадает в статистику хитов и, главное, != "ERROR", из-за чего
    кредит за проверку не возвращался.
    """
    v = (verdict or "").strip()
    if v in VERDICTS:
        return v
    base = v.split("@", 1)[0].strip()
    if base in VERDICTS:
        return base
    return "UNKNOWN"


def is_hit(verdict: str) -> bool:
    return verdict in HIT_VERDICTS


def icon(verdict: str) -> str:
    return VERDICT_ICONS.get(verdict, "·")
