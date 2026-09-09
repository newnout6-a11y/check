import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import asyncio
import time
import gate_client as gc
import setup_gate as supg

async def run():
    ready_list = supg.load_ready_gates()
    gs = supg.GateSession(ready_list[0], proxy=None)
    await gs.open()
    cards = [gc.gen_probe_card("448528"), gc.gen_probe_card("453927"), gc.gen_probe_card("517546")]
    print("=" * 75)
    print("[*] ПРОВЕРКА ЗОЛОТОЙ СЕРЕДИНЫ (ПАУЗА 8.0s) — 3 КАРТЫ ПОДРЯД В ОДНОЙ СЕССИИ:")
    print("=" * 75)
    for i, c in enumerate(cards, 1):
        c_str = f"{c['number']}|{c['mm']}|{c['yy']}|{c['cvc']}"
        t0 = time.perf_counter()
        res = await gs.check_card(c_str)
        ms = int((time.perf_counter() - t0) * 1000)
        print(f"Карта #{i} ({gc.mask_pan(c_str)}) -> {res.get('status')} | {res.get('detail')} ({ms}ms)")
        if i < len(cards):
            print("  [*] Выдерживаем 8.0 секунд кулдауна...")
            await asyncio.sleep(8.0)
    await gs.close()

if __name__ == "__main__":
    asyncio.run(run())
