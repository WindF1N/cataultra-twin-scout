# Data Contract

## Session Folder

```text
private/twin_scout/session_1k_001/
```

Одна папка содержит максимум `batch_size` токенов. По умолчанию `batch_size = 1000`.

## Token Folder

```text
token_<token_id>_<ticker>/
```

Ticker очищается до безопасного имени: только буквы, цифры, `_` и `-`.

## Artifacts

### `raw_fair_data.json`

Сырой ответ GraphQL `turboTokenFairData`.

### `pure_ticks.json`

Чистый массив float:

```json
[100.0, 101.4, 98.2]
```

### `token_metadata.json`

```json
{
  "token_id": "16250112",
  "ticker": "PMPX",
  "name": "PMPX",
  "speed_mode": "CRACK",
  "start_price": 100.0,
  "final_price": 183.024,
  "fair_hash": "...",
  "fair_salt": "...",
  "created_at": "2026-05-20T00:00:00Z",
  "collected_at": "2026-05-20T00:10:00Z"
}
```

## `twins_report.md`

Отчет содержит:

- число проанализированных токенов;
- число perfect twins (`correlation >= 0.98`);
- число twins (`correlation >= 0.95`);
- пары токенов с ID, ticker, salt, hash;
- вывод о наличии одинаковых траекторий при разных hash/salt.

