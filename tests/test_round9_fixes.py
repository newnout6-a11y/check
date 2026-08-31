# language: Python 3.12+, file: tests/test_round9_fixes.py, target: Windows 11
# Регрессии раунда 9: таксономия вердиктов, кредиты, SQLite, тир-лейблы.
# Все тесты офлайн, без сети.
# Запуск: python -m pytest tests/ -q
import importlib
import os

import pytest

import config
import gate_client as gc


# --- таксономия вердиктов ---

def test_coerce_verdict_passes_known():
    for v in config.VERDICTS:
        assert config.coerce_verdict(v) == v


def test_coerce_verdict_collapses_unknown_suffix():
    # confirm_gate.py:158 отдавал DECLINED@{CODE}: нет иконки, не попадает в
    # хиты и != "ERROR" — из-за этого кредит не возвращался
    assert config.coerce_verdict("DECLINED@EXPIRED_CARD") == "DECLINED"
    assert config.coerce_verdict("APPROVED@WHATEVER") == "APPROVED"


def test_coerce_verdict_garbage_is_unknown():
    assert config.coerce_verdict("REQUIRES_PAYMENT_METHOD") == "UNKNOWN"
    assert config.coerce_verdict("") == "UNKNOWN"
    assert config.coerce_verdict(None) == "UNKNOWN"


def test_setup_intent_status_is_in_taxonomy():
    # setup_gate.py:412 отдавал сырой str(st).upper()
    for st in ("succeeded", "requires_action", "processing", "canceled",
               "requires_payment_method", "requires_confirmation", "requires_capture"):
        v = gc.classify_setup_intent_status(st)
        assert v in config.VERDICTS, f"{st} -> {v} вне таксономии"
    assert gc.classify_setup_intent_status("succeeded") == "APPROVED"
    assert gc.classify_setup_intent_status("processing") == "PI_PENDING"
    assert gc.classify_setup_intent_status("canceled") == "DECLINED"
    assert gc.classify_setup_intent_status("requires_action") == "3DS_REQUIRED"


def test_setup_intent_unknown_status_is_unknown():
    assert gc.classify_setup_intent_status("что-то новое") == "UNKNOWN"
    assert gc.classify_setup_intent_status("") == "UNKNOWN"
    assert gc.classify_setup_intent_status(None) == "UNKNOWN"


# --- валидация карты до списания кредита ---

def test_card_rejection_accepts_valid():
    import bot.main as bm
    assert bm.card_rejection(["4111111111111111", "12", "2030", "123"]) is None


def test_card_rejection_bad_month():
    # 13-й месяц проходил parse_cards и умирал в _normalize гейта как INVALID —
    # а refund срабатывает только на ERROR, то есть чек сгорал
    import bot.main as bm
    assert bm.card_rejection(["4111111111111111", "13", "2030", "123"])


def test_card_rejection_expired():
    import bot.main as bm
    assert bm.card_rejection(["4111111111111111", "01", "2020", "123"])


def test_card_rejection_luhn():
    import bot.main as bm
    assert bm.card_rejection(["4111111111111112", "12", "2030", "123"])


def test_card_rejection_cvv_length():
    import bot.main as bm
    assert bm.card_rejection(["4111111111111111", "12", "2030", "12345"])


def test_card_rejection_short_pan():
    import bot.main as bm
    assert bm.card_rejection(["411111", "12", "2030", "123"])


# --- тир-лейблы считаются из таблицы самого гейта ---

def test_tier_label_shopify_differs_from_storegate():
    # Общий TIER_LABELS врал для Shopify по всем трём тирам, а не только по low
    import bot.main as bm
    assert bm.tier_label("shopify", "low") == "$0–$2"
    assert bm.tier_label("storegate", "low") == "$0–$1"
    assert bm.tier_label("shopify", "mid") == "$2.01–$6"
    assert bm.tier_label("storegate", "mid") == "$1–$5"


def test_tier_label_falls_back_for_untiered_gate():
    import bot.main as bm
    assert bm.tier_label("setupwoo", "20") == "$5–20"


# --- приоритет гейтов ---

def test_pick_gate_exclude_skips_first():
    import bot.main as bm
    avail = bm._available_gates()
    if len(avail) < 2:
        pytest.skip("нужны минимум два гейта с целями")
    assert bm._pick_gate(None) == avail[0]
    assert bm._pick_gate(None, exclude={avail[0]}) == avail[1]


# --- SQLite ---

@pytest.fixture()
def bdb(tmp_path, monkeypatch):
    os.environ.setdefault("PUSTO_BOT_TOKEN", "x")
    import bot.config as bcfg
    monkeypatch.setattr(bcfg, "DB_PATH", str(tmp_path / "bot.db"))
    import bot.db as bdb_mod
    importlib.reload(bdb_mod)
    bdb_mod.init_db()
    return bdb_mod


def test_wal_enabled(bdb):
    with bdb._db() as c:
        mode = c.execute("PRAGMA journal_mode").fetchone()[0]
    assert mode.lower() == "wal"


def test_schema_version_stamped(bdb):
    with bdb._db() as c:
        v = c.execute("PRAGMA user_version").fetchone()[0]
    assert v == bdb.SCHEMA_VERSION


def test_antispam_blocks_second_call(bdb):
    # SELECT+UPDATE рэйсился: два одновременных /chk оба проходили окно
    bdb.ensure_user(7, "u")
    assert bdb.antispam_ok(7) is True
    assert bdb.antispam_ok(7) is False


def test_antispam_unknown_user_passes(bdb):
    assert bdb.antispam_ok(999999) is True


def test_refund_rolls_back_checks_for_premium(bdb):
    # refund выходил по cost == 0 и не откатывал счётчик — /me и /stats врали
    bdb.ensure_user(8, "u")
    bdb.admin_add_premium(8, 30)
    assert bdb.spend_credit(8, "setupwoo") is True
    assert bdb.get_user(8)["total_checks"] == 1
    assert bdb.refund_credit(8, "setupwoo") is True
    assert bdb.get_user(8)["total_checks"] == 0


def test_admin_add_premium_unknown_user_false(bdb):
    assert bdb.admin_add_premium(424242, 30) is False


# --- атомарная запись прокси-пула ---

def test_atomic_write_lines(tmp_path):
    import bot.main as bm
    p = str(tmp_path / "proxies.txt")
    bm._atomic_write_lines(p, ["a:1", "b:2"])
    assert open(p, encoding="utf-8").read().splitlines() == ["a:1", "b:2"]
    bm._atomic_write_lines(p, [])
    assert open(p, encoding="utf-8").read() == ""
    # временный файл не должен оставаться рядом с боевым носителем
    assert not [f for f in os.listdir(tmp_path) if ".tmp." in f]
