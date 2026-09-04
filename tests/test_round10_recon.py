# language: Python 3.12+, file: tests/test_round10_recon.py
# Раунд 10: полосы добычи (recon) и оркестратор воронки (scout).
# Все тесты офлайн — сеть не нужна.
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import funnel
import recon
import scout
import surface


# =============================================================================
# D-27 — санитайзер доменов: lstrip ел символы, а не префикс
# =============================================================================

def test_clean_strips_www_without_eating_chars():
    """Регрессия: 'wordpress.org'.lstrip('www.') -> 'ordpress.org'.
    lstrip работает по МНОЖЕСТВУ символов, а не по префиксу. Один этот баг
    портил каждый домен, начинающийся на w/o/d/'.'."""
    assert recon.clean("www.CrockettCoffee.com") == "crockettcoffee.com"
    assert recon.clean("wordpress.org") == ""          # в джанк-листе
    assert recon.clean("woocommerce.com") == ""        # в джанк-листе
    # домены на 'w'/'o' не должны терять первые буквы
    assert recon.clean("wonderland.com") == "wonderland.com"
    assert recon.clean("oakville.shop") == "oakville.shop"


def test_clean_rejects_junk_and_dev():
    for bad in ("shop.example.myshopify.com", "test.myshop.com", "staging.a.com",
                "xn--80ak6aa92e.com", "themeforest.net", "blog.somesite.com",
                "docs.woocommerce.com", "localhost", ""):
        assert recon.clean(bad) == "", bad


def test_clean_accepts_real_shops():
    for good in ("crockettcoffee.com", "valid-shop.co.uk", "nut.com", "a.io"):
        assert recon.clean(good) == good, good


def test_clean_rejects_too_long():
    assert recon.clean("a" * 70 + ".com") == ""


# =============================================================================
# Парсер выдачи DDG
# =============================================================================

DDG_HTML = '''
<a rel="nofollow" class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fwww.crockettcoffee.com%2F&amp;rut=abc">Crockett</a>
<a class="result__a" href="https://nut.com/">Nuts</a>
<a class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2FWWW.YarnStreet.com%2F&amp;rut=x">Yarn</a>
'''


def test_parse_ddg_unwraps_redirect_and_normalizes():
    got = recon.parse_ddg(DDG_HTML)
    assert "crockettcoffee.com" in got          # развёрнут uddg
    assert "nut.com" in got                     # прямая ссылка
    assert "yarnstreet.com" in got              # www + верхний регистр
    # никаких обкусанных lstrip-доменов
    assert not any(d.startswith(".") for d in got)


def test_parse_ddg_empty_on_no_results():
    assert recon.parse_ddg("") == []
    assert recon.parse_ddg("<html><body>nothing here</body></html>") == []


# =============================================================================
# D-30 — ротация TLS-отпечатков
# =============================================================================

def test_impersonation_pool_excludes_throttled_chrome():
    """Боем: chrome120/124/131 режутся Cloudflare429 на витринах.
    chrome116 и старше, safari, firefox133, edge, tor — проходят.
    firefox120 падает с исключением — тоже исключён."""
    for bad in ("chrome131", "chrome124", "chrome120", "firefox120"):
        assert bad not in surface.IMPERSONATIONS, f"{bad} в пуле, хотя режется"
    for good in ("chrome116", "safari17_0", "firefox133", "edge101", "tor145"):
        assert good in surface.IMPERSONATIONS, f"{good} отсутствует"


def test_search_imps_put_chrome_last():
    """Поисковик режет хром так же, как Cloudflare: safari/firefox/edge/tor
    получают выдачу, chrome116 уходит в 202. Хром — в конец очереди."""
    first_four = list(recon.SEARCH_IMPS[:4])
    assert all(("chrome" not in imp) for imp in first_four), first_four
    assert "chrome116" in recon.SEARCH_IMPS


def test_surface_throttle_codes():
    assert 429 in surface._THROTTLE_CODES
    assert 403 in surface._THROTTLE_CODES
    assert 200 not in surface._THROTTLE_CODES


# =============================================================================
# Вочнка: причина RATE_LIMITED обязана существовать
# =============================================================================

def test_rate_limited_in_reasons_and_retryable():
    """D-30-регрессия: RATE_LIMITED был в RETRYABLE, но не в REASONS —
    воронка писала его как UNKNOWN и помечала «чинить код»."""
    assert "RATE_LIMITED" in funnel.REASONS
    assert "RATE_LIMITED" in funnel.RETRYABLE
    assert "RATE_LIMITED" not in funnel.CODE_BUGS


def test_unknown_is_code_bug_only():
    """UNKNOWN остаётся в CODE_BUGS ровно для того, чтобы ловить новые
    неклассифицированные причины, а не как штатная корзина."""
    assert "UNKNOWN" in funnel.CODE_BUGS


# =============================================================================
# S2 — роутинг с учётом крышки цены
# =============================================================================

def _fp(plat="woo_blocks", **pay):
    return {"platform": plat, "payments": pay, "routes": [], "cheapest_cents": None}


def test_setupwoo_survives_over_cap_but_storegate_dies():
    """setupwoo — $0-авторизация, цена товара безразлична. storegate —
    реальное списание на сумму товара, значит крышка обязательна."""
    fp = _fp(reg_nonce=True, methods=["stripe"])
    fp["cheapest_cents"] = 9000          # $90 — выше крышки
    surface._routes(fp)
    assert "setupwoo" in fp["routes"]
    assert "storegate" not in fp["routes"]
    assert fp.get("over_cap") == 9000


def test_storegate_present_when_under_cap():
    fp = _fp(reg_nonce=True, methods=["stripe"])
    fp["cheapest_cents"] = 500
    surface._routes(fp)
    assert "storegate" in fp["routes"]
    assert "setupwoo" in fp["routes"]


def test_storegate_present_when_price_unknown():
    """Цену не узнали — не наказываем: крышка проверится на чекауте."""
    fp = _fp(methods=["stripe"])
    surface._routes(fp)
    assert "storegate" in fp["routes"]


def test_no_routes_without_card_method_and_pk():
    fp = _fp()                            # ни pk, ни card-слага
    surface._routes(fp)
    assert fp["routes"] == []


def test_cap_constant_is_shared():
    """Крышка одна на весь проект, а не три копии в разных модулях."""
    from store_gate import MAX_PRICE_CENTS
    assert surface.MAX_PRICE_CENTS == MAX_PRICE_CENTS


# =============================================================================
# Оркестратор: ранжирование и формат пула
# =============================================================================

def test_rank_puts_setupwoo_first():
    setup = {"domain": "a", "routes": ["setupwoo"],
             "payments": {"stripe_pk": "pk_live"}, "cheapest_cents": 9000}
    shopify = {"domain": "b", "routes": ["shopify"], "payments": {}, "cheapest_cents": 10}
    store = {"domain": "c", "routes": ["storegate"], "payments": {}, "cheapest_cents": 100}
    assert scout.rank(setup) < scout.rank(shopify) < scout.rank(store)


def test_rank_pushes_routeless_to_the_end():
    dead = {"domain": "z", "routes": [], "payments": {}}
    live = {"domain": "a", "routes": ["storegate"], "payments": {}}
    assert scout.rank(dead) > scout.rank(live)


def test_pool_entry_has_fields_the_gates_need():
    fp = {"domain": "x.com", "canonical_host": "www.x.com", "platform": "woo_blocks",
          "routes": ["setupwoo"], "payments": {"stripe_pk": "pk_live_1", "methods": ["stripe"],
                                               "reg_nonce": True, "reg_nonce_value": "abc123"},
          "cheapest_cents": 300, "geo": {"country": "US"}}
    e = scout.to_pool_entry(fp)
    for k in ("domain", "canonical_host", "platform", "routes", "stripe_pk",
              "reg_nonce", "reg_nonce_value", "cheapest_cents", "geo", "evidence"):
        assert k in e, k
    assert e["reg_nonce"] is True


def test_every_vector_has_a_weight():
    """Вектор без веса молча провалится в конец очереди — ловим явно."""
    known = {"setupwoo", "storegate", "shopify", "braintreenvbv", "piconfirm"}
    assert known <= set(scout.VECTOR_WEIGHT)


# =============================================================================
# Дорк-шаблоны: Woo отделён от Shopify структурой URL
# =============================================================================

def test_dork_templates_cover_both_stacks():
    hints = {h for _, h in recon.DORK_TEMPLATES}
    assert "woo" in hints
    assert any("product-category" in t for t, _ in recon.DORK_TEMPLATES)


def test_dork_templates_render_vertical():
    for tpl, _ in recon.DORK_TEMPLATES:
        q = tpl.format(v="coffee beans")
        assert "{" not in q and "}" not in q
        assert "coffee beans" in q


def test_config_pick_impersonate_stays_in_pool():
    """Ротация обязана выдавать только отпечатки из рабочего пула."""
    import config
    for _ in range(50):
        assert config.pick_impersonate() in config.IMPERSONATIONS


def test_config_pool_has_no_throttled_chrome():
    """chrome120/124/131 режутся; firefox120 нестабилен."""
    import config
    for bad in ("chrome131", "chrome124", "chrome120", "firefox120"):
        assert bad not in config.IMPERSONATIONS


def test_live_modules_do_not_hardcode_chrome131():
    """D-30 в живом пути: ни один боевой модуль не должен жечь один отпечаток."""
    import pathlib
    root = pathlib.Path(__file__).resolve().parent.parent
    for name in ("gate_client.py", "store_gate.py", "shopify_gate.py",
                 "setup_gate.py", "hit_gate.py", "confirm_gate.py",
                 "advanced_gate_scanner.py", "proxy_manager.py", "recon.py",
                 "bot/gates/braintreenvbv.py", "scratch/dork_harvester.py",
                 "scratch/deep_dorker.py"):
        p = root / name
        if not p.exists():
            continue
        src = p.read_text(encoding="utf-8")
        assert 'impersonate="chrome131"' not in src, (
            f"{name}: зашит chrome131, ротация мимо")


def test_verticals_are_low_ticket_goods():
    """Вертикаль — физический товар мелкого чека. Не услуги, не подписки
    на софт: у тех другой платёжный стек и другая сумма авторизации."""
    assert len(recon.VERTICALS) >= 10
    assert any("coffee" in v for v in recon.VERTICALS)
    assert not any(v in ("web hosting", "saas", "insurance") for v in recon.VERTICALS)


# --- D-34: reg_nonce под капчей — фантомный setupwoo-донор ------------------


def test_reg_captcha_marker_finds_captcha_in_form():
    """D-34: капча в форме регистрации детектится по маркеру."""
    html = ('<form method="post" id="customer_login">'
            '<input name="email"><input name="password">'
            '<div class="g-recaptcha" data-sitekey="6Le..."></div>'
            '<button name="register">Register</button></form>')
    marker = surface.reg_captcha_marker(html)
    assert marker, "капча в форме регистрации не детектится"
    assert "recaptcha" in marker


def test_reg_captcha_marker_ignores_clean_form():
    """Чистая форма без капчи -> None. Иначе ловим ложные срабатывания
    на каждый сайт, у которого hCaptcha просто подключён в футере."""
    html = ('<form method="post" id="customer_login">'
            '<input name="email"><input name="password">'
            '<button name="register">Register</button></form>')
    assert surface.reg_captcha_marker(html) is None


def test_setupwoo_route_requires_nonce_and_no_captcha():
    """D-34 в маршрутизации: nonce есть, но регистрация за капчей —
    маршрута setupwoo быть не должно. Проверено боем: 7 из 7 таких
    доменов дали ERROR, ни один зонд не дошёл до Stripe."""
    base_pay = {"stripe_pk": "pk_live_" + "x" * 20}

    clean = dict(base_pay, methods=["stripe"], reg_nonce=True)
    gated = dict(base_pay, methods=["stripe"], reg_nonce=True, reg_captcha="g-recaptcha")

    fp_clean = {"platform": "woo_blocks", "payments": clean, "cheapest_cents": 100}
    fp_gated = {"platform": "woo_blocks", "payments": gated, "cheapest_cents": 100}

    assert "setupwoo" in surface._routes(fp_clean)
    assert "setupwoo" not in surface._routes(fp_gated), (
        "донор под капчей снова попал в setupwoo — D-34 вернулся")


def test_setupwoo_captcha_does_not_kill_storegate():
    """Капча на регистрации закрывает только setupwoo. storegate —
    это чекаут без регистрации, он жив и под капчей."""
    pay = {"stripe_pk": "pk_live_" + "x" * 20, "methods": ["stripe"],
           "reg_nonce": True, "reg_captcha": "recaptcha"}
    fp = {"platform": "woo_blocks", "payments": pay, "cheapest_cents": 100}
    routes = surface._routes(fp)
    assert "storegate" in routes
    assert "setupwoo" not in routes

