# language: Python 3.12+, file: bot/keyboards.py, target: Windows 11
# Интерактивные клавиатуры для Telegram-бота: выбор шлюзов, ценовых тиров, навигация.
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup

GATE_LABELS = {
    "chk": "⚡ Авто (/chk)",
    "setupwoo": "🟢 Stripe Auth ($0)",
    "storegate": "🛒 Store API",
    "shopify": "🛍 Shopify Vault",
    "hit": "🎯 Stripe /hit",
    "braintreenvbv": "🛡 Braintree VBV",
    "piconfirm": "🔑 Stripe PI",
}

TIER_LABELS = {
    "1": "🟢 <$1 (Микро)",
    "5": "🟡 $1–$5 (Оптим.)",
    "20": "🔴 $5–$20 (Широкий)",
    "all": "⚙️ Любая цена",
}


def get_gate_display(gate: str) -> str:
    return GATE_LABELS.get(gate, gate)


def get_tier_display(tier: str) -> str:
    return TIER_LABELS.get(str(tier).lower(), f"${tier}")


def main_menu_kb(gate: str = "chk", tier: str = "1", is_admin: bool = False) -> InlineKeyboardMarkup:
    """Главная интерактивная панель управления с индикацией текущих настроек."""
    gate_txt = get_gate_display(gate)
    tier_txt = get_tier_display(tier)

    buttons = [
        # Быстрый чек в один клик
        [
            InlineKeyboardButton("💳 Быстрая проверка карты", callback_data="menu:prompt_check")
        ],
        # Настройки рабочего контура: Шлюз и Цена
        [
            InlineKeyboardButton(f"🎯 Шлюз: {gate_txt}", callback_data="menu:gates"),
            InlineKeyboardButton(f"💰 Цена: {tier_txt}", callback_data="menu:prices"),
        ],
        # Инструменты чека
        [
            InlineKeyboardButton("📁 Массовый чек (/mass)", callback_data="menu:mass"),
            InlineKeyboardButton("🔍 BIN Lookup", callback_data="menu:bin"),
        ],
        # Мониторинг и профиль
        [
            InlineKeyboardButton("📊 Мой профиль", callback_data="menu:profile"),
            InlineKeyboardButton("🧩 Шлюзы и пулы", callback_data="menu:gates_monitor"),
        ],
        # Инфраструктура
        [
            InlineKeyboardButton("📡 Прокси-пул", callback_data="menu:proxy"),
            InlineKeyboardButton("🎟 Активация ключа", callback_data="menu:redeem"),
        ],
        # Помощь и обновление
        [
            InlineKeyboardButton("ℹ️ Справка и команды", callback_data="menu:help"),
            InlineKeyboardButton("🔄 Обновить", callback_data="menu:refresh"),
        ],
    ]

    if is_admin:
        buttons.append([
            InlineKeyboardButton("👑 Админ-панель", callback_data="menu:admin")
        ])

    return InlineKeyboardMarkup(buttons)


def gates_menu_kb(current_gate: str = "chk") -> InlineKeyboardMarkup:
    """Клавиатура выбора активного шлюза с галочкой текущего выбора."""
    def mark(g: str) -> str:
        return " ✓" if current_gate == g else ""

    buttons = [
        [
            InlineKeyboardButton(f"⚡ Авто-выбор цели (/chk){mark('chk')}", callback_data="gate:set:chk"),
        ],
        [
            InlineKeyboardButton(f"🟢 Stripe Auth $0 (/au){mark('setupwoo')}", callback_data="gate:set:setupwoo"),
            InlineKeyboardButton(f"🛒 Store API (/st){mark('storegate')}", callback_data="gate:set:storegate"),
        ],
        [
            InlineKeyboardButton(f"🛍 Shopify Vault (/sp){mark('shopify')}", callback_data="gate:set:shopify"),
            InlineKeyboardButton(f"🎯 Stripe Direct (/hit){mark('hit')}", callback_data="gate:set:hit"),
        ],
        [
            InlineKeyboardButton(f"🛡 Braintree VBV (/vbv){mark('braintreenvbv')}", callback_data="gate:set:braintreenvbv"),
            InlineKeyboardButton(f"🔑 PI Confirm (/pi){mark('piconfirm')}", callback_data="gate:set:piconfirm"),
        ],
        [
            InlineKeyboardButton("💰 Настроить цену", callback_data="menu:prices"),
            InlineKeyboardButton("🔙 Главное меню", callback_data="menu:main"),
        ],
    ]
    return InlineKeyboardMarkup(buttons)


def prices_menu_kb(current_tier: str = "1", current_gate: str = "chk") -> InlineKeyboardMarkup:
    """Клавиатура выбора ценового диапазона товаров."""
    t = str(current_tier).lower()

    def mark(target: str) -> str:
        return " ✓" if t == target else ""

    buttons = [
        [
            InlineKeyboardButton(
                f"🟢 Tier 1: Микрочеки (<$1){mark('1')}",
                callback_data="tier:set:1"
            )
        ],
        [
            InlineKeyboardButton(
                f"🟡 Tier 5: Оптимальный ($1–$5){mark('5')}",
                callback_data="tier:set:5"
            )
        ],
        [
            InlineKeyboardButton(
                f"🔴 Tier 20: Расширенный ($5–$20){mark('20')}",
                callback_data="tier:set:20"
            )
        ],
        [
            InlineKeyboardButton(
                f"⚙️ Auto: Любая цена без фильтра{mark('all')}",
                callback_data="tier:set:all"
            )
        ],
        [
            InlineKeyboardButton("🎯 Сменить шлюз", callback_data="menu:gates"),
            InlineKeyboardButton("🔙 Главное меню", callback_data="menu:main"),
        ],
    ]
    return InlineKeyboardMarkup(buttons)


def check_prompt_kb(gate: str, tier: str) -> InlineKeyboardMarkup:
    """Кнопки в окне быстрой отправки карты."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🎯 Сменить шлюз", callback_data="menu:gates"),
            InlineKeyboardButton("💰 Сменить цену", callback_data="menu:prices"),
        ],
        [
            InlineKeyboardButton("🔙 Главное меню", callback_data="menu:main"),
        ],
    ])


def profile_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🎟 Активировать ключ", callback_data="menu:redeem"),
            InlineKeyboardButton("🔄 Обновить", callback_data="menu:profile"),
        ],
        [
            InlineKeyboardButton("🔙 Главное меню", callback_data="menu:main"),
        ],
    ])


def gates_monitor_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🎯 Выбрать шлюз", callback_data="menu:gates"),
            InlineKeyboardButton("🔄 Обновить", callback_data="menu:gates_monitor"),
        ],
        [
            InlineKeyboardButton("🔙 Главное меню", callback_data="menu:main"),
        ],
    ])


def proxy_kb(is_admin: bool = False) -> InlineKeyboardMarkup:
    buttons = [
        [
            InlineKeyboardButton("📡 Проверить и очистить", callback_data="proxy:check"),
            InlineKeyboardButton("🔄 Обновить", callback_data="menu:proxy"),
        ],
    ]
    if is_admin:
        buttons.append([
            InlineKeyboardButton("🧹 Очистить весь пул", callback_data="proxy:clear"),
        ])
    buttons.append([
        InlineKeyboardButton("🔙 Главное меню", callback_data="menu:main"),
    ])
    return InlineKeyboardMarkup(buttons)


def back_to_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🔙 Главное меню", callback_data="menu:main"),
        ],
    ])


def admin_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📡 Прокси-пул", callback_data="menu:proxy"),
            InlineKeyboardButton("🧹 Очистить прокси", callback_data="proxy:clear"),
        ],
        [
            InlineKeyboardButton("🔙 Главное меню", callback_data="menu:main"),
        ],
    ])
