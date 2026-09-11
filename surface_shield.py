# language: Python 3.12+, file: surface_shield.py, target: Windows 11, deps: curl_cffi
"""
Surface Shield & Anti-Bot Protection Classifier for Pusto.
Identifies edge WAFs, client-side bot detection frameworks, and CAPTCHA mechanisms
with zero false-positives on legitimate checkout forms.

Capabilities:
1. Edge WAF Detection (Cloudflare, Akamai, DataDome, Kasada, AWS WAF, Imperva/Incapsula, Fastly)
2. Client Shield Detection (Cloudflare Turnstile, hCaptcha Enterprise, Google reCAPTCHA v2/v3, DataDome JS, Kasada PoW)
3. Form-Level Protection Inspection (WooCommerce nonces, honeypots, WP-Members barriers)
4. Distinguishes Active Challenge Interstitials from Passive/Embedded Widgets (<2.0s SLA)
5. Prescribes Optimal Zero-Cost Bypass Routing Vector
"""
import re
from typing import Any, Dict, List, Optional, Union
from urllib.parse import urlparse

from curl_cffi.requests import AsyncSession

import config as _cfg
import gate_client as gc
import pusto_logger as _log

# --- WAF Header Signatures ---
WAF_HEADERS = {
    "cloudflare": ("cf-ray", "cf-cache-status", "cf-mitigated", "cf-chl-bypass", "cf-apo-via"),
    "datadome": ("x-datadome-cid", "x-dd-b", "x-datadome", "x-datadome-response"),
    "akamai": ("akamai-grn", "x-akamai-transformed", "x-akamai-session-info", "x-akamai-request-id", "akamai-origin-hop"),
    "kasada": ("x-kpsdk-ct", "x-kpsdk-cd", "x-kpsdk-v"),
    "aws_waf": ("x-amzn-waf-action", "x-amzn-requestid", "x-amz-cf-id", "x-amzn-errortype"),
    "imperva": ("x-iinfo", "x-cdn", "x-incap-sess", "x-visid-incap"),
    "fastly": ("x-fastly-request-id", "fastly-restarts", "fastly-client-ip"),
    "perimeterx": ("x-px-authorization", "x-px-cookie", "x-px-original-token"),
}

# --- WAF Cookie Signatures ---
WAF_COOKIES = {
    "cloudflare": re.compile(r"\b(cf_clearance|__cf_bm|cf_chl_)\b", re.I),
    "datadome": re.compile(r"\b(datadome|_dd_s|dd_cookie_test_)\b", re.I),
    "akamai": re.compile(r"\b(_abck|bm_sz|ak_bmsc|bm_sv)\b", re.I),
    "kasada": re.compile(r"\b(KP_UIDz|x-kpsdk-)\b", re.I),
    "perimeterx": re.compile(r"\b(_px3|_pxvid|_pxhd|_pxde)\b", re.I),
    "aws_waf": re.compile(r"\baws-waf-token\b", re.I),
    "imperva": re.compile(r"\b(incap_ses_|visid_incap_|reese84|nlbi_)\b", re.I),
    "f5_shape": re.compile(r"\b(TS[0-9a-fA-F]{6,}|reese84)\b", re.I),
}

# --- Script & Asset Signatures ---
SCRIPT_SIGNATURES = [
    ("cloudflare_turnstile", re.compile(r"challenges\.cloudflare\.com/turnstile", re.I)),
    ("cloudflare_challenge", re.compile(r"/cdn-cgi/challenge-platform/", re.I)),
    ("hcaptcha", re.compile(r"hcaptcha\.com/(1/api\.js|checksiteconfig)", re.I)),
    ("recaptcha", re.compile(r"(google\.com/recaptcha|recaptcha\.net)", re.I)),
    ("datadome", re.compile(r"(js\.datadome\.co/tags\.js|captcha-delivery\.com|geo\.captcha-delivery\.com)", re.I)),
    ("perimeterx", re.compile(r"(client\.px-cdn\.net|perimeterx)", re.I)),
    ("kasada", re.compile(r"(kpsdk|\bips\.js|149e9513-01fa-4fb0-aad4-566afd725d1b)", re.I)),
    ("akamai", re.compile(r"(sensor\.js|akamai-bm-telemetry)", re.I)),
    ("altcha", re.compile(r"(<altcha-widget\b|altcha(?:\.min)?\.js)", re.I)),
    ("friendly_captcha", re.compile(r"(friendlycaptcha\.com|frc-captcha)", re.I)),
]

# --- Active Interstitial Titles ---
BLOCK_TITLES = re.compile(
    r"<title>\s*(just a moment|attention required|sorry, you have been blocked|"
    r"pardon our interruption|access denied|security check|challenge validation|"
    r"cloudflare ray id|ddos-guard|waf block|error 403: forbidden)\b",
    re.I
)
RE_BLOCK_TITLE_TEXT = re.compile(
    r"^\s*(?:just a moment|attention required|sorry, you have been blocked|"
    r"pardon our interruption|access denied|security check|challenge validation|"
    r"cloudflare ray id|ddos-guard|waf block|error 403: forbidden)\b|"
    r"\b(?:just a moment|attention required|sorry, you have been blocked|"
    r"pardon our interruption|access denied|security check|challenge validation|"
    r"cloudflare ray id|ddos-guard|waf block|error 403: forbidden)\b",
    re.I
)

# --- Sitekey Regexes ---
RE_SITEKEY_TURNSTILE = re.compile(r'data-sitekey=["\'](0x4[A-Za-z0-9_-]+)["\']', re.I)
RE_SITEKEY_HCAPTCHA = re.compile(r'data-sitekey=["\']([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})["\']', re.I)
RE_SITEKEY_RECAPTCHA = re.compile(r'data-sitekey=["\'](6L[0-9a-zA-Z_-]{20,50})["\']|render=(6L[0-9a-zA-Z_-]{20,50})', re.I)
RE_SITEKEY_FRIENDLY = re.compile(r'class=["\'][^"\']*frc-captcha[^"\']*["\'][^>]*data-sitekey=["\']([^"\']+)["\']|data-sitekey=["\'](FC[0-9A-Za-z_-]+)["\']', re.I)

# --- Form Nonce Regexes ---
RE_WOO_REG_NONCE = re.compile(
    r'(?:'
    r'name=["\']woocommerce-register-nonce["\'][^>]*value=["\']([a-f0-9]{10})["\']|'
    r'value=["\']([a-f0-9]{10})["\'][^>]*name=["\']woocommerce-register-nonce["\']|'
    r'id=["\']woocommerce-register-nonce["\'][^>]*value=["\']([a-f0-9]{10})["\']|'
    r'value=["\']([a-f0-9]{10})["\'][^>]*id=["\']woocommerce-register-nonce["\']|'
    r'woocommerce-register-nonce["\']?\s*[:=]\s*["\']([a-f0-9]{10})["\']'
    r')',
    re.I
)
RE_WPNONCE = re.compile(
    r'(?:'
    r'name=["\']_wpnonce["\'][^>]*value=["\']([a-f0-9]{10})["\']|'
    r'value=["\']([a-f0-9]{10})["\'][^>]*name=["\']_wpnonce["\']|'
    r'id=["\']_wpnonce["\'][^>]*value=["\']([a-f0-9]{10})["\']|'
    r'value=["\']([a-f0-9]{10})["\'][^>]*id=["\']_wpnonce["\']|'
    r'["\']?_wpnonce["\']?\s*[:=]\s*["\']([a-f0-9]{10})["\']'
    r')',
    re.I
)
RE_STORE_API_NONCE = re.compile(
    r'["\']?(?:storeApiNonce|X-WC-Store-API-Nonce)["\']?\s*[:=]\s*["\']([a-f0-9]{10})["\']|'
    r'wcSettings\s*=\s*\{[^\}]{0,1000}?"nonce"\s*:\s*"([a-f0-9]{10})"',
    re.I | re.S
)
RE_WOO_CHECKOUT_NONCE = re.compile(
    r'(?:'
    r'name=["\']woocommerce-process-checkout-nonce["\'][^>]*value=["\']([a-f0-9]{10})["\']|'
    r'value=["\']([a-f0-9]{10})["\'][^>]*name=["\']woocommerce-process-checkout-nonce["\']|'
    r'id=["\']woocommerce-process-checkout-nonce["\'][^>]*value=["\']([a-f0-9]{10})["\']|'
    r'value=["\']([a-f0-9]{10})["\'][^>]*id=["\']woocommerce-process-checkout-nonce["\']|'
    r'woocommerce-process-checkout-nonce["\']?\s*[:=]\s*["\']([a-f0-9]{10})["\']'
    r')',
    re.I
)

# --- Honeypot Regexes ---
RE_HONEYPOT_FIELDS = re.compile(
    r'<input[^>]+name=["\'](wpa_field|wpa_initiator|wpa_nonce|wp_armour|wpbruiser|wc_register_hp|wc_email_hp|cf7_hp|hp_email|antispam_field|antibot_field|honeypot)["\'][^>]*>',
    re.I
)
RE_HIDDEN_HONEYPOT_INPUTS = re.compile(
    r'<input[^>]+(?:style=["\'][^"\']*(?:display:\s*none|opacity:\s*0|visibility:\s*hidden)[^"\']*["\'][^>]+name=["\']([^"\']+)["\']|name=["\']([^"\']+)["\'][^>]+style=["\'][^"\']*(?:display:\s*none|opacity:\s*0|visibility:\s*hidden)[^"\']*["\'])',
    re.I
)
LEGITIMATE_FIELD_PREFIXES = (
    "billing_",
    "shipping_",
    "order_",
    "woocommerce-",
    "woocommerce_",
    "payment_",
    "account_",
    "wc-",
    "wc_",
)
EXCLUDED_HONEYPOT_NAMES = {
    "_wpnonce",
    "action",
    "_wp_http_referer",
    "submit",
    "payment_method",
    "terms",
    "ship_to_different_address",
}

# --- Membership & Mandatory Account Barrier Regexes ---
RE_WPMEMBERS = re.compile(
    r'\b(wpmem_login|wpmem_reg|wp-members|wpmem_msg|wpmem_form)\b|'
    r'You must be logged in to view this content|'
    r'This content is restricted to members|'
    r'plugins/wp-members',
    re.I
)
RE_MANDATORY_LOGIN = re.compile(
    r'\b(woocommerce-must-be-logged-in)\b|'
    r'You must be logged in to checkout|'
    r'Registration is disabled|'
    r'Only registered customers can checkout',
    re.I
)

# --- Legitimate Checkout Indicators ---
RE_CHECKOUT_MARKERS = re.compile(
    r'\b(woocommerce-checkout|wc-checkout|checkout_form|customer_details|order_review|'
    r'wp-json/wc/store|wc-stripe|payment_box|place_order|add-payment-method)\b|<form[^>]*name=["\']checkout["\']',
    re.I
)



def inspect_form_protections(html: str, headers: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    """
    Inspects form-level protections on the target page:
    1. WooCommerce Dynamic Nonces (woocommerce-register-nonce, _wpnonce, Store-API-Nonce, checkout_nonce)
    2. Honeypot Anti-Spam Fields (WP Armour, WPBruiser, hidden spam traps)
    3. Mandatory Account Barriers (WP-Members restrictions, login-required checkouts)
    """
    html = html or ""
    headers = headers or {}
    headers_lower = {str(k).lower(): str(v) for k, v in headers.items()}

    # 1. Nonces
    reg_nonce = None
    m_reg = RE_WOO_REG_NONCE.search(html)
    if m_reg:
        reg_nonce = next((g for g in m_reg.groups() if g), None)

    wpnonce = None
    m_wp = RE_WPNONCE.search(html)
    if m_wp:
        wpnonce = next((g for g in m_wp.groups() if g), None)

    store_nonce = headers_lower.get("x-wc-store-api-nonce") or headers_lower.get("nonce")
    if not store_nonce:
        m_store = RE_STORE_API_NONCE.search(html)
        if m_store:
            store_nonce = next((g for g in m_store.groups() if g), None)

    checkout_nonce = None
    m_chk = RE_WOO_CHECKOUT_NONCE.search(html)
    if m_chk:
        checkout_nonce = next((g for g in m_chk.groups() if g), None)

    nonces = {
        "woocommerce_register_nonce": reg_nonce,
        "wpnonce": wpnonce,
        "store_api_nonce": store_nonce,
        "checkout_nonce": checkout_nonce,
    }
    has_wc_nonce = any(v is not None for v in nonces.values())

    # 2. Honeypots
    honeypots = []
    for m in RE_HONEYPOT_FIELDS.finditer(html):
        val = m.group(1).strip()
        if val and val not in honeypots:
            honeypots.append(val)

    for m in RE_HIDDEN_HONEYPOT_INPUTS.finditer(html):
        val = next((g for g in m.groups() if g), "").strip()
        if not val:
            continue
        val_lower = val.lower()
        if val_lower in EXCLUDED_HONEYPOT_NAMES or any(val_lower.startswith(p) for p in LEGITIMATE_FIELD_PREFIXES):
            continue
        if val not in honeypots:
            honeypots.append(val)

    has_honeypot = len(honeypots) > 0

    # 3. Account Barriers
    has_account_barrier = False
    barrier_type = None
    barrier_details = None

    has_active_checkout = bool(
        re.search(r'<form[^>]+(?:class=["\'][^"\']*\b(?:checkout|woocommerce-checkout)\b|name=["\']checkout["\'])', html, re.I)
    )

    if not has_active_checkout:
        if RE_WPMEMBERS.search(html):
            has_account_barrier = True
            barrier_type = "wp_members"
            barrier_details = "WP-Members membership restriction detected"
        elif RE_MANDATORY_LOGIN.search(html):
            has_account_barrier = True
            barrier_type = "must_be_logged_in"
            barrier_details = "Mandatory customer registration/login required before checkout"
    else:
        # Checkout form is actively present; only flag if explicit blocking container is present
        if re.search(r'class=["\'][^"\']*\b(woocommerce-must-be-logged-in|wpmem_msg|wpmem_login)\b', html, re.I):
            has_account_barrier = True
            barrier_type = "must_be_logged_in"
            barrier_details = "Mandatory customer registration/login container present"

    return {
        "has_woocommerce_nonce": has_wc_nonce,
        "nonces": nonces,
        "has_honeypot": has_honeypot,
        "honeypots": honeypots,
        "has_account_barrier": has_account_barrier,
        "account_barrier_type": barrier_type,
        "account_barrier_details": barrier_details,
    }


def classify_protection(
    status_code: int,
    headers: Optional[Dict[str, str]] = None,
    cookies: Any = "",
    html: str = "",
    page_title: Optional[str] = None,
    *,
    cookies_str: Optional[str] = None,
) -> Dict[str, Any]:
    if headers is None:
        headers = {}
    html = html or ""
    if cookies_str is not None and (cookies == "" or cookies is None):
        cookies = cookies_str

    if isinstance(cookies, dict):
        cookies_str_val = "; ".join(f"{k}={v}" for k, v in cookies.items())
        cookies_dict = cookies
    elif isinstance(cookies, (list, tuple, set)):
        cookies_str_val = "; ".join(str(c) for c in cookies)
        cookies_dict = {}
    elif isinstance(cookies, str):
        cookies_str_val = cookies
        cookies_dict = {}
    else:
        cookies_str_val = str(cookies or "")
        cookies_dict = {}

    extracted_title = ""
    if html:
        m_t = re.search(r"<title[^>]*>(.*?)</title>", html, re.I | re.S)
        if m_t:
            extracted_title = m_t.group(1).strip()

    effective_title = (page_title or "").strip() or extracted_title

    waf_detected = "none"
    waf_confidence = 0.0
    waf_evidence = []

    headers_lower = {str(k).lower(): str(v) for k, v in headers.items()}
    server_header = str(headers_lower.get("server", "")).lower()

    # 1. Edge WAF Detection via Headers
    if "cloudflare" in server_header or "cf-ray" in headers_lower:
        waf_detected = "cloudflare"
        waf_confidence = 0.95
        waf_evidence.append(f"server={server_header}, cf-ray={headers_lower.get('cf-ray', '')[:10]}")
    elif "akamaighost" in server_header or "akamai" in server_header or any(h in headers_lower for h in WAF_HEADERS["akamai"]):
        waf_detected = "akamai"
        waf_confidence = 0.92
        waf_evidence.append("akamai header/ghost detected")
    elif "datadome" in server_header or any(h in headers_lower for h in WAF_HEADERS["datadome"]):
        waf_detected = "datadome"
        waf_confidence = 0.95
        waf_evidence.append("datadome header detected")
    elif "kasada" in server_header or any(h in headers_lower for h in WAF_HEADERS["kasada"]):
        waf_detected = "kasada"
        waf_confidence = 0.92
        waf_evidence.append("kasada header detected")
    elif "fastly" in server_header or any(h in headers_lower for h in WAF_HEADERS["fastly"]):
        waf_detected = "fastly"
        waf_confidence = 0.90
        waf_evidence.append("fastly header detected")
    elif ("imperva" in server_header or "incapsula" in server_header or
          "imperva" in headers_lower.get("x-cdn", "").lower() or
          "incapsula" in headers_lower.get("x-cdn", "").lower() or
          any(h in headers_lower for h in WAF_HEADERS["imperva"])):
        waf_detected = "imperva"
        waf_confidence = 0.90
        waf_evidence.append("imperva/incapsula header detected")
    elif any(h in headers_lower for h in WAF_HEADERS["aws_waf"]):
        waf_detected = "aws_waf"
        waf_confidence = 0.90
        waf_evidence.append("aws-waf header detected")
    else:
        for waf_name, markers in WAF_HEADERS.items():
            if any(m in headers_lower for m in markers):
                waf_detected = waf_name
                waf_confidence = 0.85
                waf_evidence.append(f"header match: {waf_name}")
                break

    # 2. Edge WAF Detection via Cookies
    for waf_name, cookie_rx in WAF_COOKIES.items():
        matched = False
        if cookie_rx.search(cookies_str_val):
            matched = True
        elif cookies_dict and any(cookie_rx.search(str(k)) for k in cookies_dict.keys()):
            matched = True

        if matched:
            if waf_detected == "none" or waf_confidence < 0.90:
                waf_detected = waf_name
                waf_confidence = 0.90
            elif waf_detected == waf_name:
                waf_confidence = min(0.99, waf_confidence + 0.05)
            waf_evidence.append(f"cookie match: {waf_name}")

    # 3. Client Bot Challenge Detection
    shields = []
    has_turnstile = False
    has_hcaptcha = False
    has_recaptcha = False
    has_pow = False

    for shield_name, script_rx in SCRIPT_SIGNATURES:
        if script_rx.search(html):
            shields.append(shield_name)

    turnstile_sk = RE_SITEKEY_TURNSTILE.search(html)
    if turnstile_sk or "cf-turnstile" in html:
        has_turnstile = True
        if "cloudflare_turnstile" not in shields:
            shields.append("cloudflare_turnstile")

    hcaptcha_sk = RE_SITEKEY_HCAPTCHA.search(html)
    if hcaptcha_sk or "h-captcha" in html:
        has_hcaptcha = True
        if "hcaptcha" not in shields:
            shields.append("hcaptcha")
        if "checksiteconfig" in html or "enterprise" in html.lower():
            if "hcaptcha_enterprise" not in shields:
                shields.append("hcaptcha_enterprise")

    recaptcha_sk = RE_SITEKEY_RECAPTCHA.search(html)
    if recaptcha_sk or "g-recaptcha" in html:
        has_recaptcha = True
        if "recaptcha" not in shields:
            shields.append("recaptcha")
        if "recaptcha/enterprise" in html or "grecaptcha.enterprise" in html:
            if "recaptcha_enterprise" not in shields:
                shields.append("recaptcha_enterprise")

    # DataDome slider / interstitial check
    if "geo.captcha-delivery.com" in html or "captcha-delivery.com" in html or "datadome-slider" in html or "dd.action" in html:
        if "datadome_slider" not in shields:
            shields.append("datadome_slider")
        if "datadome" not in shields:
            shields.append("datadome")

    # Kasada PoW / SDK check
    if "kasada" in shields:
        if "kasada_pow" not in shields:
            shields.append("kasada_pow")

    if "<altcha-widget" in html or re.search(r"altcha(?:\.min)?\.js", html, re.I):
        has_pow = True
        if "altcha" not in shields:
            shields.append("altcha")

    friendly_sk = RE_SITEKEY_FRIENDLY.search(html)
    if "frc-captcha" in html or "friendlycaptcha" in html or friendly_sk:
        has_pow = True
        if "friendly_captcha" not in shields:
            shields.append("friendly_captcha")

    # 4. Form-Level Protection Inspection
    form_protections = inspect_form_protections(html, headers)

    # 5. Discrimination Engine: Passive Telemetry vs Active Blocking Interstitial
    is_active_block = False
    block_reason = ""
    is_checkout = bool(RE_CHECKOUT_MARKERS.search(html))
    title_matches_block = bool(RE_BLOCK_TITLE_TEXT.search(effective_title) or BLOCK_TITLES.search(html))

    if status_code in (403, 429, 503):
        if title_matches_block or gc.is_cloudflare_challenge(html):
            is_active_block = True
            block_reason = f"HTTP {status_code} with challenge title/interstitial"
        elif waf_detected == "datadome" and ("geo.captcha-delivery.com" in html or "captcha-delivery.com" in html):
            is_active_block = True
            block_reason = "DataDome 403 captcha challenge page"
        elif waf_detected == "kasada":
            is_active_block = True
            block_reason = f"Kasada bare {status_code} drop"
        elif waf_detected == "aws_waf":
            is_active_block = True
            block_reason = f"AWS WAF {status_code} block action"
        elif waf_detected == "imperva":
            is_active_block = True
            block_reason = f"Imperva/Incapsula {status_code} block page"
        else:
            is_active_block = True
            block_reason = f"HTTP {status_code} active access denial"
    elif status_code == 200:
        has_challenge_interstitial = (
            "/cdn-cgi/challenge-platform/" in html
            or "geo.captcha-delivery.com" in html
            or "captcha-delivery.com" in html
        )
        if title_matches_block or has_challenge_interstitial:
            if is_checkout and ("cf-turnstile-wrapper" in html or "cf-turnstile" in html) and not has_challenge_interstitial:
                is_active_block = False
            elif has_challenge_interstitial:
                is_active_block = True
                block_reason = f"Active challenge interstitial page ({effective_title or 'HTTP 200 challenge'})"
            elif not is_checkout:
                is_active_block = True
                block_reason = f"Page title indicates active bot interstitial ({effective_title})"

    # 6. Optimal Bypass Strategy Router
    if is_active_block:
        if waf_detected == "cloudflare":
            bypass_route = "turnstile_sidecar_cdp"
        elif waf_detected == "datadome":
            bypass_route = "residential_proxy_rotation"
        elif waf_detected == "kasada":
            bypass_route = "patchright_headless_eval"
        else:
            bypass_route = "warm_session_harvest"
    elif has_pow:
        bypass_route = "captcha_pow_cpu"
    elif has_turnstile:
        bypass_route = "direct_api_or_turnstile_sidecar"
    elif has_hcaptcha:
        bypass_route = "silent_radar_token_or_ctoken"
    elif has_recaptcha:
        bypass_route = "direct_api_or_recaptcha_v3"
    elif waf_detected == "cloudflare":
        bypass_route = "curl_impersonate_direct"
    else:
        bypass_route = "standard_direct"

    recaptcha_sitekey = None
    if recaptcha_sk:
        recaptcha_sitekey = next((g for g in recaptcha_sk.groups() if g), None)

    friendly_sitekey = None
    if friendly_sk:
        friendly_sitekey = next((g for g in friendly_sk.groups() if g), None)

    return {
        "status_code": status_code,
        "page_title": effective_title,
        "waf": waf_detected,
        "waf_confidence": waf_confidence,
        "waf_evidence": waf_evidence,
        "shields": sorted(list(set(shields))),
        "is_active_block": is_active_block,
        "block_reason": block_reason,
        "sitekeys": {
            "turnstile": turnstile_sk.group(1) if turnstile_sk else None,
            "hcaptcha": hcaptcha_sk.group(1) if hcaptcha_sk else None,
            "recaptcha": recaptcha_sitekey,
            "friendly_captcha": friendly_sitekey,
        },
        "form_protections": form_protections,
        "bypass_strategy": bypass_route,
    }


async def inspect_target(url: str, proxy: Optional[str] = None, timeout: float = 2.0) -> Dict[str, Any]:
    clean_url = url.strip()
    if not clean_url.startswith("http"):
        clean_url = f"https://{clean_url}"

    imp = _cfg.pick_impersonate()
    try:
        async with AsyncSession(impersonate=imp, verify=False, proxy=proxy) as s:
            r = await s.get(clean_url, timeout=timeout, allow_redirects=True)
            cookies_blob = "\n".join(r.headers.get_list("set-cookie")) if hasattr(r.headers, "get_list") else str(r.headers)
            profile = classify_protection(
                status_code=r.status_code,
                headers=dict(r.headers),
                cookies_str=cookies_blob,
                html=r.text or "",
            )
            profile["url"] = str(r.url)
            profile["impersonate_used"] = imp
            profile["alive"] = True
            return profile
    except Exception as e:
        return {
            "url": clean_url,
            "alive": False,
            "error": f"{type(e).__name__}: {e}",
            "status_code": 0,
            "page_title": "",
            "waf": "unknown",
            "waf_confidence": 0.0,
            "waf_evidence": [],
            "shields": [],
            "is_active_block": False,
            "block_reason": "",
            "sitekeys": {
                "turnstile": None,
                "hcaptcha": None,
                "recaptcha": None,
                "friendly_captcha": None,
            },
            "form_protections": {
                "has_woocommerce_nonce": False,
                "nonces": {
                    "woocommerce_register_nonce": None,
                    "wpnonce": None,
                    "store_api_nonce": None,
                    "checkout_nonce": None,
                },
                "has_honeypot": False,
                "honeypots": [],
                "has_account_barrier": False,
                "account_barrier_type": None,
                "account_barrier_details": None,
            },
            "bypass_strategy": "retry_with_fresh_proxy",
        }

