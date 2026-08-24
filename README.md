# pusto — Инфраструктура исследования шлюзов, парсинга доноров и валидации карт

Чистая структура проекта для быстрого ориентирования в сессиях.

---

## 🎯 Основные инструменты на верстаке (Корень проекта)

### 1. `setup_gate.py` — Главный боевой чекер карт ($0 SetupIntent Live Gate)
* **Назначение:** Полнофункциональный не-SK валидатор карт через боевой WooCommerce Stripe SetupIntent. Пробивает эмитент без списания средств, возвращает точные вердикты (`APPROVED`, `3DS_REQUIRED`, `DECLINED`, `INVALID`).
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

### 2. `advanced_gate_scanner.py` — Сканер и классификатор платежных поверхностей
* **Назначение:** Асинхронно сканирует базу доменов из `data/`, классифицирует открытую регистрацию WooCommerce, находит UPE/Legacy SetupIntent nonces, GiveWP donation эндпоинты, чекауты и активные Stripe `pk_live_...` ключи.
* **Результат:** Сохраняет готовый список активных мерчантов в `data/active_surfaces.json`.
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
├── harvest_donors.py          # 🌐 Сборщик доменов с форумов
├── core/                      # Базовые вспомогательные модули
│   ├── check_single_card.py   # Прямая токенизация на ключах мерчантов + BIN lookup
│   └── bin_check.py           # Быстрая проверка BIN/Luhn
├── data/                      # Рабочие базы и результаты сканирования
│   ├── active_surfaces.json   # Классифицированные живые доноры с PK и nonces
│   ├── harvested_domains.txt  # Собранные домены магазинов
│   ├── probe_targets.txt      # Целевой список для точечного сканирования
│   └── ses_*.json             # Сессионные логи
├── archive/                   # Архив промежуточных скриптов и отладки
│   ├── probers/               # Узкие зонды (probe_registration, inspect_forms и т.д.)
│   └── test_scripts/          # Тестовые прогоны на конкретных доменах
└── research/                  # Заметки и разборы бинарей / протоколов
```

---

## ⚡ Быстрый старт новой сессии

1. **Проверить карты на боевом шлюзе:**
   ```bash
   python setup_gate.py "CARD|MM|YY|CVC"
   ```
2. **Собрать новых доноров и просканировать:**
   ```bash
   python harvest_donors.py
   python advanced_gate_scanner.py
   ```
3. **Все собранные данные хранятся в `data/`.**
