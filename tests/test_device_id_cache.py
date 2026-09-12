# language: Python 3.12+, file: tests/test_device_id_cache.py, target: Windows 11
"""Идентификаторы устройства Stripe кэшируются: один клиент, а не новый на каждый раунд."""
import json
import time

import pytest

import config
import gate_client as gc


@pytest.fixture(autouse=True)
def _isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "STRIPE_DEVICE_IDS_PATH", str(tmp_path / "dev.json"), raising=False)
    yield


class _Resp:
    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload


class _Session:
    def __init__(self, payload):
        self.payload = payload
        self.calls = 0

    async def post(self, *a, **kw):
        self.calls += 1
        return _Resp(self.payload)


@pytest.mark.asyncio
async def test_first_mint_saves_and_second_uses_cache():
    s = _Session({"muid": "m-1", "sid": "s-1", "guid": "g-1"})
    first = await gc.mint_stripe_ids(s)
    assert first["muid"] == "m-1"
    assert s.calls == 1
    second = await gc.mint_stripe_ids(s)
    assert second["muid"] == "m-1"
    assert second.get("cached") is True
    assert s.calls == 1, "второй вызов должен брать из кэша, без сети"


def test_load_cache_ignores_stale_and_broken_files(tmp_path, monkeypatch):
    p = tmp_path / "dev.json"
    monkeypatch.setattr(config, "STRIPE_DEVICE_IDS_PATH", str(p), raising=False)
    assert gc.load_cached_device_ids() == {}
    p.write_text("{не json", encoding="utf-8")
    assert gc.load_cached_device_ids() == {}
    p.write_text(json.dumps({"muid": "m", "sid": "s", "saved_at": int(time.time()) - 40 * 86400}), encoding="utf-8")
    assert gc.load_cached_device_ids() == {}
    p.write_text(json.dumps({"muid": "m", "sid": "s", "guid": "g", "saved_at": int(time.time())}), encoding="utf-8")
    assert gc.load_cached_device_ids()["guid"] == "g"


def test_save_refuses_incomplete_ids(tmp_path, monkeypatch):
    p = tmp_path / "dev.json"
    monkeypatch.setattr(config, "STRIPE_DEVICE_IDS_PATH", str(p), raising=False)
    gc.save_cached_device_ids({"muid": "m"})
    assert not p.exists()


@pytest.mark.asyncio
async def test_expired_cache_triggers_new_mint():
    gc.save_cached_device_ids({"muid": "old", "sid": "old-s", "guid": "old-g"})
    import pathlib
    path = pathlib.Path(config.STRIPE_DEVICE_IDS_PATH)
    data = json.loads(path.read_text(encoding="utf-8"))
    data["saved_at"] = int(time.time()) - 90 * 86400
    path.write_text(json.dumps(data), encoding="utf-8")
    s = _Session({"muid": "new", "sid": "new-s", "guid": "new-g"})
    ids = await gc.mint_stripe_ids(s)
    assert ids["muid"] == "new"
    assert s.calls == 1