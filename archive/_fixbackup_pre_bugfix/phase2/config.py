# language: Python 3.12+, file: config.py, target: Windows 11
# Sprint 5: единый конфиг порогов и констант пайплайна.
# Всё, что раньше было размазано по файлам магическими числами.

# --- Stripe (первоисточник — менять ЗДЕСЬ) ---
STRIPE_API_VERSION = "2024-06-20"
STRIPE_JS_BUILD = "c1fbe29896"
CHROME_IMPERSONATE = "chrome131"

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
    "TEST_MODE", "RATE_LIMITED", "RETRY", "PI_MINTED",
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
    "3DS_REQUIRED": "🔒", "3DS_FRICTIONLESS": "✅", "3DS_CHALLENGE": "🔐",
    "3DS_REDIRECT": "↪️", "UNKNOWN": "❔",
    "ERROR": "💥",
}


def is_hit(verdict: str) -> bool:
    return verdict in HIT_VERDICTS


def icon(verdict: str) -> str:
    return VERDICT_ICONS.get(verdict, "·")
