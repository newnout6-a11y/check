# language: Python, file: tests/test_audit_drift_fixes.py
import glob
import json
import os
from pathlib import Path
import pytest
from unittest.mock import patch, MagicMock

import proxy_manager
from bot.gates import piconfirm, storegate

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"


def test_drift_01_store_gates_no_duplicate_domains():
    """DRIFT-01: data/store_gates.json must not contain duplicate domains."""
    with open(DATA / "store_gates.json", encoding="utf-8") as f:
        gates = json.load(f)
    domains = [g["domain"] for g in gates if "domain" in g]
    assert len(domains) == len(set(domains)), f"Duplicates found: {[d for d in domains if domains.count(d) > 1]}"


def test_drift_01_store_targets_all_verified():
    """DRIFT-01: all entries in data/store_targets.txt must be verified in store_gates.json."""
    with open(DATA / "store_gates.json", encoding="utf-8") as f:
        gates = json.load(f)
    verified_map = {g["domain"]: g.get("verified") for g in gates if "domain" in g}

    with open(DATA / "store_targets.txt", encoding="utf-8") as f:
        targets = [ln.strip().replace("https://", "").rstrip("/") for ln in f if ln.strip().startswith("http")]

    assert len(targets) == 20
    for t in targets:
        assert verified_map.get(t) is True, f"Domain {t} is not verified: true in store_gates.json"


def test_drift_02_pi_targets_file_exists_and_piconfirm_ignores_comments():
    """DRIFT-02: data/pi_target.txt must exist and comments must be ignored."""
    assert (DATA / "pi_target.txt").exists()
    assert (DATA / "braintree_targets.txt").exists()
    # When file only contains comments and env is empty, target should be empty string without error
    with patch.dict(os.environ, {}, clear=True):
        t = piconfirm._target()
        assert t == "" or t.startswith("http")


def test_drift_09_proxy_validate_interval():
    """DRIFT-09: proxy_manager.VALIDATE_INTERVAL must be 15 minutes (900s)."""
    assert proxy_manager.VALIDATE_INTERVAL == 15 * 60


def test_drift_12_scratch_no_utf8_bom():
    """DRIFT-12: No python files in scratch/ should contain UTF-8 BOM."""
    scratch_py = list((ROOT / "scratch").glob("**/*.py"))
    assert len(scratch_py) > 0
    for p in scratch_py:
        with open(p, "rb") as f:
            head = f.read(3)
            assert head != b"\xef\xbb\xbf", f"UTF-8 BOM found in {p}"
