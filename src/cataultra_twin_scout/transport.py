from __future__ import annotations

import random
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any


WEB_GRAPHQL_URL = "https://catapult.trade/graphql"

WEB_HEADERS = {
    "accept": "application/graphql-response+json, application/graphql+json, application/json",
    "accept-language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
    "content-type": "application/json",
    "origin": "https://catapult.trade",
    "referer": "https://catapult.trade/",
    "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome Safari/537.36",
}


class GraphQLTransportError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class GraphQLResult:
    operation_name: str
    data: dict[str, Any] | None
    errors: list[dict[str, Any]]
    status_code: int | None
    latency_ms: float
    raw: dict[str, Any] | None

    @property
    def ok(self) -> bool:
        return not self.errors and self.data is not None


class GraphQLClient:
    def __init__(
        self,
        cookie: str,
        url: str = WEB_GRAPHQL_URL,
        timeout_sec: float = 20.0,
        retry_max_attempts: int = 4,
        retry_backoff_base_sec: float = 1.0,
        retry_backoff_max_sec: float = 30.0,
    ):
        headers = WEB_HEADERS.copy()
        if cookie:
            headers["cookie"] = cookie
        self.url = url
        self.headers = headers
        self.timeout_sec = timeout_sec
        self.retry_max_attempts = retry_max_attempts
        self.retry_backoff_base_sec = retry_backoff_base_sec
        self.retry_backoff_max_sec = retry_backoff_max_sec

    def execute(self, operation_name: str, query: str, variables: dict[str, Any] | None = None) -> GraphQLResult:
        started = time.perf_counter()
        status_code: int | None = None
        raw: dict[str, Any] | None = None
        error: str | None = None
        for attempt in range(1, self.retry_max_attempts + 1):
            retry_after: float | None = None
            try:
                try:
                    from curl_cffi import requests
                except ImportError as exc:  # pragma: no cover
                    raise GraphQLTransportError("curl_cffi is required") from exc
                response = requests.post(
                    self.url,
                    headers=self.headers,
                    json={"operationName": operation_name, "query": query, "variables": variables or {}},
                    impersonate="chrome",
                    timeout=self.timeout_sec,
                )
                status_code = response.status_code
                retry_after = _retry_after_seconds(response.headers.get("retry-after"))
                try:
                    raw = response.json()
                except Exception:
                    raw = None
                if not _is_retryable_status(status_code) or attempt >= self.retry_max_attempts:
                    error = None
                    break
            except Exception as exc:
                error = str(exc)
                if attempt >= self.retry_max_attempts:
                    break
            time.sleep(self._retry_delay(attempt, retry_after))

        latency_ms = round((time.perf_counter() - started) * 1000.0, 3)
        data = raw.get("data") if isinstance(raw, dict) else None
        errors = raw.get("errors") if isinstance(raw, dict) else None
        if errors is None:
            errors = []
        if error:
            errors = [{"message": error}]
        elif status_code is not None and status_code >= 400:
            errors = [{"message": f"GraphQL HTTP {status_code}"}]
        return GraphQLResult(
            operation_name=operation_name,
            data=data,
            errors=errors,
            status_code=status_code,
            latency_ms=latency_ms,
            raw=raw,
        )

    def _retry_delay(self, attempt: int, retry_after: float | None) -> float:
        if retry_after is not None:
            return min(retry_after, self.retry_backoff_max_sec)
        exponential = self.retry_backoff_base_sec * (2 ** (attempt - 1))
        capped = min(exponential, self.retry_backoff_max_sec)
        return capped + random.uniform(0, min(capped, 1.0))


def _is_retryable_status(status_code: int | None) -> bool:
    return status_code == 429 or (status_code is not None and 500 <= status_code <= 599)


def _retry_after_seconds(value: str | None) -> float | None:
    if not value:
        return None
    try:
        return max(0.0, float(value))
    except ValueError:
        pass
    try:
        parsed = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return max(0.0, (parsed - datetime.now(timezone.utc)).total_seconds())
