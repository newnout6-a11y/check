# language: Python 3.12+, file: stripe_salt.py, target: Windows 11, deps: stdlib
"""Актуальная соль сборки stripe.js — тянется из живого бандла, а не берётся из константы.

Зачем: соль ротируется вместе с бандлом js.stripe.com/v3 (2026-09-15 она сменилась дважды за день:
f0a6d7cfcd -> 2cbe95f953). Она уходит в тело confirm (`version=`), в `v=` hCaptcha и в
`payment_user_agent`, поэтому устаревшее значение — это расхождение с витриной. Аудит 2026-09 (H-02 /
C-01) закрывал такое руками; теперь значение подставляется само.

Порядок разрешения (первое успешное побеждает):
  1. переменная окружения `PUSTO_STRIPE_SALT` (для тестов и офлайна);
  2. кэш `data/stripe_salt.json`, если он не старше TTL (по умолчанию 6 часов);
  3. живой бандл `https://js.stripe.com/v3/` (при успехе кэш обновляется);
  4. `config.STRIPE_JS_BUILD` — последний рубеж, чтобы прогон не падал без сети.

CLI:
    python stripe_salt.py            # что видно сейчас: env / кэш / живой бандл / конфиг
    python stripe_salt.py --check    # exit 1, если fallback в config.py отстал от живой соли
    python stripe_salt.py --refresh  # принудительно перечитать бандл и обновить кэш
"""
from __future__ import annotations

import json
import os
import pathlib
import re
import sys
import time
import urllib.error
import urllib.request

import config

BUNDLE_URL = "https://js.stripe.com/v3/"
SALT_RE = re.compile(r"STRIPE_JS_BUILD_SALT ([0-9a-f]{10})")
ENV_VAR = "PUSTO_STRIPE_SALT"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36"

_cache_memo: dict[str, object] = {"salt": None, "at": 0.0}


def parse_salt(bundle_text: str) -> str | None:
    """Соль из текста бандла. None, если метка не найдена (формат бандла сменился)."""
    m = SALT_RE.search(bundle_text)
    return m.group(1) if m else None


def cache_path() -> pathlib.Path:
    return pathlib.Path(getattr(config, "STRIPE_SALT_CACHE_PATH", "data/stripe_salt.json"))


def cache_ttl() -> float:
    return float(getattr(config, "STRIPE_SALT_TTL_S", 6 * 3600))


def load_cache() -> dict:
    try:
        raw = json.loads(cache_path().read_text(encoding="utf-8"))
        return raw if isinstance(raw, dict) else {}
    except (OSError, ValueError):
        return {}


def save_cache(salt: str, fetched_at: float | None = None) -> None:
    p = cache_path()
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps({"salt": salt, "fetched_at": fetched_at or time.time()}, ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass


def fetch_live_salt(timeout: float = 15.0) -> str | None:
    """Соль из живого бандла. Никогда не бросает: сеть — не повод валить прогон."""
    req = urllib.request.Request(BUNDLE_URL, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8", "replace")
    except (urllib.error.URLError, OSError, ValueError):
        return None
    return parse_salt(body)


def cached_salt(max_age_s: float | None = None) -> str | None:
    data = load_cache()
    salt = data.get("salt")
    if not isinstance(salt, str) or not re.fullmatch(r"[0-9a-f]{10}", salt):
        return None
    age = time.time() - float(data.get("fetched_at") or 0)
    if age > (cache_ttl() if max_age_s is None else max_age_s):
        return None
    return salt


def current_salt(refresh: bool = False) -> str:
    """Соль для подстановки в запросы. Порядок разрешения — в docstring модуля."""
    env = os.environ.get(ENV_VAR)
    if env and re.fullmatch(r"[0-9a-f]{10}", env):
        return env
    if not refresh:
        fresh = cached_salt()
        if fresh:
            return fresh
    live = fetch_live_salt()
    if live:
        save_cache(live)
        _cache_memo.update({"salt": live, "at": time.time()})
        return live
    stale = load_cache().get("salt")
    if isinstance(stale, str) and re.fullmatch(r"[0-9a-f]{10}", stale):
        return stale
    return config.STRIPE_JS_BUILD


def main(argv: list[str]) -> int:
    refresh = "--refresh" in argv
    env = os.environ.get(ENV_VAR)
    live = fetch_live_salt()
    print(f"env {ENV_VAR}:      {env or '—'}")
    print(f"кэш:                {load_cache() or '—'}")
    print(f"живой бандл:        {live or 'недоступен'}")
    print(f"config (fallback):  {config.STRIPE_JS_BUILD}")
    print(f"отдаётся в код:     {current_salt(refresh=refresh)}")
    if "--check" in argv:
        if live is None:
            print("[!] бандл недоступен — сверить не с чем")
            return 2
        if live != config.STRIPE_JS_BUILD:
            print("[!] fallback в config.py отстал от живой соли")
            return 1
        print("[+] config.py совпадает с живой солью")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
