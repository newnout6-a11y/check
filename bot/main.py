# language: Python 3.12+, file: bot/main.py, target: Windows 11, deps: pyrogram tgcrypto
# Sprint 4: TG-бот поверх движков. Запуск:
#   PUSTO_BOT_TOKEN=... python -m bot.main
# Команды: /start /cmds /me /key <key> /setupwoo cc|mm|yy|cvv /piconfirm cc|mm|yy|cvv
# Админ: /addcredits <uid> <n> /addpremium <uid> <days> /genkey <credits|days:d>
import asyncio
import secrets as _secrets
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pyrogram import Client, filters
from pyrogram.enums import ParseMode
from pyrogram.types import Message

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
        f"<b>PUSTO checker</b>\n{me_line(u)}\n\ngates: {names}\n"
        "format: /gate CC|MM|YY|CVV\n"
        "/cmds — все команды", parse_mode=ParseMode.HTML)


@app.on_message(filters.command(["cmds"]))
async def cmds(client, message: Message):
    lines = ["/start /me /key KEY"] + \
            [f"/{k} CC|MM|YY|CVV" for k in GATES] + \
            ["/addcredits UID N", "/addpremium UID DAYS", "/genkey CREDITS [DAYS] (admin)"]
    await message.reply("\n".join(lines))


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
    parts = argline.split()
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
