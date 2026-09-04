# language: Python 3.12+, file: recon.py, target: Windows 11, deps: curl_cffi
# Раунд 10 (S0): полосы добычи → кандидаты → квалификация → domains.db.
#
# Отличие от v1: полоса отдаёт не «список доменов», а (домен, доказательство).
# Доказательство определяет приоритет — точные полосы идут первыми, дешёвый
# мусор (форумы wordpress.org) не забивает очередь впереди них.
import argparse
import asyncio
import glob
import html
import os
import random
import re
import sys
from collections import Counter
from urllib.parse import parse_qs, urlparse

from curl_cffi.requests import AsyncSession

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import config
import domains_store
import funnel
import surface

DOM_RE = re.compile(r'https?://([a-zA-Z0-9][-a-zA-Z0-9.]*\.[a-zA-Z]{2,})')
PLAIN_DOM_RE = re.compile(r'\b([a-zA-Z0-9][-a-zA-Z0-9]*\.[a-zA-Z]{2,24}\.[a-zA-Z]{2,6})\b')

# Явно не доноры: платёжная инфраструктура, соцсети, хостинги скриншотов
JUNK = {
    "checkout.stripe.com", "buy.stripe.com", "js.stripe.com", "api.stripe.com",
    "m.stripe.com", "stripe.com", "paypal.com", "t.me", "telegram.me",
    "eu.adyen.link", "adyen.com", "github.com", "google.com", "gstatic.com",
    "googleapis.com", "cloudflare.com", "wordpress.org", "wordpress.com",
    "youtube.com", "youtu.be", "netflix.com", "spotify.com", "canva.com",
    "microsoft.com", "apple.com", "amazon.com", "aliexpress.com", "ebay.com",
    "drive.google.com", "docs.google.com", "chatgpt.com", "openai.com",
    "vercel.app", "netlify.app", "herokuapp.com", "lichess.org", "jsfiddle.net",
    "serviceactivation.google.com", "scalacube.com", "chatgpt.com", "whop.com",
    "gravatar.com", "w.org", "s.w.org", "ps.w.org", "schema.org", "w3.org",
}
DEV_MARKS = ("test.", "staging.", "stage.", "dev.", "demo.", "sandbox.",
             "localhost", "127.0.0.1", "example.", "myshopify.com")

# Что не донор ни при каких условиях: темы, плагины, агентства, маркетплейсы,
# доки, соцсети. Общий для ВСЕХ полос — иначе мусор из corpus лезет в обход
# дорк-фильтра. Поддомены blog./docs./support — не магазин.
BAD_DOMAINS = re.compile(
    r"(theme|template|plugin|elementor|astra|woodmart|themeforest|envato|monster|"
    r"market|leads?|studio|design|tutorial|docs?|reddit|youtube|github|etsy|amazon|"
    r"instacart|wordpress\.(org|com)|woocommerce\.com|blog\.|hosting|wpbeginner|"
    r"kinsta|siteground|wpengine|freemius|duckduckgo|google|facebook|instagram|"
    r"pinterest|ebay|walmart|target\.com|alibaba|shopify\.com)", re.I)
BAD_SUBDOMAIN = re.compile(r"^(blog|docs?|support|help|dev|staging)\.", re.I)


def clean(dom: str) -> str:
    """Санитайзер, общий для всех полос. '' = не кандидат."""
    d = (dom or "").strip().lower().rstrip("/.")
    if d.startswith("www."):
        d = d[4:]                       # срез, НЕ lstrip: тот ест символы, а
                                        # не префикс ('woocommerce' -> 'ocommerce')
    if not d or "." not in d:
        return ""
    if d in JUNK or any(d.endswith("." + j) for j in JUNK):
        return ""
    if any(k in d for k in DEV_MARKS):
        return ""
    if d.startswith("xn--") or len(d) > 63:
        return ""
    if BAD_DOMAINS.search(d) or BAD_SUBDOMAIN.match(d):
        return ""
    return d


# --- полосы ------------------------------------------------------------------

def lane_corpus(corpus_dir="research/chat-corpus", min_hits=2) -> list[tuple[str, str]]:
    """L9: майнинг экспортов Telegram. Домен, названный людьми в чатах — уже
    кем-то проверен. Низкая точность (в основном платёжная инфраструктура),
    но бесплатно и офлайн."""
    hits: Counter = Counter()
    for f in glob.glob(os.path.join(corpus_dir, "*.txt")):
        try:
            t = open(f, encoding="utf-8", errors="replace").read()
        except Exception:
            continue
        hits.update(DOM_RE.findall(t))
        hits.update(PLAIN_DOM_RE.findall(t))
    out = []
    for d, n in hits.most_common():
        c = clean(d)
        if c and n >= min_hits:
            out.append((c, f"corpus:{n}"))
    return out


async def lane_crtsh(pattern: str, timeout: int = 40) -> list[tuple[str, str]]:
    """L7: certificate transparency. Ищем по маске сертификата.
    crt.sh живёт на одном перегруженном nginx и регулярно отдаёт 502 —
    полоса обязана деградировать молча, а не валить весь прогон."""
    url = f"https://crt.sh/?q={pattern}&output=json"
    try:
        async with AsyncSession(impersonate=config.pick_impersonate(),
                                verify=False) as s:
            r = await s.get(url, timeout=timeout)
        if r.status_code != 200 or not (r.text or "").strip().startswith("["):
            print(f"  [crt.sh] недоступен (HTTP {r.status_code}) — полоса пропущена")
            return []
        names = set()
        for row in r.json():
            for n in (row.get("name_value") or "").split("\n"):
                c = clean(n)
                if c:
                    names.add(c)
        return [(n, "crt.sh") for n in sorted(names)]
    except Exception as e:
        print(f"  [crt.sh] недоступен ({type(e).__name__}) — полоса пропущена")
        return []


# --- L1: поисковые дорки (основная полоса) -----------------------------------
#
# Боем, 2026-08-31. Два вывода, оба переворачивают прежнюю схему:
#
# 1) Дорки по ПЛАТФОРМЕ — мусор. «woocommerce coffee shop» даёт темы, плагины,
#    агентства и wordpress.org. Дорки по ВЕРТИКАЛИ («buy whole bean coffee
#    online») дают 100% настоящих магазинов: люди ищут товар, поисковик
#    отвечает магазинами.
#
# 2) Структура URL разделяет платформы. /product-category/ — это Woo
#    (на 18 кандидатах: 5 Woo против 6 Shopify), /products/ и /collections/ —
#    Shopify. Значит Woo-доноров надо искать Woo-дорком, а не общим.
#
# Итого: вертикаль задаёт «магазин вообще», URL-паттерн — «какой именно стек».

VERTICALS = (
    "coffee beans", "specialty tea", "handmade soap", "raw honey",
    "whole bean coffee", "small batch candles", "artisan chocolate",
    "loose leaf tea", "natural skincare", "beef jerky", "hot sauce",
    "spice blends", "dried herbs", "vinyl records", "plants online",
    "handmade jewelry", "leather goods", "wool yarn", "greeting cards",
    "incense sticks", "nuts and dried fruit", "olive oil", "maple syrup",
    # Цифровые товары и билеты (без физической доставки, высокий checkout pass rate)
    "ebooks download", "digital printables", "online workshop ticket",
    "webinar access", "sheet music pdf", "sewing patterns pdf",
)

# (шаблон дорка, подсказка платформы). {v} — вертикаль.
DORK_TEMPLATES = (
    ("inurl:/product-category/ {v}", "woo"),      # Woo-структура каталога
    ("inurl:/product/ {v} buy online", "woo"),
    ("{v} buy online shop", "any"),               # широкая, hohe recall
    ("{v} small batch online store", "any"),
)

# Специализированные шаблоны для SetupIntent ($0) и донатов (piconfirm)
SETUP_DORK_TEMPLATES = (
    ('inurl:/my-account/ "{v}" -site:wordpress.org', "setupwoo"),
    ('{v} "my-account" "Register" "Lost your password"', "setupwoo"),
)

DONATE_DORK_TEMPLATES = (
    ('inurl:/donate/ "stripe" {v}', "piconfirm"),
    ('inurl:/give/ "card" {v}', "piconfirm"),
)
def _norm_host(h: str) -> str:
    h = (h or "").lower().strip()
    return h[4:] if h.startswith("www.") else h   # НЕ lstrip: тот ест символы


def parse_ddg(text: str) -> list[str]:
    """Результаты html.duckduckgo.com. Ссылка завёрнута в /l/?uddg=<enc>."""
    out = []
    for m in re.finditer(r'class="result__a"[^>]*href="([^"]+)"', text or ""):
        href = html.unescape(m.group(1))
        if "uddg=" in href:
            u = (parse_qs(urlparse(href).query).get("uddg") or [None])[0]
        else:
            u = href if href.startswith("http") else "https:" + href
        h = _norm_host(urlparse(u or "").hostname)
        if h and "." in h:
            out.append(h)
    return out


# Отпечатки для ПОИСКОВИКА. Хром — в конец: боем (2026-08-31) DDG отдаёт 202
# (пустая выдача при 200-м статусе) именно на chrome-отпечатки, а safari/firefox/
# edge/tor получают полные 10-12 результатов. Тот же механизм, что D-30 у
# Cloudflare: хром — самый заезженный след сканера, по нему и режут.
SEARCH_IMPS = ("safari17_0", "firefox133", "edge101", "tor145", "safari18_0",
               "chrome99", "safari15_5", "chrome110", "chrome107", "chrome100",
               "safari17_2_ios", "chrome116")


async def _ddg_query(s, q: str, timeout: int = 25) -> list[str]:
    try:
        r = await s.get("https://html.duckduckgo.com/html/?q=" + q.replace(" ", "+"),
                        timeout=timeout)
        if r.status_code != 200:
            return []
        return parse_ddg(r.text or "")
    except Exception:                                   # noqa: BLE001
        return []


async def _ddg_query_rotating(q: str, timeout: int = 25,
                              attempts: int = 3) -> tuple[list[str], str]:
    """Один запрос с перебором отпечатков. Отдаёт (домены, отпечаток).

    Бан DDG по отпечатку, а не по IP: на chrome116 — 202 и ноль строк, на
    safari/firefox/edge/tor — полная выдача. Значимое следствие: retries с той
    же личностью бесполезны, менять надо именно TLS-след."""
    for i in range(attempts):
        imp = SEARCH_IMPS[i % len(SEARCH_IMPS)]
        try:
            async with AsyncSession(impersonate=imp, verify=False) as s:
                doms = await _ddg_query(s, q, timeout=timeout)
            if doms:
                return doms, imp
        except Exception:                               # noqa: BLE001
            continue
        await asyncio.sleep(1.5 * (i + 1))
    return [], ""


async def lane_dork(verticals=(), templates=DORK_TEMPLATES,
                    min_delay: float = 6.0, max_queries: int = 40,
                    verbose: bool = True) -> list[tuple[str, str]]:
    """L1: поисковые дорки. Отдаёт (домен, 'dork:<платформа>:<вертикаль>').

    DDG режет частые запросы: на 3-4-м подряд выдача пустая (было замерено —
    0 результатов при 200). Поэтому пауза между запросами с джиттером и
    отступление при пустом ответе, а не долбёж до бана."""
    verts = tuple(verticals) if verticals else VERTICALS
    out: dict[str, str] = {}
    queries: list[tuple[str, str, str]] = []
    for tpl, hint in templates:
        for v in verts:
            queries.append((tpl.format(v=v), hint, v))
    random.shuffle(queries)                  # не долбим одну вертикаль подряд
    queries = queries[:max_queries]

    empty_streak = 0
    imp_stat: Counter = Counter()
    for i, (q, hint, v) in enumerate(queries, 1):
        # сессия на запрос: отпечаток меняется, иначе словим бан на 3-4-м
        doms, imp = await _ddg_query_rotating(q)
        keep = [d for d in doms
                if not BAD_DOMAINS.search(d) and not BAD_SUBDOMAIN.match(d)]
        if imp:
            imp_stat[imp] += 1
        if verbose:
            print(f"  [{i:3}/{len(queries)}] {len(doms):2}→{len(keep):2} "
                  f"{imp:14} {q[:46]}")
        for d in keep:
            # первый источник побеждает — более точный шаблон важнее счёта
            out.setdefault(d, f"dork:{hint}:{v}")
        if not doms:
            empty_streak += 1
            if empty_streak >= 4:
                if verbose:
                    print("  [!] все отпечатки в бане — стоп")
                break
            await asyncio.sleep(min_delay * (2 ** empty_streak))
        else:
            empty_streak = 0
            await asyncio.sleep(min_delay + random.uniform(0, 3))
    if verbose and imp_stat:
        print(f"  отпечатки: {dict(imp_stat)}")
    return [(d, ev) for d, ev in out.items()]


def lane_file(path: str) -> list[tuple[str, str]]:
    out = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            c = clean(line.split("#")[0])
            if c:
                out.append((c, "file"))
    return out


def lane_db_pending() -> list[tuple[str, str]]:
    """Что уже лежит в очереди и ещё не сканилось."""
    domains_store.init_db()
    return [(r["domain"], "db") for r in domains_store.due_for_scan(hours=config.RESCAN_INTERVAL_HOURS)]


# --- оркестрация -------------------------------------------------------------

async def run(candidates: list[tuple[str, str]], concurrency: int = 20,
              verify: bool = True, proxy: str | None = None) -> list[dict]:
    """Кандидаты → квалификация (S1/S2) → только те, у кого есть маршруты."""
    # дедуп по домену, доказательства схлопываются
    merged: dict[str, set] = {}
    for d, ev in candidates:
        merged.setdefault(d, set()).add(ev)
    doms = list(merged)
    print(f"[*] кандидатов после дедупа и санитайза: {len(doms)}")

    if not verify:
        return [{"domain": d, "evidence": sorted(merged[d])} for d in doms]

    fps = await surface.sweep(doms, concurrency=concurrency, explicit_proxy=proxy)
    for fp in fps:
        fp["evidence"] = sorted(merged.get(fp["domain"], set()))
    return fps


def write_back(fps: list[dict]) -> int:
    """Квалифицированные — в domains.db приоритетом 1. Остальные — приоритет 3,
    но с точной причиной в funnel (не в мусорную корзину NO_REG)."""
    domains_store.init_db()
    good = [fp["domain"] for fp in fps if fp.get("alive") and fp.get("routes")]
    dead = [fp["domain"] for fp in fps if not (fp.get("alive") and fp.get("routes"))]
    n = domains_store.upsert(good, source="recon", priority=1)
    if dead:
        domains_store.upsert(dead, source="recon", priority=3)
    return n


async def main():
    ap = argparse.ArgumentParser(description="S0: полосы добычи кандидатов")
    ap.add_argument("--dork", action="store_true",
                    help="поисковые дорки (основная полоса)")
    ap.add_argument("--max-queries", type=int, default=12,
                    help="сколько дорк-запросов сделать (DDG режет частые)")
    ap.add_argument("--delay", type=float, default=6.0,
                    help="пауза между дорк-запросами, сек")
    ap.add_argument("--corpus", action="store_true", help="майнинг research/chat-corpus")
    ap.add_argument("--crtsh", default=None, metavar="PATTERN",
                    help='маска сертификата, напр. "%%25.shop"')
    ap.add_argument("--file", default=None, help="файл со списком доменов")
    ap.add_argument("--db", action="store_true", help="взять непросканированное из domains.db")
    ap.add_argument("--no-verify", action="store_true", help="только собрать, без обхода сайтов")
    ap.add_argument("--concurrency", type=int, default=20)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--proxy", default=None)
    a = ap.parse_args()

    cands: list[tuple[str, str]] = []
    if a.dork:
        got = await lane_dork(min_delay=a.delay, max_queries=a.max_queries)
        print(f"[+] полоса dork    : {len(got)}")
        cands += got
    if a.corpus:
        got = lane_corpus()
        print(f"[+] полоса corpus  : {len(got)}")
        cands += got
    if a.crtsh:
        got = await lane_crtsh(a.crtsh)
        print(f"[+] полоса crt.sh  : {len(got)}")
        cands += got
    if a.file:
        got = lane_file(a.file)
        print(f"[+] полоса file    : {len(got)}")
        cands += got
    if a.db:
        got = lane_db_pending()
        print(f"[+] полоса db      : {len(got)}")
        cands += got
    if not cands:
        print("[!] полосы не заданы — нечего делать")
        return

    if a.limit:
        cands = cands[:a.limit]

    funnel.init_db()
    fps = await run(cands, concurrency=a.concurrency,
                    verify=not a.no_verify, proxy=a.proxy)

    if a.no_verify:
        for fp in fps[:40]:
            print("  ", fp["domain"], fp["evidence"])
        print(f"[=] собрано {len(fps)} без проверки")
        return

    qualified = [fp for fp in fps if fp.get("alive") and fp.get("routes")]
    print()
    print("=" * 88)
    print(f"[🔥] КВАЛИФИЦИРОВАНО: {len(qualified)} из {len(fps)}")
    print("=" * 88)
    for fp in qualified:
        print(f"  {fp['domain']:36} {fp['platform']:12} {','.join(fp['routes']):24} "
              f"{','.join(fp['evidence'])[:18]}")
    print()
    by_route = Counter(r for fp in qualified for r in fp["routes"])
    print("  маршруты:", dict(by_route))
    print("  платформы:", dict(Counter(fp["platform"] for fp in fps if fp["alive"])))

    n = write_back(fps)
    print(f"\n[+] записано в domains.db: {n} новых приоритетных")
    print()
    print(funnel.report())


if __name__ == "__main__":
    asyncio.run(main())
