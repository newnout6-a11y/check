# language: Python 3.14, file: _audit/_D_env.py
import asyncio, warnings, inspect, py_compile, pathlib, sys
import pyrogram
from pyrogram import Client
print("pyrogram pkg:", pyrogram.__version__, "file:", pyrogram.__file__)
print("Client.loop attr:", type(getattr(Client, "loop", None)).__name__, "exists:", hasattr(Client, "loop"))
print("Client.run exists:", hasattr(Client, "run"))
try:
    print("Client.loop source:", inspect.getsource(Client.loop.fget)[:300])
except Exception as e:
    print("loop source ERR:", e)
try:
    print("pyrogram version tuple:", pyrogram.__version__)
except Exception:
    pass
async def t():
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        asyncio.get_event_loop()
        print("get_event_loop warnings:", [str(i.message)[:90] for i in w])
asyncio.run(t())
bad = []
for f in ["setup_gate.py","store_gate.py","shopify_gate.py","hit_gate.py","confirm_gate.py","funnel.py","bot/main.py","bot/db.py","bot/config.py","bot/keyboards.py","bot/utils/formatter.py"] + [str(p) for p in pathlib.Path("bot/gates").glob("*.py")]:
    try:
        py_compile.compile(f, doraise=True)
    except Exception as e:
        bad.append(f"{f}: {e}")
print("COMPILE FAILURES:", bad or "none")
import importlib.metadata as md
print("kurigram dist:", md.version("kurigram"))
