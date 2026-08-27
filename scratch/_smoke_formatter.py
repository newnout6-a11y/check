# language: python, file: scratch/_smoke_formatter.py — визуальная проверка вывода бота
import sys

sys.stdout.reconfigure(encoding="utf-8")
from bot.utils import formatter

print(formatter.format_single(
    "4111111111111111|12|27|123",
    {"scheme": "VISA", "type": "credit", "country": {"alpha2": "US"},
     "bank": {"name": "Chase"}},
    "setupwoo", "DECLINED", "card_declined by issuer", 2340))
print()
print(formatter.format_mass([
    {"card": "5378 87** **** 8595", "status": "APPROVED", "detail": "seti succeeded"},
    {"card": "4420 19** **** 2053", "status": "DECLINED", "detail": "card_declined"},
    {"card": "5164 99** **** 7375", "status": "3DS_CHALLENGE", "detail": "transStatus C"},
]))
