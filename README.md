# CATAULTRA Twin Scout

`CATAULTRA Twin Scout` — автономный демон для сбора раскрытых provable-fairness траекторий завершенных Catapult-токенов и поиска графиков-близнецов.

Это не торговый бот. Утилита ничего не покупает, не продает и не меняет состояние аккаунта. Она читает GraphQL, сохраняет `TurboTokenFairData`, упаковывает данные пачками по 1000 токенов и строит математический отчет по корреляциям.

## Возможности

- стрелочное меню через `questionary`;
- терминальный HUD через `rich`;
- чтение завершенных токенов через GraphQL `TurboTokenList`;
- сбор всех speed modes по умолчанию без фильтрации типа токена;
- параллельная загрузка раскрытых fair-data через 5 воркеров;
- случайный джиттер запросов и backoff/retry на `429`/временные ошибки;
- загрузка раскрытых `fairHash`, `fairSalt`, `speedTicksInSecond`, `ticksArray`;
- строгая структура `private/twin_scout/session_1k_001/token_<id>_<ticker>/`;
- автоматический анализ пачки 1000 токенов;
- поиск близнецов по скользящей корреляции Пирсона;
- генерация `twins_report.md` на русском языке;
- архивирование `session_1k_001.tar.gz` и очистка несжатой папки.

## Быстрый старт

```bash
cd /Users/bonecollector/Desktop/cataultra-twin-scout
python3 -m venv .venv
.venv/bin/python -m pip install -e ".[dev]"
cp .env.example .env
```

В `.env` нужно указать:

```bash
CATAPULT_COOKIE="..."
```

Опциональные параметры автономного сбора:

```bash
TWIN_SPEED_MODES="*"              # * / ALL / пусто = все типы монет
TWIN_WORKER_COUNT=5               # параллельные read-only воркеры fair-data
TWIN_REQUEST_DELAY_MIN_SEC=0.2    # нижняя граница случайной задержки перед запросом
TWIN_REQUEST_DELAY_MAX_SEC=1.2    # верхняя граница случайной задержки перед запросом
TWIN_RETRY_MAX_ATTEMPTS=4         # повторы при 429, 5xx и сетевых сбоях
TWIN_RETRY_BACKOFF_BASE_SEC=1.0
TWIN_RETRY_BACKOFF_MAX_SEC=30.0
```

Запуск:

```bash
.venv/bin/python main.py
```

Тесты:

```bash
PYTHONPATH=src .venv/bin/python -m pytest
```

## Структура данных

```text
private/twin_scout/
  state.json
  session_1k_001/
    token_16250112_PMPX/
      raw_fair_data.json
      pure_ticks.json
      token_metadata.json
    twins_report.md
  session_1k_001.tar.gz
```

## Главный цикл

1. Демон опрашивает публичный список токенов.
2. Если токен завершен, демон ставит его в очередь fair-data воркеров.
3. Если `ticksArray` раскрыт, токен сохраняется в текущую пачку.
4. Когда в пачке ровно `1000` токенов, запускается анализ.
5. Пишется `twins_report.md`.
6. Пачка архивируется в `.tar.gz`.
7. Несжатая папка удаляется.
8. Создается следующая пачка.

## Архитектурный принцип

Модули изолированы:

- `api.py` знает только про GraphQL;
- `storage.py` знает только про файлы;
- `analysis.py` знает только про математику;
- `daemon.py` связывает сбор, хранение и анализ;
- `cli.py` отвечает только за операторский интерфейс.
