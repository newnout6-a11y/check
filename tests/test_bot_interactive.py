# language: Python 3.12+, file: tests/test_bot_interactive.py, target: Windows 11
# Тесты интерактивного управления TG-бота: клавиатуры, выбор цен и шлюзов, рендеры UI, настройки БД.
import importlib
import os
import pytest

from bot import keyboards
import bot.db as bdb


@pytest.fixture()
def custom_db(tmp_path, monkeypatch):
    os.environ.setdefault("PUSTO_BOT_TOKEN", "test_token")
    import bot.config as bcfg
    monkeypatch.setattr(bcfg, "DB_PATH", str(tmp_path / "test_bot.db"))
    import bot.db as db_mod
    importlib.reload(db_mod)
    db_mod.init_db()
    return db_mod


# --- База данных и настройки пользователя ---

def test_db_user_settings_defaults(custom_db):
    custom_db.ensure_user(1001, "test_op")
    settings = custom_db.get_user_settings(1001)
    assert settings["selected_gate"] == "chk"
    assert settings["selected_tier"] == "1"


def test_db_user_set_gate_and_tier(custom_db):
    custom_db.ensure_user(1002, "trader")
    custom_db.set_user_gate(1002, "storegate")
    custom_db.set_user_tier(1002, "5")

    settings = custom_db.get_user_settings(1002)
    assert settings["selected_gate"] == "storegate"
    assert settings["selected_tier"] == "5"

    custom_db.set_user_tier(1002, "20")
    assert custom_db.get_user_settings(1002)["selected_tier"] == "20"


def test_db_schema_version_2(custom_db):
    assert custom_db.SCHEMA_VERSION == 2
    with custom_db._db() as c:
        v = c.execute("PRAGMA user_version").fetchone()[0]
        cols = {r["name"] for r in c.execute("PRAGMA table_info(users)")}
    assert v == 2
    assert "selected_gate" in cols
    assert "selected_tier" in cols


# --- Клавиатуры и разметка ---

def test_main_menu_keyboard_structure():
    kb = keyboards.main_menu_kb(gate="storegate", tier="5", is_admin=False)
    assert kb is not None
    rows = kb.inline_keyboard
    assert len(rows) >= 6

    # Быстрый чек
    assert rows[0][0].callback_data == "menu:prompt_check"

    # Шлюз и цена
    assert "Store API" in rows[1][0].text
    assert rows[1][0].callback_data == "menu:gates"
    assert "$1–$5" in rows[1][1].text
    assert rows[1][1].callback_data == "menu:prices"

    # Админ-панель отсутствует для обычного юзера
    callbacks = [btn.callback_data for row in rows for btn in row]
    assert "menu:admin" not in callbacks


def test_main_menu_keyboard_admin():
    kb = keyboards.main_menu_kb(gate="shopify", tier="20", is_admin=True)
    callbacks = [btn.callback_data for row in kb.inline_keyboard for btn in row]
    assert "menu:admin" in callbacks


def test_gates_menu_keyboard_selection():
    kb = keyboards.gates_menu_kb(current_gate="storegate")
    found_check = False
    for row in kb.inline_keyboard:
        for btn in row:
            if btn.callback_data == "gate:set:storegate":
                assert "✓" in btn.text
                found_check = True
            elif btn.callback_data == "gate:set:shopify":
                assert "✓" not in btn.text
    assert found_check is True


def test_prices_menu_keyboard_selection():
    kb = keyboards.prices_menu_kb(current_tier="5", current_gate="storegate")
    found_tier5 = False
    for row in kb.inline_keyboard:
        for btn in row:
            if btn.callback_data == "tier:set:5":
                assert "✓" in btn.text
                found_tier5 = True
            elif btn.callback_data == "tier:set:1":
                assert "✓" not in btn.text
    assert found_tier5 is True


def test_auxiliary_keyboards():
    assert keyboards.check_prompt_kb("storegate", "1") is not None
    assert keyboards.profile_kb() is not None
    assert keyboards.gates_monitor_kb() is not None
    assert keyboards.proxy_kb(is_admin=True) is not None
    assert keyboards.back_to_menu_kb() is not None
    assert keyboards.admin_kb() is not None


# --- Рендеры сообщений и UI дизайн ---

def test_render_main_menu():
    import bot.main as bm
    u = {"user_id": 9999, "username": "darklord", "credits": 50,
         "total_checks": 120, "hits": 14, "premium_until": 0}
    settings = {"selected_gate": "storegate", "selected_tier": "5"}
    text = bm.render_main_menu(u, settings)

    assert "PUSTO TERMINAL" in text or "𝐏𝐔𝐒𝐓𝐎 𝐓𝐄𝐑𝐌𝐈𝐍𝐀𝐋" in text
    assert "@darklord" in text
    assert "9999" in text
    assert "50" in text
    assert "Store API" in text
    assert "$1–$5" in text


def test_render_prices_menu():
    import bot.main as bm
    settings = {"selected_gate": "shopify", "selected_tier": "20"}
    text = bm.render_prices_menu(settings)

    assert "ВЫБОР ЦЕНОВОГО ТИРА" in text
    assert "Tier 1" in text
    assert "Tier 5" in text
    assert "Tier 20" in text


def test_render_gates_menu():
    import bot.main as bm
    settings = {"selected_gate": "chk", "selected_tier": "1"}
    text = bm.render_gates_menu(settings)

    assert "ВЫБОР ШЛЮЗА ЧЕКА" in text
    assert "Store API" in text
    assert "Shopify" in text
    assert "SetupIntent" in text


def test_render_profile():
    import bot.main as bm
    u = {"user_id": 777, "username": "vip_user", "credits": 100,
         "total_checks": 500, "hits": 45, "premium_until": 9999999999}
    settings = {"selected_gate": "setupwoo", "selected_tier": "1"}
    text = bm.render_profile(u, settings)

    assert "ПРОФИЛЬ ОПЕРАТОРА" in text
    assert "Premium" in text
    assert "100" in text
    assert "500" in text


def test_render_gates_monitor():
    import bot.main as bm
    text = bm.render_gates_monitor()
    assert "МОНИТОР ПОВЕРХНОСТЕЙ" in text
    assert "онлайн" in text or "мерчантов" in text
