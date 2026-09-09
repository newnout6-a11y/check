# language: Python 3.12+, file: surface_shield.py, target: Windows 11, deps: curl_cffi
"""
Surface Shield & Anti-Bot Protection Classifier for Pusto.
Identifies edge WAFs, client-side bot detection frameworks, and CAPTCHA mechanisms
with zero false-positives on legitimate checkout forms.

Capabilities:
1. Edge WAF Detection (Cloudflare, Akamai, DataDome, Kasada, AWS WAF, Imperva/Incapsula, Fastly)
2. Client Shield Detection (Cloudflare Turnstile, hCaptcha Enterprise, Google reCAPTCHA v2/v3, DataDome JS, PerimeterX)
3. Distinguishes Active Challenge Interstitials from Passive/Embedded Widgets
4. Prescribes Optimal Zero-Cost Bypass Routing Vector
"""
import re
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

from curl_cffi.requests import AsyncSession

import config as _cfg
import gate_client as gc
import pusto_logger as _log

# --- WAF Header Signatures ---
WAF_HEADERS = {
    "cloudflare": ("cf-ray", "cf-cache-status", "cf-mitigated"),
    "datadome": ("x-datadome-cid", "x-dd-b", "x-datadome"),
    "akamai": ("akamai-grn", "x-akamai-transformed", "x-akamai-session-info"),
    "kasada": ("x-kpsdk-ct", "x-kpsdk-cd"),
    "aws_waf": ("x-amzn-waf-action", "x-amzn-requestid"),
    "imperva": ("x-iinfo", "x-cdn"),
    "fastly": ("x-fastly-request-id", "fastly-restarts"),
}

# --- WAF Cookie Signatures ---
WAF_COOKIES = {
    "cloudflare": re.compile(r"\b(cf_clearance|__cf_bm)\b"),
    "datadome": re.compile(r"\b(datadome|_dd_s|dd_cookie_test_)\b"),
    "akamai": re.compile(r"\b(_abck|bm_sz|ak_bmsc)\b"),
    "kasada": re.compile(r"\b(KP_UIDz|x-kpsdk-)\b"),
    "perimeterx": re.compile(r"\b(_px3|_pxvid|_pxhd|_pxde)\b"),
    "aws_waf": re.compile(r"\baws-waf-token\b"),
    "imperva": re.compile(r"\b(incap_ses_|visid_incap_|reese84)\b"),
    "f5_shape": re.compile(r"\b(TS[0-9a-fA-F]{6,}|reese84)\b"),
}

# --- Script & Asset Signatures ---
SCRIPT_SIGNATURES = [
    ("cloudflare_turnstile", re.compile(r"challenges\.cloudflare\.com/turnstile", re.I)),
    ("cloudflare_challenge", re.compile(r"/cdn-cgi/challenge-platform/", re.I)),
    ("hcaptcha", re.compile(r"hcaptcha\.com/(1/api\.js|checksiteconfig)", re.I)),
    ("recaptcha", re.compile(r"(google\.com/recaptcha|recaptcha\.net)", re.I)),
    ("datadome", re.compile(r"(js\.datadome\.co/tags\.js|captcha-delivery\.com)", re.I)),
    ("perimeterx", re.compile(r"(client\.px-cdn\.net|perimeterx)", re.I)),
    ("kasada", re.compile(r"(kpsdk|ips\.js)", re.I)),
    ("akamai", re.compile(r"(sensor\.js|akamai-bm-telemetry)", re.I)),
    ("altcha", re.compile(r"(altcha\.org|altcha-widget)", re.I)),
    ("friendly_captcha", re.compile(r"friendlycaptcha\.com", re.I)),
]

# --- Active Interstitial Titles ---
BLOCK_TITLES = re.compile(
    r"<title>\s*(just a moment|attention required|sorry, you have been blocked|"
    r"pardon our interruption|access denied|security check)\b",
    re.I
)

# --- Sitekey Regexes ---
RE_SITEKEY_TURNSTILE = re.compile(r'data-sitekey=["\'](0x4[A-Za-z0-9_-]+)["\']', re.I)
RE_SITEKEY_HCAPTCHA = re.compile(r'data-sitekey=["\']([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})["\']', re.I)
RE_SITEKEY_RECAPTCHA = re.compile(r'data-sitekey=["\'](6L[0-9a-zA-Z_-]{38})["\']', re.I)


def classify_protection(
    status_code: int,
    headers: Dict[str, str],
    cookies_str: str,
    html: str
) -> Dict[str, Any]:
    waf_detected = "none"
    waf_confidence = 0.0
    waf_evidence = []
    
    server_header = headers.get("server", "").lower()
    headers_lower = {k.lower(): v for k, v in headers.items()}
    
    if "cloudflare" in server_header or "cf-ray" in headers_lower:
        waf_detected = "cloudflare"
        waf_confidence = 0.95
        waf_evidence.append(f"server={server_header}, cf-ray={headers_lower.get('cf-ray', '')[:10]}")
    elif "akamaighost" in server_header or any(h in headers_lower for h in WAF_HEADERS["akamai"]):
        waf_detected = "akamai"
        waf_confidence = 0.90
        waf_evidence.append("akamai header detected")
    else:
        for waf_name, markers in WAF_HEADERS.items():
            if any(m in headers_lower for m in markers):
                waf_detected = waf_name
                waf_confidence = 0.85
                waf_evidence.append(f"header match: {waf_name}")
                break

    for waf_name, cookie_rx in WAF_COOKIES.items():
        if cookie_rx.search(cookies_str):
            if waf_detected == "none" or waf_confidence < 0.90:
                waf_detected = waf_name
                waf_confidence = 0.90
            waf_evidence.append(f"cookie match: {waf_name}")

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

    recaptcha_sk = RE_SITEKEY_RECAPTCHA.search(html)
    if recaptcha_sk or "g-recaptcha" in html:
        has_recaptcha = True
        if "recaptcha" not in shields:
            shields.append("recaptcha")

    if "<altcha-widget" in html or "altcha.org" in html:
        has_pow = True
        if "altcha" not in shields:
            shields.append("altcha")

    if "frc-captcha" in html or "friendlycaptcha" in html:
        has_pow = True
        if "friendly_captcha" not in shields:
            shields.append("friendly_captcha")

    is_active_block = False
    block_reason = ""
    
    if status_code in (403, 429, 503):
        if BLOCK_TITLES.search(html) or gc.is_cloudflare_challenge(html):
            is_active_block = True
            block_reason = f"HTTP {status_code} with challenge title/interstitial"
        elif waf_detected == "datadome" and "geo.captcha-delivery.com" in html:
            is_active_block = True
            block_reason = "DataDome 403 captcha challenge page"
        elif waf_detected == "kasada":
            is_active_block = True
            block_reason = "Kasada bare 429/403 drop"
    elif BLOCK_TITLES.search(html) and "cf-turnstile-wrapper" not in html:
        is_active_block = True
        block_reason = "Page title indicates active bot interstitial"

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
    elif waf_detected == "cloudflare":
        bypass_route = "curl_impersonate_direct"
    else:
        bypass_route = "standard_direct"

    return {
        "status_code": status_code,
        "waf": waf_detected,
        "waf_confidence": waf_confidence,
        "waf_evidence": waf_evidence,
        "shields": list(set(shields)),
        "is_active_block": is_active_block,
        "block_reason": block_reason,
        "sitekeys": {
            "turnstile": turnstile_sk.group(1) if turnstile_sk else None,
            "hcaptcha": hcaptcha_sk.group(1) if hcaptcha_sk else None,
            "recaptcha": recaptcha_sk.group(1) if recaptcha_sk else None,
        },
        "bypass_strategy": bypass_route
    }


async def inspect_target(url: str, proxy: Optional[str] = None, timeout: float = 12.0) -> Dict[str, Any]:
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
                html=r.text or ""
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
            "waf": "unknown",
            "shields": [],
            "is_active_block": False,
            "bypass_strategy": "retry_with_fresh_proxy"
        }
