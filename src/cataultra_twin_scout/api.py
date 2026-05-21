from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from . import operations as ops
from .models import FairData, TokenCandidate
from .transport import GraphQLClient


class CatapultReadApi:
    def __init__(self, client: GraphQLClient):
        self.client = client

    def list_tokens(self, speed_modes: list[str], limit: int = 100, rank: str = "Public") -> list[TokenCandidate]:
        filter_payload: dict[str, Any] = {"rank": rank}
        if speed_modes:
            filter_payload["speedMode"] = speed_modes
        variables = {
            "filter": filter_payload,
            "pagination": {"limit": int(limit)},
            "sort": {"direction": "Desc", "field": "StartTime"},
        }
        result = self.client.execute("TurboTokenList", ops.TURBO_TOKEN_LIST, variables)
        if not result.ok:
            return []
        items = (((result.data or {}).get("turboTokenList") or {}).get("items") or [])
        return [_candidate_from_item(item) for item in items if isinstance(item, dict)]

    def fetch_token_fair_data(self, token_id: str) -> FairData | None:
        result = self.client.execute("TurboTokenFairData", ops.TURBO_TOKEN_FAIR_DATA, {"tokenId": str(token_id)})
        
        if not result.ok:
            return None
        payload = ((result.data or {}).get("turboTokenFairData") or {})
        if not payload:
            return None
        ticks = _float_list(payload.get("ticksArray"))
        return FairData(
            fair_hash=payload.get("fairHash"),
            fair_salt=payload.get("fairSalt"),
            speed_ticks_in_second=_optional_float(payload.get("speedTicksInSecond")),
            ticks_array=ticks,
            raw=payload,
        )


def is_completed(candidate: TokenCandidate, now: datetime | None = None) -> bool:
    if not candidate.end_date:
        return False
    parsed = _parse_datetime(candidate.end_date)
    if parsed is None:
        return False
    return parsed <= (now or datetime.now(timezone.utc))


def _candidate_from_item(item: dict[str, Any]) -> TokenCandidate:
    return TokenCandidate(
        token_id=str(item.get("id") or ""),
        ticker=str(item.get("symbol") or item.get("name") or "UNKNOWN"),
        name=item.get("name"),
        speed_mode=item.get("speedMode"),
        start_price=_optional_float(item.get("initialPrice")),
        final_price=_optional_float(item.get("price")),
        start_date=item.get("startDate"),
        end_date=item.get("endDate"),
        raw=item,
    )


def _optional_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _float_list(value: Any) -> list[float]:
    if not isinstance(value, list):
        return []
    result: list[float] = []
    for item in value:
        parsed = _optional_float(item)
        if parsed is not None:
            result.append(parsed)
    return result


def _parse_datetime(value: str) -> datetime | None:
    try:
        normalized = value.replace("Z", "+00:00")
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)
