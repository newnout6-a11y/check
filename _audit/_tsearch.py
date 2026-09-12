#!/usr/bin/env python
# language: Python 3.12+, file: _audit/_tsearch.py
# Обёртка над _audit/tavily.py (тот же ключ, тот же search-эндпоинт; research НЕ используется — запрет dj).
# Печатает title | url | published_date | score + сниппет, чтобы в отчёт шли URL и даты.
import importlib.util, pathlib, sys, time

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

P = pathlib.Path(__file__).with_name("tavily.py")
spec = importlib.util.spec_from_file_location("_tav_impl", P)
impl = importlib.util.module_from_spec(spec)
spec.loader.exec_module(impl)

def run(q, n=5):
    print("=" * 100)
    print("QUERY:", q)
    try:
        d = impl.search(q, n)
    except Exception as e:
        print("  ERROR:", repr(e)[:300])
        return
    ans = (d.get("answer") or "").strip()
    if ans:
        print("  ANSWER:", ans[:700].replace("\n", " "))
    for it in d.get("results", []):
        print("  -", (it.get("title") or "")[:150])
        print("    URL:", it.get("url"))
        print("    DATE:", it.get("published_date") or "n/a", "| score:", round(float(it.get("score") or 0), 3))
        c = (it.get("content") or "").replace("\n", " ")
        print("    TXT:", c[:520])

if __name__ == "__main__":
    queries = sys.argv[1:]
    for i, q in enumerate(queries):
        run(q, 5)
        if i + 1 < len(queries):
            time.sleep(1.2)
