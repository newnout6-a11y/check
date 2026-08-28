# language: Python 3.12+, file: tests/test_round1_fixes.py, target: Windows 11
# Юнит-тесты фиксов «bugfix-round-1» (см. docs/АУДИТ.md §4): чистая логика, без сети.
# Запуск: python -m pytest tests/ -q
import importlib
import os
import sqlite3

import pytest

import gate_client as gc


# --- gate_client: парсинг карт ---

def test_parse_card_seven_token_pan():
    # R-8: «4111 1111 1111 1111 09 25 123» раньше давал number="4111", mm="1111"
    c = gc.parse_card("4111 1111 1111 1111 09 25 123")
    assert c["number"] == "4111111111111111"
    assert c["month"] == "09"
    assert c["cvc"] == "123"


def test_parse_card_pipe_classic():
    c = gc.parse_card("4111111111111111|09|25|123")
    assert c["number"] == "4111111111111111"
    assert c["month"] == "09"
    assert c["cvc"] == "123"


def test_extract_pan_spaced_and_pipe():
    # R-9/R-12: BIN-ключ должен быть формат-агностик
    assert gc.extract_pan("5175 4638 2242 0903|09|2030|018") == "5175463822420903"
    assert gc.extract_pan("5175463822420903|09|2030|018") == "5175463822420903"


def test_luhn():
    assert gc.check_luhn("4111111111111111")
    assert not gc.check_luhn("4111111111111112")


# --- gate_client: None-поля из JSON ---

def test_score_gate_none_fields():
    # R-7: success_rate/latency/fail_count = null не должны валить скоринг
    assert gc.score_gate({"success_rate": None, "latency_avg_ms": None,
                          "fail_count": None}) > 0


def test_classify_verdict_taxonomy():
    assert gc.classify_verdict("Your card was declined. generic_decline") == "DECLINED"


# --- domains_store: upsert/COALESCE на временной базе ---

@pytest.fixture()
def dstore(tmp_path, monkeypatch):
    import domains_store
    monkeypatch.setattr(domains_store, "DB_PATH", str(tmp_path / "domains.db"))
    domains_store.init_db()
    return domains_store


def test_domains_upsert_priority(dstore):
    assert dstore.upsert(["a.com", "b.com"], "forum", 1) == 2
    assert dstore.upsert(["a.com", "c.com"], "dork", 3) == 1
    due = {d["domain"]: d for d in dstore.due_for_scan(hours=24)}
    assert due["a.com"]["priority"] == 1  # понижается, не повышается
    assert due["c.com"]["priority"] == 3


def test_domains_coalesce_null_priority(dstore):
    # R-20: MIN(NULL, ?) = NULL — приоритет терялся навсегда
    with dstore._db() as c:
        c.execute("INSERT OR IGNORE INTO domains(domain, source, first_seen, priority) "
                  "VALUES('x.com','manual',1,NULL)")
    dstore.upsert(["x.com"], "forum", 2)
    with dstore._db() as c:
        pr = c.execute("SELECT priority FROM domains WHERE domain='x.com'").fetchone()["priority"]
    assert pr == 2


def test_domains_mark_and_stats(dstore):
    dstore.upsert(["a.com"], "forum", 1)
    dstore.mark_scanned("a.com", "READY")
    st = dstore.stats()
    assert st["total"] == 1 and st["scanned"] == 1 and st["pending"] == 0


# --- bot/db.py: экономика ключей и кредитов ---

@pytest.fixture()
def bdb(tmp_path, monkeypatch):
    os.environ.setdefault("PUSTO_BOT_TOKEN", "x")
    import bot.config as bcfg
    monkeypatch.setattr(bcfg, "DB_PATH", str(tmp_path / "bot.db"))
    import bot.db as bdb_mod
    importlib.reload(bdb_mod)
    bdb_mod.init_db()
    return bdb_mod


def test_redeem_key_dual_days_and_credits(bdb):
    # R-17: ключ с days+credits раньше терял кредиты молча
    bdb.ensure_user(42, "tester")
    bdb.add_key("k_dual", days=30, credits=10)
    msg = bdb.redeem_key(42, "k_dual")
    u = bdb.get_user(42)
    assert "Премиум" in msg and "Кредиты" in msg
    assert u["credits"] == 5 + 10


def test_redeem_key_single_use(bdb):
    bdb.ensure_user(42, "tester")
    bdb.add_key("k_once", credits=5)
    bdb.redeem_key(42, "k_once")
    assert "Неверный" in bdb.redeem_key(42, "k_once")


def test_spend_and_refund_credit(bdb):
    bdb.ensure_user(42, "tester")
    assert bdb.spend_credit(42, "setupwoo")
    u = bdb.get_user(42)
    assert u["total_checks"] == 1 and u["credits"] == 5 - 1
    assert bdb.refund_credit(42, "setupwoo")
    u = bdb.get_user(42)
    assert u["credits"] == 5 and u["total_checks"] == 0


# --- bot/main.py: _card_fields (7-токенный коллапс) ---

def test_card_fields():
    import bot.main as bm
    assert bm._card_fields("4111 1111 1111 1111 09 25 123") ==         ["4111111111111111", "09", "25", "123"]
    assert bm._card_fields("4111111111111111|09|25|123") ==         ["4111111111111111", "09", "25", "123"]
    assert bm._card_fields("5175463822420903 12 2030 018") ==         ["5175463822420903", "12", "2030", "018"]
    assert bm._card_fields("4111111111111111 09 25") is None
