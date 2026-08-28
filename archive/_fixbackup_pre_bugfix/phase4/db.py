# language: Python 3.12+, file: bot/db.py, target: Windows 11, stdlib-only
# Sprint 4: юзеры/кредиты/ключи активации. SQLite как у эталонных ботов.
import os
import sqlite3
import time

from . import config


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(config.DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with connect() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            user_id     INTEGER PRIMARY KEY,
            username    TEXT,
            credits     INTEGER DEFAULT 0,
            premium_until INTEGER DEFAULT 0,   -- unix ts; 0 = не премиум
            total_checks INTEGER DEFAULT 0,
            hits        INTEGER DEFAULT 0,
            banned      INTEGER DEFAULT 0,
            last_cmd_ts REAL DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS keys (
            key         TEXT PRIMARY KEY,
            days        INTEGER,
            credits     INTEGER,
            used_by     INTEGER,
            used_at     INTEGER
        );
        """)


def ensure_user(user_id: int, username: str = ""):
    with connect() as c:
        cur = c.execute("INSERT OR IGNORE INTO users(user_id, username, credits) VALUES(?,?,?)",
                        (user_id, username, config.START_CREDITS))
        if cur.rowcount == 0:
            c.execute("UPDATE users SET username=? WHERE user_id=?", (username, user_id))


def get_user(user_id: int) -> dict:
    with connect() as c:
        row = c.execute("SELECT * FROM users WHERE user_id=?", (user_id,)).fetchone()
        return dict(row) if row else {}


def is_developer(u: dict) -> bool:
    return u.get("user_id") in config.ADMIN_IDS


def is_premium(u: dict) -> bool:
    if is_developer(u):
        return True
    return u.get("premium_until", 0) > time.time()


def spend_credit(user_id: int, gate: str) -> bool:
    """Премиум чекает без кредитов; разработчик — безлимитно."""
    if user_id in config.ADMIN_IDS:
        with connect() as c:
            c.execute("UPDATE users SET total_checks = total_checks + 1 WHERE user_id=?", (user_id,))
        return True
    cost = 0 if is_premium(get_user(user_id)) else config.GATE_COST.get(gate, 1)
    with connect() as c:
        row = c.execute("SELECT credits FROM users WHERE user_id=?", (user_id,)).fetchone()
        if not row or row["credits"] < cost:
            return False
        c.execute("UPDATE users SET credits = credits - ?, total_checks = total_checks + 1 "
                  "WHERE user_id=?", (cost, user_id))
        return True


def refund_credit(user_id: int, gate: str) -> bool:
    """Возврат кредита при сбое движка (verdict ERROR) + откат счётчика проверок."""
    cost = 0 if user_id in config.ADMIN_IDS else \
        (0 if is_premium(get_user(user_id)) else config.GATE_COST.get(gate, 1))
    with connect() as c:
        row = c.execute("SELECT credits, total_checks FROM users WHERE user_id=?",
                        (user_id,)).fetchone()
        if not row or cost == 0:
            return False
        c.execute("UPDATE users SET credits = credits + ?, "
                  "total_checks = MAX(0, total_checks - 1) WHERE user_id=?",
                  (cost, user_id))
        return True


def add_hit(user_id: int):
    with connect() as c:
        c.execute("UPDATE users SET hits = hits + 1 WHERE user_id=?", (user_id,))


def redeem_key(user_id: int, key: str) -> str:
    """Активация /key: premium-дни или кредиты. Возвращает текст результата."""
    with connect() as c:
        row = c.execute("SELECT * FROM keys WHERE key=? AND used_by IS NULL",
                        (key.strip(),)).fetchone()
        if not row:
            return "❌ Неверный или уже активированный ключ."
        if not row["days"] and not row["credits"]:
            # пустой ключ не помечается used — не сгорает впустую
            return "❌ Пустой ключ (0 дней / 0 кредитов) — попросите админа перевыпустить."
        c.execute("UPDATE keys SET used_by=?, used_at=? WHERE key=?",
                  (user_id, int(time.time()), key.strip()))
        if row["days"]:
            u = get_user(user_id)
            base = max(int(u.get("premium_until") or 0), int(time.time()))
            c.execute("UPDATE users SET premium_until=? WHERE user_id=?",
                      (base + row["days"] * 86400, user_id))
            return f"✅ Премиум активирован (+{row['days']} дн.)"
        if row["credits"]:
            c.execute("UPDATE users SET credits = credits + ? WHERE user_id=?",
                      (row["credits"], user_id))
            return f"✅ Начислено +{row['credits']} кредитов"
    return "❌ Пустой ключ."


def add_key(key: str, days: int = 0, credits: int = 0):
    with connect() as c:
        c.execute("INSERT OR REPLACE INTO keys(key, days, credits) VALUES(?,?,?)",
                  (key, days, credits))


def antispam_ok(user_id: int) -> bool:
    now = time.time()
    with connect() as c:
        row = c.execute("SELECT last_cmd_ts FROM users WHERE user_id=?", (user_id,)).fetchone()
        last = row["last_cmd_ts"] if row else 0
        if now - last < config.ANTISPAM_MIN_INTERVAL:
            return False
        c.execute("UPDATE users SET last_cmd_ts=? WHERE user_id=?", (now, user_id))
        return True


def get_global_stats() -> dict:
    with connect() as c:
        users_count = c.execute("SELECT COUNT(*) c FROM users").fetchone()["c"]
        total_checks = c.execute("SELECT SUM(total_checks) c FROM users").fetchone()["c"] or 0
        total_hits = c.execute("SELECT SUM(hits) c FROM users").fetchone()["c"] or 0
        premium_users = c.execute("SELECT COUNT(*) c FROM users WHERE premium_until > ?", (time.time(),)).fetchone()["c"]
    return {
        "users_count": users_count,
        "total_checks": total_checks,
        "total_hits": total_hits,
        "premium_users": premium_users,
    }

