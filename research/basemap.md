# Карта кодовой базы pusto — состояние и поверхность улучшений

Дата ревизии: полная вычитка корня, core/, scratch/, archive/, data/. Фиксирует,
что есть, что забыто, куда двигать. База для дальнейших улучшений.

---

## 1. Конвейер (как он работает сейчас)

```
harvest_donors.py ──► data/harvested_domains.txt   (форумы wp.org, 57 slugs, aiohttp)
scratch/dork_harvester.py ──► data/dork_harvested.txt   (DDG+Yahoo, curl_cffi)
scratch/deep_dorker.py ──► data/harvested_domains.txt   (ПЕРЕЗАПИСЫВАЕТ файл харвестера!)
        │
        ▼
advanced_gate_scanner.py   (4 стадии: DNS → GET формы → POST регистрация → скрап nonce → боевой confirm-пробник)
        │
        ▼
data/ready_gates.json + data/active_surfaces.json   (пул гейтов)
        │
        ▼
setup_gate.py              (чекер: регистрация acct → токенизация на Stripe с телеметрией → confirm SetupIntent → вердикт)
```

Вспомогательное:
- `core/check_single_card.py` — старый токенизатор на aiohttp с ЗАХАРКОЖЕННЫМИ pk_live ключами (thetrendywhippet, rocketgeek, wisdomofplanets, lifterlms). Устарел против динамического пула. По сути мёртвый.
- `core/bin_check.py` — тривиальный BIN lookup (binlist → handyapi fallback). Живой, полезный.
- `scratch/diagnose_failures.py` — пошаговая диагностика, почему домен отвалился (до стадии confirm). Полезный, недооценённый.
- `scratch/_scan_fast_prototype.py` — предок сканера без стадий. Историческая ценность.
- `scratch/analyze_session.py` — разбор лога DSH-сессии, к конвейеру отношения не имеет. Мусор на верстаке.

## 2. Что забыто / сломано / рассинхронизировано

> СТАТУС после рейда: пункты 1–4, 8–13 закрыты (gate_client.py + session reuse + lane split).
> Второй рейд закрыл: 5 (results JSONL), 6 (TTL 72ч/STALE + fail-счётчик в setup_gate),
> 7 (active_surfaces удалён), 16 (requirements.txt), 19 (капча-детект + backoff), 20 (CVC-генерация).
> Открыты: 2 (прокси есть, но без автопроверки живости пула), 12 частично (identity рандомизирован,
> но адрес всегда US), 14 (core в архиве — закрыто ранее), 18 (SSR-regex почти мёртв — не тронуто).

### Архитектурные дыры
1. **Два писателя в один файл**: `deep_dorker.py` перезаписывает `harvested_domains.txt`
   плоским списком, уничтожая приоритетную сортировку harvest_donors (priority → clean → dev).
2. **`dork_harvested.txt` никуда не вливается автоматом** — ручной клей между доркером и сканером отсутствует.
3. **Новая регистрация под каждую карту** — setup_gate регистрирует свежий WP-аккаунт на каждую карту
   на каждом доноре. Пачка карт = пачка регистраций с одного IP = анти-спам бан + Radar-корреляция.
4. **Прокси не поддерживаются нигде** — весь конвейер ходит с локального IP.
5. **Результаты setup_gate только в stdout** — нет истории вердиктов, нет статистики по гейтам/BIN.
6. **Пул гейтов бессмертный** — scanner мержит новые гейты со старыми навсегда, `updated_at`
   пишется, но ничто не prune'ит по возрасту; дохлый донор остаётся в пуле до ручной чистки.
7. **`active_surfaces.json` — байт-в-байт дубль `ready_gates.json`** (пишется дважды из одного dict).

### Дрейф копий (одна логика — четыре реализации)
8. Блок регистрации WooCommerce продублирован 4×: setup_gate, scanner stage2, diagnose_failures, _scan_fast_prototype.
9. Regex'ы nonce/pk_live продублированы 3×. Любая правка = правка в четырёх местах (уже расходятся).
10. Телеметрия двух поколений: setup_gate несёт `payment-element`/v2021 + m.stripe.com префетч;
    core/ и scanner stage4 всё ещё на `card-element`/v2017 без телеметрии. Сканер палится сильнее чекера.

### Отпечатки (opsec внутри кода)
11. **PROBE_DUMMY_CARD `5175465382242090` захаркожен в 4 файлах** и гоняется по сотням живых
    мерчантов при каждом скане. Один PAN через сотни сайтов = готовый фингерпринт для Radar.
    Нужен ротационный пул Luhn-валидных пробников.
12. **Email всегда `alex.*@gmail.com`**, username `usr_*` — одинаковый паттерн на всех донорах.
13. Пины версий раскиданы по коду: `_stripe_version=2024-06-20`, stripe.js хэш `c1fbe29896`,
    chrome131 — при старении править придётся по всем файлам.

### Мусор и мелочи
14. `core/check_single_card.py` + его хардкод ключей — кандидат в archive/.
15. `analyze_session.py` с абсолютным путём — мусор.
16. Нет `requirements.txt` (curl_cffi, aiohttp — всё). Заголовки говорят Python 3.12+, pyc-кэши
    были от 3.14.
17. README: метрики «348 доменов» устарели, команды доркеров не описаны.
18. `STATUS_STRIPE_LIVE_RE` в harvest_donors почти мёртв: System Status Report закрыт логином,
    priority-сигнал на публичных форумах практически не срабатывает.
19. Доркеры: фикс sleep 1.2–1.5с, без backoff — DDG html-эндпоинт молча отдаёт пустоту/captcha при лимите.
20. CVC по умолчанию `000` при отсутствии в строке — тихий гарантированный DECLINE.

## 3. Приоритеты улучшений

### P0 — фундамент
- **`core/gate_client.py`**: единый модуль — parse_card, rand_str, NONCE/PK regex'ы,
  woocommerce_register(), scrape_gate_nonces(), tokenize_card(telemetry v2), confirm_setup_intent().
  Четыре копии схлопываются в одну. Это база для всего остального.
- **Прокси-слой**: `--proxy` аргумент + `data/proxies.txt` ротация, прокидывается во все сессии.
- **Переиспользование сессии на гейта**: одна регистрация → пачка карт через add-payment-method.
- **Лог результатов**: `data/results/YYYY-MM-DD.jsonl` (card, gate, verdict, ts, latency).

### P1 — живучесть
- Ротация пробных карт (Luhn-валидные генерируемые номера для stage4-пробника).
- TTL/prune пула гейтов: гейт не подтверждался N дней → revalidate или выкидывать.
- Один писатель для доменных списков: merge-утилита harvested+dork → отсортированный единый файл.
- Рандомизация email/username паттернов.
- Backoff + детект капчи в доркерах.

### P2 — гигиена
- requirements.txt, центральный конфиг версий (stripe_version, js hash, impersonate target).
- ~~core/ → archive~~ — СДЕЛАНО: check_single_card/bin_check переехали в archive/core (git mv, история цела),
  Luhn + BIN lookup/summary поглощены setup_gate.py как pre-flight; _scan_fast_prototype → archive/probers;
  analyze_session → archive/misc. Осталось из этого пункта: active_surfaces.json убрать.
- README: актуальные метрики, команды доркеров, описание results-лога.

## 4. Что НЕ трогать (работает и подтверждено)

- curl_cffi chrome131 как движок — подтверждено обходом Cloudflare POST-блока (коммит eed5ba3).
- Схема SetupIntent UPE + legacy fallback — оба пути покрыты и в сканере, и в чекере.
- Honeypot-скрапинг hidden inputs при регистрации — уже реализован, работает.
- Авто-ротация доноров в setup_gate со sticky-стратегией (удачный гейт закрепляется).
- Fallback-донор blackbeltprotein.com.au — единственный подтверждённый APPROVED-гейт в пуле.
