# language: Python 3.12+, file: bot/gates/__init__.py, target: Windows 11
# Sprint 4: реестр гейтов. Контракт модуля (SkyBots-паттерн):
#   NAME = "gate-id"
#   COST = 1                      # опционально, перекрывает config
#   async def gate(cc, mm, yy, cvv) -> tuple[str, str]   # (verdict, detail)
# Модуль с ошибкой импорта не валит бота — просто выпадает из реестра.
import importlib
import pkgutil
import traceback


def load_gates() -> dict:
    registry = {}
    for m in sorted(pkgutil.iter_modules(__path__)):
        if m.name.startswith("_"):
            continue
        try:
            mod = importlib.import_module(f".{m.name}", __name__)
            if hasattr(mod, "NAME") and hasattr(mod, "gate"):
                registry[mod.NAME] = {
                    "fn": mod.gate,
                    "cost": getattr(mod, "COST", None),
                }
        except Exception as e:
            print(f"[gates] skip {m.name}: {e}\n{traceback.format_exc(limit=1)}")
    return registry
