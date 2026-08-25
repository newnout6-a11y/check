# pusto — Инфраструктура исследования шлюзов, парсинга доноров и валидации карт

Чистая структура проекта для быстрого ориентирования в сессиях.

---

## 🎯 Основные инструменты на верстаке (Корень проекта)

### 1. `setup_gate.py` — Главный боевой чекер карт ($0 SetupIntent Live Gate)
* **Движок:** `curl_cffi` с Chrome TLS-имперсонацией (`chrome131`) — проходит Cloudflare WAF, который резал aiohttp.
* **Pre-flight:** Luhn-проверка каждой карты + BIN-обогащение (схема/тип/страна/банк через binlist → handyapi) до прогона и в итоговой сводке.
* **Session Reuse:** одна авторизованная WP-сессия на донора обслуживает всю пачку карт — регистрации больше не плодятся на каждую карту. Протухший ajax-nonce обновляется автоматически одним ретраем.
* **Назначение:** Полнофункциональный не-SK валидатор карт через боевой WooCommerce Stripe SetupIntent. Пробивает эмитент без списания средств, возвращает точные вердикты (`APPROVED`, `3DS_REQUIRED`, `DECLINED`).
* **Пул доноров:** Автоматически загружается из `data/ready_gates.json`. При падении донора — авто-ротация на следующего.
* **Подтверждена аутентификация банком:** Карта `537872******8595` → `seti_1U86Qx...` → `succeeded`. Банк показал уведомление в приложении.
* **Запуск:**
  ```bash
  # Одиночная карта:
  python setup_gate.py "5175465382242090|09|2030|018"
  
  # Несколько карт:
  python setup_gate.py "CARD1" "CARD2"
  
  # Из файла с картами:
  python setup_gate.py cards.txt
  
  # С указанием своего мерчанта-донора:
  python setup_gate.py https://target-donor.com "CARD1"
  ```

### 2. `advanced_gate_scanner.py` — 4-стадийный сканер и классификатор (v3, curl_cffi)
* **Движок:** `curl_cffi` Chrome TLS-имперсонация — обходит динамический Cloudflare WAF, который резал POST-регистрацию на aiohttp.
* **4 стадии:** DNS-резолв → GET-проба формы → POST-регистрация (Chrome TLS) → скрапинг `pk_live` + SetupIntent nonces → боевой confirm-пробник.
* **Метрики:** Из 348 доменов: 316 живых DNS → 15 открытых форм → 1 квалифицированный SetupIntent-гейт.
* **Результат:** Сохраняет готовый пул в `data/ready_gates.json` и `data/active_surfaces.json`.
* **Запуск:** `python advanced_gate_scanner.py`

### 3. `harvest_donors.py` — Поисковик доноров по саппорт-форумам WordPress.org
* **Назначение:** Собирает живые доменные имена магазинов через топики форумов плагинов (Stripe, Subscriptions, GiveWP, Paid Memberships Pro, Tutor LMS, LifterLMS и др.).
* **Результат:** Сохраняет уникальные домены в `data/harvested_domains.txt`.
* **Запуск:** `python harvest_donors.py`

---

## 📁 Структура каталогов

```
pusto/
├── setup_gate.py              # 🔥 Главный валидатор карт ($0 SetupIntent Gate)
├── advanced_gate_scanner.py   # 🔍 Сканер уязвимых поверхностей и nonces
├── gate_client.py             # ⚙️ Общий движок: регистрация, nonces, телеметрия, identity
├── harvest_donors.py          # 🌐 Сборщик доменов с форумов
├── data/                      # Рабочие базы и результаты сканирования
│   ├── ready_gates.json       # Пул квалифицированных SetupIntent-гейтов для setup_gate
│   ├── active_surfaces.json   # Классифицированные живые доноры с PK и nonces
│   ├── harvested_domains.txt  # Домены с форумов WordPress (harvest_donors)
│   ├── dork_harvested.txt     # Домены из dork-поиска (scratch/dork_harvester)
│   ├── probe_targets.txt      # Целевой список для точечного сканирования
│   └── ses_*.json             # Сессионные логи прогонов
├── scratch/                   # Активные прототипы и утилиты
│   ├── dork_harvester.py      # Dork-сборщик доноров → data/dork_harvested.txt
│   ├── deep_dorker.py         # Расширенная версия доркера (льёт в harvested_domains.txt)
│   └── diagnose_failures.py   # Диагностика отказов шлюзов по стадиям
├── archive/                   # Архив промежуточных скриптов и отладки
│   ├── probers/               # Узкие зонды (probe_registration, inspect_forms, _scan_fast_prototype)
│   ├── test_scripts/          # Тестовые прогоны на конкретных доменах
│   ├── core/                  # Ретро: хардкод-ключи и aiohttp-BIN lookup (поглощён setup_gate)
│   └── misc/                  # Одноразовые утилиты вне конвейера
└── research/                  # Заметки и разборы экосистемы
    ├── checker_ecosystem.md   # Анализ рынка cc-чекеров
    ├── stripechecker_v2_source.py
    ├── cc-checker/            # Разбор механик cc-чекеров (auth, поиск)
    └── tg-checker-bots/       # TG чекер-боты: заметки и декодированные артефакты
```

---

## ⚡ Команды

```bash
# Проверить карту на боевом шлюзе (пул из data/ready_gates.json):
python setup_gate.py "CARD|MM|YY|CVC"

# Проверить на конкретном доноре:
python setup_gate.py https://target-donor.com "CARD|MM|YY|CVC"

# Собрать свежих доноров с форумов WordPress (62 плагина):
python harvest_donors.py

# Отсканировать базу и обновить пул готовых шлюзов:
python advanced_gate_scanner.py
```

## Проверено

| Дата | Карта | Донор | Вердикт | SetupIntent |
|---|---|---|---|---|
| 2026-08-25 | `537872******8595` | blackbeltprotein.com.au | **APPROVED** | `seti_1U86Qx...` |
| 2026-08-25 | `442019******2053` | blackbeltprotein.com.au | DECLINED | incorrect_number |
| 2026-08-25 | `516499******7375` | blackbeltprotein.com.au | DECLINED | card_declined |
| 2026-08-25 | `517546******2090` | blackbeltprotein.com.au | DECLINED | card_declined |
