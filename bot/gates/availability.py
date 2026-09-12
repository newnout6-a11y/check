# language: Python 3.12+, file: bot/gates/availability.py, target: Windows 11
"""Единый источник правды: какие поверхности можно продавать прямо сейчас.

Раньше доступность считалась только в bot/main.py для авто-выбора цели, а меню,
справка и прайс продавали всё, что есть в GATE_COST. Из-за этого /pi и /vbv
рекламировались как рабочие, хотя в их пулах нет ни одной цели: пользователь
тратил кредит и получал гарантированный ERROR (аудит 2026-09, G-03 / G-04 / H-17).

Теперь и выбор, и продажа, и меню читают один и тот же ответ, а пустой пул снимает
поверхность с продажи сам — как только цели появятся, она вернётся без правок кода.
"""
from __future__ import annotations

# Порядок приоритета авто-выбора: живой SetupIntent-донор -> Store API -> Shopify -> PI -> VBV
GATE_PRIORITY = ("storegate", "setupwoo", "shopify", "piconfirm", "braintreenvbv")

# Поверхности, которые продаются напрямую (не через реестр плагинов) и обязаны
# показывать, сколько у них целей.
SOLD_SURFACES = ("setupwoo", "storegate", "shopify", "piconfirm", "braintreenvbv")

# Пользовательские алиасы команд: внутреннее имя гейта и то, чем его зовёт человек,
# расходятся (piconfirm -> /pi, braintreenvbv -> /vbv). В меню показываем второе.
GATE_COMMANDS = {
    "setupwoo": "/au",
    "storegate": "/st",
    "shopify": "/sp",
    "piconfirm": "/pi",
    "braintreenvbv": "/vbv",
    "hit": "/hit",
}


def gate_command(gate: str) -> str:
    return GATE_COMMANDS.get(gate, f"/{gate}")


def _count(fn) -> int:
    """Сколько целей видит поверхность. Падение чтения = ноль целей, а не истина."""
    try:
        value = fn()
    except Exception:
        return 0
    if value is None:
        return 0
    if isinstance(value, (list, tuple, set, dict)):
        return len(value)
    return 1 if value else 0


def target_counts() -> dict[str, int]:
    from bot.gates.storegate import _targets as _st_targets
    from bot.gates.shopify import _targets as _sp_targets
    from bot.gates.piconfirm import _target as _pi_target
    from bot.gates.braintreenvbv import _targets as _bt_targets
    import setup_gate

    return {
        "setupwoo": _count(setup_gate.load_ready_gates),
        "storegate": _count(_st_targets),
        "shopify": _count(_sp_targets),
        "piconfirm": _count(_pi_target),
        "braintreenvbv": _count(_bt_targets),
    }


def availability() -> dict[str, dict]:
    """{gate: {targets, available, reason}} — свежий ответ на каждый вызов."""
    out: dict[str, dict] = {}
    for gate, count in target_counts().items():
        out[gate] = {
            "targets": count,
            "available": count > 0,
            "reason": "" if count > 0 else "в пуле нет ни одной цели",
        }
    return out


def available_gates(priority: tuple[str, ...] = GATE_PRIORITY) -> list[str]:
    info = availability()
    return [g for g in priority if info.get(g, {}).get("available")]


def off_sale(priority: tuple[str, ...] = GATE_PRIORITY) -> dict[str, str]:
    """Снятые с продажи поверхности с причиной — для текста меню и справки."""
    info = availability()
    return {g: info[g]["reason"] for g in priority
            if g in info and not info[g]["available"]}
