# language: Python 3.12+, file: tests/test_round7_fixes.py, target: Windows 11
# Регрессионные тесты раунда 7 (docs/АРХИТЕКТУРА-2026-08-30.md §10, дефекты D-1..D-3).
#   D-1  needs_live_check отсекал из ротации уже верифицированные Shopify-магазины
#   D-2  bin_cache.init_db() звался только из тестов — в бою схема не создавалась
#   D-3  команда /chk отсутствовала, авто-выбор гейта был недостижим
import json
import os

import pytest

import bin_cache
from bot.gates import shopify as bg_shopify


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SHOPIFY_GATES = os.path.join(ROOT, "data", "shopify_gates.json")


def _shopify_pool() -> list[dict]:
    with open(SHOPIFY_GATES, encoding="utf-8") as f:
        return json.load(f)


# --- D-1: needs_live_check — запрос на проверку, а не приговор ---

def test_unchecked_domains_skips_verified():
    """Магазин с verified=True не может быть отсечён флагом needs_live_check.

    В раунде 6.3 двадцать tavily-кандидатов прошли боевую верификацию, но флаг
    снят не был — ротация падала с 63 до 43 магазинов."""
    pool = _shopify_pool()
    unchecked = bg_shopify._unchecked_domains()
    offenders = [g["domain"] for g in pool
                 if g.get("verified") and g.get("domain") in unchecked]
    assert offenders == [], f"верифированные магазины выпали из ротации: {offenders[:5]}"


def test_unchecked_domains_still_blocks_unverified():
    """Обратная сторона: неверифицированные кандидаты по-прежнему не в бою."""
    pool = _shopify_pool()
    unchecked = bg_shopify._unchecked_domains()
    waiting = [g["domain"] for g in pool
               if g.get("needs_live_check") and not g.get("verified") and g.get("domain")]
    assert waiting, "в пуле нет кандидатов, ожидающих проверки — тест теряет смысл"
    assert set(waiting) <= unchecked


def test_shopify_rotation_uses_verified_pool():
    """Ротация покрывает подтверждённые боем магазины, а не их подмножество."""
    pool = _shopify_pool()
    dead = bg_shopify._dead_domains()
    reachable = {t.replace("https://", "").replace("http://", "").rstrip("/")
                 for t in bg_shopify._targets()}
    missed = [g["domain"] for g in pool
              if g.get("verified") and g.get("domain") not in dead
              and g["domain"] not in reachable]
    # магазин может отсутствовать в shopify_targets.txt — тогда его не в чем винить
    in_file = {ln.strip().replace("https://", "").rstrip("/")
               for ln in open(os.path.join(ROOT, "data", "shopify_targets.txt"),
                              encoding="utf-8") if ln.strip().startswith("http")}
    missed = [d for d in missed if d in in_file]
    assert missed == [], f"живые магазины не попали в ротацию: {missed[:5]}"


# --- D-2: кэш BIN должен работать без явного init_db() ---

@pytest.fixture()
def fresh_cache(tmp_path, monkeypatch):
    """Подмена DB_PATH БЕЗ вызова init_db() — именно так кэш используется в бою."""
    monkeypatch.setattr(bin_cache, "DB_PATH", str(tmp_path / "bin_cache.db"))
    return bin_cache


def test_cache_works_without_explicit_init(fresh_cache):
    """init_db() никто не звал в продакшене — схема должна встать сама."""
    info = {"scheme": "visa", "country": {"alpha2": "US"}}
    fresh_cache.put("411111", info)
    assert fresh_cache.get("411111") == info


def test_cache_miss_without_explicit_init_is_silent(fresh_cache):
    """Промах по несуществующей схеме — None, а не исключение."""
    assert fresh_cache.get("999999") is None


# --- D-3: /chk — авто-выбор поверхности ---

def test_chk_command_registered():
    import bot.main as bm
    assert "chk" in bm.ALL_GATE_CMDS


def test_pick_gate_returns_available_gate():
    """_pick_gate(None) — то, чем стал /chk: первый гейт с реально настроенными целями."""
    import bot.main as bm
    chosen = bm._pick_gate(None)
    assert chosen in bm.GATES, f"авто-выбор вернул '{chosen}', которого нет в реестре"
    assert chosen in bm._available_gates()


def test_chk_never_resolves_to_dead_gate():
    """Гейты без целей (piconfirm, braintreenvbv) авто-выбором не выбираются."""
    import bot.main as bm
    dead_without_targets = {"piconfirm", "braintreenvbv"} - set(bm._available_gates())
    chosen = bm._pick_gate(None)
    assert chosen not in dead_without_targets


def test_price_tier_parsed_by_target_gate():
    """Тир разбирается таблицей целевого гейта: у shopify границы (0,100)/(101,500),
    у storegate — (0,100)/(100,500). Токен '5' обязан давать окно своего гейта."""
    from bot.gates import storegate as bg_store
    assert bg_shopify.parse_tier("5") == (101, 500)
    assert bg_store.parse_tier("5") == (100, 500)
