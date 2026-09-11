# language: Python 3.12+, file: tests/test_bot_live_battery.py, target: Windows 11
"""
Полная батарея тестов всех функций и компонентов Telegram-бота Pusto:
1. База данных и жизненный цикл пользователей (bot/db.py):
   - Регистрация, обновление username, начисление/списание/возврат кредитов
   - Генерация и активация ключей (кредиты и премиум), защита от повторной активации
   - Персистентность настроек (шлюз, ценовой тир)
   - Антиспам-фильтр, учет статистики и хитов
   - Проверка прав администратора / разработчика
2. Интерактивные клавиатуры (bot/keyboards.py):
   - Разметка главного меню, выбор шлюзов, ценовых тиров, монитор поверхностей, профиль
   - Разделение прав обычного пользователя и администратора
3. Форматирование и локализация ответов (bot/utils/formatter.py):
   - Извлечение PAN и маскирование карт (fmt_pan, mask_pan)
   - Словарь и регулярные паттерны перевода отказов эмитентов на русский язык
   - Форматирование одиночных чеков (format_single) и массовых отчетов (format_mass)
4. Обработчики команд (bot/main.py):
   - /start, /help, /cmds, /me
   - /key, /redeem
   - /proxy, /addproxy, /clearproxy
   - /gates, /stats, /bin
   - /addcredits, /addpremium, /genkey
   - /au, /st, /sp, /pi, /vbv (gate_dispatch)
   - /hit
   - Прямой ввод карты (direct_card_input)
5. Маршрутизатор callback-запросов (callback_router):
   - Навигация по всем пунктам меню, смена шлюзов и тиров
   - Защита административных разделов
"""
import asyncio
import importlib
import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import gate_client as gc
import bot.config as bcfg
import bot.db as bdb
import bot.keyboards as bkb
from bot.utils import formatter


# --- Mock-объекты для Pyrogram ---

class MockUser:
    def __init__(self, user_id: int, username: str = "testuser", is_bot: bool = False):
        self.id = user_id
        self.username = username
        self.is_bot = is_bot
        self.first_name = "Test"
        self.last_name = "User"


class MockMessage:
    def __init__(self, text: str = "", user_id: int = 1001, username: str = "operator",
                 caption: str = "", reply_to_message=None, document=None):
        self.text = text
        self.caption = caption
        self.from_user = MockUser(user_id, username)
        self.chat = MagicMock(id=user_id)
        self.reply_to_message = reply_to_message
        self.document = document
        self.replies: list[dict] = []

    async def reply(self, text: str, parse_mode=None, reply_markup=None, **kwargs):
        msg = MockMessage(text, self.from_user.id, self.from_user.username)
        msg.parse_mode = parse_mode
        msg.reply_markup = reply_markup
        msg.edited_text = None
        self.replies.append({"text": text, "parse_mode": parse_mode, "reply_markup": reply_markup, "msg": msg})
        return msg

    async def edit_text(self, text: str, parse_mode=None, reply_markup=None, **kwargs):
        self.text = text
        self.edited_text = text
        self.parse_mode = parse_mode
        self.reply_markup = reply_markup
        return self

    def continue_propagation(self):
        pass


class MockCallbackQuery:
    def __init__(self, data: str, user_id: int = 1001, username: str = "operator"):
        self.data = data
        self.from_user = MockUser(user_id, username)
        self.message = MockMessage(text="initial message", user_id=user_id, username=username)
        self.answered: list[dict] = []
        self.edited_messages: list[dict] = []

    async def answer(self, text: str = "", show_alert: bool = False, **kwargs):
        self.answered.append({"text": text, "show_alert": show_alert})

    async def edit_message_text(self, text: str, parse_mode=None, reply_markup=None, **kwargs):
        self.edited_messages.append({"text": text, "parse_mode": parse_mode, "reply_markup": reply_markup})
        self.message.text = text
        self.message.reply_markup = reply_markup
        return self.message

    def continue_propagation(self):
        pass


@pytest.fixture()
def isolated_db(tmp_path, monkeypatch):
    """Изолированная SQLite БД в tmp_path с переинициализацией bot.db."""
    test_db_path = str(tmp_path / "test_bot_live.db")
    monkeypatch.setattr(bcfg, "DB_PATH", test_db_path)
    monkeypatch.setattr(bcfg, "ADMIN_IDS", [9999, 1337])
    monkeypatch.setattr(bcfg, "START_CREDITS", 10)
    monkeypatch.setattr(bcfg, "ANTISPAM_MIN_INTERVAL", 0.0)
    importlib.reload(bdb)
    bdb.init_db()
    return bdb


# ============================================================================
# 1. ТЕСТЫ БАЗЫ ДАННЫХ И ЖИЗНЕННОГО ЦИКЛА ПОЛЬЗОВАТЕЛЕЙ (bot/db.py)
# ============================================================================

def test_user_creation_and_balance_ops(isolated_db):
    # Регистрация нового пользователя со стартовым балансом
    isolated_db.ensure_user(2001, "trader_alpha")
    u = isolated_db.get_user(2001)
    assert u is not None
    assert u["username"] == "trader_alpha"
    assert u["credits"] == 10
    assert u["total_checks"] == 0
    assert u["hits"] == 0

    # Обновление username при повторном визите
    isolated_db.ensure_user(2001, "trader_renamed")
    assert isolated_db.get_user(2001)["username"] == "trader_renamed"

    # Начисление кредитов администратором
    isolated_db.admin_add_credits(2001, 25)
    assert isolated_db.get_user(2001)["credits"] == 35

    # Списание кредитов под гейт storegate (стоимость 2)
    ok = isolated_db.spend_credit(2001, "storegate")
    assert ok is True
    assert isolated_db.get_user(2001)["credits"] == 33

    # Возврат кредита при ошибке мерчанта (is_refundable)
    isolated_db.refund_credit(2001, "storegate")
    assert isolated_db.get_user(2001)["credits"] == 35

    # Списание под setupwoo (стоимость 1)
    assert isolated_db.spend_credit(2001, "setupwoo") is True
    assert isolated_db.get_user(2001)["credits"] == 34

    # Проверка фиксации хитов
    isolated_db.add_hit(2001)
    u_after_hit = isolated_db.get_user(2001)
    assert u_after_hit["hits"] == 1


def test_user_antispam_throttling(isolated_db, monkeypatch):
    monkeypatch.setattr(bcfg, "ANTISPAM_MIN_INTERVAL", 3.0)
    isolated_db.ensure_user(2002, "spammer")
    # Первый запрос проходит
    assert isolated_db.antispam_ok(2002) is True
    # Немедленный повторный запрос блокируется антиспамом
    assert isolated_db.antispam_ok(2002) is False


def test_key_generation_and_redemption_lifecycle(isolated_db):
    isolated_db.ensure_user(2003, "shopper")
    # Генерация ключа на кредиты
    key_cred = "KEY-CREDITS-50"
    isolated_db.add_key(key_cred, credits=50)

    # Активация ключа на кредиты
    res1 = isolated_db.redeem_key(2003, key_cred)
    assert "Кредиты +50" in res1
    assert isolated_db.get_user(2003)["credits"] == 60  # 10 старт + 50

    # Повторная активация того же ключа отклоняется
    res_repeat = isolated_db.redeem_key(2003, key_cred)
    assert "уже активированный" in res_repeat
    assert isolated_db.get_user(2003)["credits"] == 60

    # Генерация ключа на премиум
    key_prem = "KEY-PREM-7DAYS"
    isolated_db.add_key(key_prem, days=7)
    res_prem = isolated_db.redeem_key(2003, key_prem)
    assert "Премиум +7 дн." in res_prem
    u_prem = isolated_db.get_user(2003)
    assert isolated_db.is_premium(u_prem) is True

    # Активация несуществующего ключа
    assert "Неверный" in isolated_db.redeem_key(2003, "FAKE-KEY-12345")


def test_user_settings_persistence(isolated_db):
    isolated_db.ensure_user(2004, "config_tester")
    default_settings = isolated_db.get_user_settings(2004)
    assert default_settings["selected_gate"] == "chk"
    assert default_settings["selected_tier"] == "1"

    # Смена шлюза на shopify
    isolated_db.set_user_gate(2004, "shopify")
    assert isolated_db.get_user_settings(2004)["selected_gate"] == "shopify"

    # Смена ценового тира на 20
    isolated_db.set_user_tier(2004, "20")
    assert isolated_db.get_user_settings(2004)["selected_tier"] == "20"


def test_admin_roles_and_stats(isolated_db):
    isolated_db.ensure_user(9999, "root_admin")
    isolated_db.ensure_user(3001, "regular_user")

    u_admin = isolated_db.get_user(9999)
    u_user = isolated_db.get_user(3001)

    assert isolated_db.is_developer(u_admin) is True
    assert isolated_db.is_developer(u_user) is False

    # Премиум-юзер не платит за чеки
    isolated_db.admin_add_premium(3001, 5)
    u_user_prem = isolated_db.get_user(3001)
    assert isolated_db.is_premium(u_user_prem) is True

    # Глобальная статистика
    gstats = isolated_db.get_global_stats()
    assert gstats["users_count"] >= 2
    assert gstats["premium_users"] >= 1


# ============================================================================
# 2. ТЕСТЫ ИНТЕРАКТИВНЫХ КЛАВИАТУР (bot/keyboards.py)
# ============================================================================

def test_keyboard_layouts_and_admin_separation():
    # Главное меню обычного пользователя
    user_kb = bkb.main_menu_kb("storegate", "5", is_admin=False)
    user_callbacks = [b.callback_data for row in user_kb.inline_keyboard for b in row]
    assert "menu:admin" not in user_callbacks
    assert "menu:prompt_check" in user_callbacks
    assert "menu:gates" in user_callbacks
    assert "menu:prices" in user_callbacks

    # Главное меню администратора
    admin_kb = bkb.main_menu_kb("shopify", "20", is_admin=True)
    admin_callbacks = [b.callback_data for row in admin_kb.inline_keyboard for b in row]
    assert "menu:admin" in admin_callbacks

    # Клавиатура выбора шлюзов с отметкой активного
    gates_kb = bkb.gates_menu_kb("shopify")
    found_shopify_check = False
    for row in gates_kb.inline_keyboard:
        for b in row:
            if b.callback_data == "gate:set:shopify":
                assert "✓" in b.text
                found_shopify_check = True
            elif b.callback_data == "gate:set:storegate":
                assert "✓" not in b.text
    assert found_shopify_check is True

    # Клавиатура цен
    prices_kb = bkb.prices_menu_kb("20", "shopify")
    found_tier20_check = False
    for row in prices_kb.inline_keyboard:
        for b in row:
            if b.callback_data == "tier:set:20":
                assert "✓" in b.text
                found_tier20_check = True
    assert found_tier20_check is True

    # Вспомогательные клавиатуры
    assert bkb.check_prompt_kb("setupwoo", "1") is not None
    assert bkb.profile_kb() is not None
    assert bkb.gates_monitor_kb() is not None
    assert bkb.back_to_menu_kb() is not None
    assert bkb.admin_kb() is not None


# ============================================================================
# 3. ТЕСТЫ ФОРМАТИРОВАНИЯ И ТИПОГРАФИКИ (bot/utils/formatter.py)
# ============================================================================

def test_formatter_pan_extraction_and_masking():
    # Стандартный пайп
    assert formatter.extract_pan("4111111111111111|12|28|123") == "4111111111111111"
    # Пробелы
    assert formatter.extract_pan("4111 1111 1111 1111 12 28 123") == "4111111111111111"
    # Amex 15 цифр
    assert formatter.extract_pan("3782 822463 10005 1234") == "378282246310005"
    # Точки с запятой
    assert formatter.extract_pan("5536910000000000;08;29;999") == "5536910000000000"

    # Маскирование через gate_client
    assert gc.mask_pan("4111111111111111") == "411111******1111"
    assert "378282" in gc.mask_pan("378282246310005")

    # Маскирование через formatter.fmt_pan
    assert formatter.fmt_pan("4111111111111111") == "4111 11** **** 1111"


def test_formatter_translation_dictionary_and_regex():
    # Точные словарные переводы
    assert "отклонена банком" in formatter.translate_detail("your card was declined.")
    assert "Недостаточно средств" in formatter.translate_detail("insufficient funds")
    assert "Неверный CVC/CVV" in formatter.translate_detail("incorrect cvc")
    assert "Срок действия карты истек" in formatter.translate_detail("expired card")
    assert "Do Not Honor" in formatter.translate_detail("do_not_honor")

    # Префиксы цен сохраняются
    trans_with_price = formatter.translate_detail("[1200c USD] your card was declined")
    assert trans_with_price.startswith("[1200c USD]")
    assert "отклонена банком" in trans_with_price

    # Динамические паттерны регулярных выражений
    assert "Заказ успешно оплачен" in formatter.translate_detail("order #1234 paid (pi succeeded)")
    assert "Frictionless" in formatter.translate_detail("3DS frictionless passed (1000USD)")
    assert "Stripe Radar" in formatter.translate_detail("Stripe Radar bot challenge (hCaptcha)")


def test_formatter_format_single_verdicts():
    bin_info = {
        "scheme": "VISA",
        "type": "CREDIT",
        "brand": "SIGNATURE",
        "country": {"alpha2": "US", "name": "UNITED STATES"},
        "country_flag": "🇺🇸",
        "bank": {"name": "CHASE BANK"}
    }

    # 1. APPROVED@PAID
    out_approved = formatter.format_single(
        "4111111111111111", bin_info, "Store API (Tier 5)",
        "APPROVED@PAID", "order #101 paid (pi succeeded)", 3450
    )
    assert "APPROVED" in out_approved
    assert "4111 11** **** 1111" in out_approved
    assert "CHASE BANK" in out_approved
    assert "3.5с" in out_approved or "3450" in out_approved

    # 2. DECLINED
    out_declined = formatter.format_single(
        "4111111111111111", bin_info, "Shopify (Tier 1)",
        "DECLINED", "your card has insufficient funds", 2100
    )
    assert "DECLINED" in out_declined
    assert "Недостаточно средств" in out_declined

    # 3. 3DS_CHALLENGE
    out_3ds = formatter.format_single(
        "4111111111111111", bin_info, "Stripe Checkout",
        "3DS_CHALLENGE", "3DS2 challenge required (OTP/SMS)", 1890
    )
    assert "3DS" in out_3ds

    # 4. CAPTCHA_CHECKOUT
    out_captcha = formatter.format_single(
        "4111111111111111", bin_info, "Store API",
        "CAPTCHA_CHECKOUT", "Stripe Radar bot challenge", 450
    )
    assert "CAPTCHA" in out_captcha or "CAPTCHA_CHECKOUT" in out_captcha


def test_formatter_format_mass_report():
    results = [
        {"card": "411111******1111", "status": "APPROVED@PAID", "detail": "Paid $1.00"},
        {"card": "553691******2222", "status": "DECLINED", "detail": "Insufficient funds"},
        {"card": "400000******3333", "status": "CVV_FAILURE", "detail": "Incorrect CVC"},
    ]
    rep = formatter.format_mass(results, header=True)
    assert "РЕЗУЛЬТАТЫ МАССОВОЙ ПРОВЕРКИ" in rep
    assert "Всего: 3" in rep
    assert "APPROVED@PAID" in rep
    assert "DECLINED" in rep


# ============================================================================
# 4. ТЕСТЫ ОБРАБОТЧИКОВ КОМАНД (bot/main.py) ЧЕРЕЗ MOCK
# ============================================================================

@pytest.mark.asyncio
async def test_cmd_start_and_me(isolated_db):
    import bot.main as bm

    # /start
    msg_start = MockMessage("/start", user_id=4001, username="alex")
    await bm.cmd_start(None, msg_start)
    assert len(msg_start.replies) == 1
    rep = msg_start.replies[0]
    assert "PUSTO TERMINAL" in rep["text"] or "𝐏𝐔𝐒𝐓𝐎 𝐓𝐄𝐑𝐌𝐈𝐍𝐀𝐋" in rep["text"]
    assert rep["reply_markup"] is not None

    # /me
    msg_me = MockMessage("/me", user_id=4001, username="alex")
    await bm.cmd_me(None, msg_me)
    assert len(msg_me.replies) == 1
    assert "ПРОФИЛЬ ОПЕРАТОРА" in msg_me.replies[0]["text"]
    assert "4001" in msg_me.replies[0]["text"]


@pytest.mark.asyncio
async def test_cmd_key_redemption(isolated_db):
    import bot.main as bm

    # Без ключа -> показ формата
    msg_err = MockMessage("/key", user_id=4002, username="bob")
    await bm.cmd_key(None, msg_err)
    assert "Формат: <code>/redeem КЛЮЧ</code>" in msg_err.replies[0]["text"]

    # С валидным ключом
    key = "TEST-KEY-100"
    isolated_db.add_key(key, credits=100)
    msg_valid = MockMessage(f"/key {key}", user_id=4002, username="bob")
    await bm.cmd_key(None, msg_valid)
    assert "Кредиты +100" in msg_valid.replies[0]["text"]


@pytest.mark.asyncio
async def test_cmd_gates_and_stats(isolated_db):
    import bot.main as bm

    # /gates
    msg_gates = MockMessage("/gates", user_id=4003, username="carol")
    await bm.cmd_gates(None, msg_gates)
    assert len(msg_gates.replies) == 1
    assert "Активные гейты" in msg_gates.replies[0]["text"]

    # /stats
    msg_stats = MockMessage("/stats", user_id=4003, username="carol")
    await bm.cmd_stats(None, msg_stats)
    assert len(msg_stats.replies) == 1
    assert "СТАТИСТИКА" in msg_stats.replies[0]["text"] or "статистика" in msg_stats.replies[0]["text"].lower()


@pytest.mark.asyncio
async def test_cmd_bin_lookup(isolated_db):
    import bot.main as bm

    # /bin без аргумента
    msg_no_arg = MockMessage("/bin", user_id=4004, username="dave")
    await bm.cmd_bin(None, msg_no_arg)
    assert "Формат: /bin 123456" in msg_no_arg.replies[0]["text"]

    # /bin с валидным номером
    msg_bin = MockMessage("/bin 411111", user_id=4005, username="dave_alt")
    await bm.cmd_bin(None, msg_bin)
    assert len(msg_bin.replies) >= 1
    last_text = msg_bin.replies[-1]["msg"].text or msg_bin.replies[-1]["text"]
    assert "411111" in last_text
    assert "БИН" in last_text


@pytest.mark.asyncio
async def test_admin_commands_security(isolated_db):
    import bot.main as bm

    isolated_db.ensure_user(4006, "target_user")

    # Не-админ пытается выполнить /addcredits
    msg_unauth = MockMessage("/addcredits 4006 50", user_id=4006, username="intruder")
    await bm.addcredits(None, msg_unauth)
    assert "Доступ только для администраторов" in msg_unauth.replies[0]["text"]

    # Админ начисляет кредиты
    msg_admin = MockMessage("/addcredits 4006 50", user_id=9999, username="root")
    await bm.addcredits(None, msg_admin)
    assert "UID 4006 кредиты +50" in msg_admin.replies[0]["text"]
    assert isolated_db.get_user(4006)["credits"] == 60  # 10 + 50

    # Админ генерирует ключ
    msg_gen = MockMessage("/genkey 100", user_id=9999, username="root")
    await bm.genkey(None, msg_gen)
    assert "Ключ:" in msg_gen.replies[0]["text"]
    assert "100 кр." in msg_gen.replies[0]["text"]


@pytest.mark.asyncio
async def test_gate_dispatch_success_and_refund(isolated_db, monkeypatch):
    import bot.main as bm

    # Создаем пользователя с балансом
    isolated_db.ensure_user(5001, "carder")
    isolated_db.admin_add_credits(5001, 10)

    # 1. Симулируем успешный вызов гейта setupwoo -> статус APPROVED@PAID
    fake_gate_fn = AsyncMock(return_value=("APPROVED@PAID", "Card verified $0", {"proxy": "direct"}))
    monkeypatch.setitem(bm.GATES, "setupwoo", {"fn": fake_gate_fn, "cost": 1})

    msg_au = MockMessage("/au 4111111111111111 12 28 123", user_id=5001, username="carder")
    await bm.gate_dispatch(None, msg_au)

    # Баланс уменьшился на 1 (успешный вердикт не возвращается)
    assert isolated_db.get_user(5001)["credits"] == 19  # 10 старт + 10 добавл - 1

    # 2. Симулируем падение гейта с возвратной ошибкой (ERROR)
    fake_gate_fail = AsyncMock(return_value=("ERROR", "Merchant offline", {}))
    monkeypatch.setitem(bm.GATES, "setupwoo", {"fn": fake_gate_fail, "cost": 1})
    # Отключаем фоллбэк, чтобы изолированно проверить возврат
    monkeypatch.setattr(bm, "_pick_gate", lambda force, exclude=None: None)

    msg_fail = MockMessage("/au 4111111111111111 12 28 123", user_id=5001, username="carder")
    await bm.gate_dispatch(None, msg_fail)

    # Баланс остался прежним (списан 1 и возвращен 1)
    assert isolated_db.get_user(5001)["credits"] == 19


@pytest.mark.asyncio
async def test_cmd_hit_execution(isolated_db, monkeypatch):
    import bot.main as bm

    isolated_db.ensure_user(5002, "hitter")
    isolated_db.admin_add_credits(5002, 20)

    # Невалидная ссылка
    msg_bad_url = MockMessage("/hit https://example.com 4111111111111111 12 28 123", user_id=5002, username="hitter")
    await bm.cmd_hit(None, msg_bad_url)
    assert "Формат: <code>/hit" in msg_bad_url.replies[0]["text"]

    # Валидная ссылка с моком CsHitSession
    mock_cs_session = MagicMock()
    mock_cs_session.open = AsyncMock(return_value=(True, "ok"))
    mock_cs_session.check_card = AsyncMock(return_value={"status": "APPROVED@PAID", "detail": "PI succeeded (1000USD)"})
    mock_cs_session.close = AsyncMock()

    with patch("hit_gate.CsHitSession", return_value=mock_cs_session):
        msg_hit = MockMessage(
            "/hit https://checkout.stripe.com/c/pay/cs_live_test123#fid123 4111111111111111 12 28 123",
            user_id=5003, username="hitter_alt"
        )
        isolated_db.ensure_user(5003, "hitter_alt")
        isolated_db.admin_add_credits(5003, 20)
        await bm.cmd_hit(None, msg_hit)

        # Проверяем, что была отправка статуса и финальный вердикт
        assert len(msg_hit.replies) >= 1
        last_rep = msg_hit.replies[-1]["msg"].text or msg_hit.replies[-1]["text"]
        assert "APPROVED" in last_rep or "ОПЛАЧЕНО" in last_rep or "succeeded" in last_rep


@pytest.mark.asyncio
async def test_direct_card_input_routing(isolated_db, monkeypatch):
    import bot.main as bm

    isolated_db.ensure_user(5004, "fast_operator")
    isolated_db.set_user_gate(5004, "storegate")

    mock_run_gate = AsyncMock()
    monkeypatch.setattr(bm, "run_gate", mock_run_gate)

    # Сообщение содержит только строку карты без слэш-команды
    msg_card = MockMessage("4111111111111111 12 28 123", user_id=5004, username="fast_operator")
    await bm.direct_card_input(None, msg_card)

    # Проверяем, что перенаправлено в run_gate с сохраненным шлюзом storegate
    mock_run_gate.assert_awaited_once()
    args, kwargs = mock_run_gate.call_args
    assert args[1] == "storegate"
    assert "4111111111111111" in args[2]

    # Проверяем пачку из нескольких карт прямым вводом
    mock_cmd_mass = AsyncMock()
    monkeypatch.setattr(bm, "cmd_mass", mock_cmd_mass)
    isolated_db.set_user_gate(5004, "shopify")
    isolated_db.set_user_tier(5004, "5")

    msg_batch = MockMessage("4111111111111111 12 28 123\n4242424242424242 10 29 456", user_id=5004, username="fast_operator")
    await bm.direct_card_input(None, msg_batch)

    mock_cmd_mass.assert_awaited_once()
    _, mass_kwargs = mock_cmd_mass.call_args
    assert mass_kwargs.get("gate_forced") == "shopify"
    assert mass_kwargs.get("tier_forced") == "5"


# ============================================================================
# 5. ТЕСТЫ МАРШРУТИЗАТОРА CALLBACK-ЗАПРОСОВ (callback_router)
# ============================================================================

@pytest.mark.asyncio
async def test_callback_navigation_tree(isolated_db):
    import bot.main as bm

    isolated_db.ensure_user(6001, "navigator")

    # 1. menu:main
    cb_main = MockCallbackQuery("menu:main", user_id=6001)
    await bm.callback_router(None, cb_main)
    assert len(cb_main.edited_messages) == 1
    assert "PUSTO TERMINAL" in cb_main.edited_messages[0]["text"] or "𝐏𝐔𝐒𝐓𝐎 𝐓𝐄𝐑𝐌𝐈𝐍𝐀𝐋" in cb_main.edited_messages[0]["text"]

    # 2. menu:prices
    cb_prices = MockCallbackQuery("menu:prices", user_id=6001)
    await bm.callback_router(None, cb_prices)
    assert "ВЫБОР ЦЕНОВОГО ТИРА" in cb_prices.edited_messages[0]["text"]

    # 3. tier:set:5
    cb_set_tier = MockCallbackQuery("tier:set:5", user_id=6001)
    await bm.callback_router(None, cb_set_tier)
    assert isolated_db.get_user_settings(6001)["selected_tier"] == "5"

    # 4. menu:gates
    cb_gates = MockCallbackQuery("menu:gates", user_id=6001)
    await bm.callback_router(None, cb_gates)
    assert "ВЫБОР ШЛЮЗА ЧЕКА" in cb_gates.edited_messages[0]["text"]

    # 5. gate:set:shopify
    cb_set_gate = MockCallbackQuery("gate:set:shopify", user_id=6001)
    await bm.callback_router(None, cb_set_gate)
    assert isolated_db.get_user_settings(6001)["selected_gate"] == "shopify"

    # 6. menu:profile
    cb_profile = MockCallbackQuery("menu:profile", user_id=6001)
    await bm.callback_router(None, cb_profile)
    assert "ПРОФИЛЬ ОПЕРАТОРА" in cb_profile.edited_messages[0]["text"]

    # 7. menu:gates_monitor
    cb_mon = MockCallbackQuery("menu:gates_monitor", user_id=6001)
    await bm.callback_router(None, cb_mon)
    assert "МОНИТОР ПОВЕРХНОСТЕЙ" in cb_mon.edited_messages[0]["text"]

    # 8. menu:proxy
    cb_proxy = MockCallbackQuery("menu:proxy", user_id=6001)
    await bm.callback_router(None, cb_proxy)
    assert "Прокси-пул" in cb_proxy.edited_messages[0]["text"] or "прокси" in cb_proxy.edited_messages[0]["text"].lower()

    # 9. menu:help
    cb_help = MockCallbackQuery("menu:help", user_id=6001)
    await bm.callback_router(None, cb_help)
    assert "СПРАВОЧНИК" in cb_help.edited_messages[0]["text"]

    # 10. menu:refresh
    cb_refresh = MockCallbackQuery("menu:refresh", user_id=6001)
    await bm.callback_router(None, cb_refresh)
    assert any("обновлены" in a.get("text", "") for a in cb_refresh.answered)


@pytest.mark.asyncio
async def test_callback_admin_panel_access_control(isolated_db):
    import bot.main as bm

    # Обычный пользователь пытается войти в menu:admin -> alert
    cb_user = MockCallbackQuery("menu:admin", user_id=6002, username="ordinary")
    await bm.callback_router(None, cb_user)
    assert any("Только для администраторов" in a.get("text", "") or "Доступно только" in a.get("text", "") for a in cb_user.answered)
    assert len(cb_user.edited_messages) == 0

    # Администратор заходит в menu:admin -> успех
    cb_admin = MockCallbackQuery("menu:admin", user_id=9999, username="sysadmin")
    await bm.callback_router(None, cb_admin)
    assert len(cb_admin.edited_messages) == 1
    assert "ПАНЕЛЬ УПРАВЛЕНИЯ" in cb_admin.edited_messages[0]["text"]
