# language: Python 3.12+, file: bin_cache.py, target: Windows 11, stdlib-only
# A1 (ИССЛЕДОВАНИЕ-СКОРОСТЬ.md): SQLite-кэш BIN-ответов.
# BIN не меняется со временем — TTL бесконечный. Убирает 1.5-18с внешних
# запросов (binlist/handyapi/antipublic) со второго обращения к тому же BIN.
import contextlib
import json
import os
import sqlite3
import time

DB_PATH = os.path.join("data", "bin_cache.db")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS bins (
    bin       TEXT PRIMARY KEY,
    info      TEXT NOT NULL,
    cached_at INTEGER NOT NULL
);
"""


@contextlib.contextmanager
def _db():
    """Соединение с гарантией close (контекст sqlite3 коммитит, но не закрывает)."""
    conn = sqlite3.connect(DB_PATH, timeout=10)
    try:
        with conn:
            yield conn
    finally:
        conn.close()


def init_db():
    os.makedirs("data", exist_ok=True)
    with _db() as c:
        c.executescript(_SCHEMA)


def get(bin6: str) -> dict | None:
    """Кэшированный бандл BIN или None. Пустые ответы не кэшируются."""
    if not bin6 or len(bin6) < 6:
        return None
    try:
        with _db() as c:
            row = c.execute("SELECT info FROM bins WHERE bin=?", (bin6,)).fetchone()
        return json.loads(row[0]) if row else None
    except Exception:
        return None


def put(bin6: str, info: dict) -> None:
    if not bin6 or len(bin6) < 6 or not info:
        return
    try:
        with _db() as c:
            c.execute("INSERT OR REPLACE INTO bins(bin, info, cached_at) VALUES(?,?,?)",
                      (bin6, json.dumps(info, ensure_ascii=False), int(time.time())))
    except Exception:
        pass  # кэш — ускоритель, не критический путь


async def cached_lookup(bin6: str, fetch):
    """Кэш-сначала: попадание — мгновенно; промах — fetch(bin6) и запись.
    fetch — async-функция; None/{} от fetch не кэшируются (транзиентный фейл)."""
    hit = get(bin6)
    if hit is not None:
        return hit
    info = await fetch(bin6)
    if info:
        put(bin6, info)
    return info or {}


if __name__ == "__main__":
    init_db()
    with _db() as c:
        n = c.execute("SELECT COUNT(*) FROM bins").fetchone()[0]
    print(f"[*] bin_cache: {n} BINs cached in {DB_PATH}")
