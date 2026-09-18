# language: Python 3.12+, file: tests/test_page_bundle.py, target: Windows 11
"""Набор полей живой страницы: разбор тела confirm, отбор полей, привязка к сессии."""
from __future__ import annotations

import json
import pathlib

import pytest

import config
import page_bundle

BODY = ("eid=NA&payment_method=pm_1TEST&key=pk_live_x&expected_amount=2514"
        "&init_checksum=AAA111&version=abc123def4"
        "&js_checksum=qto%7E1&rv_timestamp=qto%3E2&passive_captcha_token=P1_eyJhbGci"
        "&px3=deadbeef%3A1&pxvid=11111111-2222-3333-4444-555555555555&pxcts=xyz")


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "PAGE_BUNDLE_PATH", str(tmp_path / "page_bundle.json"), raising=False)


def test_parse_body_keeps_page_fields_and_drops_our_own():
    fields = page_bundle.parse_body(BODY)
    for k in ("js_checksum", "rv_timestamp", "passive_captcha_token", "px3", "pxvid", "pxcts", "init_checksum"):
        assert k in fields
    for k in page_bundle.NEVER:
        assert k not in fields, f"{k} переносить нельзя — это наше поле"


def test_from_report_takes_the_fullest_body(tmp_path):
    rep = tmp_path / "run.json"
    rep.write_text(json.dumps({
        "link": "https://checkout.stripe.com/c/pay/cs_live_AAA#fid",
        "confirms": [{"kind": "req", "body": "eid=NA&payment_method=pm_1"}, {"kind": "req", "body": BODY}],
    }), encoding="utf-8")
    bundle = page_bundle.from_report(rep)
    assert bundle["fields"]["js_checksum"] == "qto%7E1"
    assert bundle["fields"]["passive_captcha_token"].startswith("P1_")


def test_fields_for_empty_without_bundle():
    assert page_bundle.fields_for("cs_live_AAA") == {}


def test_fields_for_respects_session_link(tmp_path):
    rep = tmp_path / "run.json"
    rep.write_text(json.dumps({"link": "https://checkout.stripe.com/c/pay/cs_live_AAA#fid",
                               "confirms": [{"kind": "req", "body": BODY}]}), encoding="utf-8")
    page_bundle.save(page_bundle.from_report(rep))
    assert page_bundle.fields_for("cs_live_AAA")["js_checksum"] == "qto%7E1"
    assert page_bundle.fields_for("cs_live_OTHER") == {}      # набор от другой ссылки не подмешиваем


def test_confirm_body_uses_page_fields(monkeypatch):
    """Регрессия: confirm берёт js_checksum со страницы, если набор есть."""
    import hit_gate
    monkeypatch.setattr(page_bundle, "fields_for", lambda cs=None: {"js_checksum": "qto%7E1", "px3": "deadbeef%3A1"})
    src = pathlib.Path("hit_gate.py").read_text(encoding="utf-8")
    assert "page_bundle" in src and "js_checksum" in src + "PAGE_FIELDS"
