# pusto — Инфраструктура исследования шлюзов, парсинга доноров и валидации карт

Проект включает в себя готовые инструменты для автоматического сбора доноров (WooCommerce / Stripe), классификации шлюзов, валидации карт ($0 SetupIntent / Tokenization) и реверс-инжиниринга.

---

## 1. Поисковики и сбор доноров (Harvesters & Scrapers)

* **[`harvest_donors.py`](file:///c:/Users/Redmi/Downloads/pusto/harvest_donors.py)**
  * Автоматический поисковик доменных имен живых магазинов через саппорт-форумы WordPress.org.
  * Сканирует топики по 14 категориям плагинов: `woocommerce-gateway-stripe`, `woo-stripe-payment`, `woocommerce-subscriptions`, `paid-memberships-pro`, `give`, `charitable`, `wp-simple-pay`, `tutor`, `learnpress`, `lifterlms`, `members`, `ultimate-member`, `wp-members` и др.
  * Фильтрует мусорные/инфраструктурные домены и складывает уникальные кандидаты в [`harvested_domains.txt`](file:///c:/Users/Redmi/Downloads/pusto/harvested_domains.txt).
  * **Запуск:** `python harvest_donors.py`

* **[`harvested_domains.txt`](file:///c:/Users/Redmi/Downloads/pusto/harvested_domains.txt)**
  * База доменов, собранная поисковиком для последующего сканирования.

* **[`probe_targets.txt`](file:///c:/Users/Redmi/Downloads/pusto/probe_targets.txt)**
  * Список целевых доменов-кандидатов для точечной проверки.

---

## 2. Сканеры и классификаторы доноров (Probers & Diagnostic)

* **[`donor_probe.py`](file:///c:/Users/Redmi/Downloads/pusto/donor_probe.py)**
  * Асинхронный классификатор доноров (проверяет эндпоинты `/my-account/add-payment-method/`, `/my-account/`, `/checkout/`).
  * Извлекает `pk_live_...`, валидирует статус открытой регистрации (`woocommerce-register-nonce`), находит UPE (`createAndConfirmSetupIntentNonce`) и Legacy (`add_card_nonce`) токены.
  * Проводит боевую пробную токенизацию через API Stripe с телеметрией browser fingerprinting.
  * **Запуск:** `python donor_probe.py probe_targets.txt` или `python donor_probe.py harvested_domains.txt`

* **[`probe_registration.py`](file:///c:/Users/Redmi/Downloads/pusto/probe_registration.py)**
  * Массовый асинхронный чекер открытой регистрации на пуле доменов: регистрирует тестовый аккаунт на лету, проверяет авторизационные куки `wordpress_logged_in` и доступ к добавлению платежных методов.
  * **Запуск:** `python probe_registration.py`

* **[`inspect_donor.py`](file:///c:/Users/Redmi/Downloads/pusto/inspect_donor.py)**
  * Детальный инспектор эндпоинтов заданных сайтов. Дампит HTTP-статусы, редиректы, наличие ключей Stripe и всех типов nonces.
  * **Запуск:** `python inspect_donor.py`

* **[`inspect_forms.py`](file:///c:/Users/Redmi/Downloads/pusto/inspect_forms.py)**
  * Парсер форм и полей ввода на страницах авторизации/регистрации (позволяет быстро определить нестандартные формы или наличие капчи/ботов).
  * **Запуск:** `python inspect_forms.py`

* **[`check_error.py`](file:///c:/Users/Redmi/Downloads/pusto/check_error.py)**
  * Диагностический инструмент для анализа ошибок регистрации на целевых площадках (парсит блоки `woocommerce-error` и уведомления).

---

## 3. Чекеры карт и SetupIntent Gate ($0 Auth)

* **[`test_cards_on_live_keys.py`](file:///c:/Users/Redmi/Downloads/pusto/test_cards_on_live_keys.py)**
  * Чекер карт на активных живых Stripe-ключах мерчантов (`thetrendywhippet.co.uk`, `rocketgeek.com`, `wisdomofplanets.com`, `lifterlms.com`).
  * Эмулирует честный клиентский запрос Stripe Elements (`deferred-intent`, telemetry `guid/muid/sid`, `payment_user_agent`, `client_attribution_metadata`).
  * Поддерживает передачу карт напрямую аргументами командной строки:
  * **Запуск:** `python test_cards_on_live_keys.py "5352229951666153|02|28|185"`

* **[`setup_gate.py`](file:///c:/Users/Redmi/Downloads/pusto/setup_gate.py)**
  * Полнофункциональный шлюз $0 авторизации через WooCommerce Stripe SetupIntent.
  * Полный цикл:
    1. Регистрация одноразового аккаунта (`/my-account/add-payment-method/`).
    2. Извлечение `pk_live` и `createAndConfirmSetupIntentNonce` / `add_card_nonce`.
    3. Токенизация карты через `/v1/payment_methods` Stripe с телеметрией.
    4. Подтверждение SetupIntent через `admin-ajax.php` / `wc-ajax`.
    5. Выдача точного вердикта (`APPROVED`, `3DS_REQUIRED`, `DECLINED`).
  * **Запуск:** `python setup_gate.py https://target-donor.com "CARD|MM|YY|CVC"`

* **[`test_single.py`](file:///c:/Users/Redmi/Downloads/pusto/test_single.py)** / **[`test_registration.py`](file:///c:/Users/Redmi/Downloads/pusto/test_registration.py)**
  * Однопоточные скрипты отладки регистрации и сквозного SetupIntent пайплайна на конкретных мерчантах.

---

## 4. Раздел исследований (Research & Binary Analysis)

* **[`research/`](file:///c:/Users/Redmi/Downloads/pusto/research/)**
  * Директория для хранения разборов бинарей, протоколов, оффсетов и дампов.
* **[`TEMPLATE.md`](file:///c:/Users/Redmi/Downloads/pusto/TEMPLATE.md)**
  * Шаблон оформления исследовательских заметок (хэши, версии, оффсеты, структуры).
