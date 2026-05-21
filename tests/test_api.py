from datetime import datetime, timezone

from cataultra_twin_scout.api import CatapultReadApi, is_completed
from cataultra_twin_scout.models import TokenCandidate
from cataultra_twin_scout.transport import GraphQLResult


def test_is_completed_uses_end_date() -> None:
    candidate = TokenCandidate(
        token_id="1",
        ticker="AAA",
        end_date="2026-05-20T00:00:00Z",
    )

    assert is_completed(candidate, now=datetime(2026, 5, 20, 0, 1, tzinfo=timezone.utc))


class RecordingClient:
    def __init__(self) -> None:
        self.variables = None

    def execute(self, operation_name: str, query: str, variables: dict | None = None) -> GraphQLResult:
        self.variables = variables
        return GraphQLResult(
            operation_name=operation_name,
            data={"turboTokenList": {"items": []}},
            errors=[],
            status_code=200,
            latency_ms=1.0,
            raw={"data": {"turboTokenList": {"items": []}}},
        )


def test_list_tokens_omits_speed_filter_for_all_types() -> None:
    client = RecordingClient()
    api = CatapultReadApi(client)  # type: ignore[arg-type]

    assert api.list_tokens([], limit=25, rank="Public") == []
    assert client.variables is not None
    assert client.variables["filter"] == {"rank": "Public"}
