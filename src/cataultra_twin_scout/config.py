from __future__ import annotations

import os

from dotenv import load_dotenv

from .models import TwinScoutConfig


def load_config() -> TwinScoutConfig:
    load_dotenv()
    return TwinScoutConfig(
        root_dir=os.getenv("TWIN_SCOUT_ROOT", "private/twin_scout"),
        batch_size=int(os.getenv("TWIN_BATCH_SIZE", "1000")),
        scan_interval_sec=float(os.getenv("TWIN_SCAN_INTERVAL_SEC", "10")),
        market_limit=int(os.getenv("TWIN_MARKET_LIMIT", "100")),
        speed_modes=parse_speed_modes(os.getenv("TWIN_SPEED_MODES", "*")),
        worker_count=int(os.getenv("TWIN_WORKER_COUNT", "5")),
        request_delay_min_sec=float(os.getenv("TWIN_REQUEST_DELAY_MIN_SEC", "0.2")),
        request_delay_max_sec=float(os.getenv("TWIN_REQUEST_DELAY_MAX_SEC", "1.2")),
        retry_max_attempts=int(os.getenv("TWIN_RETRY_MAX_ATTEMPTS", "4")),
        retry_backoff_base_sec=float(os.getenv("TWIN_RETRY_BACKOFF_BASE_SEC", "1.0")),
        retry_backoff_max_sec=float(os.getenv("TWIN_RETRY_BACKOFF_MAX_SEC", "30.0")),
        twin_correlation_threshold=float(os.getenv("TWIN_CORRELATION_THRESHOLD", "0.95")),
        perfect_correlation_threshold=float(os.getenv("TWIN_PERFECT_CORRELATION_THRESHOLD", "0.98")),
        max_correlation_lag=int(os.getenv("TWIN_MAX_CORRELATION_LAG", "8")),
    )


def require_cookie() -> str:
    load_dotenv()
    cookie = os.getenv("CATAPULT_COOKIE", "").strip()
    if not cookie:
        raise RuntimeError("CATAPULT_COOKIE не найден. Заполни .env перед запуском.")
    return cookie


def parse_speed_modes(value: str | None) -> list[str]:
    if value is None:
        return []
    normalized = value.strip()
    if not normalized or normalized.upper() in {"*", "ALL", "ANY"}:
        return []
    return [part.strip().upper() for part in normalized.split(",") if part.strip()]
