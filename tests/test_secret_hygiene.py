# language: Python 3.12+, file: tests/test_secret_hygiene.py, target: Windows 11
"""Гигиена секретов: карточные данные, пулы и креды не должны попадать в репозиторий.

Появились после аудита 2026-09 (Фиксация №25): в git лежали data/probe_20_cards.txt,
data/amex_379363.txt (живые по формату PAN) и data/proxies_https_60k.txt (1 МБ ip:port).
Тесты офлайновые: используется локальный git и чтение файлов, сети нет.
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


def _luhn(number: str) -> bool:
    digits = [int(c) for c in number]
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
            ["git", *args], cwd=ROOT, capture_output=True, text=True, timeout=30
        )
    except (OSError, subprocess.SubprocessError):  # pragma: no cover
        pytest.skip("git недоступен — проверка отслеживания пропущена")
    if out.returncode != 0:
        pytest.skip(f"git {args[0]} вернул {out.returncode}: {out.stderr.strip()[:120]}")
    return out.stdout


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


def test_no_real_pan_literals_in_tracked_code():
    """В отслеживаемом коде (кроме tests/) не должно быть PAN вне публичного тест-набора."""
    rx = re.compile(r"(?<!\d)(?:\d[ -]?){13,19}(?!\d)")
    offenders: list[str] = []
    for rel in _git("ls-files", "*.py").splitlines():
        if rel.startswith("tests/"):
            continue
        try:
            text = (ROOT / rel).read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for m in rx.finditer(text):
            number = re.sub(r"[ -]", "", m.group(0))
            if not 13 <= len(number) <= 19 or number in PUBLIC_TEST_PANS:
                continue
            if _luhn(number):
                offenders.append(f"{rel}: {number[:6]}******{number[-4:]}")
    assert not offenders, "в коде найдены PAN вне публичного тест-набора: " + "; ".join(offenders)


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
