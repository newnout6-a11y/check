# language: Python 3.12+, file: tests/test_spinner_rotation.py, target: Windows 11
"""Ротация внутри крутилки: по смерти ссылки выпускаем новую и продолжаем."""
import pytest

import account_rotator as ar
import link_spinner as ls


@pytest.mark.asyncio
async def test_try_rotate_respects_link_limit():
    res = await ls.try_rotate("https://checkout.stripe.com/g/pay/cs_live_old#fid", None, minted=2, max_links=2)
    assert res["ok"] is False
    assert "лимит" in res["error"]


@pytest.mark.asyncio
async def test_try_rotate_returns_new_link(monkeypatch):
    async def fake_mint(auth=None, goods_id=None, proxy=None, timeout=20):
        return {"ok": True, "link": "https://checkout.stripe.com/c/pay/cs_live_new#fid", "subscription_id": "sub-9"}

    monkeypatch.setattr(ar, "mint_link", fake_mint)
    monkeypatch.setattr(ar, "load_auth", lambda path=None: {"access_token": "t", "headers": {}, "source": "тест"})
    res = await ls.try_rotate("https://checkout.stripe.com/g/pay/cs_live_old#fid", None, 0, 3)
    assert res["ok"] is True
    assert res["link"].endswith("cs_live_new#fid")
    assert res["subscription_id"] == "sub-9"


@pytest.mark.asyncio
async def test_try_rotate_surfaces_missing_auth(monkeypatch):
    def boom(path=None):
        raise ar.AccountAuthError("нет данных аккаунта для ротации")

    monkeypatch.setattr(ar, "load_auth", boom)
    res = await ls.try_rotate("https://checkout.stripe.com/g/pay/cs_live_old#fid", None, 0, 3)
    assert res["ok"] is False
    assert "нет данных аккаунта" in res["error"]


@pytest.mark.asyncio
async def test_spin_rotates_on_dead_link_and_keeps_going(monkeypatch):
    """Ядро задачи dj: умерла сессия -> выпустили новую -> крутим дальше (а не остановка)."""
    states = [
        {"ok": False, "dead": True, "reason": "сессия мертва (checkout_not_active_session)"},
        {"ok": True, "status": "open", "payment_status": "unpaid", "amount": 2504, "currency": "SGD",
         "pi_id": "pi_1", "pi_status": "requires_payment_method", "checksum": True},
        {"ok": True, "status": "open", "payment_status": "unpaid", "amount": 2504, "currency": "SGD",
         "pi_id": "pi_1", "pi_status": "requires_payment_method", "checksum": True},
    ]

    async def fake_probe(link):
        return states.pop(0) if states else {"ok": True, "status": "open", "payment_status": "unpaid",
                                             "amount": 2504, "currency": "SGD", "pi_id": "pi_1",
                                             "pi_status": "requires_payment_method", "checksum": True}

    minted = []

    async def fake_mint(auth=None, goods_id=None, proxy=None, timeout=20):
        minted.append(1)
        return {"ok": True, "link": "https://checkout.stripe.com/c/pay/cs_live_fresh#fid", "subscription_id": "sub-fresh"}

    async def fake_round(link, cards, proxy):
        return [{"status": "DECLINED", "detail": "card_declined", "confirmed_amount_cents": 2504}]

    dumps = []
    monkeypatch.setattr(ls, "probe_session", fake_probe)
    monkeypatch.setattr(ls, "run_round", fake_round)
    monkeypatch.setattr(ar, "mint_link", fake_mint)
    monkeypatch.setattr(ar, "load_auth", lambda path=None: {"access_token": "t", "headers": {}, "source": "тест"})
    monkeypatch.setattr(ls, "_dump", lambda *a, **kw: dumps.append(a))
    monkeypatch.setattr(ls, "fresh_probe_card", lambda: "4111111111111111|01|30|123")

    code = await ls.spin("https://checkout.stripe.com/g/pay/cs_live_old#fid", rounds=3, cards_per_round=1,
                         interval=0, max_attempts=10, fixed_card=None, proxy=None, dry=False,
                         rotate=True, max_links=2)
    assert code == 0, code
    assert len(minted) == 1
    assert dumps, "журнал должен быть записан"


@pytest.mark.asyncio
async def test_spin_without_rotate_still_stops_on_dead(monkeypatch):
    async def fake_probe(link):
        return {"ok": False, "dead": True, "reason": "сессия мертва"}

    monkeypatch.setattr(ls, "probe_session", fake_probe)
    monkeypatch.setattr(ls, "_dump", lambda *a, **kw: None)
    code = await ls.spin("https://checkout.stripe.com/g/pay/cs_live_old#fid", rounds=2, cards_per_round=1,
                         interval=0, max_attempts=10, fixed_card=None, proxy=None, dry=False)
    assert code == 3


@pytest.mark.asyncio
async def test_spin_stops_when_link_limit_exhausted(monkeypatch):
    async def fake_probe(link):
        return {"ok": False, "dead": True, "reason": "сессия мертва"}

    monkeypatch.setattr(ls, "probe_session", fake_probe)
    monkeypatch.setattr(ls, "_dump", lambda *a, **kw: None)
    code = await ls.spin("https://checkout.stripe.com/g/pay/cs_live_old#fid", rounds=2, cards_per_round=1,
                         interval=0, max_attempts=10, fixed_card=None, proxy=None, dry=False,
                         rotate=True, max_links=0)
    assert code == 3