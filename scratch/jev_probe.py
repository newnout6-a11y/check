# language: Python 3.14, file: scratch/jev_probe.py, target: Windows 11, deps: jev (typesafe-sdk)
"""Полевые испытания Jev: где он точен, где слеп и сколько стоит по времени.

Задача не в том, чтобы показать, что движок отвечает, а в том, чтобы измерить,
можно ли на него опираться на этом стенде. Поэтому у каждой пробы ожидание
объявлено заранее, а вердикт считает код, а не глаз.

Пробы:
  1. чувствительность к state — один вопрос при двух противоположных состояниях.
     Если значения не расходятся, state не читается, и как судья по коду движок
     бесполезен;
  2. отрицание — та же пара с обратной формулировкой (проверка, что модель читает
     смысл, а не ключевые слова);
  3. форма кода — известная ошибка в сниппете против исправленного;
  4. закрытый мир — факт о непубличном поведении Stripe, которого в весах модели
     нет (по AGENTS.md это слепая зона). Значение фиксируем, не судим;
  5. choice на живом коде — три утверждения проекта, истина о которых известна
     из замеров 2026-09-18: два закрытых и один открытый;
  6. score — различает ли настоящего сторожа от бутафории;
  7. время — три повтора одного вопроса и пачка из трёх, плюс заявленные ~100 мс
     против фактических.

Живой запуск: python scratch/jev_probe.py
"""
from __future__ import annotations

import os
import pathlib
import statistics
import sys
import time

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import jev

ROOT = pathlib.Path(__file__).resolve().parent.parent
REPORT_PATH = pathlib.Path(__file__).resolve().parent / "jev_probe_report.txt"
REPORT: list[str] = []
results: list[tuple[str, str, str, str]] = []


def say(line: str = "") -> None:
    """Печать идёт в файл-отчёт: консоль Windows портит кириллицу при захвате вывода."""
    REPORT.append(line)


def excerpt(rel: str, needle: str, span: int = 42) -> str:
    """Живой фрагмент файла: от строки с needle и span строк вперёд."""
    lines = (ROOT / rel).read_text(encoding="utf-8", errors="replace").splitlines()
    for i, ln in enumerate(lines):
        if needle in ln:
            return "\n".join(lines[i:i + span])
    return "\n".join(lines[:span])


def record(name: str, value: str, expected: str, ok: bool | None) -> None:
    verdict = "измерено" if ok is None else ("ПРОШЛА" if ok else "ПРОВАЛ")
    results.append((name, value, expected, verdict))


GATE_WITH = excerpt("gate_client.py", "def tokenize_payment_method")
GATE_WITHOUT = "\n".join((ROOT / "config.py").read_text(encoding="utf-8").splitlines()[:60])
BAD = "def total(rows):\n    acc = defaultdict(int)\n    for r in rows:\n        acc[r] += 1\n    return acc\n"
GOOD = "from collections import defaultdict\n\n" + BAD

say(f"замер: {time.strftime('%Y-%m-%d %H:%M')} MSK | движок: {jev.DEFAULT_MODEL} | ключ из окружения: "
    + ("да" if os.environ.get("TYPESAFE_API_KEY") else "нет, взят встроенный в jev.py"))
say("модуль: " + jev.__file__)

# --- 1. чувствительность к state ------------------------------------------------
q1 = "The file defines a function named tokenize_payment_method."
v = jev.noul(q1, {"file": GATE_WITH})
record("1a state: функция есть в файле", f"{v:.2f}", ">= 0.90", v >= 0.90)
v = jev.noul(q1, {"file": GATE_WITHOUT})
record("1b state: функции нет в файле", f"{v:.2f}", "<= 0.10", v <= 0.10)

# --- 2. отрицание ---------------------------------------------------------------
q2 = "The file does NOT define a function named tokenize_payment_method."
v = jev.noul(q2, {"file": GATE_WITH})
record("2a отрицание при наличии", f"{v:.2f}", "<= 0.10", v <= 0.10)
v = jev.noul(q2, {"file": GATE_WITHOUT})
record("2b отрицание при отсутствии", f"{v:.2f}", ">= 0.90", v >= 0.90)

# --- 3. форма кода --------------------------------------------------------------
q3 = "This snippet raises NameError at runtime because defaultdict is undefined."
v = jev.noul(q3, {"snippet": BAD})
record("3a ошибка в сниппете", f"{v:.2f}", ">= 0.80", v >= 0.80)
v = jev.noul(q3, {"snippet": GOOD})
record("3b тот же сниппет с импортом", f"{v:.2f}", "<= 0.20", v <= 0.20)

# --- 4. закрытый мир (слепая зона, не судим) ------------------------------------
q4 = "A POST request to /v1/3ds2/authenticate without an API key returns HTTP 401."
t0 = time.perf_counter()
v = jev.noul(q4, {"note": "no network access, no documentation, no prior measurements"})
t_blind = (time.perf_counter() - t0) * 1000
record("4 закрытый мир (слепая зона)", f"{v:.2f} за {t_blind:.0f} мс",
       "не судим — факт измерен нами сегодня: 401", None)

# --- 5. choice на живом коде: истина известна --------------------------------
c_fixed = {"FIXED": "the current file already guards or removes the problem",
           "OPEN": "the current file still shows the problem as described"}
c_claim = "data/scout_pool.json with live keys is not covered by .gitignore"
c_state = {"claim": c_claim, "gitignore": (ROOT / ".gitignore").read_text(encoding="utf-8")}
c = jev.choice("Classify the claim against the current state.", c_fixed, c_state)
record("5a scout_pool в .gitignore", f"{c['choice']} ({c['confidence']:.2f})",
       "FIXED — закрыто Фиксацией №65", c["choice"] == "FIXED")

c_claim = "tests/test_confirm_body_parity.py compares the confirm version with the constant config.STRIPE_JS_BUILD"
c_state = {"claim": c_claim, "test_file": (ROOT / "tests" / "test_confirm_body_parity.py").read_text(encoding="utf-8")}
c = jev.choice("Classify the claim against the current state.", c_fixed, c_state)
record("5b тест цементирует константу", f"{c['choice']} ({c['confidence']:.2f})",
       "FIXED — закрыто волной №64", c["choice"] == "FIXED")

c_open = {"OPEN": "the code still constructs the pool without arguments and the punishment path is a no-op",
          "FIXED": "the pool receives entries or the punishment path is guarded"}
c_claim = ("bot/gates/storegate.py creates ProxyPool() without arguments, so mark_bad never punishes "
           "and overwrites data/proxy_health.json with an empty list")
c_state = {"claim": c_claim,
           "storegate": excerpt("bot/gates/storegate.py", "ProxyPool("),
           "proxy_health": (ROOT / "data" / "proxy_health.json").read_text(encoding="utf-8", errors="replace")}
c = jev.choice("Classify the claim against the current state.", c_open, c_state)
record("5c storegate: штраф прокси — no-op", f"{c['choice']} ({c['confidence']:.2f})",
       "OPEN — дефект из №62 не исправлен", c["choice"] == "OPEN")

# --- 6. score: настоящий сторож против бутафории ------------------------------
rubric = ["no assertion at all",
          "asserts a tautology that cannot fail",
          "asserts a property, but not the invariant named in the claim",
          "asserts exactly the invariant named in the claim"]
fake = "def test_guard():\n    assert True\n"
real = ("def test_pipeline_states_never_collide_with_verdicts():\n"
        "    overlap = set(config.PIPELINE_STATES) & set(config.VERDICTS)\n"
        "    assert not overlap\n"
        "    assert 'UNKNOWN' not in config.REFUNDABLE_VERDICTS\n")
instr = "Score how well this test closes the stated class of defect."
s_fake = jev.score(instr, rubric, {"claim": "pipeline states must never collide with verdicts", "test": fake})
s_real = jev.score(instr, rubric, {"claim": "pipeline states must never collide with verdicts", "test": real})
record("6a score бутафории", f"{s_fake['score']} ({s_fake['confidence']:.2f})", "ниже, чем у настоящего", None)
record("6b score настоящего сторожа", f"{s_real['score']} ({s_real['confidence']:.2f})", "выше, чем у бутафории",
       s_real["score"] > s_fake["score"])

# --- 7. время -------------------------------------------------------------------
lat = []
vals = []
for _ in range(3):
    t0 = time.perf_counter()
    vals.append(jev.noul("The file defines a function named tokenize_payment_method.", {"file": GATE_WITH}))
    lat.append((time.perf_counter() - t0) * 1000)
t0 = time.perf_counter()
jev.batch({"a": {"type": "noul", "instructions": q1},
           "b": {"type": "noul", "instructions": q2},
           "c": {"type": "noul", "instructions": q3}},
          {"file": GATE_WITH, "snippet": BAD})
t_batch = (time.perf_counter() - t0) * 1000
record("7a один вопрос, три повтора",
       f"{min(lat):.0f} / {statistics.median(lat):.0f} / {max(lat):.0f} мс",
       "AGENTS.md обещает ~100 мс", statistics.median(lat) < 200)
record("7c стабильность значения", " / ".join(f"{v:.2f}" for v in vals), "одинаковый ответ на тот же вход",
       len(set(vals)) == 1)
record("7b пачка из трёх", f"{t_batch:.0f} мс", "выгоднее трёх одиночных",
       t_batch < sum(lat) / len(lat) * 2)

# --- сводка ---------------------------------------------------------------------
w = max(len(r[0]) for r in results)
say(f"{'проба'.ljust(w)} | {'значение'.ljust(24)} | ожидание | вердикт")
say("-" * (w + 62))
for name, value, expected, verdict in results:
    say(f"{name.ljust(w)} | {value.ljust(24)} | {expected} | {verdict}")
passed = sum(1 for r in results if r[3] == "ПРОШЛА")
failed = sum(1 for r in results if r[3] == "ПРОВАЛ")
say()
say(f"итог: прошло {passed}, провалено {failed}, измерено без суда {len(results) - passed - failed}")
say("слепая зона (проба 4) — единственная, где ожидание сознательно не выставлялось:")
say("факт о непубличном поведении Stripe измерен нами сегодня (401), у модели такого замера нет.")
REPORT_PATH.write_text("\n".join(REPORT), encoding="utf-8")
print("report:", REPORT_PATH)
