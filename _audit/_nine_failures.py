# -*- coding: utf-8 -*-
import json, pathlib, sys, collections
sys.path.insert(0, ".")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
import config

rep = sorted(pathlib.Path("data/results").glob("check35_*.json"))[-1]
d = json.loads(rep.read_text(encoding="utf-8"))
tech = [r for r in d["results"] if not (r["status"].startswith(("DECLINED","APPROVED","3DS")) or r["status"] in ("PI_PENDING","RATE_LIMITED","WRONG_CVC","RESTRICTED","INVALID","EXPIRED"))]
store_cat = {str(v.get("domain","")).lower(): v for v in json.loads(pathlib.Path("data/store_gates.json").read_text(encoding="utf-8"))}
shop_cat  = {str(v.get("domain","")).lower(): v for v in json.loads(pathlib.Path("data/shopify_gates.json").read_text(encoding="utf-8"))}
rot_store = {l.strip().replace("https://","") for l in pathlib.Path("data/store_targets.txt").read_text(encoding="utf-8").splitlines() if l.strip().startswith("http")}

print("отчёт:", rep.name, "| технических сбоев:", len(tech))
print()
for i, r in enumerate(sorted(tech, key=lambda x: (x["kind"], x["status"])), 1):
    dom = r["target"].replace("https://","").replace("http://","").split("/")[0]
    cat = (store_cat if r["kind"] == "store" else shop_cat).get(dom, {})
    print(f"--- {i}. {r['kind'].upper():7} {dom}")
    print(f"    статус      : {r['status']}  ({config.icon(r['status'])}) -> coerce={config.coerce_verdict(r['status'])}, refundable={config.is_refundable(r['status'])}")
    print(f"    деталь      : {r['detail']}")
    print(f"    латентность : {r['latency_ms']} ms | сумма: {r.get('amount_cents') or '-'}c {r.get('currency') or ''}")
    if r["kind"] == "store":
        print(f"    в ротации   : {'да' if dom in rot_store else 'нет'} | каталог: verify_status={cat.get('verify_status')} battle={cat.get('battle_result')} verified={cat.get('verified')} dead_surface={cat.get('dead_surface')}")
    else:
        print(f"    каталог     : verified={cat.get('verified')} last_live_verdict={cat.get('last_live_verdict')} cheapest={cat.get('cheapest_cents')}c")
    print()
print("=== ГРУППИРОВКА ПО ПРИЧИНЕ ===")
def cause(r):
    dt = r["detail"].lower()
    if "human" in dt: return "антибот-капча на витрине (CAPTCHA_CHECKOUT)"
    if "no nonce" in dt: return "витрина не отдаёт Nonce заголовок Store API"
    if "403" in dt: return "доступ к корзине закрыт (403, WAF/защита)"
    if "500" in dt: return "ошибка сервера мерчанта (500)"
    if "invalid or missing payment" in dt or "ungültige" in dt: return "плагин платежей мерчанта не принимает запрос"
    if "no available product" in dt: return "нет товара под крышкой $20"
    if dt.startswith("checkout http 200"): return "чекаут отвечает 200 без тела (заглушка плагина)"
    return "прочее: " + r["detail"][:60]
g = collections.Counter(cause(r) for r in tech)
for k, n in g.most_common():
    who = [r["target"].replace("https://","") for r in tech if cause(r) == k]
    print(f"  {n}x {k}")
    print(f"      {', '.join(who)}")
