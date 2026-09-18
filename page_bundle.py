# language: Python 3.12+, file: page_bundle.py, target: Windows 11, deps: stdlib
"""Набор полей, которым страница Stripe подтверждает платёж — снятый с ЖИВОЙ страницы.

Зачем: HTTP-путь (/hit) умирает на Radar, а страница проходит его без челленджа. Разница — в теле confirm.
Замер по нашим перехватам: страница шлёт

    guid, muid, sid, init_checksum, version, expected_amount,
    js_checksum, rv_timestamp, passive_captcha_token        (съём 2026-09-15)

а наш /hit шлёт `init_checksum` и версию, но БЕЗ `js_checksum`, `rv_timestamp` и без
`passive_captcha_token` — вместо него мы кладём предварительный P1_-токен в чужое поле
`radar_options[hcaptcha_token]`. Radar такой токен считает сожжённым и отвечает CHALLENGE_BURNED.

Модуль делает одно: читает тело confirm, снятое браузерным контуром (data/results/run_*.json),
и отдаёт его поля в /hit, чтобы наш confirm был той же формы, что у страницы.

CLI:
    python page_bundle.py --from-report data/results/run_XXXX.json     # собрать набор из отчёта
    python page_bundle.py --show                                       # что лежит в наборе
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys
import time

import config

# Поля страницы, которые переносим в наш confirm. Ключи — как в теле запроса.
PAGE_FIELDS = (
    "js_checksum",
    "rv_timestamp",
    "passive_captcha_token",
    "px3",
    "pxvid",
    "pxcts",
    "init_checksum",
    "version",
)
# Никогда не переносим: это наше, а не страницы.
NEVER = ("payment_method", "key", "eid", "expected_amount", "expected_payment_method_type", "return_url")


def bundle_path() -> pathlib.Path:
    return pathlib.Path(getattr(config, "PAGE_BUNDLE_PATH", "data/page_bundle.json"))


def parse_body(body: str) -> dict[str, str]:
    """Тело confirm (urlencoded) -> словарь. Значения НЕ декодируем: страница шлёт их как есть."""
    out: dict[str, str] = {}
    for part in (body or "").split("&"):
        if "=" not in part:
            continue
        k, v = part.split("=", 1)
        if k and k not in NEVER:
            out[k] = v
    return out


def from_report(path: str | pathlib.Path) -> dict:
    """Собирает набор из отчёта браузерного прогона (confirms[].body)."""
    raw = json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
    bodies = [c.get("body") or "" for c in raw.get("confirms", []) if c.get("kind") == "req"]
    if not bodies:
        raise SystemExit(f"в отчёте {path} нет тела confirm (confirms[].kind == req)")
    body = max(bodies, key=len)                      # самое полное тело из перехваченных
    fields = parse_body(body)
    bundle = {
        "link": (raw.get("link") or "").split("#")[0],
        "harvested_at": time.time(),
        "harvested_date": time.strftime("%Y-%m-%d %H:%M:%S"),
        "source_report": str(path),
        "fields": {k: v for k, v in fields.items() if k in PAGE_FIELDS},
        "seen_keys": sorted(fields.keys()),
    }
    return bundle


def from_capture(path: str | pathlib.Path) -> dict:
    """Собирает набор из тела confirm, снятого перехватом CDP (tools/hcaptcha_capture.cjs).

    Отличие от отчёта: у перехвата есть только URL запроса и тело. Сессию берём из URL
    (/payment_pages/{cs}/confirm), ссылку не знаем — fields_for() сверяет по cs.
    """
    raw = json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
    body = str(raw.get("body") or "")
    if not body:
        raise SystemExit(f"в {path} нет тела confirm")
    m = re.search(r"/payment_pages/(cs_[A-Za-z0-9]+)/confirm", str(raw.get("url") or ""))
    fields = parse_body(body)
    return {
        "link": "",
        "cs": m.group(1) if m else "",
        "harvested_at": time.time(),
        "harvested_date": time.strftime("%Y-%m-%d %H:%M:%S"),
        "source_report": str(path),
        "fields": {k: v for k, v in fields.items() if k in PAGE_FIELDS},
        "seen_keys": sorted(fields.keys()),
    }


def save(bundle: dict) -> pathlib.Path:
    p = bundle_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(bundle, ensure_ascii=False, indent=1), encoding="utf-8")
    return p


def load() -> dict:
    try:
        data = json.loads(bundle_path().read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def fields_for(cs_id: str | None = None) -> dict[str, str]:
    """Поля страницы для подстановки в confirm. Пусто, если набора нет или он от другой сессии."""
    data = load()
    if not data.get("fields"):
        return {}
    if cs_id:
        cs = str(data.get("cs") or "")
        if cs:
            return dict(data["fields"]) if cs == cs_id else {}   # набор снят под другую сессию
        link = str(data.get("link") or "")
        if link and cs_id not in link:
            return {}                                 # набор от другой ссылки — не мешаем
    return dict(data["fields"])


def age_s(bundle: dict | None = None) -> float | None:
    data = bundle if bundle is not None else load()
    at = data.get("harvested_at")
    return None if not at else max(0.0, time.time() - float(at))


def summarise(bundle: dict) -> str:
    names = ", ".join(bundle.get("fields", {}).keys()) or "—"
    age = age_s(bundle)
    return (f"набор от {bundle.get('harvested_date', '—')} "
            f"(возраст {age/60:.1f} мин), поля: {names}\nисточник: {bundle.get('source_report', '—')}")


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="Поля страницы Stripe для /hit")
    ap.add_argument("--from-report", dest="report", help="отчёт браузерного прогона run_*.json")
    ap.add_argument("--from-capture", dest="capture", help="перехват CDP data/confirm_capture.json")
    ap.add_argument("--show", action="store_true", help="показать текущий набор")
    args = ap.parse_args(argv)

    if args.report or args.capture:
        bundle = from_report(args.report) if args.report else from_capture(args.capture)
        p = save(bundle)
        print(f"[+] набор сохранён: {p}")
        print(summarise(bundle))
        return 0
    if args.show:
        data = load()
        if not data:
            print("набора нет")
            return 1
        print(summarise(data))
        print("поля:", json.dumps(data.get("fields", {}), ensure_ascii=False)[:600])
        return 0
    ap.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
