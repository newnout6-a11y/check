# language: Python 3.12+, file: tests/test_radar_config.py, target: Windows 11
"""Снятие конфигурации Radar и капчи без траты попытки: чистые функции, без сети."""
import json

import config
import hit_gate
import radar_config as rc


def test_mask_keeps_only_head():
    assert rc.mask("24ed0064-62cf-4d42-9960-5dd1a41d4e29") == "24ed0064…"
    assert rc.mask("short") == "short"
    assert rc.mask("") == ""


def test_challenges_for_filters_by_session(tmp_path, monkeypatch):
    p = tmp_path / "radar.jsonl"
    p.write_text("\n".join([
        json.dumps({"at": "2026-09-18 19:00:00", "cs": "cs_live_a1", "site_key": "c7faac4c-x", "rqdata_len": 264}),
        json.dumps({"at": "2026-09-18 19:05:00", "cs": "cs_live_b2", "site_key": "c7faac4c-x", "rqdata_len": 264}),
    ]), encoding="utf-8")
    monkeypatch.setattr(config, "RADAR_CHALLENGE_LOG", str(p), raising=False)
    assert len(rc.challenges_for("")) == 2
    assert [r["cs"] for r in rc.challenges_for("cs_live_a1")] == ["cs_live_a1"]


def test_challenges_for_missing_log_is_empty(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "RADAR_CHALLENGE_LOG", str(tmp_path / "нет.jsonl"), raising=False)
    assert rc.challenges_for("cs_live_x") == []


def test_record_radar_challenge_writes_session_and_sitekey(tmp_path, monkeypatch):
    """Ответ confirm — единственный источник sitekey интерактивного челленджа: его пишем в журнал."""
    p = tmp_path / "radar.jsonl"
    monkeypatch.setattr(config, "RADAR_CHALLENGE_LOG", str(p), raising=False)
    hit_gate.record_radar_challenge(
        "cs_live_probe",
        {"type": "intent_confirmation_challenge",
         "site_key": "c7faac4c-1cd7-4b1b-b2d4-42ba98d09c7a",
         "rqdata": "T+AjOO0JYCbDLoMW",
         "verification_url": "/v1/payment_intents/pi_x/verify_challenge"},
        {"rqdata": "T+AjOO0JYCbDLoMW"},
    )
    rec = json.loads(p.read_text(encoding="utf-8").strip())
    assert rec["cs"] == "cs_live_probe"
    assert rec["site_key"].startswith("c7faac4c")
    assert rec["rqdata_len"] == len("T+AjOO0JYCbDLoMW")
    assert rec["type"] == "intent_confirmation_challenge"


def test_record_radar_challenge_never_raises(monkeypatch):
    """Журнал — вспомогательный: сбой записи не должен ломать прогон."""
    monkeypatch.setattr(config, "RADAR_CHALLENGE_LOG", "Z:\\нет\\такого\\пути.jsonl", raising=False)
    hit_gate.record_radar_challenge("cs_live_x", {}, {})   # не бросает


def test_verdict_says_passive_allowed_when_pass_true():
    rep = {"ok": True, "checksiteconfig": {"pass": True, "type": "hsw"},
           "feature_flags": {"checkout_passive_captcha": True}, "challenges_seen": []}
    v = rc.radar_verdict(rep)
    assert "пассивный проход разрешён" in v and "челленджей на этой сессии не записано" in v


def test_verdict_warns_on_interactive_when_pass_false():
    rep = {"ok": True, "checksiteconfig": {"pass": False, "type": "hsw"},
           "feature_flags": {"checkout_passive_captcha": True}, "challenges_seen": []}
    assert "потребуется интерактивный челлендж" in rc.radar_verdict(rep)


def test_verdict_counts_seen_challenges():
    rep = {"ok": True, "checksiteconfig": {"pass": True, "type": "hsw"},
           "feature_flags": {"checkout_passive_captcha": True},
           "challenges_seen": [{"site_key": "c7faac4c-1cd7-4b1b-b2d4-42ba98d09c7a"}]}
    v = rc.radar_verdict(rep)
    assert "видели 1 раз" in v and "c7faac4c…" in v


def test_verdict_handles_unreadable_link():
    assert "ссылка не читается" in rc.radar_verdict({"ok": False, "detail": "HTTP 404"})
