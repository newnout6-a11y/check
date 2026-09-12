# language: Python 3.12+, file: tests/conftest.py, target: Windows 11
# pytest-подводка: корень проекта в sys.path, чтобы импортировать модули без установки.
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

# bot.main на импорте требует креды Telegram из окружения (Фиксация №25: публичной пары
# официального клиента в коде больше нет — раньше она стояла дефолтом). Тестам нужны
# фиктивные значения, иначе импорт модуля завершается SystemExit. Реальные креды не нужны:
# тесты офлайновые и клиент не подключается.
os.environ.setdefault("PUSTO_TG_API_ID", "1")
os.environ.setdefault("PUSTO_TG_API_HASH", "0" * 32)
