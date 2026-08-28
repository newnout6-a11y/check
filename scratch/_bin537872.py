# -*- coding: utf-8 -*-
import sys, os, asyncio, json
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import gate_client as gc
d = asyncio.run(gc.bin_lookup_enriched("537872"))
print(json.dumps(d, ensure_ascii=False, indent=1))
