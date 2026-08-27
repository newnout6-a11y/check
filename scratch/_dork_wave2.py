# language: Python 3.12+, file: scratch/_dork_wave2.py, target: Windows 11
# Wave 2: дорки с прицелом на ОТКРЫТУЮ регистрацию + SetupIntent-поверхность.
# Ник: ниши подписок/триалов/донатов, где $0-auth живёт по определению.
import asyncio
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(line_buffering=True, encoding="utf-8")

from curl_cffi.requests import AsyncSession

import domains_store

QUERIES = [
    # открытая регистрация + add-payment-method (ядро $0-auth)
    '"Create an account" "add-payment-method" "Credit Card (Stripe)"',
    '"Register" "my-account/add-payment-method" "Stripe"',
    '"woocommerce-form-register" "add payment method" stripe',
    '"Save payment information to my account" "Stripe" -site:woocommerce.com',
    # подписки/триалы — $0 SetupIntent по определению
    '"free trial" "add-payment-method" stripe subscription',
    '"Start your free trial" "credit card" stripe wordpress',
    '"no charge today" "Stripe" subscription wordpress',
    '"we authorize a $0" stripe',
    '"zero-dollar" authorization stripe wordpress',
    # мембершипы
    '"become a member" "add-payment-method" stripe',
    '"membership" "add-payment-method" "Credit Card (Stripe)"',
    # ниши (малые магазины, подписочные боксы)
    '"add-payment-method" stripe site:.co.nz',
    '"add-payment-method" stripe site:.co.za',
    '"add-payment-method" stripe site:.in',
    '"add-payment-method" stripe site:.fr',
    '"add-payment-method" stripe site:.jp',
    '"add-payment-method" stripe site:.ch',
    '"add-payment-method" stripe site:.dk',
    '"add-payment-method" stripe site:.no',
    '"add-payment-method" stripe site:.fi',
    '"add-payment-method" stripe site:.pt',
    '"add-payment-method" stripe site:.gr',
    '"add-payment-method" stripe site:.cz',
    '"add-payment-method" stripe site:.at',
    '"add-payment-method" stripe site:.be',
    # TLD-хвосты и платформы
    '"add-payment-method" stripe site:.io',
    '"add-payment-method" stripe site:.co',
    '"add-payment-method" stripe site:.me',
    '"add-payment-method" stripe site:.is',
    '"add-payment-method" stripe site:.sk',
    '"add-payment-method" stripe site:.hu',
    '"add-payment-method" stripe site:.lt',
    '"add-payment-method" stripe site:.lv',
    '"add-payment-method" stripe site:.ee',
    '"add-payment-method" stripe site:.mx',
    '"add-payment-method" stripe site:.ar',
    '"add-payment-method" stripe site:.cl',
    '"add-payment-method" stripe site:.ph',
    '"add-payment-method" stripe site:.id',
    '"add-payment-method" stripe site:.vn',
    '"add-payment-method" stripe site:.th',
    '"add-payment-method" stripe site:.my',
    '"add-payment-method" stripe site:.sg -site:woo.com',
    # UPE-маркеры в дикой природе
    '"wc_stripe_upe_params" "add-payment-method"',
    '"createAndConfirmSetupIntent" "my-account"',
    '"payment_method_preview" stripe "add-payment-method"',
]

ENGINES = {
    "duckduckgo": "https://html.duckduckgo.com/html/?q={q}",
    "bing": "https://www.bing.com/search?q={q}&count=30",
    "aol": "https://search.aol.com/aol/search?q={q}",
    "yahoo": "https://search.yahoo.com/search?p={q}",
}

RE_URL = re.compile(r'https?://([a-z0-9.-]+\.[a-z]{2,})', re.I)
SKIP = ("woocommerce.com", "woo.com", "wordpress.org", "stripe.com", "youtube.com",
        "facebook.com", "twitter.com", "x.com", "linkedin.com", "reddit.com",
        "github.com", "stackoverflow.com", "google.com", "microsoft.com", "apple.com",
        "amazon.com", "pinterest.com", "instagram.com", "tiktok.com", "aol.com",
        "bing.com", "duckduckgo.com", "yahoo.com", "wpcode.com", "wpbeginner.com",
        "docs.woocommerce.com", "developer.woocommerce.com")


def extract_domains(html: str) -> set:
    out = set()
    for m in RE_URL.finditer(html):
        dom = m.group(1).lower().lstrip("www.")
        if dom not in SKIP and not any(dom.endswith("." + s) for s in SKIP):
            if not re.match(r'^(wordpress|woo|stripe)[.-]', dom):
                out.add(dom)
    return out


async def search_engine(s, engine: str, q: str) -> set:
    url = ENGINES[engine].format(q=__import__("urllib.parse", fromlist=["quote"]).quote(q))
    try:
        r = await s.get(url, timeout=12)
        if r.status_code == 200:
            return extract_domains(r.text)
    except Exception:
        pass
    return set()


async def main():
    found: dict[str, int] = {}
    sem = asyncio.Semaphore(6)

    async def one(qi: int, q: str):
        async with sem:
            acc: set = set()
            for eng in ("duckduckgo", "bing", "yahoo", "aol"):
                async with AsyncSession(impersonate="chrome131", verify=False) as s:
                    acc |= await search_engine(s, eng, q)
                await asyncio.sleep(1.5)
            if acc:
                for d in acc:
                    found[d] = found.get(d, 0) + 1
            print(f"  [{qi+1}/{len(QUERIES)}] {q[:60]:60} -> +{len(acc)}")

    await asyncio.gather(*[one(i, q) for i, q in enumerate(QUERIES)])
    print(f"\n[+] unique: {len(found)}")
    # в db приоритетом 2 (woo-гейт-кандидаты)
    for d in found:
        domains_store.upsert(d, source="dork2", priority=2)
    st = domains_store.stats()
    print(f"[=] pool: {st}")


if __name__ == "__main__":
    asyncio.run(main())
