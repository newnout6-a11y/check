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


def _card_fields(text: str) -> list[str] | None:
    """CC|MM|YY|CVV / CC MM YY CVV / 4-блочный PAN + MM YY CVV -> [cc, mm, yy, cvv].
    Раньше '4111 1111 1111 1111 09 25 123' парсился как cc=4111 mm=1111 — мусор."""
    parts = text.replace("|", " ").replace(":", " ").replace("/", " ").split()
    if len(parts) == 7 and all(re.fullmatch(r"\d{4}", p) for p in parts[:4]):
        parts = ["".join(parts[:4])] + parts[4:]
    return parts if len(parts) == 4 else None


_PAN_RE = re.compile(r"\d{13,19}")
_MM_RE = re.compile(r"\d{1,2}")
_YY_RE = re.compile(r"\d{2,4}")
_CVV_RE = re.compile(r"\d{3,4}")


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
                and _YY_RE.fullmatch(toks[i + 2]) and _CVV_RE.fullmatch(toks[i + 3])):
            _add([toks[i], toks[i + 1], toks[i + 2], toks[i + 3]])
            i += 4
            continue
        if (i + 6 < len(toks)
                and all(re.fullmatch(r"\d{4}", t) for t in toks[i:i + 4])
                and _MM_RE.fullmatch(toks[i + 4]) and _YY_RE.fullmatch(toks[i + 5])
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
        "💳 <code>/chk</code> cc — авто-выбор поверхности\n"
        "💳 <code>/au</code> cc — Stripe $0 Auth (SetupIntent)\n"
        "💳 <code>/st1</code> <code>/st5</code> <code>/st20</code> cc — Store API (тир: &lt;$1 / $1-5 / $5-20)\n"
        "💳 <code>/sp1</code> <code>/sp5</code> <code>/sp20</code> cc — Shopify Checkout (тир: &lt;$1 / $1-5 / $5-20)\n"
        "⚡ <code>/hit</code> url cc — Stripe Checkout (готовый cs_live-линк)\n"
        "🔍 <code>/bin</code> bin — BIN Lookup\n"
        "📁 <code>/mass</code> [гейт] — Mass Check (≤20 карт, .txt или текст)\n\n"
        "🌐 <b>𝑷𝑹𝑶𝑿𝑰𝑬𝑺</b> 🌐\n\n"
        "📡 <code>/proxy</code> — Check &amp; clean proxies\n"
        "📡 <code>/addproxy</code> — Add proxies (text/file) <i>— админ</i>\n"
        "📡 <code>/clearproxy</code> — Clear all proxies <i>— админ</i>\n\n"
        "📈 <b>𝑰𝑵𝑭𝑶</b> 📈\n\n"
        "📊 <code>/stats</code> — твоя статистика и пул\n"
        "🧩 <code>/gates</code> — какие гейты живы и сколько стоят\n"
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
    proxies = gc.load_proxies()
    if not proxies:
        return await message.reply("📡 <b>Прокси-пул:</b> пуст (прямое подключение)\nДобавить: <code>/addproxy host:port</code> или файлом.", parse_mode=ParseMode.HTML)

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
            parse_mode=ParseMode.HTML)

    # «мёртвый» по ProxyPool = три накопленных фейла, но для ручной чистки
    # считаем неответивших на ЭТОЙ проверке: alive=False или fail_count вырос.
    # Сравниваем по URL, не по словарю: два одинаковых entry дали бы ложное
    # совпадение и выкосили бы живой прокси.
    dead_urls = {e["url"] for e in pool.entries
                 if not e["alive"] or e["fail_count"] > fails_before.get(e["url"], 0)}
    alive_urls = [e["url"] for e in pool.entries if e["url"] not in dead_urls]

    if dead_urls:
        # обратно в файл — тем же форматом, что пишет /addproxy (без схемы).
        # load_proxies() сам вернёт схему при чтении. Непроверенный хвост
        # дописываем как есть — /proxy не должен молча терять прокси.
        os.makedirs("data", exist_ok=True)
        with open(os.path.join("data", "proxies.txt"), "w", encoding="utf-8") as f:
            for url in alive_urls + skipped:
                f.write(url.split("://", 1)[-1] + "\n")

    lats = sorted(e["latency_ms"] for e in pool.entries
                  if e["url"] not in dead_urls and e.get("latency_ms"))
    med = lats[len(lats) // 2] if lats else 0
    lines = [
        f"📡 <b>Прокси-пул:</b> {len(alive_urls)}/{len(checked)} живых",
        f"• Медиана отклика: <b>{med} ms</b>",
        f"• Не ответили: <b>{len(dead_urls)}</b>"
        + (" — удалены из пула" if dead_urls else ""),
    ]
    if skipped:
        lines.append(f"• Не проверено (лимит {PROBE_CAP}): <b>{len(skipped)}</b> — остались в пуле")
    # alive от ProxyPool считает по своим трём страйкам; он мягче нашей чистки,
    # поэтому показываем обе цифры, чтобы не казалось, что они противоречат.
    lines.append(f"• По пулу (3 страйка): <b>{alive}</b> живых")
    if dead_urls:
        sample = ", ".join(html.escape(u.split("://", 1)[-1]) for u in
                           list(dead_urls)[:3])
        lines.append(f"• Примеры: <code>{sample}</code>")
    lines.append("• Управление: <code>/addproxy</code> (админ) | Очистить: <code>/clearproxy</code> (админ)")
    await status.edit_text("\n".join(lines), parse_mode=ParseMode.HTML)


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

    p_path = os.path.join("data", "proxies.txt")
    existing: list[str] = []
    if os.path.exists(p_path):
        try:
            with open(p_path, encoding="utf-8") as f:
                existing = [x.strip() for x in f if x.strip()]
        except Exception:
            existing = []
    # dict.fromkeys сохраняет порядок и режет дубли: /addproxy один и тот же
    # список дважды раздувал пул, а ротация 1/lat потом взвешивала копии
    merged = list(dict.fromkeys(existing + lines))
    _atomic_write_lines(p_path, merged)
    added = len(merged) - len(existing)
    await message.reply(f"✅ Добавлено <b>{added}</b> прокси (дубли отсечены). "
                        f"Всего в пуле: <b>{len(merged)}</b> шт.", parse_mode=ParseMode.HTML)


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
        # формат валидируется ДО списания кредитов — кривой ввод не сжигает баланс.
        # Тот же parse_cards, что в /hit и /mass: запятые в '/chk 4111...,12,30,123'
        # раньше ломались, потому что _card_fields их не ел.
        cards = parse_cards(argline, limit=1)
        parts = cards[0] if cards else None
        if parts is None:
            return await message.reply(f"Формат: /{gate_name} CC MM YY CVV")
        bad = card_rejection(parts)
        if bad:
            return await message.reply(bad)
        cost = (meta["cost"] if meta["cost"] is not None else config.GATE_COST.get(gate_name, 1))
        if not db.spend_credit(u_id, gate_name):
            return await message.reply(f"❌ Недостаточно кредитов ({cost}/чек). Используйте /redeem для пополнения")
        label = gate_label(gate_name, tier)
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
        if verdict == "ERROR":
            db.refund_credit(u_id, gate_name)  # сбой движка — кредит возвращается
        latency_ms = int((asyncio.get_event_loop().time() - t0) * 1000)
        try:
            binfo = await asyncio.wait_for(binfo_task, timeout=4)
        except Exception:
            binfo = {}
        if verdict != "ERROR":
            break
        nxt = _pick_gate(None, exclude=tried)
        if not nxt:
            break
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
        parse_mode=ParseMode.HTML)

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

GATE_PRIORITY = ["setupwoo", "storegate", "shopify", "piconfirm", "braintreenvbv"]


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
        if verdict == "ERROR":
            db.refund_credit(u_id, "hit")
        else:
            price_s = formatter.fmt_price(amount, currency)
            detail = f"[{price_s}] {detail}" if price_s else detail
            if verdict in HIT_VERDICTS:
                db.add_hit(u_id)
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

    if not cards_text.strip():
        return await message.reply(
            "<b>Использование массовой проверки:</b>\n"
            "• <code>/mass [гейт] CC MM YY CVV\nCC MM YY CVV...</code>\n"
            "• Гейт: <code>au</code> / <code>st</code> <code>1|5|20</code> / <code>st1</code> / <code>sp20</code>\n"
            "• Или ответом на .txt файл: <code>/mass [гейт]</code>\n"
            "(Максимум 20 карт за раз)", parse_mode=ParseMode.HTML)

    valid_cards = parse_cards(cards_text, limit=10 ** 6, dedupe=False)

    if not valid_cards:
        return await message.reply("❌ Не найдено карт в подходящем формате (ожидается CC MM YY CVV).")

    if len(valid_cards) > 20:
        await message.reply(f"⚠️ Лимит 20 карт за прогон — взяты первые 20 из {len(valid_cards)}.")
    valid_cards = valid_cards[:20]

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

    u = db.get_user(u_id)
    is_prem = db.is_premium(u)
    if not is_prem and u.get("credits", 0) < len(valid_cards) * cost_per:
        return await message.reply(f"❌ Недостаточно кредитов. Требуется {len(valid_cards) * cost_per} кредитов на {len(valid_cards)} карт.")

    status_msg = await message.reply(
        f"🚀 Запуск массовой проверки ({len(valid_cards)} карт) через <b>{gate_label(gate_name, tier_forced)}</b>...",
        parse_mode=ParseMode.HTML)

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
                if tier_forced and gate_name in ("storegate", "shopify"):
                    res = await meta["fn"](*card_parts, tier=tier_forced)
                else:
                    res = await meta["fn"](*card_parts)
                # гейт волен вернуть 2 или 3 элемента — как в run_gate, а не
                # хрупким распаковыванием в две переменные
                verdict, detail = engine_cfg.coerce_verdict(res[0]), res[1]
            except Exception as e:
                verdict, detail = "ERROR", f"{type(e).__name__}: {e}"[:100]
            if verdict == "ERROR":
                try:
                    db.refund_credit(u_id, gate_name)  # сбой движка — кредит возвращается
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
