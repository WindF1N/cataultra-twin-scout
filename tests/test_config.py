from cataultra_twin_scout.config import parse_speed_modes
from cataultra_twin_scout.models import TwinScoutConfig


def test_empty_speed_modes_mean_all_token_types() -> None:
    config = TwinScoutConfig(speed_modes=[])

    assert config.speed_modes == []


def test_parse_speed_modes_accepts_all_marker() -> None:
    assert parse_speed_modes("*") == []
    assert parse_speed_modes("ALL") == []
    assert parse_speed_modes("MAYHEM, CRACK") == ["MAYHEM", "CRACK"]


def test_default_worker_config_is_five_workers_with_jitter() -> None:
    config = TwinScoutConfig()

    assert config.worker_count == 5
    assert config.request_delay_min_sec < config.request_delay_max_sec
