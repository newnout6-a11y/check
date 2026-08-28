# language: Python 3.12+, file: bot/utils/formatter.py, target: Windows 11
# Sprint 4.5: форматы вывода чеков на русском языке (референс MeduzaPro/SkyBots).
import html
import re
import config


# Словарь переводов типовых ответов шлюзов, эмитентов и ошибок
DETAIL_TRANSLATIONS = {
    # Stripe & WooCommerce типовые отказы
    "your card was declined.": "Карта отклонена банком-эмитентом.",
    "your card was declined": "Карта отклонена банком-эмитентом.",
    "the card was declined.": "Карта отклонена банком-эмитентом.",
    "the card was declined": "Карта отклонена банком-эмитентом.",
    "your card has insufficient funds.": "Недостаточно средств на карте.",
    "your card has insufficient funds": "Недостаточно средств на карте.",
    "insufficient funds": "Недостаточно средств.",
    "your card's security code is incorrect.": "Неверный CVC/CVV код.",
    "your card's security code is incorrect": "Неверный CVC/CVV код.",
    "the card's security code is incorrect.": "Неверный CVC/CVV код.",
    "the card's security code is incorrect": "Неверный CVC/CVV код.",
    "incorrect cvc": "Неверный CVC/CVV код.",
    "invalid cvc": "Недействительный CVC/CVV код.",
    "your card's expiration date is incorrect.": "Неверный срок действия карты.",
    "your card's expiration date is incorrect": "Неверный срок действия карты.",
    "your card has expired.": "Срок действия карты истек.",
    "your card has expired": "Срок действия карты истек.",
    "the card has expired.": "Срок действия карты истек.",
    "the card has expired": "Срок действия карты истек.",
    "expired card": "Срок действия карты истек.",
    "invalid expiry month": "Неверный месяц окончания действия.",
    "invalid expiry year": "Неверный год окончания действия.",
    "your card number is incorrect.": "Неверный номер карты.",
    "your card number is incorrect": "Неверный номер карты.",
    "the card number is incorrect.": "Неверный номер карты.",
    "the card number is incorrect": "Неверный номер карты.",
    "incorrect number": "Неверный номер карты.",
    "invalid number": "Недействительный номер карты.",
    "your card does not support this type of purchase.": "Карта не поддерживает данный тип платежей.",
    "your card does not support this type of purchase": "Карта не поддерживает данный тип платежей.",
    "transaction not allowed": "Транзакция запрещена банком-эмитентом.",
    "do_not_honor": "Отказ эмитента без объяснения причин (Do Not Honor).",
    "generic_decline": "Общий отказ банка-эмитента.",
    "lost_card": "Карта числится утерянной.",
    "stolen_card": "Карта числится украденной.",
    "pickup_card": "Карта заблокирована / подлежит изъятию.",
    "restricted_card": "Ограничения на карте / карта заблокирована.",
    "security_violation": "Нарушение правил безопасности эмитента.",
    "card_velocity_exceeded": "Превышен лимит операций по карте.",
    "card_not_supported": "Тип карты не поддерживается мерчантом.",
    "currency_not_supported": "Валюта операции не поддерживается картой.",
    "duplicate_transaction": "Дублирующая транзакция.",
    "testmode_charges_only": "Шлюз мерчанта в тестовом режиме.",
    "processing_error": "Ошибка обработки платежа банком.",
    "an error occurred while processing your card. try again later.": "Ошибка процессинга карты. Повторите позже.",
    
    # Успех и 3DS
    "setupintent confirmed successfully": "Авторизация $0 успешно подтверждена (Live).",
    "setupintent succeeded": "Авторизация $0 успешно подтверждена (Live).",
    "paymentintent succeeded": "Платеж успешно подтвержден (Approved).",
    "3ds authentication required": "Требуется 3DS подтверждение (SMS/App).",
    "3ds required": "Требуется 3DS подтверждение (SMS/App).",
    "3ds frictionless passed": "3DS пройден без подтверждения (Frictionless).",
    "3ds challenge required": "Требуется подтверждение 3DS кода / Challenge.",
    "non-vbv / no 3ds required": "3DS не требуется (Non-VBV).",

    # Внутренние / форматные
    "bad card format / luhn fail": "Неверный формат карты / ошибка проверки Луна.",
    "insufficient credits": "Недостаточно кредитов на балансе.",
    "no live donor in pool": "Нет доступных живых доноров в пуле.",
    "no store targets": "Нет доступных Store-API целей.",
    "all targets failed": "Все доноры в ротации вернули ошибку.",
    "antispam cooldown": "Слишком частые запросы — подождите пару секунд.",
}

SUBSTRING_PATTERNS = [
    (r"(?i)insufficient\s+funds", "Недостаточно средств на карте."),
    (r"(?i)security\s+code\s+is\s+incorrect|incorrect\s+cvc|invalid\s+cvc", "Неверный CVC/CVV код."),
    (r"(?i)card\s+has\s+expired|expired\s+card|invalid\s+expiry", "Срок действия карты истек."),
    (r"(?i)card\s+number\s+is\s+incorrect|incorrect\s+number|invalid\s+number", "Неверный номер карты."),
    (r"(?i)card\s+was\s+declined|generic_decline", "Карта отклонена банком-эмитентом."),
    (r"(?i)do_not_honor|do\s+not\s+honor", "Отказ эмитента (Do Not Honor)."),
    (r"(?i)stolen_card|lost_card", "Карта утеряна или украдена."),
    (r"(?i)not\s+support\s+this\s+type|transaction\s+not\s+allowed", "Транзакция запрещена банком."),
    (r"(?i)restricted_card|pickup_card", "Карта заблокирована / ограничения."),
    (r"(?i)3ds\s+authentication\s+required|3ds_required", "Требуется 3DS подтверждение."),
    (r"(?i)3ds\s+frictionless", "3DS пройден без подтверждения (Frictionless)."),
    (r"(?i)luhn\s+fail", "Ошибка проверки контрольной суммы (Luhn)."),
    (r"(?i)timeouterror|timed?\s*out", "Таймаут соединения с сервером."),
    (r"(?i)cannot\s+tokenize", "Не удалось токенизировать карту."),
    (r"(?i)processing\s+failed|please\s+retry", "Ошибка процессинга платежа. Повторите позже."),
    # локализованные отказы эмитентов (ES/IT/DE) — реальные ответы store-гейтов пула
    (r"(?i)tarjeta\s+ha\s+sido\s+rechazada", "Карта отклонена банком-эмитентом."),
    (r"(?i)carta\s+è\s+stata\s+rifiutata|carta.{0,20}rifiutata", "Карта отклонена банком-эмитентом."),
    (r"(?i)fehler\s+bei\s+der\s+zahlungsabwicklung", "Ошибка при обработке платежа."),
]


def translate_detail(detail: str) -> str:
    """Переводит технические ответы шлюза и сообщения банков на понятный русский."""
    if not detail:
        return "Нет дополнительных данных."
    
    # Сохраняем префикс цены/валюты, если он есть (например, [100c USD])
    prefix = ""
    clean_detail = detail.strip()
    m_pref = re.match(r"^(\[\d+c\s+[A-Za-z]{0,3}\]\s*)(.*)$", clean_detail)
    if m_pref:
        prefix = m_pref.group(1)
        clean_detail = m_pref.group(2).strip()

    low = clean_detail.lower().rstrip(".")
    # Прямое совпадение по словарю
    if low in DETAIL_TRANSLATIONS:
        return f"{prefix}{DETAIL_TRANSLATIONS[low]}"
    if clean_detail.lower() in DETAIL_TRANSLATIONS:
        return f"{prefix}{DETAIL_TRANSLATIONS[clean_detail.lower()]}"

    # Поиск по регулярным паттернам
    for pat, ru_text in SUBSTRING_PATTERNS:
        if re.search(pat, clean_detail):
            return f"{prefix}{ru_text}"

    return detail


def extract_pan(card_raw: str) -> str:
    """Извлекает только номер карты (PAN 13-19 цифр) из любой строки (CC|MM|YY|CVV или CC MM YY CVV)."""
    if not card_raw:
        return ""
    # 1. Если есть явный разделитель даты/cvv (| : / ;)
    first_chunk = re.split(r"[|:;/]", card_raw.strip())[0].strip()
    
    # 2. Если в строке несколько токенов через пробелы
    tokens = first_chunk.split()
    if len(tokens) >= 4:
        # Проверяем: это 4 блока номера карты (например 4937 2410 0664 3332) или CC MM YY CVV?
        if all(len(t) == 4 and t.isdigit() for t in tokens[:4]):
            return "".join(tokens[:4])
        if len(tokens[0]) >= 13 and tokens[0].isdigit():
            return tokens[0]
        # Amex 4-3-3-4: «3782 822463 10005 1234» — cvv из 4 цифр в конце
        amex = "".join(t for t in tokens if t.isdigit())
        if len(amex) == 19 and amex[:2] in ("34", "37"):
            return amex[:15]
    elif len(tokens) > 1:
        if len(tokens[0]) >= 13 and tokens[0].isdigit():
            return tokens[0]
        joined = "".join(tokens)
        if 13 <= len(joined) <= 19 and joined.isdigit():
            return joined

    digits = "".join(ch for ch in tokens[0] if ch.isdigit()) if tokens else ""
    if len(digits) >= 13:
        return digits[:19]
    
    # Fallback: первый блок из 13-19 цифр
    m = re.search(r"\b(\d{13,19})\b", card_raw)
    if m:
        return m.group(1)

    return digits


# Символы валют для человеческого вывода цены (10c USD -> $0.10)
CUR_SYMBOLS = {"USD": "$", "EUR": "€", "GBP": "£", "JPY": "¥", "CNY": "¥",
               "AUD": "A$", "NZD": "NZ$", "CAD": "C$", "SGD": "S$"}


def fmt_price(cents, currency: str = "") -> str:
    """Центы+код валюты -> '$0.10' / '€3.99' / '20.00 CHF'."""
    try:
        cents = int(cents or 0)
    except (TypeError, ValueError):
        return ""
    if not cents:
        return ""
    cur = (currency or "").upper()
    amount = f"{cents / 100:.2f}".rstrip("0").rstrip(".") if cents % 100 else f"{cents // 100}"
    if not cents % 100:
        amount = str(cents // 100)
    else:
        amount = f"{cents / 100:.2f}"
    sym = CUR_SYMBOLS.get(cur)
    if sym:
        return f"{sym}{amount}"
    return f"{amount} {cur}".strip()


def fmt_latency(ms) -> str:
    """Миллисекунды -> '843мс' или '12.8с'."""
    try:
        ms = int(ms)
    except (TypeError, ValueError):
        return ""
    return f"{ms / 1000:.1f}с" if ms >= 1000 else f"{ms}мс"


def fmt_pan(card_raw: str) -> str:
    """Маскирует номер карты: 4937241006643332 -> 4937 24** **** 3332"""
    digits = extract_pan(card_raw)
    if len(digits) < 13:
        # мусорный ввод не показываем как есть — глухая маска
        return "•••• •••• •••• ••••" if digits else "—"
    return f"{digits[:4]} {digits[4:6]}** **** {digits[-4:]}"




def fmt_bin(binfo: dict) -> str:
    if not binfo:
        return "?"
    esc = lambda s: html.escape(str(s), quote=False)
    scheme = binfo.get("scheme") or "?"
    ftype = binfo.get("type") or "?"
    c = binfo.get("country") or {}
    country = c.get("alpha2") or c.get("name") or "?"
    bank = (binfo.get("bank") or {}).get("name") or "?"
    vbv = " [non-VBV]" if binfo.get("is_vbv") is False else ""
    return f"{esc(scheme)}/{esc(ftype)}/{esc(country)} {esc(bank)}{vbv}"


def format_single(card_raw: str, binfo: dict, gate_name: str,
                  status: str, detail: str, latency_ms: int | None = None,
                  proxy: str | None = None, pool_size: int | None = None) -> str:
    line = "─" * 25
    # detail приходит из внешних ответов (Stripe/Woo/банки) — экранируем от HTML-поломки
    detail_ru = html.escape(translate_detail(detail), quote=False)
    # префикс цены «[10c USD]» -> «($0.10)» в хвосте строки вердикта
    price = ""
    m = re.match(r"^(\[(\d+)c\s*([A-Za-z]{0,3})\]\s*)(.*)$", detail_ru, re.S)
    if m:
        price = fmt_price(m.group(2), m.group(3))
        detail_ru = m.group(4)
    price_s = f" ({price})" if price else ""
    lat = f"\n⏱ {fmt_latency(latency_ms)}" if latency_ms else ""
    # админ-блок: прокси запроса и живой пул (передаются только для админа)
    admin = ""
    if proxy is not None or pool_size is not None:
        proxy_s = proxy if proxy else "direct"
        admin = f"\n🛡 Прокси: {proxy_s}"
        if pool_size is not None:
            admin += f"\n📡 Пул: {pool_size}"
    return (f"{line}\n"
            f"💳 {fmt_pan(card_raw)}\n"
            f"📦 {fmt_bin(binfo)}\n"
            f"🏪 {gate_name}\n"
            f"{config.icon(status)} {status}\n"
            f"📝 {detail_ru[:180]}{price_s}{lat}{admin}\n"
            f"{line}")


def format_mass(results: list[dict], header: bool = True) -> str:
    """results: [{card, binfo?, status, detail}]; header=False — только строки
    (когда вызывающая сторона строит свой заголовок со счётчиками)."""
    lines = []
    if header:
        hits = sum(1 for r in results if config.is_hit(r["status"]))
        warns = sum(1 for r in results
                    if r["status"] not in config.HIT_VERDICTS and r["status"] != "DECLINED")
        fails = sum(1 for r in results if r["status"] == "DECLINED")
        lines += ["━━━ РЕЗУЛЬТАТЫ МАССОВОЙ ПРОВЕРКИ ━━━",
                  f"Всего: {len(results)} | ✅ {hits} | ❌ {fails} | ⚠️ {warns}"]
    for r in results:
        b = r.get("binfo") or {}
        bs = "/".join(html.escape(str(b.get(k)), quote=False)
                      for k in ("scheme", "type") if b.get(k))
        bs_s = f" | {bs}" if bs else ""
        detail_ru = html.escape(translate_detail(r.get("detail", "")), quote=False)
        lines.append(f"{config.icon(r['status'])} {r['card']}{bs_s} | {r['status']}"
                     + (f" ({detail_ru[:40]})" if detail_ru else ""))
    return "\n".join(lines)
