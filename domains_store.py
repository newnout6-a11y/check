# language: Python 3.12+, file: domains_store.py, target: Windows 11, stdlib-only
# Sprint 3.1: единое межсессионное хранилище доменов (SQLite, WAL).
# INSERT OR IGNORE — домен никогда не теряется; приоритет понижается, не повышается.
import contextlib
import os
import sqlite3
import time

DB_PATH = os.path.join("data", "domains.db")


@contextlib.contextmanager
def _db():
    """Соединение с гарантией close: контекст sqlite3 коммитит, но не закрывает."""
    conn = connect()
    try:
        with conn:
            yield conn
    finally:
        conn.close()

_SCHEMA = """
CREATE TABLE IF NOT EXISTS domains (
    domain       TEXT PRIMARY KEY,
    source       TEXT NOT NULL,            -- forum | dork | manual
    first_seen   INTEGER NOT NULL,
    last_scanned INTEGER,
    scan_result  TEXT,                     -- NULL|READY|DEAD|CF_BLOCKED|NO_REG|NO_STRIPE|TEST_MODE|CAPTCHA_ADDCARD
    priority     INTEGER DEFAULT 3         -- 1=subscription/donation, 2=generic woo, 3=dork
);
CREATE INDEX IF NOT EXISTS idx_domains_scan ON domains(last_scanned);
CREATE INDEX IF NOT EXISTS idx_domains_prio ON domains(priority);
"""


def connect() -> sqlite3.Connection:
    os.makedirs("data", exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=15)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with _db() as conn:
        conn.executescript(_SCHEMA)


def upsert(domains: list[str] | set[str], source: str, priority: int = 3) -> int:
    """Новые вставляются, существующие сохраняют источник/first_seen;
    приоритет только понижается (меньше = важнее). Возвращает число новых."""
    if not domains:
        return 0
    now = int(time.time())
    added = 0
    with _db() as conn:
        for d in sorted({d.strip().lower() for d in domains if d and "." in d}):
            cur = conn.execute(
                "INSERT OR IGNORE INTO domains(domain, source, first_seen, priority) VALUES(?,?,?,?)",
                (d, source, now, priority))
            if cur.rowcount:
                added += 1
                continue
            conn.execute(
                "UPDATE domains SET priority = MIN(COALESCE(priority, 3), ?) WHERE domain = ?",
                (priority, d))
    return added


def due_for_scan(hours: int = 24, limit: int | None = None) -> list[dict]:
    """Домены новые или старше hours с последнего скана; приоритетные впереди."""
    cutoff = int(time.time()) - hours * 3600
    q = ("SELECT domain, source, priority, scan_result FROM domains "
         "WHERE last_scanned IS NULL OR last_scanned < ? "
         "ORDER BY priority ASC, last_scanned IS NOT NULL, last_scanned ASC")
    if limit:
        q += f" LIMIT {int(limit)}"
    with _db() as conn:
        return [dict(r) for r in conn.execute(q, (cutoff,))]


def mark_scanned(domain: str, result: str):
    with _db() as conn:
        conn.execute("UPDATE domains SET last_scanned = ?, scan_result = ? WHERE domain = ?",
                     (int(time.time()), result, domain))


def all_domains() -> list[dict]:
    """Весь пул в порядке приоритета — для экспорта txt-совместимости."""
    with _db() as conn:
        return [dict(r) for r in conn.execute(
            "SELECT * FROM domains ORDER BY priority ASC, domain ASC")]


def stats() -> dict:
    with _db() as conn:
        total = conn.execute("SELECT COUNT(*) c FROM domains").fetchone()["c"]
        by_source = {r["source"]: r["c"] for r in conn.execute(
            "SELECT source, COUNT(*) c FROM domains GROUP BY source")}
        by_result = {r["scan_result"]: r["c"] for r in conn.execute(
            "SELECT scan_result, COUNT(*) c FROM domains WHERE scan_result IS NOT NULL GROUP BY scan_result")}
        scanned = conn.execute(
            "SELECT COUNT(*) c FROM domains WHERE last_scanned IS NOT NULL").fetchone()["c"]
        pending = conn.execute(
            "SELECT COUNT(*) c FROM domains WHERE last_scanned IS NULL").fetchone()["c"]
    return {"total": total, "by_source": by_source, "by_result": by_result,
            "scanned": scanned, "pending": pending}


def export_txt(path: str):
    """Обратная совместимость: сканер продолжает читать txt, порядок по приоритету."""
    rows = all_domains()
    with open(path, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(r["domain"] + "\n")
    return len(rows)


if __name__ == "__main__":
    init_db()
    s = stats()
    print(f"[*] domains.db: {s['total']} total | sources={s['by_source']} | "
          f"scanned={s['scanned']} pending={s['pending']}")
