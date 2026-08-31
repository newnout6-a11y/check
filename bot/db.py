# language: Python 3.12+, file: bot/db.py, target: Windows 11, stdlib-only
# Sprint 4: юзеры/кредиты/ключи активации. SQLite как у эталонных ботов.
import contextlib
import os
import sqlite3
import time

from . import config


# Версия схемы живёт в PRAGMA user_version. Раньше было только
# CREATE TABLE IF NOT EXISTS — добавление колонки в новой версии молча ломало
# dict(row) у старых баз: SELECT * возвращал набор полей без новой колонки,
# и KeyError всплывал уже в обработчике, а не на старте.
SCHEMA_VERSION = 1
# Миграции: {целевая_версия: [(таблица, колонка, DDL), ...]}
# Пусто SCHEMA_VERSION=1 — это «исходная схема», механизм готов, миграций пока нет.
_MIGRATIONS: dict[int, list[tuple[str, str, str]]] = {}


def _table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {r["name"] for r in conn.execute(f"PRAGMA table_info({table})")}


def _migrate(conn: sqlite3.Connection) -> None:
    cur = conn.execute("PRAGMA user_version").fetchone()[0] or 0
    for target in sorted(v for v in _MIGRATIONS if v > cur):
        for table, column, ddl in _MIGRATIONS[target]:
            if column not in _table_columns(conn, table):
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")
        conn.execute(f"PRAGMA user_version = {target}")
    if cur == 0:
        conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(config.DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    try:
        # WAL: /mass держит до 20 карт на Semaphore(5), writers бились об
        # единственную эксклюзивную блокировку rollback-journal — отсюда
        # 'database is locked' на ровном месте. WAL даёт читателям не блокировать
        # писателя, busy_timeout заставляет ждать, а не падать сразу.
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=10000")
        conn.execute("PRAGMA synchronous=NORMAL")
    except sqlite3.DatabaseError:
        pass  # WAL недоступен (сеть/exFAT) — лучше жить без него, чем не стартовать
    return conn


@contextlib.contextmanager
def _db():
    """Соединение с гарантией close: контекст sqlite3 только коммитит,
    но НЕ закрывает — в долгоживущем боте это утечка дескрипторов."""
    conn = connect()
    try:
        with conn:
            yield conn
    finally:
        conn.close()


def init_db():
    with _db() as c:
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
    with _db() as c:
        _migrate(c)  # executescript коммитит и рвёт транзакцию — мигрируем отдельно


def ensure_user(user_id: int, username: str = ""):
    with _db() as c:
        cur = c.execute("INSERT OR IGNORE INTO users(user_id, username, credits) VALUES(?,?,?)",
                        (user_id, username, config.START_CREDITS))
        if cur.rowcount == 0:
            c.execute("UPDATE users SET username=? WHERE user_id=?", (username, user_id))


def get_user(user_id: int) -> dict:
    with _db() as c:
        row = c.execute("SELECT * FROM users WHERE user_id=?", (user_id,)).fetchone()
        return dict(row) if row else {}


def is_developer(u: dict) -> bool:
    return u.get("user_id") in config.ADMIN_IDS


def is_premium(u: dict) -> bool:
    if is_developer(u):
        return True
    return u.get("premium_until", 0) > time.time()


def _premium_on(conn: sqlite3.Connection, user_id: int) -> bool:
    """Тот же признак премиума, но на УЖЕ открытом соединении.

    get_user() открывал второе соединение, пока первое держало транзакцию —
    это гонка за блокировку в /mass и лишний дескриптор на каждый чек.
    """
    if user_id in config.ADMIN_IDS:
        return True
    row = conn.execute("SELECT premium_until FROM users WHERE user_id=?", (user_id,)).fetchone()
    return bool(row and (row["premium_until"] or 0) > time.time())


def spend_credit(user_id: int, gate: str) -> bool:
    """Премиум чекает без кредитов; разработчик — безлимитно."""
    with _db() as c:
        if user_id in config.ADMIN_IDS:
            c.execute("UPDATE users SET total_checks = total_checks + 1 WHERE user_id=?", (user_id,))
            return True
        # премиум читается на ЭТОМ же соединении — раньше get_user() открывал
        # второе, пока первое держало транзакцию
        cost = 0 if _premium_on(c, user_id) else config.GATE_COST.get(gate, 1)
        # атомарный списывающий UPDATE: SELECT→UPDATE в разных неявных
        # транзакциях терял обновление при параллельных /mass (lost update)
        cur = c.execute(
            "UPDATE users SET credits = credits - ?, total_checks = total_checks + 1 "
            "WHERE user_id=? AND credits >= ?", (cost, user_id, cost))
        return cur.rowcount > 0


def admin_add_credits(uid: int, delta: int) -> bool:
    """Атомарное изменение баланса админ-командой; False = юзера нет."""
    with _db() as c:
        cur = c.execute("UPDATE users SET credits = MAX(0, credits + ?) WHERE user_id=?",
                        (delta, uid))
        return cur.rowcount > 0


def admin_add_premium(uid: int, days: int) -> bool:
    """Продление премиума от текущего max(premium_until, now); False = юзера нет."""
    with _db() as c:
        row = c.execute("SELECT premium_until FROM users WHERE user_id=?", (uid,)).fetchone()
        if not row:
            return False
        base = max(int(row["premium_until"] or 0), int(time.time()))
        cur = c.execute("UPDATE users SET premium_until=? WHERE user_id=?",
                        (base + days * 86400, uid))
        return cur.rowcount > 0


def refund_credit(user_id: int, gate: str) -> bool:
    """Возврат кредита при сбое движка (verdict ERROR) + откат счётчика проверок.

    Списанных кредитов у премиума/админа нет, но счётчик проверок уже накручен —
    откатываем его ВСЕГДА. Раньше refund выходил по `cost == 0` и не откатывал
    ничего, из-за чего /me и /stats неуклонно расходились с реальностью.
    """
    with _db() as c:
        row = c.execute("SELECT premium_until FROM users WHERE user_id=?", (user_id,)).fetchone()
        if not row:
            return False
        cost = 0 if _premium_on(c, user_id) else config.GATE_COST.get(gate, 1)
        if cost:
            c.execute("UPDATE users SET credits = credits + ?, "
                      "total_checks = MAX(0, total_checks - 1) WHERE user_id=?",
                      (cost, user_id))
        else:
            c.execute("UPDATE users SET total_checks = MAX(0, total_checks - 1) "
                      "WHERE user_id=?", (user_id,))
        return True


def add_hit(user_id: int):
    with _db() as c:
        c.execute("UPDATE users SET hits = hits + 1 WHERE user_id=?", (user_id,))


def redeem_key(user_id: int, key: str) -> str:
    """Активация /key: premium-дни или кредиты. Возвращает текст результата."""
    with _db() as c:
        row = c.execute("SELECT * FROM keys WHERE key=? AND used_by IS NULL",
                        (key.strip(),)).fetchone()
        if not row:
            return "❌ Неверный или уже активированный ключ."
        if not row["days"] and not row["credits"]:
            # пустой ключ не помечается used — не сгорает впустую
            return "❌ Пустой ключ (0 дней / 0 кредитов) — попросите админа перевыпустить."
        c.execute("UPDATE keys SET used_by=?, used_at=? WHERE key=?",
                  (user_id, int(time.time()), key.strip()))
        # ключ может нести И дни, И кредиты (/genkey 10 30) — начисляем оба,
        # раньше credits-ветка была недостижима при непустом days
        msgs = []
        if row["days"]:
            # чтение на ЭТОМ соединении: get_user() открывал второе, пока первое
            # держит открытую транзакцию redeem — contention и лишний fd
            u_row = c.execute("SELECT premium_until FROM users WHERE user_id=?",
                              (user_id,)).fetchone()
            base = max(int((u_row["premium_until"] if u_row else 0) or 0), int(time.time()))
            c.execute("UPDATE users SET premium_until=? WHERE user_id=?",
                      (base + row["days"] * 86400, user_id))
            msgs.append(f"✅ Премиум +{row['days']} дн.")
        if row["credits"]:
            c.execute("UPDATE users SET credits = credits + ? WHERE user_id=?",
                      (row["credits"], user_id))
            msgs.append(f"✅ Кредиты +{row['credits']}")
        return " ".join(msgs) or "❌ Пустой ключ."


def add_key(key: str, days: int = 0, credits: int = 0):
    with _db() as c:
        c.execute("INSERT OR REPLACE INTO keys(key, days, credits) VALUES(?,?,?)",
                  (key, days, credits))


def antispam_ok(user_id: int) -> bool:
    """Атомарное окно: один UPDATE с условием вместо SELECT→UPDATE.

    Разделённые операторы рэйсились: два одновременных /chk от одного
    пользователя оба читали протухший last_cmd_ts и оба проходили окно —
    антиспам 3 с держался только на удаче и на глобальном GIL.
    """
    now = time.time()
    with _db() as c:
        cur = c.execute(
            "UPDATE users SET last_cmd_ts=? "
            "WHERE user_id=? AND ? - last_cmd_ts >= ?",
            (now, user_id, now, config.ANTISPAM_MIN_INTERVAL))
        if cur.rowcount > 0:
            return True
        # либо окно не истекло, либо юзера ещё нет (ensure_user вызывается не
        # перед каждым антиспамом) — второй случай пускаем, как и раньше
        row = c.execute("SELECT 1 FROM users WHERE user_id=?", (user_id,)).fetchone()
        return row is None


def get_global_stats() -> dict:
    with _db() as c:
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

