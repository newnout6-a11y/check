# language: Python 3.12+, file: scratch/_billing_probe.py, target: Windows 11
# Диагностика экономики бота: что реально списывается, что возвращается,
# где баланс может уйти в минус или в плюс. Гоняется на временной SQLite,
# боевую bot_users.db не трогает.
#
# Запуск: python scratch/_billing_probe.py
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)

import bot.config as bcfg
from bot import db
from bot.gates import load_gates

TMP = tempfile.mkdtemp(prefix="pusto_billing_")
bcfg.DB_PATH = os.path.join(TMP, "bot_users.db")
bcfg.ADMIN_IDS = set()
bcfg.START_CREDITS = 5
db.init_db()

GATES = load_gates()


def fresh(uid: int, credits: int = 5, premium_days: int = 0) -> dict:
    db.ensure_user(uid, f"user{uid}")
    with db._db() as c:
        c.execute("UPDATE users SET credits=?, premium_until=?, total_checks=0, hits=0 "
                  "WHERE user_id=?", (credits, premium_days * 86400 + int(__import__("time").time())
                                      if premium_days else 0, uid))
    return db.get_user(uid)


def line(tag, ok, detail=""):
    print(f"  [{'OK ' if ok else 'FAIL'}] {tag}{(' — ' + detail) if detail else ''}")
    return ok


print("=" * 78)
print("[*] BILLING PROBE — экономика бота на временной БД")
print("=" * 78)

print("\n-- 1. Источник цены: модуль гейта vs config.GATE_COST --")
for name, meta in sorted(GATES.items()):
    module_cost = meta["cost"]
    cfg_cost = bcfg.GATE_COST.get(name)
    charged = cfg_cost if cfg_cost is not None else 1  # ровно то, что делает spend_credit
    shown = module_cost if module_cost is not None else charged  # то, что показывает run_gate
    flag = "" if shown == charged else "  <-- РАСХОЖДЕНИЕ: показано одно, списано другое"
    print(f"    {name:16} module={module_cost}  config={cfg_cost}  показано={shown}  списано={charged}{flag}")

print("\n-- 2. Имитация состояния ДО раунда 7 (GATE_COST без storegate/shopify) --")
saved = dict(bcfg.GATE_COST)
bcfg.GATE_COST = {"setupwoo": 1, "piconfirm": 2, "hit": 2}
u = fresh(101, credits=5)
db.spend_credit(101, "storegate")
after = db.get_user(101)
line("списано за storegate (модуль COST=2)",
     after["credits"] == 4,
     f"баланс 5 -> {after['credits']} (ожидал пользователь: -2, по факту: {5 - after['credits']})")
bcfg.GATE_COST = saved

print("\n-- 3. Базовое списание и возврат --")
u = fresh(201, credits=5)
ok_spend = db.spend_credit(201, "storegate")
after_spend = db.get_user(201)
db.refund_credit(201, "storegate")
after_refund = db.get_user(201)
line("spend_credit вернул True", ok_spend)
line("списано 2 (COST storegate)", after_spend["credits"] == 3, f"5 -> {after_spend['credits']}")
line("refund вернул баланс ровно", after_refund["credits"] == 5, f"-> {after_refund['credits']}")
line("total_checks откатился", after_refund["total_checks"] == 0,
     f"total_checks={after_refund['total_checks']}")

print("\n-- 4. Недостаточно кредитов --")
u = fresh(301, credits=1)
ok = db.spend_credit(301, "storegate")
after = db.get_user(301)
line("списание отклонено", ok is False)
line("баланс не ушёл в минус", after["credits"] == 1, f"credits={after['credits']}")

print("\n-- 5. Премиум: цена 0 --")
u = fresh(401, credits=0, premium_days=30)
ok = db.spend_credit(401, "storegate")
after = db.get_user(401)
line("чек с нулевым балансом разрешён", ok is True)
line("баланс не тронут", after["credits"] == 0, f"credits={after['credits']}")
db.refund_credit(401, "storegate")  # ERROR-вердикт у премиум-юзера
after2 = db.get_user(401)
line("total_checks НЕ откатился у премиума",
     after2["total_checks"] == after["total_checks"],
     f"total_checks={after2['total_checks']} (списание учло, возврат вернул False → счётчик растёт)")

print("\n-- 6. Разработчик (ADMIN) --")
bcfg.ADMIN_IDS = {501}
fresh(501, credits=0)
db.spend_credit(501, "storegate")
a1 = db.get_user(501)
r = db.refund_credit(501, "storegate")
a2 = db.get_user(501)
line("списание разрешено при нулевом балансе", a1["credits"] == 0)
line("total_checks растёт", a1["total_checks"] == 1, f"total_checks={a1['total_checks']}")
line("refund вернул False (cost=0)", r is False)
line("total_checks не откатился", a2["total_checks"] == 1, f"total_checks={a2['total_checks']}")
bcfg.ADMIN_IDS = set()

print("\n-- 7. Двойной возврат (идемпотентность) --")
u = fresh(601, credits=5)
db.spend_credit(601, "storegate")
db.refund_credit(601, "storegate")
db.refund_credit(601, "storegate")  # повторная доставка того же ERROR
after = db.get_user(601)
line("баланс не раздулся", after["credits"] == 5, f"credits={after['credits']} (ожидалось 5)")
line("total_checks не ушёл ниже нуля", after["total_checks"] == 0,
     f"total_checks={after['total_checks']}")

print("\n-- 8. Потерянный кредит: списали, движок упал, возврат не выполнился --")
u = fresh(701, credits=5)
db.spend_credit(701, "storegate")
# здесь процесс умирает / gather падает / edit_text кидает BadRequest
after = db.get_user(701)
line("кредит сгорел без вердикта", after["credits"] == 3,
     f"credits={after['credits']}, verdict пользователю не доставлен, следа в БД нет")

print("\n-- 9. Параллельный /mass: 20 чеков, 5 кредитов, цена 2 --")
import asyncio


async def mass_like(uid, n_cards, gate):
    async def one():
        if not db.spend_credit(uid, gate):
            return "NO_FUNDS"
        await asyncio.sleep(0)
        return "OK"
    return await asyncio.gather(*[one() for _ in range(n_cards)])


u = fresh(801, credits=5)
res = asyncio.run(mass_like(801, 20, "storegate"))
after = db.get_user(801)
spent = res.count("OK")
line("списаний не больше, чем позволяет баланс", spent == 2 and after["credits"] == 1,
     f"списано {spent}×2, остаток {after['credits']} (lost update исключён)")
line("total_checks совпадает с числом списаний", after["total_checks"] == spent,
     f"total_checks={after['total_checks']} vs spent={spent}")

print("\n-- 10. Аудит: можно ли восстановить историю? --")
with db._db() as c:
    tables = {r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
line("есть таблица операций (ledger)", "ledger" in tables or "operations" in tables,
     f"таблицы: {sorted(tables)} → история списаний не хранится, reconcile невозможен")

print("\n" + "=" * 78)
print(f"[*] временная БД: {TMP} (боевая bot/bot_users.db не тронута)")
print("=" * 78)
