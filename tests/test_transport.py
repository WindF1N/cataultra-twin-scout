from cataultra_twin_scout.transport import _is_retryable_status, _retry_after_seconds


def test_retryable_status_targets_rate_limit_and_server_errors() -> None:
    assert _is_retryable_status(429)
    assert _is_retryable_status(502)
    assert not _is_retryable_status(400)
    assert not _is_retryable_status(200)


def test_retry_after_seconds_accepts_delta_seconds() -> None:
    assert _retry_after_seconds("2.5") == 2.5
    assert _retry_after_seconds("bad-value") is None
