# language: Python 3.14, file: scratch/jev_audit.py, target: Windows 11, deps: jev (typesafe-sdk)
"""Аудит кода через Jev так, как его задумали: файл целиком в state, вопросы — в questions.

Ничего не подмешиваем и не подсказываем: дампится весь модуль, вопросы ставятся по одному
на суждение, ответы собираются одним запросом на файл (speculative fan-out).
Истина известна заранее — из аудита 2026-09 и разбора Фиксации №62:
  confirm_gate.py:294-298 — цикл while '--proxy' in raw_args не удаляет элемент, если он
      последний, и крутится вечно; это единственный дефект класса «отказ, а не мелочь»;
  stripe_salt.py:38,106 — _cache_memo заполняется и НИКОГДА не читается: мёртвое состояние.

Живой запуск: python scratch/jev_audit.py
"""
from __future__ import annotations

import os
import pathlib
import sys
import time

sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from typesafe_sdk import Choice, Noul, TypeSafeClient

ROOT = pathlib.Path(__file__).resolve().parent.parent
REPORT_PATH = pathlib.Path(__file__).resolve().parent / 'jev_audit_report.txt'
REPORT: list[str] = []


def say(line: str = '') -> None:
    REPORT.append(line)


def full(rel: str) -> str:
    return (ROOT / rel).read_text(encoding='utf-8', errors='replace')


evidence: list[tuple[str, str, str, str]] = []


def record(where: str, what: str, value: str, truth: str, ok: bool | None) -> None:
    verdict = 'измерено' if ok is None else ('ПОПАЛ' if ok else 'МИМО')
    evidence.append((where, what, value, truth + ' | ' + verdict))


say(f'замер: {time.strftime("%Y-%m-%d %H:%M")} MSK | ключ: ' + ('env' if os.environ.get('TYPESAFE_API_KEY') else 'встроенный'))
say()

# ---- файл 1: confirm_gate.py целиком --------------------------------------
code = full('confirm_gate.py')
first_class = next(l.split()[1].rstrip(':') for l in code.splitlines() if l.startswith('class '))
has_requests = 'import requests' in code
say(f'файл 1: confirm_gate.py — {len(code)} символов, {len(code.splitlines())} строк | класс в файле: {first_class} | import requests: {has_requests}')

with TypeSafeClient(model='jev-1.13.0') as cli:
    t0 = time.perf_counter()
    r = cli.system_one(
        {'file': 'confirm_gate.py', 'code': code},
        {
            'hang':      Noul(instructions='Can the loop while --proxy in raw_args inside main() run forever when the argument --proxy is the last element of raw_args and no value follows it?'),
            'any_hang':  Noul(instructions='Does this file contain a defect that can make the tool hang or never terminate?'),
            'severity':  Choice(instructions='Classify the most severe real defect present in this file. Ignore style and naming.',
                                criteria={'NO_REAL_DEFECT': 'no defect that changes runtime behaviour',
                                          'DEAD_CODE': 'unreachable, unused or dead state only',
                                          'WRONG_RESULT': 'produces a wrong verdict or wrong output',
                                          'HANG_OR_CRASH': 'can hang, never terminate or crash the process'}),
            'ctl_class': Noul(instructions=f'Is a class named {first_class} defined in this file?'),
            'ctl_req':   Noul(instructions='Does this file import the requests library?'),
        },
    )
    dt1 = (time.perf_counter() - t0) * 1000
a = r.answers
record('confirm_gate.py', 'цикл --proxy может крутиться вечно', f"{a['hang'].noul:.2f}", 'истина: да', a['hang'].noul >= 0.80)
record('confirm_gate.py', 'есть дефект-зависание', f"{a['any_hang'].noul:.2f}", 'истина: да', a['any_hang'].noul >= 0.80)
record('confirm_gate.py', 'класс серьезности', f"{a['severity'].choice} ({a['severity'].confidence:.2f})", 'истина: HANG_OR_CRASH', a['severity'].choice == 'HANG_OR_CRASH')
record('confirm_gate.py', f'контроль: класс {first_class} есть', f"{a['ctl_class'].noul:.2f}", 'истина: да', a['ctl_class'].noul >= 0.90)
record('confirm_gate.py', 'контроль: import requests есть', f"{a['ctl_req'].noul:.2f}", 'истина: нет', a['ctl_req'].noul <= 0.10)
say(f'   один запрос, 5 вопросов: {dt1:.0f} мс | токенов: {r.usage.input_tokens} | модель: {r.model}')
say()

# ---- файл 2: stripe_salt.py целиком ---------------------------------------
code2 = full('stripe_salt.py')
say(f'файл 2: stripe_salt.py — {len(code2)} символов, {len(code2.splitlines())} строк')

with TypeSafeClient(model='jev-1.13.0') as cli:
    t0 = time.perf_counter()
    r2 = cli.system_one(
        {'file': 'stripe_salt.py', 'code': code2},
        {
            'memo_read': Noul(instructions='After _cache_memo is updated on line 106, is its value ever read by any code in this file?'),
            'fallback':  Noul(instructions='Does this file fall back to the constant config.STRIPE_JS_BUILD when the live bundle is unreachable?'),
            'severity':  Choice(instructions='Classify the most severe real defect present in this file. Ignore style and naming.',
                                criteria={'NO_REAL_DEFECT': 'no defect that changes runtime behaviour',
                                          'DEAD_CODE': 'unreachable, unused or dead state only',
                                          'WRONG_RESULT': 'produces a wrong verdict or wrong output',
                                          'HANG_OR_CRASH': 'can hang, never terminate or crash the process'}),
        },
    )
    dt2 = (time.perf_counter() - t0) * 1000
b = r2.answers
record('stripe_salt.py', '_cache_memo читается после записи', f"{b['memo_read'].noul:.2f}", 'истина: нет', b['memo_read'].noul <= 0.20)
record('stripe_salt.py', 'фолбэк на config.STRIPE_JS_BUILD', f"{b['fallback'].noul:.2f}", 'истина: да', b['fallback'].noul >= 0.80)
record('stripe_salt.py', 'класс серьезности', f"{b['severity'].choice} ({b['severity'].confidence:.2f})", 'истина: DEAD_CODE', b['severity'].choice == 'DEAD_CODE')
say(f'   один запрос, 3 вопроса: {dt2:.0f} мс | токенов: {r2.usage.input_tokens} | модель: {r2.model}')
say()

w1 = max(len(e[0]) for e in evidence)
w2 = max(len(e[1]) for e in evidence)
say(f"{'файл'.ljust(w1)} | {'вопрос'.ljust(w2)} | ответ | истина")
say('-' * (w1 + w2 + 40))
for where, what, value, truth in evidence:
    say(f'{where.ljust(w1)} | {what.ljust(w2)} | {value.ljust(20)} | {truth}')
hit = sum(1 for e in evidence if e[3].endswith('ПОПАЛ'))
say()
say(f'итог: попаданий {hit} из {len(evidence)}')
REPORT_PATH.write_text('\n'.join(REPORT), encoding='utf-8')
print('report:', REPORT_PATH)