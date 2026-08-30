# language: Python 3.12+, file: scratch/_doc_audit.py, target: Windows 11
# Срез фактического состояния проекта для документации: пулы, ротация гейтов,
# таксономия. Цифры считаются кодом, а не переписываются из прошлых доков.
# Запуск (рабочий рантайм проекта — python 3.14 с curl_cffi):
#   C:\Users\Redmi\AppData\Local\Python\pythoncore-3.14-64\python.exe scratch\_doc_audit.py
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
DATA = ROOT / "data"

TRACKED = [
    "ready_gates.json", "store_gates.json", "shopify_gates.json", "final_gates.json",
    "pi_gates.json", "proxy_health.json", "active_surfaces.json", "proxies.txt",
    "store_targets.txt", "shopify_targets.txt", "hit_targets.txt",
    "braintree_targets.txt", "probe_targets.txt", "bin_cache.db",
]


def jload(name):
    p = DATA / name
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception as e:
        return f"BROKEN: {e}"


def lines(name):
    p = DATA / name
    if not p.exists():
        return None
    return [l.strip() for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]


def cnt(rows, pred):
    return sum(1 for r in rows if isinstance(r, dict) and pred(r))


print("=" * 78)
print("DATA FILES")
print("=" * 78)
for n in TRACKED:
    p = DATA / n
    print(f"  {n:24} exists={str(p.exists()):5} size={p.stat().st_size if p.exists() else '-'}")

print()
print("=" * 78)
print("DOMAINS QUEUE — data/domains.db")
print("=" * 78)
import domains_store

domains_store.init_db()
s = domains_store.stats()
print(f"  total={s['total']} scanned={s['scanned']} pending={s['pending']}")
print(f"  by_source={s['by_source']}")
print(f"  by_result={s['by_result']}")

print()
print("=" * 78)
print("POOLS")
print("=" * 78)

ready = jload("ready_gates.json") or []
print(f"  ready_gates.json    {len(ready)} records | READY="
      f"{cnt(ready, lambda g: g.get('status', 'READY') == 'READY')}"
      f" | STALE={cnt(ready, lambda g: g.get('status') == 'STALE')}")
for g in ready:
    if isinstance(g, dict):
        print(f"      {g.get('domain')} | {g.get('gate_type')} | SR="
              f"{g.get('success_rate')} | lat={g.get('latency_avg_ms')}ms"
              f" | fails={g.get('fail_count')} | {g.get('status', 'READY')}")

store = jload("store_gates.json") or []
print(f"\n  store_gates.json    {len(store)} records | verified="
      f"{cnt(store, lambda g: g.get('verified'))} | dead="
      f"{cnt(store, lambda g: g.get('dead_surface'))} | phantom="
      f"{cnt(store, lambda g: g.get('phantom'))}")

shop = jload("shopify_gates.json") or []
print(f"  shopify_gates.json  {len(shop)} records | verified="
      f"{cnt(shop, lambda g: g.get('verified'))} | verified=False="
      f"{cnt(shop, lambda g: g.get('verified') is False)} | needs_live_check="
      f"{cnt(shop, lambda g: g.get('needs_live_check'))} | unchecked(needs&!verified)="
      f"{cnt(shop, lambda g: g.get('needs_live_check') and not g.get('verified'))}"
      f" | dead/phantom/blocked="
      f"{cnt(shop, lambda g: g.get('dead_surface') or g.get('phantom') or g.get('blocked'))}")

final = jload("final_gates.json") or []
by_vec = {}
for g in final:
    if isinstance(g, dict):
        by_vec.setdefault(g.get("vector", "?"), []).append(g.get("domain"))
print(f"  final_gates.json    {len(final)} records | by_vector="
      f"{ {k: len(v) for k, v in by_vec.items()} }")

for name in ("pi_gates.json", "proxy_health.json"):
    v = jload(name)
    print(f"  {name:20} {v if not isinstance(v, list) else f'{len(v)} records'}")

print()
print("=" * 78)
print("BOT GATE ROTATION (то, что реально видит бот)")
print("=" * 78)
try:
    from bot.gates import braintreenvbv, piconfirm, shopify, storegate

    for label, mod in (("storegate", storegate), ("shopify", shopify)):
        base = mod._targets()
        print(f"  {label}: {len(base)} targets in rotation")
        for t in ("1", "5", "20", "low", "mid", "high"):
            w = mod.parse_tier(t)
            print(f"      tier {t:4} {w} -> {len(mod._targets(tier=w))} targets")
    print(f"  piconfirm: target={piconfirm._target()!r}")
    print(f"  braintreenvbv: {len(braintreenvbv._targets())} targets")
except Exception as e:
    print(f"  [!] gate rotation unavailable: {type(e).__name__}: {e}")

print()
print("=" * 78)
print("TAXONOMY")
print("=" * 78)
import config

print(f"  config.VERDICTS: {len(config.VERDICTS)} classes")
print(f"  HIT_VERDICTS: {sorted(config.HIT_VERDICTS)}")
print(f"  MAX_PI_AMOUNT_CENTS={config.MAX_PI_AMOUNT_CENTS} "
      f"MAX_CONFIRMS_PER_SECRET={config.MAX_CONFIRMS_PER_SECRET} "
      f"DONOR_FAIL_LIMIT={config.DONOR_FAIL_LIMIT} "
      f"GATE_TTL_HOURS={config.GATE_TTL_HOURS} STALE_AFTER_HOURS={config.STALE_AFTER_HOURS}")
print(f"  STRIPE_API_VERSION={config.STRIPE_API_VERSION} "
      f"CHROME_IMPERSONATE={config.CHROME_IMPERSONATE}")

import bot.config as bcfg

print(f"  bot GATE_COST={bcfg.GATE_COST} START_CREDITS={bcfg.START_CREDITS} "
      f"ANTISPAM={bcfg.ANTISPAM_MIN_INTERVAL}s")
