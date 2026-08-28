# language: Python 3.12+, file: tests/conftest.py, target: Windows 11
# pytest-подводка: корень проекта в sys.path, чтобы импортировать модули без установки.
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
