from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


class TwinScoutConfig(StrictModel):
    root_dir: str = "private/twin_scout"
    batch_size: int = Field(default=1000, ge=2)
    scan_interval_sec: float = Field(default=10.0, gt=0)
    market_limit: int = Field(default=100, ge=1, le=500)
    speed_modes: list[str] = Field(default_factory=list)
    rank: str = "Public"
    worker_count: int = Field(default=5, ge=1, le=20)
    request_delay_min_sec: float = Field(default=0.2, ge=0.0)
    request_delay_max_sec: float = Field(default=1.2, ge=0.0)
    retry_max_attempts: int = Field(default=4, ge=1, le=10)
    retry_backoff_base_sec: float = Field(default=1.0, gt=0.0)
    retry_backoff_max_sec: float = Field(default=30.0, gt=0.0)
    twin_correlation_threshold: float = Field(default=0.95, ge=-1.0, le=1.0)
    perfect_correlation_threshold: float = Field(default=0.98, ge=-1.0, le=1.0)
    max_correlation_lag: int = Field(default=8, ge=0, le=200)

    @model_validator(mode="after")
    def validate_timing(self) -> "TwinScoutConfig":
        if self.request_delay_max_sec < self.request_delay_min_sec:
            raise ValueError("request_delay_max_sec должен быть >= request_delay_min_sec")
        if self.retry_backoff_max_sec < self.retry_backoff_base_sec:
            raise ValueError("retry_backoff_max_sec должен быть >= retry_backoff_base_sec")
        return self


class TokenCandidate(StrictModel):
    token_id: str
    ticker: str
    name: str | None = None
    speed_mode: str | None = None
    start_price: float | None = None
    final_price: float | None = None
    start_date: str | None = None
    end_date: str | None = None
    raw: dict[str, Any] = Field(default_factory=dict)


class FairData(StrictModel):
    fair_hash: str | None = None
    fair_salt: str | None = None
    speed_ticks_in_second: float | None = None
    ticks_array: list[float] = Field(default_factory=list)
    raw: dict[str, Any] = Field(default_factory=dict)

    @property
    def is_revealed(self) -> bool:
        return bool(self.fair_salt and self.ticks_array)


class TokenMetadata(StrictModel):
    token_id: str
    ticker: str
    name: str | None = None
    speed_mode: str | None = None
    start_price: float | None = None
    final_price: float | None = None
    fair_hash: str | None = None
    fair_salt: str | None = None
    speed_ticks_in_second: float | None = None
    created_at: str | None = None
    ended_at: str | None = None
    collected_at: str = Field(default_factory=utc_now_iso)


class TwinPair(StrictModel):
    left_token_id: str
    left_ticker: str
    left_fair_hash: str | None = None
    left_fair_salt: str | None = None
    right_token_id: str
    right_ticker: str
    right_fair_hash: str | None = None
    right_fair_salt: str | None = None
    correlation: float
    lag: int = 0
    overlap: int = 0
    classification: str


class ScoutState(StrictModel):
    current_session_number: int = 1
    processed_token_ids: list[str] = Field(default_factory=list)
    archived_sessions: int = 0
    total_twin_pairs_found: int = 0
    last_token_id: str | None = None
    last_ticker: str | None = None
    updated_at: str = Field(default_factory=utc_now_iso)
