# language: Python 3.14, file: scratch/jev_audit_narrow.py, target: Windows 11, deps: jev (typesafe-sdk)
"""Третий раунд: тот же файл, но вопросы сужены до одного шага — проверка гипотезы,
почему целостный вопрос про зависание промахнулся, а узкий может попасть.

Гипотеза: Jev отвечает на то, что написано в тексте, и плохо моделирует последствия
потока управления. Тогда дефект-зависание ловится не вопросом «может ли зависнуть», а
набором однoшаговых вопросов, каждый из которых человек решает за секунду.

Истина (проверена чтением кода): у while --proxy in raw_args нет ветки else,
элемент не удаляется, если он последний, и цикл не завершается.

Живой запуск: python scratch/jev_audit_narrow.py
"""
from __future__ import annotations

import os
import pathlib
import sys
import time

sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from typesafe_sdk import Noul, TypeSafeClient

ROOT = pathlib.Path(__file__).resolve().parent.parent
REPORT_PATH = pathlib.Path(__file__).resolve().parent / 'jev_audit_narrow_report.txt'
REPORT: list[str] = []
def say(line: str = '') -> None:
    REPORT.append(line)

code = (ROOT / 'confirm_gate.py').read_text(encoding='utf-8', errors='replace')
say(f'замер: {time.strftime("%Y-%m-%d %H:%M")} MSK | файл confirm_gate.py, {len(code)} символов')
say()

questions = {
    'else':    Noul(instructions='Inside the while loop whose condition is --proxy in raw_args, does the if statement that checks i + 1 < len(raw_args) have an else branch?'),
    'removed': Noul(instructions='Inside that loop, when the check i + 1 < len(raw_args) is false, is the element --proxy removed from raw_args?'),
    'always':  Noul(instructions='Is the element --proxy guaranteed to be removed from raw_args on every iteration of that loop?'),
    'ctl':     Noul(instructions='Does the loop body delete exactly two elements from raw_args when a value follows --proxy?'),
}
truth = {'else': ('нет ветки else', False),
         'removed': ('нет, элемент остаётся', False),
         'always': ('нет, гарантии нет', False),
         'ctl': ('да, del raw_args[i:i+2]', True)}

with TypeSafeClient(model='jev-1.13.0') as cli:
    t0 = time.perf_counter()
    r = cli.system_one({'file': 'confirm_gate.py', 'code': code}, questions)
    dt = (time.perf_counter() - t0) * 1000

say(f'один запрос, 4 вопроса: {dt:.0f} мс | токенов: {r.usage.input_tokens}')
say()
say(f"{'вопрос'.ljust(10)} | {'ответ'.ljust(6)} | истина")
say('-' * 70)
hit = 0
for key, t in truth.items():
    v = r.answers[key].noul
    ok = (v >= 0.80) if t[1] else (v <= 0.20)
    hit += ok
    say(f"{key.ljust(10)} | {v:<6.2f} | {t[0]} -> {'ПОПАЛ' if ok else 'МИМО'}")
say()
say(f'узких вопросов попало: {hit} из {len(truth)}')
REPORT_PATH.write_text('\n'.join(REPORT), encoding='utf-8')
print('report:', REPORT_PATH)