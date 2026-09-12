# language: Python 3.12+, file: tests/test_section3_modernization.py
"""Раздел 3 модернизации (аудит 2026-09): залитые в код правки должны быть закреплены.

Проверяется то, что можно проверить офлайн:
  * каталог Shopify листается до config.SHOPIFY_CATALOG_PAGES (G-28) и не тратит лишние запросы;
  * cf-turnstile-wrapper больше не блокирует живой чекаут (H-10 / B-01);
  * ветка чекаута телеметрируется: checkout_one_graphql / classic_form, LEGACY-предупреждение,
    ALERT на выведенный внутренний маршрут (H-07 / G-06 / G-18);
  * checkout_url берётся из /cart.js, а не собирается жёстко;
  * 3DS Method notification URL указывает на живой hosted-эндпоинт Stripe, а не на 404 (E-08);
  * setupwoo явно помечает LEGACY-ветку эпохи Sources.
"""
from __future__ import annotations

import asyncio
import config
import frictionless_engine as fe
import shopify_gate as sg


class FakeResp:
    def __init__(self, status_code=200, json_data=None, text="", url="https://shop.example/checkout"):
        self.status_code = status_code
        self._json = json_data
        self.text = text
        self.url = url
        self.headers = {}

    def json(self):
        return self._json

    def __bool__(self):
        return True


class FakeSession:
    """Сессия-заглушка: маршрутизирует по URL и пишет журнал вызовов."""

    def __init__(self, routes=None):
        self.routes = routes or {}
        self.calls = []

    def _route(self, method: str, url: str):
        for key, value in self.routes.items():
            if key in url:
                return value(url) if callable(value) else value
        return FakeResp(status_code=404, json_data={}, text="")

    def _record(self, method, url, kwargs):
        self.calls.append({
            "method": method,
            "url": url,
            "json": kwargs.get("json"),
            "data": kwargs.get("data"),
        })

    async def get(self, url, **kwargs):
        self._record("GET", url, kwargs)
        return self._route("GET", url)

    async def post(self, url, **kwargs):
        self._record("POST", url, kwargs)
        return self._route("POST", url)


def _variant(vid: int, price: float, available: bool = True) -> dict:
    return {"id": vid, "title": "v", "price": f"{price:.2f}", "available": available,
            "requires_shipping": False}


def _product(pid: int, variants: list) -> dict:
    return {"id": pid, "title": f"p{pid}", "variants": variants}


def run(coro):
    return asyncio.run(coro)


# --- каталог: пагинация (G-28) -------------------------------------------------

def test_catalog_pagination_reaches_second_page():
    page1 = [_product(i, [_variant(i, 15.00)]) for i in range(250)]
    page2 = [_product(10_000, [_variant(10_001, 3.50)])]

    def route(url):
        page = url.rsplit("page=", 1)[-1]
        return FakeResp(json_data={"products": page1 if page == "1" else page2})

    s = FakeSession({"products.json": route})
    best = run(sg.get_shopify_cheapest_product(s, "https://shop.example", max_price_cents=2000))
    pages = [c["url"] for c in s.calls]
    assert pages == ["https://shop.example/products.json?limit=250&page=1",
                     "https://shop.example/products.json?limit=250&page=2"], pages
    assert best is not None
    assert best["variant_id"] == 10_001 and best["price_cents"] == 350


def test_catalog_stops_on_partial_page():
    page1 = [_product(1, [_variant(2, 4.00)])]
    s = FakeSession({"products.json": FakeResp(json_data={"products": page1})})
    best = run(sg.get_shopify_cheapest_product(s, "https://shop.example", max_price_cents=2000))
    assert best is not None and best["price_cents"] == 400
    assert len(s.calls) == 1, "неполная страница обязана прекращать обход"


def test_catalog_respects_page_cap(monkeypatch):
    full_page = [_product(i, [_variant(i, 99.00)]) for i in range(250)]
    s = FakeSession({"products.json": FakeResp(json_data={"products": full_page})})
    run(sg.get_shopify_cheapest_product(s, "https://shop.example", max_price_cents=2000))
    assert len(s.calls) == int(config.SHOPIFY_CATALOG_PAGES) >= 2


# --- классификатор: ложный маркер Turnstile (H-10) ----------------------------

def test_submit_success_wrapper_with_failed_receipt_is_declined():
    """SubmitSuccess — контейнер: под ним приходит FailedReceipt, успех объявлять нельзя."""
    payload = {"data": {"submitForCompletion": {"__typename": "SubmitSuccess",
               "receipt": {"__typename": "FailedReceipt", "id": "r1"}}}}
    verdict, detail = sg.classify_shopify_verdict(payload, context_str=str(payload))
    assert verdict == "DECLINED", (verdict, detail)


def test_processed_receipt_is_still_paid():
    payload = {"data": {"submitForCompletion": {"__typename": "SubmitSuccess",
               "receipt": {"__typename": "ProcessedReceipt", "orderStatusPageUrl": "/orders/1"}}}}
    verdict, _ = sg.classify_shopify_verdict(payload, context_str=str(payload))
    assert verdict == "APPROVED@PAID", verdict


def test_turnstile_wrapper_container_is_not_a_challenge():
    html = ('<div class="cf-turnstile-wrapper"><div id="cf-turnstile"></div></div>'
            '{"errors":[{"message":"Card declined","code":"card_declined"}]}')
    verdict, _ = sg.classify_shopify_verdict(html)
    assert verdict == "DECLINED", verdict


def test_real_challenge_still_classified_as_error():
    verdict, _ = sg.classify_shopify_verdict("<h1>Verify you are human</h1>")
    assert verdict == "ERROR"
    verdict2, _ = sg.classify_shopify_verdict("<title>Just a moment...</title>")
    assert verdict2 == "ERROR"


# --- ветки чекаута: телеметрия миграции (H-07 / G-18) ------------------------

_CHECKOUT_ONE_HTML = ('<meta name="serialized-sessionToken" content="sess-token-1">'
                      '<meta name="serialized-shopifyY" content="y1">'
                      '<meta name="serialized-shopifyS" content="s1">')


def _patch_common(monkeypatch):
    async def fake_tokenize(s, card):
        return "vault-1"

    monkeypatch.setattr(sg, "tokenize_shopify_card", fake_tokenize)
    monkeypatch.setattr(sg, "get_cached_variant", lambda root: None)
    monkeypatch.setattr(sg, "set_cached_variant", lambda root, product: None)


def test_flow_a_reports_checkout_one_graphql(monkeypatch, capsys):
    _patch_common(monkeypatch)
    routes = {
        "products.json": FakeResp(json_data={"products": [_product(1, [_variant(2, 5.00)])]}),
        "cart/add.js": FakeResp(status_code=200, json_data={"items": []}),
        "cart.js": FakeResp(json_data={"checkout_url": "/checkouts/abc"}),
        "checkouts/unstable/graphql": FakeResp(json_data={"data": {"submitForCompletion": {
            "__typename": "SubmitSuccess", "receipt": {"__typename": "FailedReceipt"}}}}),
    }
    s = FakeSession(routes)
    s.routes["/checkouts/abc"] = FakeResp(text=_CHECKOUT_ONE_HTML, url="https://shop.example/checkouts/abc")
    res = run(sg.shopify_confirm(s, "https://shop.example", "4111111111111111|12|30|123"))
    assert res["status"] == "DECLINED", res
    assert res["flow"] == "checkout_one_graphql"
    out = capsys.readouterr().out
    assert "LEGACY" not in out


def test_cart_js_checkout_url_is_used(monkeypatch):
    _patch_common(monkeypatch)
    routes = {
        "products.json": FakeResp(json_data={"products": [_product(1, [_variant(2, 5.00)])]}),
        "cart/add.js": FakeResp(status_code=200, json_data={"items": []}),
        "cart.js": FakeResp(json_data={"checkout_url": "/checkouts/from-cart-js"}),
        "checkouts/unstable/graphql": FakeResp(json_data={"data": {"submitForCompletion": {
            "__typename": "SubmitSuccess", "receipt": {"__typename": "FailedReceipt"}}}}),
    }
    s = FakeSession(routes)
    s.routes["/checkouts/from-cart-js"] = FakeResp(text=_CHECKOUT_ONE_HTML)
    run(sg.shopify_confirm(s, "https://shop.example", "4111111111111111|12|30|123"))
    got = [c["url"] for c in s.calls if "/checkouts/" in c["url"]]
    assert "https://shop.example/checkouts/from-cart-js" in got, got
    assert "https://shop.example/checkout" not in got


def test_flow_b_warns_legacy(monkeypatch, capsys):
    _patch_common(monkeypatch)
    legacy_html = ('<input name="authenticity_token" value="tok123">'
                   '<input name="checkout[payment_gateway]" value="123456">')
    routes = {
        "products.json": FakeResp(json_data={"products": [_product(1, [_variant(2, 5.00)])]}),
        "cart/add.js": FakeResp(status_code=200, json_data={"items": []}),
        "cart.js": FakeResp(json_data={"checkout_url": "/checkouts/legacy"}),
        "checkouts/unstable/graphql": FakeResp(status_code=403, text="forbidden"),
    }
    s = FakeSession(routes)
    s.routes["/checkouts/legacy"] = FakeResp(text=legacy_html)
    res = run(sg.shopify_confirm(s, "https://shop.example", "4111111111111111|12|30|123"))
    assert res["flow"] == "classic_form", res
    assert "LEGACY" in capsys.readouterr().out


def test_graphql_404_raises_alert(monkeypatch, capsys):
    _patch_common(monkeypatch)
    routes = {
        "products.json": FakeResp(json_data={"products": [_product(1, [_variant(2, 5.00)])]}),
        "cart/add.js": FakeResp(status_code=200, json_data={"items": []}),
        "cart.js": FakeResp(json_data={"checkout_url": "/checkouts/x"}),
        "checkouts/unstable/graphql": FakeResp(status_code=404, text="not found"),
    }
    s = FakeSession(routes)
    s.routes["/checkouts/x"] = FakeResp(text=_CHECKOUT_ONE_HTML)
    run(sg.shopify_confirm(s, "https://shop.example", "4111111111111111|12|30|123"))
    out = capsys.readouterr().out
    assert "unstable/graphql" in out and "404" in out, out


# --- 3DS Method notification URL (E-08) --------------------------------------

def test_three_ds_notification_url_is_live_hosted_endpoint():
    url = config.THREE_DS_METHOD_NOTIFICATION_URL
    assert url == "https://hooks.stripe.com/3d_secure_2/hosted/complete", url
    assert "3ds2/fingerprint/complete" not in url, "этот маршрут отдаёт 404"


def test_frictionless_uses_config_notification_url():
    telemetry = fe.build_browser_telemetry(country_code="US", method_executed=False)
    assert telemetry["threeDSCompInd"] == "U"
    assert telemetry["fingerprintAttempted"] is False
    telemetry_ok = fe.build_browser_telemetry(country_code="US", method_executed=True)
    assert telemetry_ok["threeDSCompInd"] == "Y"
    assert telemetry_ok["fingerprintAttempted"] is True


# --- setupwoo: LEGACY-ветка эпохи Sources ------------------------------------

def test_setup_gate_legacy_branch_is_marked():
    import inspect
    import setup_gate
    src = inspect.getsource(setup_gate)
    assert "LEGACY-хук эпохи Sources" in src
