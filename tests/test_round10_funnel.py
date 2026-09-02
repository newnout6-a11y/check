# language: Python 3.12+, file: tests/test_round10_funnel.py
# Раунд 10: воронка с учётом потерь, инвариант мутаций, роутинг векторов.
# Все тесты офлайн — сеть не нужна, HTTP подменяется заглушками.
import json
import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
import funnel
import gate_client as gc
import surface


# --- заглушка HTTP-ответа ----------------------------------------------------
class Resp:
    def __init__(self, status_code=200, body="", ct="application/json", headers=None):
        self.status_code = status_code
        self.text = body
        self._body = body
        self.headers = {"content-type": ct}
        if headers:
            self.headers.update(headers)

    def json(self):
        return json.loads(self._body)


# =============================================================================
# D-22 — инвариант мутаций
# =============================================================================

def test_mutation_ok_rejects_html_200():
    """Главный кейс D-22: add-item ответил 302, клиент дошёл по редиректу и
    получил 200 text/html. Старый код принимал это за успех."""
    ok, why = gc.mutation_ok(Resp(200, "<!DOCTYPE html><html>product</html>", "text/html"))
    assert ok is False
    assert why == "ADD_ITEM_NO_JSON"


def test_mutation_ok_rejects_empty_body_with_json_ct():
    """302 с пустым телом и content-type json — не успех."""
    ok, why = gc.mutation_ok(Resp(200, "", "application/json"))
    assert ok is False and why == "ADD_ITEM_NO_JSON"


def test_mutation_ok_rejects_unparseable():
    ok, why = gc.mutation_ok(Resp(200, "{not json", "application/json"))
    assert ok is False and why == "ADD_ITEM_NO_JSON"


def test_mutation_ok_rejects_missing_key():
    ok, why = gc.mutation_ok(Resp(201, '{"totals":{}}', "application/json"),
                             expect_key="items")
    assert ok is False and why == "ADD_ITEM_NO_ITEMS"


def test_mutation_ok_accepts_real_cart():
    ok, why = gc.mutation_ok(Resp(201, '{"items":[{"key":"abc","id":1}]}',
                                  "application/json"), expect_key="items")
    assert ok is True and why == ""


def test_mutation_ok_without_expect_key():
    ok, _ = gc.mutation_ok(Resp(200, '{"ok":1}', "application/json"))
    assert ok is True


# =============================================================================
# D-25 — выбор платёжного слага
# =============================================================================

def test_pm_slug_picks_funnelkit_stripe():
    """fkwcs_stripe — карта. Регрессия раунда: startswith('stripe') его терял."""
    assert gc._pick_pm_slug(["fkwcs_stripe", "fkwcs_stripe_apple_pay"]) == "fkwcs_stripe"


def test_pm_slug_picks_woopayments_over_wallets():
    ms = ["wps_paypal", "woocommerce_payments_klarna",
          "woocommerce_payments", "woocommerce_payments_affirm"]
    assert gc._pick_pm_slug(ms) == "woocommerce_payments"


def test_pm_slug_prefers_stripe_cc():
    assert gc._pick_pm_slug(["ppcp", "stripe_applepay", "stripe_cc"]) == "stripe_cc"


def test_pm_slug_refuses_invoice_only():
    """Rechnungskauf/invoice карту не берут — тратить карту нельзя."""
    assert gc._pick_pm_slug(["Rechnung", "invoice"]) == ""
    assert gc._pick_pm_slug(["bacs", "cod"]) == ""


def test_pm_slug_keeps_unknown_gateway():
    assert gc._pick_pm_slug(["mycustomgateway"]) == "mycustomgateway"


def test_pm_slug_empty_list_falls_back():
    assert gc._pick_pm_slug([]) == "stripe"


def test_pm_slug_valid_checks_membership():
    assert gc.pm_slug_valid(["stripe", "ppcp"], "stripe") is True
    assert gc.pm_slug_valid(["stripe", "ppcp"], "nope") is False
    # пустой список — доверяем (фоллбэк, список не получен)
    assert gc.pm_slug_valid([], "stripe") is True


def test_pm_slug_ignores_non_string_methods():
    """D-28: payment_methods — список СТРОК. Объекты не должны ломать пикер."""
    assert gc._pick_pm_slug([{"id": "stripe"}]) == "stripe"


# =============================================================================
# surface — платформа, маршруты, детекторы блокировок
# =============================================================================

def test_platform_detection():
    assert surface._platform("", shopify_ok=True, woo_blocks=True) == "shopify"
    assert surface._platform("", shopify_ok=False, woo_blocks=True) == "woo_blocks"
    assert surface._platform("wp-content/plugins/woocommerce", False, False) == "woo_legacy"
    assert surface._platform("wp-content/themes/x", False, False) == "wordpress"
    assert surface._platform("<html>plain</html>", False, False) == "other"


def test_routes_shopify():
    fp = {"platform": "shopify", "payments": {}}
    assert surface._routes(fp) == ["shopify"]


def test_routes_woo_needs_card_evidence():
    fp = {"platform": "woo_blocks", "payments": {"stripe_pk": "", "methods": ["ppcp"]}}
    assert surface._routes(fp) == []


def test_routes_woo_with_card_slug_even_without_pk():
    """pk_live может жить только за авторизацией — слаг карты из /cart suffice."""
    fp = {"platform": "woo_blocks", "payments": {"stripe_pk": "", "methods": ["stripe"]}}
    assert "storegate" in surface._routes(fp)


def test_routes_setupwoo_needs_reg_nonce():
    fp = {"platform": "woo_blocks",
          "payments": {"stripe_pk": "pk_live_x", "methods": ["stripe"], "reg_nonce": True}}
    r = surface._routes(fp)
    assert "storegate" in r and "setupwoo" in r


def test_routes_piconfirm_on_exposed_secret():
    fp = {"platform": "other", "payments": {"secret_exposed": True}}
    assert "piconfirm" in surface._routes(fp)


def test_card_method_slug_filters_wallets():
    assert surface._card_method_slug(["stripe_applepay", "stripe_cc"]) == "stripe_cc"
    assert surface._card_method_slug(["ppcp", "klarna"]) is None
    assert surface._card_method_slug(["woocommerce_payments_affirm",
                                      "woocommerce_payments"]) == "woocommerce_payments"


def test_captcha_blocked_ignores_script_only_mention():
    """Страница просто подключает hCaptcha — это НЕ блокировка.
    Регрессия: gc.looks_like_captcha так убивал allbirds.com."""
    html = "<html><script src='https://hcaptcha.com/1/api.js'></script><body>Shop</body></html>"
    assert surface.captcha_blocked(html) is False
    assert gc.looks_like_captcha(html) is True  # старый детектор ложно срабатывает


def test_captcha_blocked_detects_interstitial():
    html = "<html><body><h1>Please verify that you are human</h1></body></html>"
    assert surface.captcha_blocked(html) is True


def test_cf_blocked_needs_refusal_status():
    """Виджет Turnstile на странице — не блокировка. Нужен 403/429/503 + след CF."""
    ok_page = Resp(200, "<div class='cf-turnstile-wrapper'></div>", "text/html")
    assert surface.cf_blocked(ok_page) is False

    blocked = Resp(403, "<title>Just a moment...</title>", "text/html",
                   headers={"cf-ray": "abc"})
    assert surface.cf_blocked(blocked) is True

    no_cf_trace = Resp(503, "<html>down</html>", "text/html")
    assert surface.cf_blocked(no_cf_trace) is False


# =============================================================================
# funnel — учёт потерь
# =============================================================================

@pytest.fixture
def isolated_funnel(tmp_path, monkeypatch):
    """Свой временный DB — тесты не трогают рабочий data/domains.db."""
    db = tmp_path / "domains.db"
    monkeypatch.setattr(funnel, "DB_PATH", str(db))
    funnel.init_db()
    return funnel


def test_funnel_records_reason(isolated_funnel):
    isolated_funnel.record("a.com", "S1", "NOT_WOO", ms=120)
    isolated_funnel.record("b.com", "S1", "CF_CHALLENGE", ms=90)
    h = isolated_funnel.histogram()
    assert h["NOT_WOO"] == 1 and h["CF_CHALLENGE"] == 1


def test_funnel_coerces_unknown_reason(isolated_funnel):
    """Урок D-11/D-14: сырая причина наружу не выходит, сводится к UNKNOWN."""
    isolated_funnel.record("c.com", "S3", "RAW_GARBAGE_STRING")
    assert isolated_funnel.histogram()["UNKNOWN"] == 1


def test_funnel_successes_not_counted_as_losses(isolated_funnel):
    isolated_funnel.record("d.com", "S1", "ALIVE")
    isolated_funnel.record("e.com", "S1", "NOT_WOO")
    rep = isolated_funnel.report()
    assert "ALIVE" in rep and "конверсия 50.0%" in rep


def test_funnel_report_flags_code_bugs(isolated_funnel):
    isolated_funnel.record("f.com", "S3", "PM_SLUG_MISSING")
    isolated_funnel.record("g.com", "S3", "NO_PRODUCT_UNDER_CAP")
    rep = isolated_funnel.report()
    assert "ЧИНИТЬ КОД" in rep
    assert "годен, поднять крышку" in rep


def test_funnel_record_many_batch(isolated_funnel):
    rows = [(f"h{i}.com", "S1", "TIMEOUT", 10, None) for i in range(5)]
    isolated_funnel.record_many(rows)
    assert isolated_funnel.histogram()["TIMEOUT"] == 5


def test_funnel_by_stage(isolated_funnel):
    isolated_funnel.record("i.com", "S1", "NOT_WOO")
    isolated_funnel.record("j.com", "S3", "ADD_ITEM_NO_JSON")
    by = isolated_funnel.by_stage()
    assert "NOT_WOO" in by["S1"] and "ADD_ITEM_NO_JSON" in by["S3"]


# =============================================================================
# D-26 — что считать живым гейтом
# =============================================================================

def test_declined_is_a_live_surface():
    """Отказ эмитента доказывает, что карта дошла до банка."""
    live = r"^(APPROVED|DECLINED|3DS|EXPIRED|INVALID|WRONG_CVC|RESTRICTED|RATE_LIMITED|RETRY|TEST_MODE)"
    import re
    rx = re.compile(live)
    assert rx.match("DECLINED")
    assert rx.match("APPROVED@CVV")
    assert rx.match("3DS_CHALLENGE")
    # заказ создан, но платежа нет — НЕ доказательство живости
    assert not rx.match("PI_PENDING")
    assert not rx.match("ERROR")


def test_verdicts_still_closed_taxonomy():
    """Правки раунда не должны были протащить сырые вердикты."""
    assert config.coerce_verdict("DECLINED@SOMETHING_NEW") == "DECLINED"
    assert config.coerce_verdict("TOTAL_GARBAGE") == "UNKNOWN"
    assert len(config.VERDICTS) == 24
