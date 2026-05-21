from datetime import datetime, timedelta, timezone
from pathlib import Path

from cataultra_twin_scout.daemon import TwinScoutDaemon
from cataultra_twin_scout.models import FairData, TokenCandidate, TwinScoutConfig
from cataultra_twin_scout.storage import TwinScoutStorage


def _ended(minutes_ago: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(minutes=minutes_ago)).isoformat().replace("+00:00", "Z")


class FakeApi:
    def __init__(self) -> None:
        self.list_speed_modes: list[str] | None = None
        self.fetch_order: list[str] = []

    def list_tokens(self, speed_modes: list[str], limit: int = 100, rank: str = "Public") -> list[TokenCandidate]:
        self.list_speed_modes = speed_modes
        return [
            TokenCandidate(token_id="1", ticker="AAA", end_date=_ended(3)),
            TokenCandidate(token_id="2", ticker="BBB", end_date=_ended(2)),
            TokenCandidate(token_id="3", ticker="CCC", end_date=_ended(1)),
        ]

    def fetch_token_fair_data(self, token_id: str) -> FairData | None:
        self.fetch_order.append(token_id)
        return FairData(
            fair_hash=f"hash-{token_id}",
            fair_salt=f"salt-{token_id}",
            ticks_array=[1.0, 2.0, 3.0],
            raw={"tokenId": token_id},
        )


class PartiallyRevealedApi(FakeApi):
    def fetch_token_fair_data(self, token_id: str) -> FairData | None:
        self.fetch_order.append(token_id)
        if token_id == "1":
            return FairData(fair_hash="hash-1", fair_salt=None, ticks_array=[], raw={"tokenId": token_id})
        return FairData(
            fair_hash=f"hash-{token_id}",
            fair_salt=f"salt-{token_id}",
            ticks_array=[1.0, 2.0, 3.0],
            raw={"tokenId": token_id},
        )


def test_run_once_collects_completed_tokens_with_all_speed_modes(tmp_path: Path) -> None:
    api = FakeApi()
    storage = TwinScoutStorage(tmp_path)
    config = TwinScoutConfig(
        root_dir=str(tmp_path),
        batch_size=10,
        market_limit=3,
        speed_modes=[],
        worker_count=5,
        request_delay_min_sec=0,
        request_delay_max_sec=0,
    )
    daemon = TwinScoutDaemon(api, storage, config)  # type: ignore[arg-type]

    result = daemon.run_once()

    assert api.list_speed_modes == []
    assert sorted(api.fetch_order) == ["1", "2", "3"]
    assert result.added_count == 3
    assert storage.token_count(storage.session_dir(1)) == 3


def test_run_once_keeps_scanning_when_candidate_is_not_revealed(tmp_path: Path) -> None:
    api = PartiallyRevealedApi()
    storage = TwinScoutStorage(tmp_path)
    config = TwinScoutConfig(
        root_dir=str(tmp_path),
        batch_size=3,
        market_limit=3,
        speed_modes=[],
        worker_count=1,
        request_delay_min_sec=0,
        request_delay_max_sec=0,
    )
    daemon = TwinScoutDaemon(api, storage, config)  # type: ignore[arg-type]

    result = daemon.run_once()

    assert api.fetch_order == ["1", "2", "3"]
    assert result.added_count == 2
    assert result.collected_count == 2
