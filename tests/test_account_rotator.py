# language: Python 3.12+, file: tests/test_account_rotator.py, target: Windows 11
"""Ротация ссылки аккаунтом: чтение данных, выпуск ссылки, понятные отказы."""
import json

import pytest

import account_rotator as ar
import config


def test_load_auth_from_file_fills_default_headers(tmp_path):
    p = tmp_path / "auth.json"
    p.write_text(json.dumps({"access_token": "tok-123"}), encoding="utf-8")
    auth = ar.load_auth(str(p))
    assert auth["access_token"] == "tok-123"
    assert auth["headers"]["x-msh-platform"] == "web"
    assert auth["headers"]["connect-protocol-version"] == "1"
    assert "файл" in auth["source"]


def test_load_auth_from_file_honours_custom_headers(tmp_path):
    p = tmp_path / "auth.json"
    p.write_text(json.dumps({"access_token": "tok", "headers": {"x-msh-device-id": "dev-1"}}), encoding="utf-8")
    auth = ar.load_auth(str(p))
    assert auth["headers"]["x-msh-device-id"] == "dev-1"
    assert auth["headers"]["x-msh-platform"] == "web"


def test_load_auth_missing_everything_is_actionable(tmp_path, monkeypatch):
    monkeypatch.delenv("KIMI_ACCESS_TOKEN", raising=False)
    missing = str(tmp_path / "nope.json")
    with pytest.raises(ar.AccountAuthError) as exc:
        ar.load_auth(missing)
    msg = str(exc.value)
    assert "nope.json" in msg
    assert "grab_account_auth" in msg


def test_load_auth_from_environment(tmp_path, monkeypatch):
    monkeypatch.setenv("KIMI_ACCESS_TOKEN", "env-token")
    monkeypatch.setenv("KIMI_MSH_DEVICE_ID", "dev-env")
    auth = ar.load_auth(str(tmp_path / "absent.json"))
    assert auth["access_token"] == "env-token"
    assert auth["headers"]["x-msh-device-id"] == "dev-env"
    assert "окружение" in auth["source"]


def test_load_auth_file_without_token_is_actionable(tmp_path, monkeypatch):
    monkeypatch.delenv("KIMI_ACCESS_TOKEN", raising=False)
    p = tmp_path / "auth.json"
    p.write_text(json.dumps({"headers": {}}), encoding="utf-8")
    with pytest.raises(ar.AccountAuthError) as exc:
        ar.load_auth(str(p))
    assert "access_token" in str(exc.value)


class _Resp:
    def __init__(self, status_code=200, payload=None, text=""):
        self.status_code = status_code
        self._payload = payload or {}
        self.text = text or json.dumps(self._payload)

    def json(self):
        return self._payload


class _Session:
    def __init__(self, resp):
        self.resp = resp
        self.calls = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def post(self, url, json=None, headers=None, timeout=None):
        self.calls.append({"url": url, "json": json, "headers": headers})
        return self.resp


def _patch_session(monkeypatch, resp):
    holder = {}

    def factory(*a, **kw):
        holder["s"] = _Session(resp)
        return holder["s"]

    monkeypatch.setattr(ar, "AsyncSession", factory)
    return holder


@pytest.mark.asyncio
async def test_mint_link_builds_request_and_returns_link(monkeypatch):
    resp = _Resp(200, {"subscription": {"subscriptionId": "sub-1"}, "redirectUrl": "https://checkout.stripe.com/g/pay/cs_live_x#fid"})
    holder = _patch_session(monkeypatch, resp)
    res = await ar.mint_link({"access_token": "tok", "headers": ar.default_headers()})
    assert res["ok"] is True
    assert res["link"].startswith("https://checkout.stripe.com/g/pay/cs_live_x")
    assert res["subscription_id"] == "sub-1"
    call = holder["s"].calls[0]
    assert call["url"].endswith("/CreateSubscription")
    assert call["headers"]["authorization"] == "tok"
    assert call["json"]["goods_id"] == config.ACCOUNT_ROTATION_GOODS_ID
    assert call["json"]["payment_channel"] == "PAYMENT_CHANNEL_STRIPE"


@pytest.mark.asyncio
async def test_mint_link_expired_token_is_actionable(monkeypatch):
    resp = _Resp(401, {"code": "unauthenticated", "debug": {"reason": "REASON_INVALID_AUTH_TOKEN"}})
    _patch_session(monkeypatch, resp)
    res = await ar.mint_link({"access_token": "tok", "headers": ar.default_headers()})
    assert res["ok"] is False
    assert res["http"] == 401
    assert "протух" in res["error"]
    assert "grab_account_auth" in res["error"]


@pytest.mark.asyncio
async def test_mint_link_without_redirect_url_reports_format_change(monkeypatch):
    _patch_session(monkeypatch, _Resp(200, {"subscription": {"subscriptionId": "sub-2"}}))
    res = await ar.mint_link({"access_token": "tok", "headers": ar.default_headers()})
    assert res["ok"] is False
    assert "redirectUrl" in res["error"]


@pytest.mark.asyncio
async def test_mint_link_network_error_is_returned_not_raised(monkeypatch):
    class _Boom(_Session):
        async def post(self, *a, **kw):
            raise RuntimeError("сеть легла")

    monkeypatch.setattr(ar, "AsyncSession", lambda *a, **kw: _Boom(_Resp()))
    res = await ar.mint_link({"access_token": "tok", "headers": ar.default_headers()})
    assert res["ok"] is False
    assert "сеть легла" in res["error"]