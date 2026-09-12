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




def _jwt(exp: int) -> str:
    import base64 as b64

    def enc(obj: dict) -> str:
        raw = json.dumps(obj).encode()
        return b64.urlsafe_b64encode(raw).decode().rstrip("=")

    return enc({"alg": "HS256", "typ": "JWT"}) + "." + enc({"exp": exp}) + ".sig"


class _Router:
    """Фейковая сессия: на auth.kimi.ai отдаёт продление, на остальное — выпуск ссылки."""

    def __init__(self, refresh_payload=None, refresh_status=200, mint_payload=None, mint_status=200):
        self.refresh_payload = refresh_payload if refresh_payload is not None else {}
        self.refresh_status = refresh_status
        self.mint_payload = mint_payload if mint_payload is not None else {}
        self.mint_status = mint_status
        self.calls = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def post(self, url, json=None, headers=None, timeout=None):
        self.calls.append({"url": url, "json": json, "headers": headers or {}})
        if "auth.kimi.ai" in url:
            return _Resp(self.refresh_status, self.refresh_payload)
        return _Resp(self.mint_status, self.mint_payload)

def _patch_router(monkeypatch, router):
    monkeypatch.setattr(ar, "AsyncSession", lambda *a, **kw: router)
    return router


@pytest.mark.asyncio
async def test_refresh_calls_auth_host_with_proto_field_name(monkeypatch):
    """Живой замер 2026-09-13: продление — Connect-RPC на auth.kimi.ai, поле refreshToken."""
    router = _patch_router(monkeypatch, _Router(refresh_payload={"accessToken": _jwt(1_800_000_000), "refreshToken": "rt-2"}))
    res = await ar.refresh_access_token({"refresh_token": "rt-1"})
    assert res["ok"] is True
    assert res["refresh_token"] == "rt-2"
    assert res["expires_at"] == 1_800_000_000
    call = router.calls[0]
    assert call["url"] == "https://auth.kimi.ai/api/account.gateway.v1.AuthService/RefreshToken"
    assert call["json"] == {"refreshToken": "rt-1"}


@pytest.mark.asyncio
async def test_refresh_without_refresh_token_is_actionable(monkeypatch):
    _patch_router(monkeypatch, _Router())
    res = await ar.refresh_access_token({})
    assert res["ok"] is False
    assert "refresh_token" in res["error"]


@pytest.mark.asyncio
async def test_refresh_rejects_bad_response(monkeypatch):
    _patch_router(monkeypatch, _Router(refresh_status=401, refresh_payload={"code": "unauthenticated"}))
    res = await ar.refresh_access_token({"refresh_token": "rt"})
    assert res["ok"] is False
    assert res["http"] == 401


@pytest.mark.asyncio
async def test_mint_link_refreshes_nearly_expired_token_itself(monkeypatch):
    """Токену 10 секунд — ротатор продлевает его сам и выпускает ссылку без браузера."""
    import time as _t

    router = _patch_router(monkeypatch, _Router(
        refresh_payload={"accessToken": _jwt(int(_t.time()) + 900), "refreshToken": "rt-new"},
        mint_payload={"subscription": {"subscriptionId": "sub-r"}, "redirectUrl": "https://checkout.stripe.com/c/pay/cs_live_r#fid"},
    ))
    auth = {"access_token": _jwt(int(_t.time()) + 10), "refresh_token": "rt-old",
            "headers": ar.default_headers(), "expires_at": int(_t.time()) + 10}
    res = await ar.mint_link(auth)
    assert res["ok"] is True
    urls = [c["url"] for c in router.calls]
    assert any("auth.kimi.ai" in u for u in urls), "должен был продлить токен"
    mint_call = [c for c in router.calls if "CreateSubscription" in c["url"]][0]
    assert mint_call["headers"]["authorization"].startswith("eyJ")


@pytest.mark.asyncio
async def test_mint_link_refuses_expired_token_when_refresh_fails(monkeypatch):
    import time as _t

    _patch_router(monkeypatch, _Router(refresh_status=401, refresh_payload={"code": "unauthenticated"}))
    auth = {"access_token": _jwt(int(_t.time()) - 10), "refresh_token": "rt",
            "headers": ar.default_headers(), "expires_at": int(_t.time()) - 10}
    res = await ar.mint_link(auth)
    assert res["ok"] is False
    assert "истёк" in res["error"]


def test_save_auth_writes_tokens_and_headers(tmp_path):
    p = tmp_path / "auth.json"
    path = ar.save_auth({"access_token": "a-1", "refresh_token": "r-1",
                         "headers": {"x-msh-device-id": "dev"}}, str(p))
    saved = json.loads((tmp_path / "auth.json").read_text(encoding="utf-8"))
    assert saved["access_token"] == "a-1"
    assert saved["refresh_token"] == "r-1"
    assert saved["headers"]["x-msh-device-id"] == "dev"
    assert path.endswith("auth.json")


def test_token_expiry_reads_exp_from_payload():
    exp = 1_800_000_000
    assert ar.token_expiry(_jwt(exp)) == exp


def test_token_expiry_returns_zero_on_garbage():
    assert ar.token_expiry("не-jwt") == 0
    assert ar.token_expiry("") == 0


def test_expiry_note_marks_dead_and_live_tokens():
    assert "истёк" in ar._expiry_note(int(__import__("time").time()) - 10)
    assert "мин" in ar._expiry_note(int(__import__("time").time()) + 600)
    assert ar._expiry_note(0) == ""


@pytest.mark.asyncio
async def test_mint_link_refuses_expired_token_without_network(monkeypatch):
    """Истёкший токен: отказ сразу и с инструкцией, а не загадочный 401 после запроса."""
    called = []

    def factory(*a, **kw):
        called.append(1)
        raise AssertionError("сеть не должна была вызываться")

    monkeypatch.setattr(ar, "AsyncSession", factory)
    auth = {"access_token": _jwt(1_700_000_000), "headers": ar.default_headers(), "expires_at": 1_700_000_000}
    res = await ar.mint_link(auth)
    assert res["ok"] is False
    assert "истёк" in res["error"]
    assert "grab_account_auth" in res["error"]
    assert called == []


@pytest.mark.asyncio
async def test_mint_link_network_error_is_returned_not_raised(monkeypatch):
    class _Boom(_Session):
        async def post(self, *a, **kw):
            raise RuntimeError("сеть легла")

    monkeypatch.setattr(ar, "AsyncSession", lambda *a, **kw: _Boom(_Resp()))
    res = await ar.mint_link({"access_token": "tok", "headers": ar.default_headers()})
    assert res["ok"] is False
    assert "сеть легла" in res["error"]