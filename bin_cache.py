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


_INITIALIZED_PATH = None


def _ensure(force: bool = False):
    """Схема создаётся лениво, при первом обращении к кэшу.

    init_db() раньше вызывался только из тестов — в боте и CLI таблица bins не
    существовала, get/put глушили исключения, и весь кэш (фикс A1 раунда
    скорости) молча не работал: data/bin_cache.db оставался нулевым файлом,
    каждый новый BIN уходил в сеть на 1.5-18с и чекался с US-гео.

    Запоминается путь, а не флаг: тесты подменяют DB_PATH на tmp_path и ждут
    свежую схему на каждый вызов init_db()."""
    global _INITIALIZED_PATH
    if not force and _INITIALIZED_PATH == DB_PATH:
        return
    try:
        d = os.path.dirname(DB_PATH)
        if d:
            os.makedirs(d, exist_ok=True)
        conn = sqlite3.connect(DB_PATH, timeout=10)
        try:
            conn.executescript(_SCHEMA)
            conn.commit()
        finally:
            conn.close()
        _INITIALIZED_PATH = DB_PATH
    except Exception:
        pass  # кэш — ускоритель, не критический путь


def connect() -> sqlite3.Connection:
    _ensure()
    conn = sqlite3.connect(DB_PATH, timeout=10)
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=10000")
        conn.execute("PRAGMA synchronous=NORMAL")
    except sqlite3.DatabaseError:
        pass
    return conn


@contextlib.contextmanager
def _db():
    """Соединение с гарантией close (контекст sqlite3 коммитит, но не закрывает)."""
    conn = connect()
    try:
        with conn:
            yield conn
    finally:
        conn.close()


def init_db():
    """Явная инициализация (тесты, CLI). Повторный вызов безопасен."""
    _ensure(force=True)


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
