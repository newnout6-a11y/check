import sys, json
sys.path.insert(0, r"C:\Users\Redmi\Downloads\pusto")
import funnel, config
used = ["RATE_LIMITED","CF_CHALLENGE","CAPTCHA","NOT_WORDPRESS","NOT_WOO","NO_STORE_API","TEST_MODE_PK","NO_STRIPE_PK","NO_ROUTE","HTTP_4XX","HTTP_5XX","DNS_FAIL","TIMEOUT","UNKNOWN","NO_REG"]
reasons = set(getattr(funnel, "REASONS", []) or [])
print("funnel.REASONS type:", type(getattr(funnel,'REASONS',None)).__name__, "count:", len(reasons))
missing = [r for r in used if r not in reasons]
print("REASONS missing from funnel:", missing)
print("sample REASONS:", sorted(list(reasons))[:40])
# curl_cffi cookie dict behaviour
from curl_cffi.requests import AsyncSession
print("curl_cffi:", __import__("curl_cffi").__version__ if hasattr(__import__("curl_cffi"),"__version__") else "?")
