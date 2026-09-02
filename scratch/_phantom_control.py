# language: python, file: scratch/_phantom_control.py — expired-контроль пула store-гейтов.
# Фантомный гейт оформляет заказ (success) по ПРОТУХШЕЙ карте — его APPROVED ничего
# не значит: платёж никогда не доходит до банка. Честный гейт отвечает card-ошибкой
# (EXPIRED/DECLINED/INVALID). Пишет phantom-флаги в data/store_gates.json.
# Запуск: python scratch/_phantom_control.py [домен-фильтры...]
import asyncio
import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(line_buffering=True, encoding="utf-8")

from curl_cffi.requests import AsyncSession

import gate_client as gc

MAX_PRICE = 2000  # кап как в боевых прогонах — чтобы дойти до чекаута
STORE_GATES = Path(__file__).resolve().parents[1] / "data" / "store_gates.json"

# success-классы на протухшей карте = фантом
PHANTOM_STATUSES = {"APPROVED@PAID", "PI_PENDING", "PI_MINTED"}
# card-ошибки = честный гейт: платёжный путь реально валидирует карту
HONEST_STATUSES = {"EXPIRED", "DECLINED", "INVALID", "WRONG_CVC",
                   "DECLINED@DO_NOT_HONOR", "DECLINED@FRAUD", "DECLINED@STOLEN"}


def expired_card() -> str:
    """Luhn-валидный пробник со сроком 2019 — авторизовать невозможно в принципе."""
    probe = gc.gen_probe_card(random.choice(gc._PROBE_BINS))
    return f"{probe['number']}|{probe['mm']}|2019|{probe['cvc']}"


async def check_gate(root: str) -> dict:
    card = expired_card()
    async with AsyncSession(impersonate="chrome131", verify=False) as s:
        return await gc.store_api_confirm(s, root, "", card, country="US",
                                          max_price_cents=MAX_PRICE)


async def main():
    only = set(sys.argv[1:]) or None
    gates = json.loads(STORE_GATES.read_text(encoding="utf-8"))
    print("=" * 78)
    print("[*] PHANTOM CONTROL — expired-card pass over store pool")
    print("=" * 78)
    for g in gates:
        dom = g.get("domain")
        if only and dom not in only:
            continue
        root = g.get("base_url") or f"https://{dom}"
        try:
            res = await check_gate(root)
        except Exception as e:
            res = {"status": "ERROR", "detail": f"{type(e).__name__}: {e}"[:120]}
        st = res.get("status", "ERROR")
        # D-29: зонд, упавший в ERROR/таймаут, НЕ доказывает честность гейта.
        # Раньше phantom = st in PHANTOM_STATUSES давал False на любой ошибке —
        # контроль открывался, и гейт с неудавшимся зондом уходил в «чистые».
        # Так в пул попал wellyou.lt: phantom_probe = ERROR (pk не найден),
        # phantom=False, статус APPROVED@PAID — а live-прогон раунда 10 показывает
        # PI_PENDING, то есть платёж не подтверждён. Три состояния вместо двух.
        if st in PHANTOM_STATUSES:
            phantom = True
            verdict = "PHANTOM"
        elif st in HONEST_STATUSES:
            phantom = False
            verdict = "honest"
        else:
            phantom = None  # зонд не дал ответа — гейт НЕ проверен
            verdict = "inconclusive"
        g["phantom"] = phantom
        g["phantom_probe"] = f"{st}: {str(res.get('detail', ''))[:90]}"
        print(f"  [{verdict:12}] {dom:34} {st:14} {str(res.get('detail', ''))[:70]}")
    STORE_GATES.write_text(json.dumps(gates, indent=2, ensure_ascii=False),
                           encoding="utf-8")
    ph = sum(1 for g in gates if g.get("phantom") is True)
    honest = sum(1 for g in gates if g.get("phantom") is False)
    inc = sum(1 for g in gates if g.get("phantom") is None)
    print("-" * 78)
    print(f"[*] phantom {ph} · honest {honest} · inconclusive {inc} (из {len(gates)})")
    if inc:
        print(f"[!] {inc} гейт(ов) с неудавшимся зондом — НЕ считаются чистыми, "
              f"в финальный пул не идут, пока зонд не пройдёт")


if __name__ == "__main__":
    asyncio.run(main())
