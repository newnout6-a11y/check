# language: Python 3.12+, file: scratch/_probe_bot_gates.py, target: Windows 11
# Sprint 4 verification: gate registry loads, contract works, live donor check
# through the bot's own code path (no telegram needed).
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from bot.gates import load_gates
import gate_client as gc


async def main():
    GATES = load_gates()
    print(f"[*] gates loaded: {list(GATES)}")
    assert "setupwoo" in GATES and "piconfirm" in GATES

    # контрактные проверки без сети
    v, d = await GATES["setupwoo"]["fn"]("1234", "13", "29", "000")
    assert v == "INVALID", f"bad format must be INVALID, got {v}"
    print(f"[*] invalid-format guard OK: {v}")

    # живой прогон на случайном Luhn-пробнике через гейт-контракт
    probe = gc.gen_probe_card("453927")
    card = f"{probe['number']}|{probe['mm']}|{probe['yy']}|{probe['cvc']}"
    parts = card.split("|")
    v, d = await GATES["setupwoo"]["fn"](*parts)
    expected = {"APPROVED", "APPROVED@CVV", "APPROVED@CCN", "3DS_REQUIRED",
                "DECLINED", "ERROR"}
    assert v in expected or v.startswith("DECLINED@"), f"unexpected verdict {v}: {d}"
    print(f"[+] LIVE via bot gate contract: [{v}] {gc.mask_pan(card)} -> {d[:80]}")

    # piconfirm без цели должен честно вернуть ERROR с подсказкой
    v2, d2 = await GATES["piconfirm"]["fn"](*parts)
    assert v2 == "ERROR" and ("not configured" in d2 or "open failed" in d2), f"{v2}: {d2}"
    print(f"[*] piconfirm unconfigured guard OK: {d2[:60]}")


if __name__ == "__main__":
    asyncio.run(main())
