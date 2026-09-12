# language: Python 3.12+, file: tests/test_3ds_cookie_conflict.py, target: Windows 11
"""Регрессия по живому дефекту 2026-09-13: обход 3DS обрывался на CookieConflict.

Arcot (ACS Amex) и hCaptcha ставят __cf_bm на РАЗНЫХ доменах (.arcot.com и .hcaptcha.com).
curl_cffi на такое бросает CookieConflict при dict(session.cookies) — то есть уже ПОСЛЕ успешного
POST на tds-method (HTTP 200). Из-за этого execute_3ds_method возвращал success=False, движок
обрывал обход, и вердикт всегда съезжал в 3DS_CHALLENGE, даже когда метод проходил.
"""
import pytest

import frictionless_engine as fe


class _Cookie:
    def __init__(self, name, value, domain):
        self.name = name
        self.value = value
        self.domain = domain


class _Cookies:
    def __init__(self, items):
        self.jar = [_Cookie(n, v, d) for n, v, d in items]


class _Resp:
    def __init__(self, status_code=200, text=""):
        self.status_code = status_code
        self.text = text


class _Session:
    def __init__(self, items, resp):
        self.cookies = _Cookies(items)
        self._resp = resp
        self.posts = []

    async def post(self, url, data=None, headers=None, timeout=None):
        self.posts.append({"url": url, "data": data})
        return self._resp


def test_raw_dict_conversion_still_conflicts_in_curl_cffi():
    """Корень дефекта: сам curl_cffi на двух __cf_bm с разных доменов бросает CookieConflict."""
    from curl_cffi.requests import Cookies

    c = Cookies()
    c.set("__cf_bm", "aaa", domain=".hcaptcha.com")
    c.set("__cf_bm", "bbb", domain=".arcot.com")
    with pytest.raises(Exception) as exc:
        dict(c)
    assert "Multiple cookies exist with name=__cf_bm" in str(exc.value)


def test_snapshot_cookies_keeps_duplicates_and_does_not_raise():
    """Наш снимок обязан не падать и не терять оба домена."""
    s = _Session([("__cf_bm", "aaa", ".hcaptcha.com"),
                  ("__cf_bm", "bbb", ".arcot.com"),
                  ("m", "muid", ".stripe.com")], _Resp())
    snap = fe.snapshot_cookies(s)
    assert snap["__cf_bm"] in ("aaa", "bbb")
    assert "bbb" in snap.values() and "aaa" in snap.values()
    assert snap["m"] == "muid"


def test_snapshot_cookies_handles_missing_jar():
    class _NoJar:
        cookies = None

    assert fe.snapshot_cookies(_NoJar()) == {}


@pytest.mark.asyncio
async def test_3ds_method_survives_cookie_conflict_after_200():
    """Живой случай: POST tds-method вернул 200, а результат падал на cookie-jar."""
    s = _Session([("__cf_bm", "aaa", ".hcaptcha.com"), ("__cf_bm", "bbb", ".arcot.com")],
                 _Resp(200, "<html><body>arcot method ok</body></html>"))
    res = await fe.execute_3ds_method(s, "https://secure2.arcot.com/content-server/api/tds2/txn/browser/v1/tds-method",
                                      "trans-uuid-1", notification_url="https://hooks.stripe.com/3d_secure_2/hosted/complete")
    assert res["success"] is True, res
    assert res["status_code"] == 200
    assert "__cf_bm" in res["cookies"]
    assert len(s.posts) == 1


@pytest.mark.asyncio
async def test_3ds_method_still_reports_failure_on_http_error():
    """Обратная сторона: настоящая ошибка HTTP по-прежнему success=False."""
    s = _Session([("__cf_bm", "aaa", ".hcaptcha.com")], _Resp(500, "boom"))
    res = await fe.execute_3ds_method(s, "https://acs.example/tds-method", "trans-uuid-2")
    assert res["success"] is False
    assert res["status_code"] == 500
