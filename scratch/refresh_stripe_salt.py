#!/usr/bin/env python
# language: Python 3.12+, file: scratch/refresh_stripe_salt.py, target: Windows 11, deps: stdlib
"""Актуализация соли сборки stripe.js (config.STRIPE_JS_BUILD).

Зачем: соль меняется вместе с бандлом js.stripe.com/v3 (в сентябре 2026 — f0a6d7cfcd,
до этого fe705f067f / eb42eea6af / c1fbe29896). Держать её значение в тесте бессмысленно —
тест цементирует устаревшее состояние (аудит 2026-09, C-01 / M-07). Поэтому формат проверяет
тест, а актуальность — этот скрипт против живого бандла.

    python scratch/refresh_stripe_salt.py --check    # exit 1, если config.py отстал
    python scratch/refresh_stripe_salt.py --write    # вписать живую соль в config.py
    python scratch/refresh_stripe_salt.py --print    # только показать обе соли

Коды выхода: 0 — совпадает, 1 — расходится, 2 — не удалось получить/разобрать бандл.
"""
from __future__ import annotations

import argparse
import pathlib
import re
import sys
import urllib.error
import urllib.request

BUNDLE_URL = "https://js.stripe.com/v3/"
SALT_IN_BUNDLE = re.compile(r"STRIPE_JS_BUILD_SALT ([0-9a-f]{10})")
SALT_IN_CONFIG = re.compile(r'^STRIPE_JS_BUILD = "([0-9a-f]{10})"', re.M)
CONFIG_PATH = pathlib.Path(__file__).resolve().parent.parent / "config.py"


def live_salt(timeout: float = 30.0) -> str:
    """Соль из живого бандла. Бросает RuntimeError, если бандл недоступен или сменил формат."""
    req = urllib.request.Request(BUNDLE_URL, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8", "replace")
    except (urllib.error.URLError, OSError) as exc:
        raise RuntimeError(f"бандл {BUNDLE_URL} недоступен: {exc}") from exc
    m = SALT_IN_BUNDLE.search(body)
    if not m:
        raise RuntimeError("в бандле нет метки STRIPE_JS_BUILD_SALT — формат бандла изменился")
    return m.group(1)


def config_salt() -> str:
    m = SALT_IN_CONFIG.search(CONFIG_PATH.read_text(encoding="utf-8"))
    if not m:
        raise RuntimeError(f"в {CONFIG_PATH.name} не найдена строка STRIPE_JS_BUILD")
    return m.group(1)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Сверка/обновление соли сборки stripe.js")
    ap.add_argument("--check", action="store_true", help="exit 1, если config.py отстал от живого бандла")
    ap.add_argument("--write", action="store_true", help="вписать живую соль в config.py")
    ap.add_argument("--print", dest="show", action="store_true", help="показать обе соли и выйти")
    args = ap.parse_args(argv)

    try:
        live = live_salt()
    except RuntimeError as exc:
        print(f"[!] {exc}")
        return 2
    local = config_salt()

    if args.show:
        print(f"config.py: {local}\nбандл:     {live}")
        return 0 if local == live else 1

    if live == local:
        print(f"[+] соль актуальна: {local}")
        return 0

    print(f"[!] соль устарела: в config.py {local}, в бандле {live}")
    if args.write:
        text = CONFIG_PATH.read_text(encoding="utf-8")
        CONFIG_PATH.write_text(SALT_IN_CONFIG.sub(f'STRIPE_JS_BUILD = "{live}"', text, count=1), encoding="utf-8")
        print(f"[+] config.py обновлён: {live}")
        return 0
    if args.check:
        return 1
    print("    запусти с --write, чтобы обновить, или с --check для exit 1")
    return 1


if __name__ == "__main__":
    sys.exit(main())
