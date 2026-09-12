# language: Python 3.12+, file: tests/test_card_metadata.py, target: Windows 11
"""Живой BIN-lookup Stripe (edge-internal/card-metadata): то, что страница зовёт при вводе номера.

Найдено на живой странице оплаты 2026-09-13: отдаёт brand/funding/country/pan_length по префиксу
и бесплатен. Проверяем разбор ответа и отсутствие падений на странных данных.
"""
import pytest

import gate_client as gc


class _Resp:
    def __init__(self, status_code=200, payload=None, text=""):
        self.status_code = status_code
        self._payload = payload if payload is not None else {}
        self.text = text

    def json(self):
        return self._payload


class _Session:
    def __init__(self, resp):
        self.resp = resp
        self.calls = []

    async def get(self, url, params=None, headers=None, timeout=None):
        self.calls.append({"url": url, "params": params or {}})
        return self.resp


@pytest.mark.asyncio
async def test_card_metadata_parses_range_row():
    s = _Session(_Resp(200, {"data": [{"brand": "AMERICAN_EXPRESS", "funding": "CREDIT", "country": "US",
                                 "pan_length": 15, "account_range_low": "379363000000000",
                                 "account_range_high": "379363999999999"}]}))
    res = await gc.card_metadata(s, "pk_live_x", "379363")
    assert res["ok"] is True
    assert res["brand"] == "american_express"
    assert res["funding"] == "credit"
    assert res["country"] == "US"
    assert res["pan_length"] == 15
    assert s.calls[0]["params"] == {"bin_prefix": "379363", "key": "pk_live_x"}
    assert s.calls[0]["url"].endswith("/edge-internal/card-metadata")


@pytest.mark.asyncio
async def test_card_metadata_empty_data_is_not_ok():
    s = _Session(_Resp(200, {"data": []}, text=chr(123) + chr(34) + "data" + chr(34) + ":[]" + chr(125)))
    res = await gc.card_metadata(s, "pk", "999999")
    assert res["ok"] is False


@pytest.mark.asyncio
async def test_card_metadata_sanitizes_prefix():
    s = _Session(_Resp(200, {"data": [{"brand": "visa"}]}))
    res = await gc.card_metadata(s, "pk", "45 3927-abc")
    assert res["ok"] is True
    assert s.calls[0]["params"]["bin_prefix"] == "453927"


@pytest.mark.asyncio
async def test_card_metadata_rejects_empty_prefix():
    s = _Session(_Resp(200, {"data": []}))
    res = await gc.card_metadata(s, "pk", "abc")
    assert res["ok"] is False
    assert "BIN" in res["error"]
    assert not s.calls


@pytest.mark.asyncio
async def test_card_metadata_network_error_is_returned():
    class _Boom(_Session):
        async def get(self, *a, **kw):
            raise RuntimeError("нет сети")

    res = await gc.card_metadata(_Boom(_Resp()), "pk", "379363")
    assert res["ok"] is False
    assert "нет сети" in res["error"]