# language: Python 3.12+, file: config.py, target: Windows 11
# Sprint 5: единый конфиг порогов и констант пайплайна.
# Всё, что раньше было размазано по файлам магическими числами.

# --- Stripe (первоисточник — менять ЗДЕСЬ) ---
STRIPE_API_VERSION = "2026-08-26.dahlia"   # актуальный месячный релиз Dahlia (сентябрь 2026); endive (2026-09-30) — major, потребует аудита
# Соль сборки stripe.js. Это ПОСЛЕДНИЙ РУБЕЖ: рабочее значение подставляет stripe_salt.current_salt()
# (кэш data/stripe_salt.json -> живой бандл js.stripe.com/v3), потому что соль ротируется — 2026-09-15
# она сменилась дважды за день (f0a6d7cfcd -> 2cbe95f953). Здесь держим заведомо рабочее значение
# на случай офлайна; синхронность проверяет python stripe_salt.py --check.
STRIPE_JS_BUILD = "2cbe95f953"
STRIPE_SALT_CACHE_PATH = "data/stripe_salt.json"   # кэш живой соли (не в репозитории)
STRIPE_SALT_TTL_S = 6 * 3600                       # сколько держать кэш, прежде чем перечитать бандл
CHROME_IMPERSONATE = "edge101"   # устарело: см. pick_impersonate() ниже

# --- D-30: ротация TLS-отпечатка ---------------------------------------------
# chrome120 и новее (120/124/131) систематически режутся: Cloudflare отдаёт 429
# на витринах, DuckDuckGo отдаёт 202 с пустой выдачей. Проверено боем 2026-08-31
# на 4 доменах и 6 поисковых отпечатках. chrome116 и старше, весь Safari,
# Firefox, Edge и Tor проходят. firefox120 нестабилен (падает) — исключён.
#
# В 2026 году добавлены актуальные профили Chromium 136-146, Safari 18.4/26.0,
# Firefox 135-147 из curl_cffi 0.15.0; устаревшие chrome99-110 удалены.
IMPERSONATIONS = (
    # Chromium (2025-2026)
    "chrome136", "chrome142", "chrome145", "chrome146", "chrome133a", "chrome131_android",
    # Safari / WebKit (macOS & iOS)
    "safari184", "safari184_ios", "safari260", "safari260_ios", "safari18_0", "safari17_2_ios", "safari17_0",
    # Firefox / Gecko
    "firefox147", "firefox144", "firefox135", "firefox133",
    # Windows-native & privacy
    "edge101", "edge99", "tor145",
    # Proven fallback
    "chrome116",
)


def pick_impersonate() -> str:
    """Случайный отпечаток из рабочего пула. Случайность важна: пул, долбящий
    одним и тем же следом синхронно, снова ловит 429 — просто позже."""
    import random
    return random.choice(IMPERSONATIONS)

# --- SetupIntent / WooCommerce cooldown & Session Pacing ---
# Платформенный порог ядра WooCommerce для add_payment_method: 20 с, и ключ лимита
# ПЕРСОНАЛЬНЫЙ — 'add_payment_method_' . user_id, а не сессионный
# (class-wc-form-handler.php:654-674, trunk; тот же лимитер проверяет плагин в
# create_and_confirm_setup_intent_ajax: «You cannot add a new payment method so soon
# after the previous one»). Источник: woocommerce/woocommerce trunk @ 2026-09.
WC_ADD_PAYMENT_METHOD_DELAY_S = 20.0  # проверено 2026-09-12 по trunk, перепроверять раз в 30 дней
WC_COOLDOWN_JITTER_MIN = 0.5          # джиттер поверх фактического кулдауна донора
WC_COOLDOWN_JITTER_MAX = 1.5

# Калибровка против конкретного донора (наблюдение 2026-09 на одном доноре,
# scratch/test_rate_limit_calibration.py: обход по [3, 5, 8, 10, 15, 20] с). Это НЕ порог
# платформы и НЕ «защита WooCommerce»: значение ниже платформенного дефолта в 20 с и годится
# только там, где фактический лимит донора измерен и оказался меньше (аудит 2026-09, G-01).
SETUP_COOLDOWN_CALIBRATED_MIN = 8.1
SETUP_COOLDOWN_CALIBRATED_MAX = 9.0
# Совместимость имён: прежние константы остались, но их смысл — калибровка, а не порог ядра.
SETUP_COOLDOWN_MIN = SETUP_COOLDOWN_CALIBRATED_MIN
SETUP_COOLDOWN_MAX = SETUP_COOLDOWN_CALIBRATED_MAX

SESSION_PACING_MIN = 8.1           # пауза для rate-limited эндпоинтов Stripe (НЕ кулдаун WooCommerce)
SESSION_PACING_MAX = 9.0


def wc_cooldown_floor(measured_delay_s: float | None = None) -> float:
    """Фактический кулдаун донора: измеренный, иначе платформенный дефолт ядра (20 с).

    Раньше пауза всегда бралась равной калибровке 8.1-9.0 с и подавалась как платформенная
    защита: на доноре с дефолтным фильтром вторая карта получала отказ плагина, а не вердикт
    эмитента (аудит 2026-09, G-01).
    """
    if measured_delay_s and float(measured_delay_s) > 0:
        return float(measured_delay_s)
    return WC_ADD_PAYMENT_METHOD_DELAY_S


def setup_cooldown_delay(measured_delay_s: float | None = None) -> float:
    """Пауза между add-payment-method на одном WP-аккаунте: кулдаун донора + джиттер.

    Без измеренного кулдауна берётся платформенный дефолт (20.5-21.5 с). Калиброванные
    8.1-9.0 с доступны только явно — передав measured_delay_s меньше платформенного.
    """
    import random
    floor = wc_cooldown_floor(measured_delay_s)
    return round(floor + random.uniform(WC_COOLDOWN_JITTER_MIN, WC_COOLDOWN_JITTER_MAX), 2)


def session_pacing_delay(min_delay: float = SESSION_PACING_MIN, max_delay: float = SESSION_PACING_MAX) -> float:
    """Джиттерная пауза для rate-limited эндпоинтов Stripe (по умолчанию 8.1-9.0 с).

    Это НЕ кулдаун WooCommerce: у платформы свой порог на add_payment_method — 20 с
    и персональный ключ (см. WC_ADD_PAYMENT_METHOD_DELAY_S).
    """
    import random
    return round(random.uniform(min_delay, max_delay), 2)


# --- PaymentIntent vector (Фаза 2) ---
MAX_PI_AMOUNT_CENTS = 10000        # выше — CHARGE_RISK, не подтверждаем ($100)
MAX_CONFIRMS_PER_SECRET = 20       # бюджет подтверждений на один client_secret

# --- Donor pool / scanner ---
DONOR_FAIL_LIMIT = 3               # подряд идущих отказов до выброса донора
GATE_TTL_HOURS = 72                # донор без подтверждения N часов -> из пула
STALE_AFTER_HOURS = 24             # ... сначала пометка STALE
RESCAN_INTERVAL_HOURS = 24         # очередь domains.db

# --- Verdict taxonomy (план §6.2 + реальные исходы трёх поверхностей) ---
VERDICTS = [
    "APPROVED", "APPROVED@HOLD", "APPROVED@PAID", "APPROVED@CVV", "APPROVED@CCN",
    "DECLINED", "DECLINED@DO_NOT_HONOR", "DECLINED@FRAUD", "DECLINED@STOLEN",
    "INVALID", "EXPIRED", "WRONG_CVC", "RESTRICTED",
    "TEST_MODE", "RATE_LIMITED", "RETRY", "PI_MINTED", "PI_PENDING",
    "3DS_REQUIRED", "3DS_FRICTIONLESS", "3DS_CHALLENGE", "3DS_REDIRECT",
    "SESSION_EXPIRED", "SESSION_CANCELED",
    # Внутренние исходы антибот-челленджа Radar (gate_client.verify_intent_challenge).
    # В таксономии, иначе любой путь через coerce_verdict давал UNKNOWN без возврата
    # кредита (аудит 2026-09, M-06 / G-10).
    "CHALLENGE_FAILED", "CHALLENGE_BURNED",
    # Транспортные маркеры, которые раньше жили вне таксономии и потому могли стать UNKNOWN:
    # «OK» после пройденного челленджа и после выпуска confirmation-токена,
    # а также классификация витрины, которую платформа отдаёт вместо вердикта карты
    # (аудит 2026-09, M-06 / G-10; проверено 2026-09-12).
    "CHALLENGE_PASSED",
    "CAPTCHA_CHECKOUT", "GUEST_CHECKOUT_DISABLED",
    "UNKNOWN", "ERROR",
]

# Статусы сканера целей (domains.db). Это НЕ вердикты карт: в отчёты они попадают строкой,
# поэтому держим их отдельным множеством, чтобы никто не принял их за исход чека
# (аудит 2026-09, M-06: «READY»/«CAPTCHA_ADDCARD»/«BRAINTREE_KEY» выглядели как вердикты).
# Внимание: «READY» есть ещё у записей донорского пула (data/ready_gates.json, bot/main.py) —
# это другой жизненный цикл, смешивать их нельзя.
SCAN_STATUSES = ("READY", "CAPTCHA_ADDCARD", "BRAINTREE_KEY")
HIT_VERDICTS = {"APPROVED", "APPROVED@HOLD", "APPROVED@PAID", "APPROVED@CVV", "APPROVED@CCN"}
VERDICT_ICONS = {
    "APPROVED": "✅", "APPROVED@HOLD": "🟡", "APPROVED@PAID": "💰",
    "APPROVED@CVV": "✅", "APPROVED@CCN": "✅",
    "DECLINED": "❌", "DECLINED@DO_NOT_HONOR": "❌", "DECLINED@FRAUD": "🚫", "DECLINED@STOLEN": "🚨",
    "INVALID": "⚠️", "EXPIRED": "⌛", "WRONG_CVC": "⚠️", "RESTRICTED": "⛔",
    "TEST_MODE": "🧪", "RATE_LIMITED": "🐢", "RETRY": "🔁", "PI_MINTED": "🪙",
    "PI_PENDING": "🧾",
    "3DS_REQUIRED": "🔒", "3DS_FRICTIONLESS": "✅", "3DS_CHALLENGE": "🔐",
    "3DS_REDIRECT": "↪️",
    "SESSION_EXPIRED": "⌛", "SESSION_CANCELED": "🚫",
    "CHALLENGE_FAILED": "🔐", "CHALLENGE_BURNED": "🔥", "CHALLENGE_PASSED": "🔓",
    "CAPTCHA_CHECKOUT": "🧩", "GUEST_CHECKOUT_DISABLED": "🚪",
    "UNKNOWN": "❔",
    "ERROR": "💥",
}


def coerce_verdict(verdict: str) -> str:
    """Страховка таксономии: вердикт вне VERDICTS сводится к ближайшему классу.

    Порядок: технические сбои витрины/цели -> ERROR (возврат кредита + фолл-троу)
    -> точное совпадение -> базовый класс по префиксу (DECLINED@{ЧТО-ТО}
    -> DECLINED) -> UNKNOWN.
    """
    v = (verdict or "").strip()
    # Сбои витрины/цели (не свойство карты) обязаны быть ERROR
    if v in ("GUEST_CHECKOUT_DISABLED", "GUEST_CHECKOUT_OFF", "CAPTCHA_CHECKOUT",
             "NO_PM_SLUG", "PM_SLUG_MISSING", "NO_PRODUCT_UNDER_CAP", "NO_PRODUCTS",
             "ADD_ITEM_NO_JSON", "VARIATION_REQUIRED", "CHARGE_RISK",
             "OUT_OF_STOCK", "CART_EMPTY", "CHECKPOINT_DENIED",
             # Технические исходы, которые раньше уходили в UNKNOWN и не возвращали кредит:
             # провал челленджа, невалидный линк, исключение движка, провал пайплайна.
             "CHALLENGE_FAILED", "CHALLENGE_BURNED",
             "INVALID_URL", "EXCEPTION", "FAILED"):
        return "ERROR"
    if v in VERDICTS:
        return v
    base = v.split("@", 1)[0].strip()
    if base in VERDICTS:
        return base
    return "UNKNOWN"


def is_hit(verdict: str) -> bool:
    return verdict in HIT_VERDICTS


# Вердикты, при которых бот ВОЗВРАЩАЕТ кредит: сбой движка (ERROR) и смерть
# цели/сессии (SESSION_*). Это свойство цели, а не карты — пользователь не
# должен платить за мёртвый линк/донора. Всё остальное (включая DECLINED и
# любые 3DS_*) — честный результат проверки карты.
# Возвратные классы: сбой движка или витрины, а не свойство карты. CAPTCHA_CHECKOUT и
# GUEST_CHECKOUT_DISABLED возвратны (раньше они попадали сюда только через coerce_verdict;
# теперь они в таксономии, и набор обязан совпадать с прежним поведением).
REFUNDABLE_VERDICTS = {"ERROR", "SESSION_EXPIRED", "SESSION_CANCELED",
                       "CAPTCHA_CHECKOUT", "GUEST_CHECKOUT_DISABLED"}

# Состояния пайплайна /hit (execute_hit). Это НЕ вердикты карты: держим отдельным полем,
# чтобы терминальный статус прогона не подменял таксономию (аудит 2026-09, G-10).
PIPELINE_STATES = ("SUCCESS", "COMPLETED", "PARTIAL", "FAILED")

# 3DS Method notification URL. Прежний хардкод https://hooks.stripe.com/3ds2/fingerprint/complete
# отдаёт 404 (проверено боем 2026-09-12), а живой маршрут того же семейства — /3d_secure_2/...
# (200 ОК). Пока значение берётся из ответа Stripe, но дефолт обязан быть живым.
THREE_DS_METHOD_NOTIFICATION_URL = "https://hooks.stripe.com/3d_secure_2/hosted/complete"

# Сколько раз опрашивать сессию ПОСЛЕ исполнения 3DS-Method и с какой паузой.
# Живой замер 2026-09-13: одного опроса мало — ACS подтверждает не мгновенно, и движок успевал
# прочитать ещё «stripe_3ds2_fingerprint», из-за чего «frictionless» не отличался от челленджа.
THREE_DS_METHOD_POLL_ROUNDS = 4
THREE_DS_METHOD_POLL_DELAY_S = 2.5

# Отправлять ли radar_options[hcaptcha_token] в payment_pages/confirm.
# Живой замер 2026-09-13 на двух разных витринах: маршрут отвечает 400 parameter_unknown
# («Received unknown parameter: radar_options») на первом же confirm, а сама страница Stripe
# отправляет токен капчи верхним уровнем как passive_captcha_token. Пока держим False — иначе
# каждая попытка начинается со сгоревшего запроса; флаг оставлен для отката мимикрии.
CONFIRM_SEND_RADAR_OPTIONS = False

# --- Ротация ссылки аккаунтом (по смерти сессии) ---
# Живой замер 2026-09-13: выпуск новой ссылки делает предыдущую недействительной, поэтому ротация —
# это замена на месте, а не пул. Данные аккаунта читаются из файла (не отслеживается гитом) или из
# переменных окружения, так что ротация не зависит ни от браузера, ни от платформы.
ACCOUNT_AUTH_PATH = "data/account_auth.json"

# Идентификаторы устройства Stripe (muid/guid/sid). Настоящий браузер хранит их в куках месяцами и
# приходит как «тот же» клиент; поэтому мы их кэшируем и переиспользуем, а не минтим заново на каждый
# раунд (живой замер 2026-09-13: m.stripe.com/6 выдаёт нормализованные id, суффикс — метка устройства).
STRIPE_DEVICE_IDS_PATH = "data/stripe_device_ids.json"
STRIPE_DEVICE_ID_TTL_DAYS = 30
# Месячный Moderato ($19): самая дешёвая платная цель, проходит наш лимит суммы с запасом.
ACCOUNT_ROTATION_GOODS_ID = "b2c3d4e5-f6a7-8901-bcde-f23456789012"
# Сколько новых ссылок разрешено выпустить за один прогон крутилки.
ACCOUNT_ROTATION_MAX_LINKS = 3

# Версия протокола 3DS. Интенты создаёт мерчант (мы работаем на донорских сессиях), поэтому
# версию выбирает не наш контур — но фиксировать её обязательно: аудит 2026-09 (E-33) показал,
# что она не отражалась нигде, хотя Stripe с релиза clover/2026-01-28 принимает её явно.
# Живой первоисточник (проверено 2026-09-12): changelog — «Der Parameter Version in
# payment_method_options.card.three_d_secure akzeptiert jetzt 2.3.0 und 2.3.1», полный список
# значений 1.0.2 / 2.1.0 / 2.2.0 / 2.3.0 / 2.3.1; действующая линия EMVCo — 2.3.1.
THREE_DS_VERSION_TARGET = "2.3.1"
THREE_DS_VERSIONS_SUPPORTED = ("1.0.2", "2.1.0", "2.2.0", "2.3.0", "2.3.1")

# Сколько страниц /products.json обходить при поиске самого дешёвого варианта:
# эндпоинт отдаёт максимум 250 товаров на страницу без пагинации, у крупных каталогов
# дешёвые позиции лежат дальше первой страницы (аудит 2026-09, G-28).
SHOPIFY_CATALOG_PAGES = 3

# Известные НЕПУБЛИЧНЫЕ эндпоинты Stripe, на которых стоит боевой контур. В API-референсе
# их нет (docs.stripe.com отдаёт 404), но маршруты живы и отвечают 401 без ключа. Начал
# отдавать 404 — Stripe убрал маршрут: это сломанный контур, а не отказ карты.
UNDOCUMENTED_ENDPOINTS = {
    "/v1/payment_pages/{cs}": "Stripe Checkout hosted pages (чтение сессии)",
    "/v1/payment_pages/{cs}/confirm": "Stripe Checkout hosted pages (подтверждение)",
    "/v1/payment_intents/{pi}/verify_challenge": "Radar hCaptcha Enterprise challenge",
    "/v1/confirmation_tokens": "ConfirmationToken из pk (документирован только клиентский путь)",
    "/v1/3ds2/authenticate": "3DS2 из эпохи Sources API (официально деприкейтнут)",
}


def is_refundable(verdict: str) -> bool:
    """ERROR или смерть цели/сессии: кредит возвращается, фолл-троу продолжается."""
    return coerce_verdict(verdict) in REFUNDABLE_VERDICTS


def icon(verdict: str) -> str:
    return VERDICT_ICONS.get(verdict, "·")
