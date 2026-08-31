# language: Python 3.13+, file: scratch/_bot_handler_probe.py, target: Windows 11
# Разрешение команд бота через РЕАЛЬНЫЕ фильтры pyrogram — без сети и без Telegram.
# Импортируем bot.main (он регистрирует хендлеры на app), затем для каждой команды
# из меню прогоняем текст через фильтры и смотрим, какой хендлер её ловит.
#
# ВАЖНО: filters.command — корутина. f(c, msg) без await ВСЕГДА truthy, поэтому
# старый тест «всё MATCH» был ложью. Здесь await обязателен.
#
# Запуск: python scratch/_bot_handler_probe.py
import asyncio
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import pyrogram  # noqa: E402
from pyrogram.enums import ChatType  # noqa: E402

import bot.main as M  # noqa: E402


class FakeMe:
    username = "pusto_test_bot"


class FakeClient:
    me = FakeMe()


class FakeUser:
    def __init__(self, uid):
        self.id = uid
        self.username = "dj"
        self.first_name = "dj"


class FakeChat:
    type = ChatType.PRIVATE
    id = 1


class FakeMessage:
    def __init__(self, text, uid):
        self.text = text
        self.caption = None
        self.chat = FakeChat()
        self.from_user = FakeUser(uid)
        self.command = None
        self.outgoing = False


def iter_handlers(app):
    """Все MessageHandler, зарегистрированные на клиенте, по группам."""
    groups = getattr(app.dispatcher, "groups", {}) or {}
    for group in sorted(groups):
        for h in groups[group]:
            yield group, h


async def resolve(app, text, uid):
    """Возвращает список (group, имя_колбэка) хендлеров, чьи фильтры матчат текст."""
    client, msg = FakeClient(), FakeMessage(text, uid)
    hits = []
    for group, h in iter_handlers(app):
        flt = getattr(h, "filters", None)
        if flt is None:
            continue
        try:
            ok = await flt(client, msg)
        except Exception as e:  # фильтр упал — считаем, что не матчит, но сообщаем
            hits.append((group, f"ИСКЛЮЧЕНИЕ {type(e).__name__}: {e}", None))
            continue
        if ok:
            cb = h.callback
            name = getattr(cb, "__name__", repr(cb))
            # filters.command кладёт распознанную команду в message.command[0]
            hits.append((group, name, (msg.command or [None])[0]))
    return hits


# Полный список команд, которые бот объявляет или обязан объявлять.
ADMIN_ID = sorted(M.config.ADMIN_IDS)[0] if M.config.ADMIN_IDS else 1
FREEMAN_ID = 999_999_999  # заведомо не админ — проверяем, что публичные команды доступны всем

CHECKS = [
    # (текст сообщения, uid, ожидаемый хендлер, пометка)
    ("/start",                          FREEMAN_ID, "cmd_start",      "публичная"),
    ("/cmds",                           FREEMAN_ID, "cmd_start",      "публичная"),
    ("/help",                           FREEMAN_ID, "cmd_start",      "публичная"),
    ("/me",                             FREEMAN_ID, "cmd_me",         "публичная"),
    ("/redeem ABC-DEF",                 FREEMAN_ID, "cmd_key",        "публичная"),
    ("/key ABC-DEF",                    FREEMAN_ID, "cmd_key",        "публичная"),
    ("/bin 411111",                     FREEMAN_ID, "cmd_bin",        "публичная"),
    ("/gates",                          FREEMAN_ID, "cmd_gates",      "публичная"),
    ("/stats",                          FREEMAN_ID, "cmd_stats",      "публичная"),
    ("/proxy",                          FREEMAN_ID, "cmd_proxy",      "публичная"),
    ("/addproxy 1.2.3.4:8080",          ADMIN_ID,   "cmd_addproxy",   "админ"),
    ("/clearproxy",                     ADMIN_ID,   "cmd_clearproxy", "админ"),
    ("/hit https://x cs_live_x 4111111111111111 12 30 123", FREEMAN_ID, "cmd_hit", "публичная"),
    ("/mass 4111111111111111 12 30 123", FREEMAN_ID, "cmd_mass",      "публичная"),
    ("/mass st5 4111111111111111 12 30 123", FREEMAN_ID, "cmd_mass",  "публичная"),
    ("/chk 4111111111111111 12 30 123", FREEMAN_ID, "gate_dispatch",  "публичная"),
    ("/au 4111111111111111 12 30 123",  FREEMAN_ID, "gate_dispatch",  "публичная"),
    ("/st 4111111111111111 12 30 123",  FREEMAN_ID, "gate_dispatch",  "публичная"),
    ("/sp 4111111111111111 12 30 123",  FREEMAN_ID, "gate_dispatch",  "публичная"),
    # ТО, ЧТО БЫЛО МЕРТВО: /st1 /st5 /st20 /sp1 /sp5 /sp20
    ("/st1 4111111111111111 12 30 123", FREEMAN_ID, "gate_dispatch",  "БЫЛО МЕРТВО"),
    ("/st5 4111111111111111 12 30 123", FREEMAN_ID, "gate_dispatch",  "БЫЛО МЕРТВО"),
    ("/st20 4111111111111111 12 30 123", FREEMAN_ID, "gate_dispatch", "БЫЛО МЕРТВО"),
    ("/sp1 4111111111111111 12 30 123", FREEMAN_ID, "gate_dispatch",  "БЫЛО МЕРТВО"),
    ("/sp5 4111111111111111 12 30 123", FREEMAN_ID, "gate_dispatch",  "БЫЛО МЕРТВО"),
    ("/sp20 4111111111111111 12 30 123", FREEMAN_ID, "gate_dispatch", "БЫЛО МЕРТВО"),
]


async def main():
    # add_handler в pyrogram кладёт регистрацию в задачу на loop клиента, поэтому
    # хендлеры появляются в dispatcher.groups только когда ЗАПУЩЕН ИМЕННО ЭТОТ loop.
    # asyncio.run() поднял бы новый loop, и groups остался бы пустым.
    for _ in range(5):
        await asyncio.sleep(0)

    print(f"pyrogram {pyrogram.__version__}")
    handlers = list(iter_handlers(M.app))
    print(f"хендлеров зарегистрировано: {len(handlers)}")
    print()

    ok = fail = 0
    print("=" * 96)
    print("РЕШЕНИЕ КОМАНД ЧЕРЕЗ РЕАЛЬНЫЕ ФИЛЬТРЫ")
    print("=" * 96)
    for text, uid, expect, tag in CHECKS:
        hits = await resolve(M.app, text, uid)
        names = [h[1] for h in hits]
        good = expect in names
        ok, fail = (ok + 1, fail) if good else (ok, fail + 1)
        mark = "OK  " if good else "ПРОМАХ"
        print(f"  {mark} [{tag:12}] {text[:52]:52} -> {names}")
        if not good:
            print(f"         ожидался хендлер: {expect}")

    print()
    print("=" * 96)
    print("КОНТРОЛЬ: мусор НЕ должен ничего ловить")
    print("=" * 96)
    for text in ("/zzz 1 2 3", "просто текст", "/st99 4111111111111111 12 30 123", ""):
        hits = await resolve(M.app, text, FREEMAN_ID)
        names = [h[1] for h in hits]
        good = not names
        ok, fail = (ok + 1, fail) if good else (ok, fail + 1)
        print(f"  {'OK  ' if good else 'ПРОМАХ'} {text!r:32} -> {names}")

    print()
    print("=" * 96)
    print("ЧТО КОМАНДА РЕАЛЬНО ЗАПУСТИТ: resolve_gate_cmd(cmd) -> (gate, tier)")
    print("=" * 96)
    live = set(M.GATES)
    for cmd in list(M.TIERED_GATE_CMDS) + ["st", "sh", "sp", "au", "chk", "setupwoo",
                                           "storegate", "shopify", "piconfirm",
                                           "braintreenvbv"]:
        gate, tier = M.resolve_gate_cmd("/" + cmd)
        known = gate in live
        ok, fail = (ok + 1, fail) if known else (ok, fail + 1)
        print(f"  {'OK  ' if known else 'НЕТ '} /{cmd:14} -> gate={str(gate):14} "
              f"tier={str(tier):5} {'' if known else '← гейт не в реестре!'}")

    print()
    print("=" * 96)
    print("РАЗБОР КАРТ: parse_cards()")
    print("=" * 96)
    samples = [
        ("4111111111111111 12 30 123", "пробелы — раньше /hit давал 0 карт"),
        ("4111111111111111|12|30|123", "пайпы"),
        ("4111111111111111/12/30/123", "слеши"),
        ("4111 1111 1111 1111 12 30 123", "PAN блоками по 4"),
        ("4111111111111111,12,30,123", "запятые как разделитель полей"),
        ("4111111111111111,12,30,123\n5500005555555559 01 29 456",
         "запятые + перенос строки"),
        ("4111111111111111 12 30 123, 5500005555555559 01 29 456",
         "две карты через запятую"),
        ("/chk 4111111111111111 12 30 123", "команда + карта в одной строке"),
        ("4111111111111111 12 30", "битая — cvv нет"),
        ("мусор без цифр", "мусор"),
        ("", "пусто"),
    ]
    for s, note in samples:
        print(f"  {s!r:58} -> {M.parse_cards(s)}   # {note}")

    print()
    print("=" * 96)
    print("ДЕДУП И ЛИМИТ parse_cards")
    print("=" * 96)
    dup = "4111111111111111 12 30 123\n" * 5
    print(f"  dedupe=True : {len(M.parse_cards(dup))} карт из 5 одинаковых строк")
    print(f"  dedupe=False: {len(M.parse_cards(dup, dedupe=False))} карт (для /mass — порядок важен)")
    many = "\n".join(f"41111111111111{i:02d} 12 30 123" for i in range(30))
    print(f"  limit=20    : {len(M.parse_cards(many, limit=20))} карт из 30")

    print()
    print("=" * 96)
    print(f"ИТОГ: {ok} пройдено, {fail} провалено")
    print("=" * 96)
    return 1 if fail else 0


if __name__ == "__main__":
    loop = M.app.loop
    try:
        rc = loop.run_until_complete(main())
    finally:
        pass
    sys.exit(rc)
