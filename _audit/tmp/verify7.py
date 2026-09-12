
import re, os
os.chdir(r"C:\Users\Redmi\Downloads\pusto")
lines = open("free-buff-lol/proxy.js", encoding="utf-8").read().splitlines()
print("--- 41-99 ---")
print(chr(10).join("%d: %s" % (i, lines[i-1]) for i in range(41,100)))
print("--- buffy / system prompt ---")
for k,l in enumerate(lines, 1):
    if "Buffy" in l or "buffy" in l:
        print(k, l.strip()[:200])
print("--- requestTimeout ---")
for k,l in enumerate(lines, 1):
    if "requestTimeout" in l or "REQUEST_TIMEOUT" in l or "timeout" in l.lower():
        print(k, l.strip()[:160])
print("--- chatCompletions ctx ---")
print(chr(10).join("%d: %s" % (i, lines[i-1][:180]) for i in range(950,962)))
print("--- proxy_manager VALIDATE_INTERVAL ---")
pm = open("proxy_manager.py", encoding="utf-8").read()
for k,l in enumerate(pm.splitlines(), 1):
    if "VALIDATE_INTERVAL" in l or "async def" in l and "validate" in l.lower():
        print("proxy_manager.py:%d: %s" % (k, l.strip()[:160]))
bm = open("bot/main.py", encoding="utf-8").read()
print("bot mentions proxy_manager:", "proxy_manager" in bm, "| VALIDATE_INTERVAL:", "VALIDATE_INTERVAL" in bm)
for k,l in enumerate(bm.splitlines(), 1):
    if "proxy" in l.lower() and ("interval" in l.lower() or "sleep" in l.lower() or "create_task" in l.lower()):
        print("bot/main.py:%d: %s" % (k, l.strip()[:150]))
