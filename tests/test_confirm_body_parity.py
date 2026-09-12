# language: Python 3.12+, file: tests/test_confirm_body_parity.py, target: Windows 11
"""Тело confirm по набору полей должно совпадать со страницей (живая съёмка 2026-09-13).

Страница отправляет ещё и guid/muid/sid + version; без них наш confirm отличался от неё.
"""
import config
import hit_gate as hg


def _session():
    s = hg.CsHitSession("https://checkout.stripe.com/c/pay/cs_live_test#fid")
    s.pk = "pk_live_test"
    s.cs = "cs_live_test"
    s.amount = 2504
    s.expected_amount = 2504
    s.checksum = "checksum-1"
    return s


def test_confirm_body_carries_device_ids_and_version():
    s = _session()
    telem = {"guid": "guid-1", "muid": "muid-1", "sid": "sid-1"}
    body = s.confirm_body({"id": "pm_test"}, telem)
    assert body["guid"] == "guid-1"
    assert body["muid"] == "muid-1"
    assert body["sid"] == "sid-1"
    assert body["version"] == config.STRIPE_JS_BUILD
    assert body["expected_amount"] == "2504"
    assert body["init_checksum"] == "checksum-1"


def test_confirm_body_without_telemetry_still_has_version():
    body = _session().confirm_body({"id": "pm_test"}, {})
    assert body["version"] == config.STRIPE_JS_BUILD
    assert "guid" not in body and "muid" not in body and "sid" not in body