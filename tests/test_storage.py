from pathlib import Path

from cataultra_twin_scout.models import FairData, TokenCandidate
from cataultra_twin_scout.storage import TwinScoutStorage, safe_name


def test_safe_name_removes_unsafe_symbols() -> None:
    assert safe_name("BAD/COIN 🚀") == "BAD_COIN"


def test_storage_writes_token_contract(tmp_path: Path) -> None:
    storage = TwinScoutStorage(tmp_path)
    session = storage.session_dir(1)
    candidate = TokenCandidate(
        token_id="123",
        ticker="PMPX",
        name="Pump X",
        speed_mode="CRACK",
        start_price=100.0,
        final_price=150.0,
    )
    fair = FairData(
        fair_hash="hash",
        fair_salt="salt",
        speed_ticks_in_second=5,
        ticks_array=[100.0, 120.0, 150.0],
        raw={"fairHash": "hash", "ticksArray": [100, 120, 150]},
    )

    token_dir = storage.write_token(session, candidate, fair)

    assert (token_dir / "raw_fair_data.json").exists()
    assert (token_dir / "pure_ticks.json").exists()
    assert (token_dir / "token_metadata.json").exists()
    assert storage.token_count(session) == 1

