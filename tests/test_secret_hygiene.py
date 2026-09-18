# language: Python 3.12+, file: tests/test_secret_hygiene.py, target: Windows 11
"""Гигиена секретов: карточные данные, пулы и креды не должны попадать в репозиторий.

Появились после аудита 2026-09 (Фиксация №25): в git лежали data/probe_20_cards.txt,
data/amex_379363.txt (живые по формату PAN) и data/proxies_https_60k.txt (1 МБ ip:port).
Тесты офлайновые: используется локальный git и чтение файлов, сети нет.

Расширение скана (2026-09-12). Раньше сторож смотрел только *.py и целиком пропускал tests/,
поэтому PAN, вставленный в data/*.json, в README или в тест, не ловился вообще. Теперь:
  * сканируются все текстовые типы, которые отслеживает git (.py/.json/.md/.txt/.yml/.toml/
    .ini/.cfg/.csv/.js/.ts/.cjs/.sh/.html/.example), а не только .py;
  * tests/ не пропускается: вместо этого разрешены публичные тест-PAN и явно объявленный
    список фикстур проекта (KNOWN_FIXTURES), всё остальное — падение;
  * data/ и файлы корня проверяются без исключений;
  * сырые ресёрч-дампы _audit/_e_raw/ не освобождаются целиком: голые цифровые совпадения там
    шум (фрагменты sha256, npm tmp-пути, параметры Incapsula), но карточные шаблоны и
    карточные слова рядом проверяются и там;
  * отдельный тест следит, что скан действительно покрывает репозиторий и не выродился.

Расширение сторожа (2026-09-18, Фиксация №65). Раздел 1 закрывался по картам и кредам, а состояние
регистрации осталось: `data/scout_pool.json` держал 190 значений поля `reg_nonce_value` и лежал
в индексе. Файл снят с индекса и закрыт `.gitignore`; ниже два сторожа — на значения nonce и на
правила `.gitignore` для WAL боевой базы бота, — чтобы класс не вернулся молча.
"""
from __future__ import annotations

import pathlib
import re
import subprocess
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent

# Запрещённые к отслеживанию носители карточных данных и внешних пулов.
FORBIDDEN_TRACKED = (
    "data/probe_20_cards.txt",
    "data/amex_379363.txt",
    "data/proxies_https_60k.txt",
)

# Публичные тестовые PAN (платёжные системы, docs.stripe.com/testing). Их в коде держать можно:
# это не чужие карты, а канонические фикстуры платёжных тестов.
PUBLIC_TEST_PANS = {
    "4111111111111111",
    "4012888888881881",
    "4000000000000002",
    "4000000000009995",
    "4242424242424242",
    "5555555555554444",
    "5200828282828210",
    "5105105105105100",
    "2223003122003222",
    "378282246310005",
    "371449635398431",
    "378734493671000",
    "6011111111111117",
    "30569309025904",
    "3530111333300000",
}

# Фикстуры проекта: сгенерированные по Луну пробники на BIN из gate_client._PROBE_BINS
# и BIN-групп bin_steering. Это наши собственные номера, а не чужие карты — но список
# объявлен явно, чтобы любая новая цифра в тестах требовала осознанной регистрации здесь.
KNOWN_FIXTURES = {
    "4485287641630198",   # пробник проекта, BIN 448528
    "4539274130459806",   # пробник проекта, BIN 453927
    "4539274558237997",   # пробник проекта, BIN 453927
    "5175461780694255",   # пробник проекта, BIN 517546
    "5175465382242090",   # пробник проекта, BIN 517546
    "5500005555555559",   # пробник проекта (тестовый Mastercard)
    "4403931234567890",   # фикстура BIN-группы bin_steering
}

# Заглушки поля регистрационного nonce в тестах: заполнитель, а не живое значение. Список явный —
# как наборы PAN выше, — чтобы любое новое значение требовало осознанной регистрации здесь.
# Живой nonce в отслеживаемом файле — падение: см. test_no_registration_nonce_values_in_tracked_files.
NONCE_PLACEHOLDERS = {"abc123"}

# Расширения, которые считаются текстом и подлежат скану.
SCAN_EXTS = {".py", ".json", ".md", ".txt", ".yml", ".yaml", ".toml", ".ini", ".cfg",
             ".csv", ".js", ".ts", ".cjs", ".mjs", ".sh", ".html", ".example"}

# Сырые дампы ресёрча: цифровой шум ожидаем, карточные шаблоны всё равно проверяются.
RAW_DUMP_PREFIXES = ("_audit/_e_raw/",)

# data/ проверяется без исключений.
STRICT_PREFIXES = ("data/",)

MAX_SCAN_BYTES = 4_000_000


def _luhn(number: str) -> bool:
    digits = [int(c) for c in number]
    if not 13 <= len(digits) <= 19 or len(set(digits)) == 1:
        return False
    total = 0
    for i, d in enumerate(reversed(digits)):
        if i % 2:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0


def _git(*args: str) -> str:
    try:
        out = subprocess.run(
            ["git", *args], cwd=ROOT, capture_output=True, text=True, timeout=60
        )
    except (OSError, subprocess.SubprocessError):  # pragma: no cover
        pytest.skip("git недоступен — проверка отслеживания пропущена")
    if out.returncode != 0:
        pytest.skip(f"git {args[0]} вернул {out.returncode}: {out.stderr.strip()[:120]}")
    return out.stdout


# Непрерывный прогон 13-19 цифр. Разделители (пробел, дефис) в шаблон НЕ входят намеренно:
# с ними склеивались посторонние токены — например хост wordpress-1550062-5998994.cloudwaysapps.com
# давал «PAN» из склеенных 1550062-5998994, а SVG-путь Stripe — из одиночных цифр пути. Группировка
# проверяется отдельным шаблоном ниже.
RE_DIGIT_RUN = re.compile(r"(?<!\d)\d{13,19}(?!\d)")
# Карточные шаблоны: PAN, разбитый по четвёркам (в т.ч. Amex 4-6-5), и форма PAN|MM|YY|CVV.
RE_PAN_GROUPED_4 = re.compile(r"(?<![\w-])(?:\d{4}[ -]\d{4}[ -]\d{4}[ -]\d{3,4}|"
                              r"\d{4}[ -]\d{6}[ -]\d{5})(?![\w-])")
RE_PAN_WITH_EXPIRY = re.compile(
    r"(?<![\w-])\d{12,19}\s*[|/ ]\s*\d{1,2}\s*[|/ ]\s*\d{2,4}\s*[|/ ]\s*\d{3,4}(?![\w-])"
)
RE_CARD_WORD = re.compile(
    r"(?i)\b(pan|card|cc|cvv|cvc|expiry|cardnumber|номер карты|карта|карты)\b"
)
# Идентификаторы в JSON — не карты: Shopify variant_id 44705130******** проходит Луна по случайности.
RE_ID_VALUE = re.compile(r'"[A-Za-z_]*(?:id|sku|ref|num|no)\w*"\s*:\s*$', re.I)
TOKEN_CHARS = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_.")
CONTEXT_WINDOW = 40


def _tracked_files(exts=SCAN_EXTS):
    """Отслеживаемые git текстовые файлы для скана (без карт исходников и бинарников)."""
    for rel in _git("ls-files").splitlines():
        if rel.endswith((".map", ".tgz", ".png", ".jpg", ".ico", ".woff", ".woff2")):
            continue
        if "node_modules/" in rel or rel.startswith(".git/"):
            continue
        if pathlib.Path(rel).suffix.lower() not in exts:
            continue
        path = ROOT / rel
        try:
            if not path.is_file() or path.stat().st_size > MAX_SCAN_BYTES:
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        yield rel, text


def _is_allowed_number(number: str) -> bool:
    return number in PUBLIC_TEST_PANS or number in KNOWN_FIXTURES


def _is_standalone_token(text: str, start: int, end: int) -> bool:
    """Номер должен быть самостоятельным токеном, а не куском хоста/хеша/пути."""
    before = text[start - 1] if start else ""
    after = text[end] if end < len(text) else ""
    return before not in TOKEN_CHARS and after not in TOKEN_CHARS


def _is_identifier_value(text: str, start: int) -> bool:
    """Значение ключа вида variant_id/product_id/order_no — это ID, а не карта."""
    return bool(RE_ID_VALUE.search(text[max(0, start - 60):start]))


def _bare_pan_offenders(rel: str, text: str) -> list[str]:
    """PAN-литералы вне публичного тест-набора и объявленных фикстур."""
    out = []
    for m in RE_DIGIT_RUN.finditer(text):
        number = m.group(0)
        if not 13 <= len(number) <= 19 or _is_allowed_number(number):
            continue
        if not _is_standalone_token(text, m.start(), m.end()):
            continue
        if _is_identifier_value(text, m.start()):
            continue
        if _luhn(number):
            out.append(f"{rel}: {number[:6]}******{number[-4:]}")
    return out


def _context_offenders(rel: str, text: str) -> list[str]:
    """Карточные шаблоны: PAN по четвёркам, PAN|MM|YY|CVV и PAN рядом с карточным словом."""
    out = []
    for pattern, label in ((RE_PAN_GROUPED_4, "PAN, разбитый по четвёркам"),
                           (RE_PAN_WITH_EXPIRY, "PAN|MM|YY|CVV")):
        for m in pattern.finditer(text):
            digits = re.sub(r"\D", "", m.group(0))
            pan = digits[:16]
            if _is_allowed_number(pan) or _is_allowed_number(digits):
                continue
            if _luhn(pan) or _luhn(digits[:15]):
                out.append(f"{rel}: {label} -> {m.group(0)[:32]}")
    for m in RE_DIGIT_RUN.finditer(text):
        number = m.group(0)
        if not 13 <= len(number) <= 19 or _is_allowed_number(number) or not _luhn(number):
            continue
        if not _is_standalone_token(text, m.start(), m.end()) or _is_identifier_value(text, m.start()):
            continue
        left = max(0, m.start() - CONTEXT_WINDOW)
        window = text[left:m.end() + CONTEXT_WINDOW]
        if RE_CARD_WORD.search(window):
            out.append(f"{rel}: PAN рядом с карточным словом -> {window.strip()[:60]}")
    return out


def _raw_dump(rel: str) -> bool:
    return rel.startswith(RAW_DUMP_PREFIXES)


def test_card_containers_are_not_tracked():
    """Носители probe-карт и внешних пулов не должны быть в индексе git."""
    tracked = set(_git("ls-files").splitlines())
    leaked = sorted(f for f in FORBIDDEN_TRACKED if f in tracked)
    assert not leaked, (
        "в git отслеживаются карточные/пуловые носители: "
        + ", ".join(leaked)
        + " — сними их с индекса (git rm --cached) и ротируй данные"
    )


def test_gitignore_covers_card_and_proxy_dumps():
    """.gitignore обязан закрывать карточные и прокси-дампы, оставляя пример формата."""
    text = (ROOT / ".gitignore").read_text(encoding="utf-8")
    for pattern in ("data/probe_*.txt", "data/*_cards*.txt", "data/amex_*.txt",
                    "data/proxies_*.txt", "!data/proxies.txt.example"):
        assert pattern in text, f"в .gitignore нет правила {pattern!r}"


def test_no_card_data_in_data_dir_and_root():
    """data/ и файлы корня — без исключений: ни одного Лун-номера вне публичного набора.

    Раньше сторож смотрел только *.py, поэтому список карт, положенный в data/*.json,
    в README или в .txt, не ловился вообще.
    """
    offenders: list[str] = []
    scanned = 0
    for rel, text in _tracked_files():
        if not (rel.startswith(STRICT_PREFIXES) or "/" not in rel):
            continue
        scanned += 1
        offenders += _bare_pan_offenders(rel, text)
    assert scanned > 0, "строгие каталоги почему-то не просканированы"
    assert not offenders, (
        "карточные номера в data/ или в файлах корня: " + "; ".join(offenders[:20])
    )


def test_no_pan_literals_anywhere_outside_fixtures():
    """Голые PAN-литералы во всех отслеживаемых текстовых файлах, включая tests/.

    tests/ больше не пропускается целиком: разрешены публичные тест-PAN и явно объявленные
    фикстуры проекта (KNOWN_FIXTURES). Сырые дампы _audit/_e_raw/ освобождены только от этого
    правила — их цифровой шум разобран по контексту, и для них отдельно работает проверка
    карточных шаблонов ниже.
    """
    offenders: list[str] = []
    for rel, text in _tracked_files():
        if _raw_dump(rel):
            continue
        offenders += _bare_pan_offenders(rel, text)
    assert not offenders, (
        "в репозитории найдены PAN вне публичного набора и фикстур: "
        + "; ".join(offenders[:20])
    )


def test_no_card_context_patterns_including_raw_dumps():
    """Карточные шаблоны (PAN|MM|YY|CVV и PAN рядом со словом card/cvv) — без освобождений."""
    offenders: list[str] = []
    for rel, text in _tracked_files():
        offenders += _context_offenders(rel, text)
    assert not offenders, (
        "карточные данные в карточном контексте: " + "; ".join(offenders[:20])
    )


def test_scan_actually_covers_the_repo():
    """Скан не должен выродиться: расширения и объём проверяются явно."""
    files = list(_tracked_files())
    exts = {pathlib.Path(rel).suffix.lower() for rel, _ in files}
    # Порог снижен после чистки проекта (Фиксация №57): из индекса убраны 823 файла сырых дампов
    # (_audit/_e_raw и _audit/tmp). Проверяем, что скан не выродился, а не абсолютный объём.
    assert len(files) >= 200, f"просканировано всего {len(files)} файлов — скан выродился"
    for ext in (".py", ".json", ".md", ".txt"):
        assert ext in exts, f"тип {ext} выпал из скана"
    assert any(rel.startswith(STRICT_PREFIXES) for rel, _ in files), "data/ не попал в скан"


def test_telegram_credentials_are_env_only():
    """Публичная пара официального клиента Telegram не должна быть дефолтом."""
    text = (ROOT / "bot" / "main.py").read_text(encoding="utf-8")
    assert "eb06d4abfb49dc3eeb1aeb98ae0f581e" not in text
    assert "PUSTO_TG_API_ID" in text and "PUSTO_TG_API_HASH" in text


def test_no_foreign_absolute_paths_in_scratch():
    """В scratch/ не должно быть путей внутрь чужих каталогов агентов."""
    offenders: list[str] = []
    for rel in _git("ls-files", "scratch/*.py").splitlines():
        text = (ROOT / rel).read_text(encoding="utf-8", errors="replace")
        if ".gemini" in text or "antigravity" in text:
            offenders.append(rel)
    assert not offenders, "абсолютные пути во внешние каталоги: " + ", ".join(offenders)


# Поле регистрационного nonce с непустым значением в JSON. Голое имя поля ловить нельзя: оно
# упоминается в документации и в этом файле как описание находки, и это законно.
RE_REG_NONCE_ASSIGNED = re.compile(r'"reg_nonce_value"\s*:\s*"([^"]+)"')


def test_no_registration_nonce_values_in_tracked_files():
    """Значения регистрационного nonce не должны лежать ни в одном отслеживаемом файле.

    До Фиксации №65 в индексе был `data/scout_pool.json` — 19 живых `pk_live_*` и 190 значений этого
    поля. Ловится класс, а не конкретный файл: имя поля упоминать можно, значение — нет.
    """
    offenders: list[str] = []
    for rel, text in _tracked_files():
        for m in RE_REG_NONCE_ASSIGNED.finditer(text):
            if m.group(1) in NONCE_PLACEHOLDERS:
                continue
            offenders.append(f"{rel}: {m.group(1)[:4]}… ({len(m.group(1))} симв.)")
    assert not offenders, (
        "в отслеживаемых файлах лежат значения регистрационного nonce: "
        + "; ".join(sorted(set(offenders))[:20])
    )


def test_gitignore_covers_bot_wal_and_scout_pool():
    """WAL/SHM боевой базы бота и пул S0→S2 — вне репозитория (Фиксация №65)."""
    text = (ROOT / ".gitignore").read_text(encoding="utf-8")
    for pattern in ("bot/bot_users.db-shm", "bot/bot_users.db-wal", "data/scout_pool.json"):
        assert pattern in text, f"в .gitignore нет правила {pattern!r}"

