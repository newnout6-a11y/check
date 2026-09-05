# language: Python 3.12+, file: funnel.py, target: Windows 11, stdlib-only
# Раунд 10 (D-27): учёт потерь воронки.
#
# Почему это существует: `domains.scan_result='NO_REG'` у 926 доменов — мусорная
# корзина, а не диагноз. Туда падает и «домена нет», и «сайт жив, просто Shopify»,
# и «регистрация закрыта», и «таймаут». Ноль бит информации, воронку нельзя улучшить.
#
# Здесь каждая смерть кандидата получает причину из закрытого enum'а. Причина — это
# ДЕЙСТВИЕ: CF_CHALLENGE → нужен прокси; PM_SLUG_MISSING → чинить код, не домен;
# NOT_WOO → проверить Shopify-ветку.
import os
import sqlite3
import time
from collections import Counter

DB_PATH = os.path.join("data", "domains.db")

# --- Закрытый enum причин отказа ---------------------------------------------
# Слой: S0 — добыча, S1 — отпечаток, S2 — роутинг, S3 — проба, S4 — бой.
REASONS = {
    # сеть и доступность
    "DNS_FAIL":              "домен не резолвится",
    "TLS_FAIL":              "ошибка TLS",
    "TIMEOUT":               "таймаут",
    "HTTP_4XX":              "4xx на витрине",
    "HTTP_5XX":              "5xx на витрине",
    # D-30: 429/403 на ВСЕХ отпечатках. Это не «сайт мёртв» и не «чинить код» —
    # это исчерпанная ротация. Сайт жив, нас не пускают: повтор позже/с прокси.
    "RATE_LIMITED":          "все TLS-отпечатки дали 403/429 (D-30)",
    "CF_CHALLENGE":          "Cloudflare-челлендж",
    "CAPTCHA":               "капча на витрине",
    # платформа (S1)
    "NOT_WORDPRESS":         "не WordPress",
    "NOT_WOO":               "WordPress без WooCommerce",
    "WOO_LEGACY":            "Woo без Store API (legacy-чекаут)",
    "NO_STORE_API":          "/wc/store/v1 недоступен",
    # платёжный стек
    "NO_STRIPE_PK":          "нет pk_live на витрине",
    "TEST_MODE_PK":          "pk_test вместо pk_live",
    "NO_PM_SLUG":            "нет card-совместимого платёжного слага",
    "PM_SLUG_MISSING":       "наш пикер выбрал слаг, которого нет на сайте (D-25)",
    # корзина и товар
    "NO_PRODUCTS":           "каталог пуст",
    "NO_PRODUCT_UNDER_CAP":  "нет товара дешевле крышки — честное несовпадение",
    "ADD_ITEM_NO_JSON":      "мутация ответила не JSON (D-22, тихий фантом)",
    "ADD_ITEM_REJECTED":     "add-item отвергнут сайтом",
    "VARIATION_REQUIRED":    "variable-товар требует вариацию (D-24)",
    "GUEST_CHECKOUT_OFF":    "гостевой чекаут запрещён",
    # SetupIntent-вектор
    "REG_CLOSED":            "регистрация закрыта",
    "NO_REG_NONCE":          "нет woocommerce-register-nonce",
    "NO_ADD_PM_PAGE":        "нет /my-account/add-payment-method/",
    "NO_UPE_NONCE":          "нет nonce для SetupIntent",
    # бой
    "TOKENIZE_FAILED":       "токенизация карты не удалась",
    "GATE_TIMEOUT":          "таймаут на боевом чеке",
    # прочее
    "NO_ROUTE":              "отпечаток не дал ни одного возможного вектора",
    "UNKNOWN":               "не классифицировано",
}

# Успешные исходы. Не причины отказа, но пишутся в scans — без них гистограмма
# показывает только мёртвых и нельзя посчитать конверсию слоя.
SUCCESSES = {
    "ALIVE":    "жив, есть маршруты",
    "ROUTED":   "маршрут выбран, ушёл в S3",
    "VERIFIED": "поверхность подтверждена боем",
}

# Успешные терминальные состояния (не причины отказа, но пишутся в scans)
STAGES = ("S0", "S1", "S2", "S3", "S4")

# Что считать «домен жив, просто не наш вектор» — не выкидывать из корпуса
RETRYABLE = {"TIMEOUT", "CF_CHALLENGE", "CAPTCHA", "HTTP_5XX", "GATE_TIMEOUT",
             "RATE_LIMITED"}
# Что чинить в коде, а не в корпусе
CODE_BUGS = {"PM_SLUG_MISSING", "ADD_ITEM_NO_JSON", "VARIATION_REQUIRED", "UNKNOWN"}

_SCHEMA = """
CREATE TABLE IF NOT EXISTS scans (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    domain   TEXT NOT NULL,
    stage    TEXT NOT NULL,
    reason   TEXT NOT NULL,
    ts       INTEGER NOT NULL,
    ms       INTEGER,
    extra    TEXT
);
CREATE INDEX IF NOT EXISTS idx_scans_domain ON scans(domain);
CREATE INDEX IF NOT EXISTS idx_scans_reason ON scans(reason);
CREATE INDEX IF NOT EXISTS idx_scans_ts ON scans(ts);
"""


class ManagedConnection:
    """Обертка sqlite3 соединения, гарантирующая закрытие дескриптора при выходе из with (AUD-034)."""
    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn

    def __enter__(self) -> sqlite3.Connection:
        self._conn.__enter__()
        return self._conn

    def __exit__(self, exc_type, exc_val, exc_tb):
        try:
            return self._conn.__exit__(exc_type, exc_val, exc_tb)
        finally:
            self._conn.close()

    def __getattr__(self, name: str):
        return getattr(self._conn, name)


def connect():
    os.makedirs("data", exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=15)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.row_factory = sqlite3.Row
    return ManagedConnection(conn)


def init_db():
    with connect() as conn:
        conn.executescript(_SCHEMA)


def record(domain: str, stage: str, reason: str, ms: int | None = None,
           extra: str | None = None) -> None:
    """Одна строка на событие воронки. reason обязан быть из REASONS или SUCCESSES,
    иначе UNKNOWN с пометкой в extra — сырые строки наружу не выходят (урок D-11/D-14)."""
    if reason not in REASONS and reason not in SUCCESSES:
        extra = f"{extra or ''}|raw={reason}".strip("|")
        reason = "UNKNOWN"
    with connect() as conn:
        conn.execute(
            "INSERT INTO scans(domain, stage, reason, ts, ms, extra) VALUES(?,?,?,?,?,?)",
            (domain, stage, reason, int(time.time()), ms, extra))


def record_many(rows: list[tuple]) -> None:
    """rows: [(domain, stage, reason, ms, extra), ...] — одна транзакция на пачку."""
    if not rows:
        return
    clean = []
    for domain, stage, reason, ms, extra in rows:
        if reason not in REASONS and reason not in SUCCESSES:
            extra = f"{extra or ''}|raw={reason}".strip("|")
            reason = "UNKNOWN"
        clean.append((domain, stage, reason, int(time.time()), ms, extra))
    with connect() as conn:
        conn.executemany(
            "INSERT INTO scans(domain, stage, reason, ts, ms, extra) VALUES(?,?,?,?,?,?)",
            clean)


def histogram(since_ts: int | None = None) -> Counter:
    q = "SELECT reason, COUNT(*) c FROM scans"
    args: tuple = ()
    if since_ts:
        q += " WHERE ts >= ?"
        args = (since_ts,)
    q += " GROUP BY reason ORDER BY c DESC"
    with connect() as conn:
        return Counter({r["reason"]: r["c"] for r in conn.execute(q, args)})


def by_stage(since_ts: int | None = None) -> dict:
    q = "SELECT stage, reason, COUNT(*) c FROM scans"
    args: tuple = ()
    if since_ts:
        q += " WHERE ts >= ?"
        args = (since_ts,)
    q += " GROUP BY stage, reason ORDER BY stage, c DESC"
    out: dict[str, Counter] = {}
    with connect() as conn:
        for r in conn.execute(q, args):
            out.setdefault(r["stage"], Counter())[r["reason"]] += r["c"]
    return out


def report(since_ts: int | None = None, top: int = 30) -> str:
    """Готовый к печати отчёт: где умирают кандидаты и что с этим делать."""
    h = histogram(since_ts)
    total = sum(h.values())
    passed = sum(v for k, v in h.items() if k in SUCCESSES)
    failed = total - passed
    lines = ["=" * 78,
             f"ВОРОНКА — УЧЁТ ПОТЕРЬ  (событий: {total} | "
             f"прошло: {passed} | отсеяно: {failed}"
             + (f" | конверсия {passed / total * 100:.1f}%" if total else "") + ")",
             "=" * 78]
    if not total:
        lines.append("  (пусто — прогон ещё не был)")
        return "\n".join(lines)
    lines.append(f"{'причина':24} {'шт':>6} {'доля':>7}  действие")
    lines.append("-" * 78)
    for reason, c in h.most_common(top):
        if reason in SUCCESSES:
            lines.append(f"{reason:24} {c:6d} {'':>7}  ✓ {SUCCESSES[reason]}")
            continue
        if reason in CODE_BUGS:
            act = "ЧИНИТЬ КОД"
        elif reason in RETRYABLE:
            act = "повторить / прокси"
        elif reason == "NO_PRODUCT_UNDER_CAP":
            act = "годен, поднять крышку"
        elif reason in ("NOT_WOO", "NOT_WORDPRESS"):
            act = "проверить Shopify-ветку"
        else:
            act = "выбросить из корпуса"
        lines.append(f"{reason:24} {c:6d} {c / total * 100:6.1f}%  {act}")
    lines.append("-" * 78)
    denom = failed or 1  # доли потерь считаем от отсеянных, а не от всех
    bugs = sum(v for k, v in h.items() if k in CODE_BUGS)
    retry = sum(v for k, v in h.items() if k in RETRYABLE)
    lines.append(f"  из {failed} отсеянных: чинить код {bugs} ({bugs / denom * 100:.1f}%) · "
                 f"повторить {retry} ({retry / denom * 100:.1f}%)")
    lines.append("=" * 78)
    return "\n".join(lines)


def reset():
    with connect() as conn:
        conn.execute("DELETE FROM scans")


if __name__ == "__main__":
    init_db()
    print(report())
