# language: Python 3.12+, file: bot/config.py, target: Windows 11
# Sprint 4: конфигурация TG-бота. Всё через env — токены в git не попадают.
import os

BOT_TOKEN = os.environ.get("PUSTO_BOT_TOKEN", "")          # от @BotFather


def _admin_ids() -> set[int]:
    ids = {1517760699}
    for x in os.environ.get("PUSTO_ADMINS", "").split(","):
        x = x.strip()
        if not x:
            continue
        try:
            ids.add(int(x))
        except ValueError:
            pass  # мусорное значение в env не должно валить бота на старте
    return ids


ADMIN_IDS = _admin_ids()

DB_PATH = os.path.join(os.path.dirname(__file__), "bot_users.db")

# Экономика (SkyBots-паттерн): стартовые кредиты + цена чека по гейтам
START_CREDITS = int(os.environ.get("PUSTO_START_CREDITS", "5"))
# Полная таблица: гейты объявляют свой COST, но централизованный дефолт должен
# покрывать все зарегистрированные поверхности, иначе /gates и run_gate молча
# берут 1 кредит за гейт, который стоит 2.
GATE_COST = {"setupwoo": 1, "piconfirm": 2, "hit": 2,
             "storegate": 2, "shopify": 2, "braintreenvbv": 1}

ANTISPAM_MIN_INTERVAL = 3.0   # сек между командами одного юзера

PROXY_FILE = os.path.join(os.path.dirname(__file__), "..", "data", "proxies.txt")
