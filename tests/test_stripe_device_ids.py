# language: Python 3.12+, file: tests/test_stripe_device_ids.py, target: Windows 11
"""Настоящие идентификаторы устройства Stripe (m.stripe.com/6) вместо синтетических.

Живой замер 2026-09-13: сервис не echo, а минтит идентичность — на наши UUID он вернул другие
значения с добавленным суффиксом устройства. Витрина берёт muid/guid/sid именно оттуда.
"""
import pytest

import config
import gate_client as gc


@pytest.fixture(autouse=True)
def _isolated_device_cache(tmp_path, monkeypatch):
    """Тесты не должны читать/писать рабочий кэш идентификаторов устройства."""
    monkeypatch.setattr(config, "STRIPE_DEVICE_IDS_PATH", str(tmp_path / "dev.json"), raising=False)
    yield


class _Resp:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = payload if payload is not None else {}

    def json(self):
        return self._payload


class _Session:
    def __init__(self, resp):
        self.resp = resp
        self.calls = []

    async def post(self, url, data=None, headers=None, timeout=None):
        self.calls.append({"url": url, "data": data, "headers": headers or {}})
        return self.resp


@pytest.mark.asyncio
async def test_mint_returns_real_identifiers():
    s = _Session(_Resp(200, {"muid": "7f40f0ae-f9ea-4f7a-ac65-e526f7310feb537dc3",
                          "guid": "843f75d6-7e2e-4563-aa46-f6aad17aaeca8c38b6",
                          "sid": "7e4a564d-05bf-44d2-a022-ecb8c405b9e3f22684"}))
    ids = await gc.mint_stripe_ids(s)
    assert ids["muid"].startswith("7f40f0ae-")
    assert ids["guid"] and ids["sid"]
    call = s.calls[0]
    assert call["url"] == "https://m.stripe.com/6"
    assert call["headers"]["content-type"] == "application/x-www-form-urlencoded"
    assert call["data"] and isinstance(call["data"], bytes)


@pytest.mark.asyncio
async def test_mint_without_muid_is_empty():
    s = _Session(_Resp(200, {"sid": "x"}))
    assert await gc.mint_stripe_ids(s) == {}


@pytest.mark.asyncio
async def test_mint_network_failure_is_empty():
    class _Boom(_Session):
        async def post(self, *a, **kw):
            raise RuntimeError("нет сети")

    assert await gc.mint_stripe_ids(_Boom(_Resp())) == {}