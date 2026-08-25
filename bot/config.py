# language: Python 3.12+, file: bot/config.py, target: Windows 11
# Sprint 4: конфигурация TG-бота. Всё через env — токены в git не попадают.
import os

BOT_TOKEN = os.environ.get("PUSTO_BOT_TOKEN", "")          # от @BotFather
ADMIN_IDS = {int(x) for x in os.environ.get("PUSTO_ADMINS", "").split(",") if x.strip()}

DB_PATH = os.path.join(os.path.dirname(__file__), "bot_users.db")

# Экономика (SkyBots-паттерн): стартовые кредиты + цена чека по гейтам
START_CREDITS = int(os.environ.get("PUSTO_START_CREDITS", "5"))
GATE_COST = {"setupwoo": 1, "piconfirm": 2}

ANTISPAM_MIN_INTERVAL = 3.0   # сек между командами одного юзера

PROXY_FILE = os.path.join(os.path.dirname(__file__), "..", "data", "proxies.txt")
