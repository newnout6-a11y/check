# language: Python 3.12+, file: tests/test_section4_structural.py, target: Windows 11
"""Раздел 4 аудита (структурное): слой защиты врезан в прод-граф, мёртвые пулы сняты с продажи.

Проверяется контракт, а не наличие строк:
  * gate_client.classify_surface_challenge различает виджет и блок-страницу, видит PoW
    и маршрут обхода (закрывает §7 п.4 «врезать или признать инструментами»);
  * clear_surface_challenge честно сообщает результат по каждому маршруту;
  * мёртвый пул /hit удалён, а CLI больше не подставляет его молча (G-02 / H-16);
  * /pi и /vbv с пустыми пулами не продаются: нет кнопки, нет списания, нет строки в меню
    (G-03 / G-04 / H-17).
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import pathlib
import sys

import pytest

import captcha_pow as cp
import config
import gate_client as gc
import hit_gate as hg
from bot import keyboards
from bot.gates import availability as ga

ROOT = pathlib.Path(__file__).resolve().parent.parent


def run(coro):
    return asyncio.run(coro)


# --- классификатор поверхности -------------------------------------------------

def test_legit_turnstile_widget_is_not_a_block():
    html = ('<html><body><div class="cf-turnstile-wrapper">'
            '<div class="cf-turnstile" data-sitekey="0x4AAAAAAA"></div>'
            '</div><form class="checkout">Card number</form></body></html>')
    prof = gc.classify_surface_challenge(200, html)
    assert prof["block"] is False, prof


_CF_BLOCK_HTML = (
    "<html><head><title>Just a moment...</title></head><body>"
    '<script src="/cdn-cgi/challenge-platform/scripts/jsd/main.js"></script>'
    "</body></html>"
)


def test_cloudflare_interstitial_is_a_block_with_route():
    prof = gc.classify_surface_challenge(503, _CF_BLOCK_HTML, headers={"server": "cloudflare"})
    assert prof["block"] is True, prof
    assert prof["waf"] == "cloudflare", prof
    assert prof["bypass_strategy"] == "turnstile_sidecar_cdp", prof


def test_altcha_page_is_classified_as_solvable_pow():
    html = ('<form><altcha-widget challengeurl="/altcha/challenge"></altcha-widget></form>'
            '<script src="/dist/altcha.min.js"></script>')
    prof = gc.classify_surface_challenge(200, html)
    assert prof["pow"].get("type") == "altcha", prof
    assert prof["solvable"] is True
    assert prof["bypass_strategy"] == "captcha_pow_cpu", prof


def test_friendly_v2_is_reported_but_not_claimed_solvable():
    html = '<script src="https://cdn.friendlycaptcha.com/sdk"></script><div class="frc-captcha"></div>'
    prof = gc.classify_surface_challenge(200, html)
    assert prof["pow"].get("type") == "friendly_captcha_v2", prof
    assert prof["solvable"] is False


# --- снятие защиты -------------------------------------------------------------

class _Resp:
    def __init__(self, json_data=None, text=""):
        self.status_code = 200
        self._json = json_data or {}
        self.text = text or "{}"
        self.headers = {}
        self.url = "https://shop.example/checkout"

    def json(self):
        return self._json


class _Session:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    async def get(self, url, **kwargs):
        self.calls.append(url)
        return self.responses.pop(0) if self.responses else _Resp(text="")

    async def post(self, url, **kwargs):
        self.calls.append(url)
        return self.responses.pop(0) if self.responses else _Resp()


def _altcha_v3_challenge(nonce: str = "abc", salt: str = "salt-1", cost: int = 30, answer: int = 7):
    """Настоящий v3-челлендж: KDF(nonce+counter) — эталон считаем тем же примитивом."""
    key = hashlib.pbkdf2_hmac("sha256", f"{nonce}{answer}".encode(), salt.encode(), cost, dklen=32)
    return {
        "algorithm": "PBKDF2/SHA-256",
        "challenge": base64.b64encode(key).decode().rstrip("="),
        "salt": salt,
        "nonce": nonce,
        "cost": cost,
    }


def test_clear_challenge_solves_pow_and_returns_payload():
    challenge = _altcha_v3_challenge()
    html = '<altcha-widget challengeurl="/altcha/challenge"></altcha-widget>'
    s = _Session([_Resp(json_data=challenge)])
    out = run(gc.clear_surface_challenge(s, "https://shop.example/checkout", html))
    assert out["route"] == "captcha_pow_cpu", out
    assert out["token"], out
    payload = base64.b64decode(out["token"] + "===").decode()
    assert '"number": 7' in payload or '"number":7' in payload, payload
    assert "решён" in out["detail"]


def test_clear_challenge_without_declared_url_is_honest():
    html = '<script src="/dist/altcha.min.js"></script><altcha-widget></altcha-widget>'
    out = run(gc.clear_surface_challenge(_Session([]), "https://shop.example/checkout", html))
    assert out["cleared"] is False
    assert "URL не объявлен" in out["detail"], out


def test_clear_challenge_unimplemented_route_says_so(monkeypatch):
    html = '<html><head><title>Access denied</title></head><body>DataDome</body></html>'
    out = run(gc.clear_surface_challenge(_Session([]), "https://shop.example/checkout", html))
    assert out["cleared"] is False
    assert out["detail"], out


def test_clear_turnstile_reports_when_interstitial_is_gone(monkeypatch):
    async def fake_sidecar(url, timeout_sec=15.0, headless=True):
        return "turnstile-token"

    monkeypatch.setattr(gc, "solve_turnstile_url_async", fake_sidecar)
    profile = gc.classify_surface_challenge(503, _CF_BLOCK_HTML, headers={"server": "cloudflare"})
    s = _Session([_Resp(text="<html><body>checkout is fine</body></html>")])
    out = run(gc.clear_surface_challenge(s, "https://shop.example/checkout", _CF_BLOCK_HTML,
                                         profile=profile))
    assert out["cleared"] is True, out
    assert out["token"] == "turnstile-token"


# --- мёртвый пул /hit (G-02) --------------------------------------------------

def test_hit_pool_has_no_live_targets():
    lines = (ROOT / "data" / "hit_targets.txt").read_text(encoding="utf-8").splitlines()
    assert not [ln for ln in lines if ln.strip().startswith("http")], "в пуле снова боевые строки"


def test_hit_cli_refuses_to_take_dead_default(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["hit_gate.py"])
    with pytest.raises(SystemExit) as exc:
        run(hg.main())
    assert exc.value.code == 2
    out = capsys.readouterr().out
    assert "дефолт из пула больше не подставляется" in out, out


# --- /pi и /vbv: пустой пул = не продаём (G-03 / G-04) ------------------------

def test_availability_reports_dead_surfaces_with_reason():
    info = ga.availability()
    assert info["piconfirm"]["available"] is False
    assert info["braintreenvbv"]["available"] is False
    assert "цел" in info["piconfirm"]["reason"]
    assert info["storegate"]["available"] is True and info["storegate"]["targets"] > 0


def test_off_sale_excludes_dead_surfaces_from_available_list():
    assert "piconfirm" not in ga.available_gates()
    assert "braintreenvbv" not in ga.available_gates()
    off = ga.off_sale()
    assert set(off) == {"piconfirm", "braintreenvbv"}, off


def test_keyboard_hides_gates_without_targets():
    kb = keyboards.gates_menu_kb("chk", available={"storegate", "shopify", "setupwoo"})
    labels = [b.text for row in kb.inline_keyboard for b in row]
    assert any("/st)" in t for t in labels), labels
    assert any("/sp)" in t for t in labels), labels
    assert not any("/pi)" in t for t in labels), labels
    assert not any("/vbv)" in t for t in labels), labels


def test_keyboard_without_filter_keeps_all_buttons():
    kb = keyboards.gates_menu_kb("chk", available=None)
    labels = [b.text for row in kb.inline_keyboard for b in row]
    assert any("/pi)" in t for t in labels), labels
    assert any("/vbv)" in t for t in labels), labels


def test_gates_menu_text_lists_off_sale_reasons():
    from bot import main as bot_main
    text = bot_main.render_gates_menu({"selected_gate": "chk", "selected_tier": "1"})
    assert "Снято с продажи" in text, text
    assert "/pi" in text and "/vbv" in text
    assert "PI Confirm (/pi):</b> Чекаут по client_secret" not in text, "мёртвая поверхность снова продаётся"


def test_bot_availability_wrapper_matches_registry():
    from bot import main as bot_main
    assert set(bot_main._available_gates()) == set(ga.available_gates()) & set(bot_main.GATES)
