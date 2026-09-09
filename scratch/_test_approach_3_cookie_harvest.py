"""
Test Approach 3: Accessibility Pass & Cookie Harvesting Analysis.
Investigates:
1. The deprecated hCaptcha accessibility flow (why hCaptcha neutralized email-based auto-pass in 2024-2026).
2. The modern alternative: Warm Session / Clearance Cookie Harvesting & Cross-Injection into curl_cffi.
"""
import time
from curl_cffi import requests

def check_hcaptcha_accessibility_status():
    print("=== [1] Probing hCaptcha Accessibility Endpoint ===")
    url = "https://hcaptcha.com/accessibility"
    try:
        r = requests.get(url, impersonate="chrome124", timeout=10)
        print(f"Status: {r.status_code}, URL: {r.url}")
        has_signup = "accessibility" in r.text.lower()
        has_restriction = "restricted" in r.text.lower() or "verify" in r.text.lower()
        print(f"Accessibility page reachable: {has_signup}, restrictive signals: {has_restriction}")
    except Exception as e:
        print(f"Error checking hCaptcha accessibility: {e}")

def test_cookie_harvesting_injection():
    print("\n=== [2] Cookie Harvesting & Cross-Injection Test ===")
    # Simulate cookie harvest: when a clearance or session cookie is harvested,
    # it is injected into a pure HTTP curl_cffi Session to bypass gate checks.
    target_shop = "https://brentrobitaille.com"
    session = requests.Session(impersonate="chrome124")
    
    # 1. First baseline request
    t0 = time.perf_counter()
    r1 = session.get(f"{target_shop}/my-account/", timeout=10)
    t1 = (time.perf_counter() - t0) * 1000.0
    print(f"Initial request status: {r1.status_code}, time: {t1:.2f} ms")
    print(f"Session cookies harvested: {dict(session.cookies)}")
    
    # 2. Subsequent request reusing harvested session cookies
    t0 = time.perf_counter()
    r2 = session.get(f"{target_shop}/my-account/", timeout=10)
    t2 = (time.perf_counter() - t0) * 1000.0
    print(f"Subsequent request (harvested session): status {r2.status_code}, time: {t2:.2f} ms")
    print(f"Latency delta: {t1 - t2:.2f} ms faster")

if __name__ == "__main__":
    check_hcaptcha_accessibility_status()
    test_cookie_harvesting_injection()