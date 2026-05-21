# Архитектура CATAULTRA Twin Scout

## Цель

`Twin Scout` изолирует поиск графиков-близнецов от основного `catapulta-ai`. Основной проект остается ML/trading research контуром, а Twin Scout становится 24/7 сборщиком раскрытых математических траекторий.

## Поток данных

```text
Catapult GraphQL
  -> TurboTokenList
  -> completed token candidates
  -> 5-worker fair-data queue with jitter/backoff
  -> TurboTokenFairData
  -> raw_fair_data.json
  -> pure_ticks.json
  -> token_metadata.json
  -> 1000-token batch
  -> Pearson sliding correlation analyzer
  -> twins_report.md
  -> session_1k_NNN.tar.gz
```

## Модули

```text
src/cataultra_twin_scout/
  analysis.py      # корреляция Пирсона, попарный анализ, markdown report
  api.py           # Catapult read-only GraphQL API
  cli.py           # стрелочное меню, rich HUD
  config.py        # env/config loader
  daemon.py        # 24/7 цикл сбора, упаковки и анализа
  models.py        # Pydantic-контракты
  operations.py    # GraphQL operation text
  storage.py       # файловый контракт private/twin_scout
  transport.py     # HTTP GraphQL client
```

## Политика сбора

По умолчанию `TWIN_SPEED_MODES="*"` не передает `speedMode` в GraphQL-фильтр и тем самым собирает все типы токенов, которые сервер возвращает для выбранного `rank`.

`daemon.py` запускает до `TWIN_WORKER_COUNT` read-only воркеров для `TurboTokenFairData`. Каждый воркер делает случайную паузу между `TWIN_REQUEST_DELAY_MIN_SEC` и `TWIN_REQUEST_DELAY_MAX_SEC`, а `transport.py` повторяет только временные ошибки: `429`, `5xx` и сетевые исключения. При `Retry-After` клиент уважает серверную паузу; при падении одного цикла бесконечный демон ждет `TWIN_SCAN_INTERVAL_SEC` и запускает следующий цикл.

## Domain Isolation

- API-слой не знает о файловой структуре.
- Storage-слой не делает сетевых запросов.
- Analyzer не знает о Catapult и работает только с массивами float.
- CLI не считает корреляции и не парсит GraphQL.

## Почему отдельная папка

Twin Scout должен жить как отдельный демон. Он может быть запущен на отдельной машине, в screen/tmux, Docker или systemd без загрузки основного research/trading проекта.
