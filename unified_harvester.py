# language: Python 3.12+, file: unified_harvester.py, target: Windows 11
# Sprint 3.1: единый конвейер добычи — форумная полоса + доркеры + manual-цели → SQLite.
# Доркеры запускаются как подпроцессы (свои event-loop'ы), форум — напрямую.
import asyncio
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.stdout.reconfigure(line_buffering=True, encoding="utf-8")

ROOT = os.path.dirname(os.path.abspath(__file__))

import domains_store


MANUAL_TARGETS = os.path.join("data", "probe_targets.txt")


async def forum_lane() -> tuple[int, int]:
    """harvest_donors.harvest() напрямую: (новых в db, всего приоритетных)."""
    import harvest_donors as hd
    unique, priority = await hd.harvest()
    clean_priority = [d for d in priority if not any(k in d for k in hd.DEV_KEYWORDS)]
    others = [d for d in (unique - priority) if not any(k in d for k in hd.DEV_KEYWORDS)]
    n = (domains_store.upsert(clean_priority, source="forum", priority=1)
         + domains_store.upsert(others, source="forum", priority=2))
    return n, len(clean_priority)


def dork_lane(script: str) -> int:
    """dork_harvester / deep_dorker своим процессом; сами пишут в db."""
    r = subprocess.run([sys.executable, script], capture_output=True, text=True,
                       encoding="utf-8", errors="replace", cwd=ROOT)
    tail = (r.stdout or "").strip().splitlines()[-6:]
    print(f"--- {os.path.basename(script)} ---")
    print("\n".join(tail) if tail else f"(no output, rc={r.returncode})")
    if r.returncode != 0:
        print(f"[!] {script} rc={r.returncode}: {(r.stderr or '')[-300:]}")
    return r.returncode


async def manual_lane() -> int:
    if not os.path.exists(MANUAL_TARGETS):
        return 0
    doms = []
    with open(MANUAL_TARGETS, encoding="utf-8") as f:
        for line in f:
            d = line.strip().lower().replace("https://", "").replace("http://", "").rstrip("/")
            d = d.split("/")[0]
            if d and "." in d and not d.startswith("#"):
                doms.append(d)
    return domains_store.upsert(doms, source="manual", priority=1)


async def main():
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    skip_dorks = "--forum-only" in sys.argv
    pages = 2
    if "--pages" in sys.argv:
        i = sys.argv.index("--pages")
        if i + 1 < len(sys.argv):
            pages = max(1, int(sys.argv[i + 1]))

    print("=" * 80)
    print("[*] UNIFIED HARVESTER — forums + dorks + manual -> data/domains.db")
    print("=" * 80)
    domains_store.init_db()
    before = domains_store.stats()["total"]

    tasks = [forum_lane(), manual_lane()]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    forum_new = results[0] if isinstance(results[0], tuple) else (0, 0)
    manual_new = results[1] if isinstance(results[1], int) else 0
    print(f"[+] forum lane: +{forum_new[0]} new ({forum_new[1]} priority)")
    print(f"[+] manual lane: +{manual_new} new")

    if not skip_dorks:
        # Последовательно: поисковики банят параллельные полосы с одного IP
        dork_lane(os.path.join(ROOT, "scratch", "dork_harvester.py"))
        dork_lane(os.path.join(ROOT, "scratch", "deep_dorker.py"))

    after = domains_store.stats()
    print("=" * 80)
    print(f"[🔥] POOL: {after['total']} domains (+{after['total'] - before}) | "
          f"sources={after['by_source']} | scanned={after['scanned']} | pending={after['pending']}")
    print(f"[*] by_result: {after['by_result']}")
    n_txt = domains_store.export_txt(os.path.join("data", "harvested_domains.txt"))
    domains_store.export_txt(os.path.join("data", "dork_harvested.txt"))
    print(f"[*] exported {n_txt} domains -> harvested_domains.txt / dork_harvested.txt")
    due = domains_store.due_for_scan(hours=24)
    print(f"[*] due for scan (>24h or never): {len(due)}")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(main())
