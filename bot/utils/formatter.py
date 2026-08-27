# language: Python 3.12+, file: bot/utils/formatter.py, target: Windows 11
# Sprint 4.5: форматы вывода чеков (референс MeduzaPro/SkyBots).
import config


def fmt_pan(card_raw: str) -> str:
    """411111******1111 -> 4111 11** **** 1111 (план §4.5)."""
    digits = "".join(ch for ch in card_raw.split("|")[0] if ch.isdigit())
    if len(digits) < 10:
        return card_raw
    return f"{digits[:4]} {digits[4:6]}** **** {digits[-4:]}"


def fmt_bin(binfo: dict) -> str:
    if not binfo:
        return "?"
    scheme = binfo.get("scheme") or "?"
    ftype = binfo.get("type") or "?"
    c = binfo.get("country") or {}
    country = c.get("alpha2") or c.get("name") or "?"
    bank = (binfo.get("bank") or {}).get("name") or "?"
    vbv = " [non-VBV]" if binfo.get("is_vbv") is False else ""
    return f"{scheme}/{ftype}/{country} {bank}{vbv}"


def format_single(card_raw: str, binfo: dict, gate_name: str,
                  status: str, detail: str, latency_ms: int | None = None) -> str:
    line = "─" * 25
    lat = f"\n⏱ Latency: {latency_ms}ms" if latency_ms else ""
    return (f"{line}\n"
            f"💳 Card: {fmt_pan(card_raw)}\n"
            f"📦 BIN: {fmt_bin(binfo)}\n"
            f"🏪 Gate: {gate_name}\n"
            f"{config.icon(status)} Status: {status}\n"
            f"📝 Detail: {detail[:180]}{lat}\n"
            f"{line}")


def format_mass(results: list[dict], header: bool = True) -> str:
    """results: [{card, binfo?, status, detail}]; header=False — только строки
    (когда вызывающая сторона строит свой заголовок со счётчиками)."""
    lines = []
    if header:
        hits = sum(1 for r in results if config.is_hit(r["status"]))
        warns = sum(1 for r in results
                    if r["status"] not in config.HIT_VERDICTS and r["status"] != "DECLINED")
        fails = sum(1 for r in results if r["status"] == "DECLINED")
        lines += ["━━━ MASS CHECK RESULTS ━━━",
                  f"Total: {len(results)} | ✅ {hits} | ❌ {fails} | ⚠️ {warns}"]
    for r in results:
        b = r.get("binfo") or {}
        bs = "/".join(str(b.get(k)) for k in ("scheme", "type") if b.get(k))
        bs_s = f" | {bs}" if bs else ""
        lines.append(f"{config.icon(r['status'])} {r['card']}{bs_s} | {r['status']}"
                     + (f" ({r['detail'][:40]})" if r.get("detail") else ""))
    return "\n".join(lines)
