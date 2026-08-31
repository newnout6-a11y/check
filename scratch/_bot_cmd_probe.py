# language: Python 3.12+, file: scratch/_bot_cmd_probe.py, target: Windows 11
# Прогон команд бота БЕЗ сети и без Telegram: собираем реестр гейтов,
# разбор карт и тиров, доступность целей. Ничего не списывает и не шлёт.
#
# Запуск: python scratch/_bot_cmd_probe.py
import asyncio
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.stdout.reconfigure(encoding='utf-8')

# pyrogram поднимает Client при импорте bot.main — объект создаётся, но не коннектится.
import bot.main as M  # noqa: E402
import gate_client as gc  # noqa: E402
from bot.gates import load_gates  # noqa: E402
from bot.gates.storegate import parse_tier as sg_tier, _targets as sg_targets
from bot.gates.shopify import parse_tier as sp_tier, _targets as sp_targets
from bot.gates.piconfirm import _target as pi_target
from bot.gates.braintreenvbv import _targets as bt_targets

print("=" * 78)
print("РЕЕСТР ГЕЙТОВ")
print("=" * 78)
G = load_gates()
for k, v in G.items():
    print(f"  {k:16} cost={v['cost']}  fn={v['fn'].__module__}.{v['fn'].__name__}")
print(f"\n  GATE_ALIASES: {M.GATE_ALIASES}")
print(f"  ALL_GATE_CMDS (зарегистрировано в фильтре): {sorted(M.ALL_GATE_CMDS)}")

print()
print("=" * 78)
print("КОМАНДЫ ИЗ МЕНЮ /start -> зарегистрированы?")
print("=" * 78)
# Зарегистрированные команды: явные filters.command + ALL_GATE_CMDS
explicit = ["start", "cmds", "help", "me", "key", "redeem", "proxy", "addproxy",
            "clearproxy", "hit", "mass", "bin", "gates", "stats",
            "addcredits", "addpremium", "genkey"]
registered = set(explicit) | set(M.ALL_GATE_CMDS)
menu = ["start", "chk", "au", "st1", "st5", "st20", "sp1", "sp5", "sp20",
        "hit", "bin", "mass", "gates", "stats",
        "redeem", "addproxy", "proxy", "clearproxy"]
for c in menu:
    mark = "OK  " if c in registered else "НЕТ "
    print(f"  {mark} /{c}")

print()
print("=" * 78)
print("ЦЕНОВЫЕ ТИРЫ: /st 1|5|20  и  /sp 1|5|20")
print("=" * 78)
for name, fn in (("storegate", sg_tier), ("shopify", sp_tier)):
    for t in ("1", "5", "20", "low", "mid", "high", "50", "abc"):
        print(f"  {name:10} parse_tier({t!r:6}) -> {fn(t)!r}")

print()
print("=" * 78)
print("ЦЕЛИ ГЕЙТОВ (_available_gates / _pick_gate)")
print("=" * 78)


def safe(fn):
    try:
        v = fn()
        return v if isinstance(v, (list, tuple)) else [v] if v else []
    except Exception as e:
        return f"ИСКЛЮЧЕНИЕ {type(e).__name__}: {e}"[:70]


for label, fn in (("storegate", sg_targets), ("shopify", sp_targets),
                  ("piconfirm", pi_target), ("braintreenvbv", bt_targets)):
    v = safe(fn)
    n = len(v) if isinstance(v, list) else f"ERR: {v}"
    print(f"  {label:14} целей: {n}")
print(f"\n  _available_gates(): {M._available_gates()}")
print(f"  _pick_gate(None)  : {M._pick_gate(None)}")
print(f"  _pick_gate('sh')  : {M._pick_gate('sh')}")
print(f"  _pick_gate('zzz') : {M._pick_gate('zzz')}")

print()
print("=" * 78)
print("РАЗБОР КАРТЫ (_card_fields)")
print("=" * 78)
samples = [
    "4111111111111111 12 30 123",
    "4111111111111111|12|30|123",
    "4111 1111 1111 1111 12 30 123",
    "4111111111111111/12/30/123",
    "/chk 4111111111111111 12 30 123",
    "4111111111111111 12 30",
    "",
]
for s in samples:
    print(f"  {s!r:40} -> {M._card_fields(s)}")

print()
print("=" * 78)
print("ПРОКСИ И BIN")
print("=" * 78)
proxies = gc.load_proxies()
print(f"  gc.load_proxies() -> {len(proxies)} шт.  (data/proxies.txt)")
print(f"  data/proxies.txt размер: {os.path.getsize(os.path.join(ROOT, 'data', 'proxies.txt'))} байт")
print(f"  ADMIN_IDS: {sorted(M.config.ADMIN_IDS)}")
print(f"  START_CREDITS: {M.config.START_CREDITS}")

print()
print("== /bin: живой запрос к BIN-источнику ==")
try:
    info = asyncio.run(M.setup_gate.bin_lookup("411111"))
    print(f"  bin_lookup('411111') -> {str(info)[:160]}")
except Exception as e:
    print(f"  bin_lookup ИСКЛЮЧЕНИЕ: {type(e).__name__}: {e}"[:200])

print()
print("=" * 78)
print("ГЕЙТЫ: сухой прогон run_gate без сети невозможен — проверяем контракт")
print("=" * 78)
for name, meta in G.items():
    fn = meta["fn"]
    sig = getattr(fn, "__code__", None)
    nargs = sig.co_argcount if sig else "?"
    print(f"  {name:14} аргументов: {nargs}  (ожидается cc,mm,yy,cvv [+tier])")
