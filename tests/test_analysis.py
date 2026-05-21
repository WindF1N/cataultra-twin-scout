from cataultra_twin_scout.analysis import pearson_correlation, sliding_pearson


def test_pearson_detects_identical_shape() -> None:
    left = [1.0, 2.0, 4.0, 8.0]
    right = [10.0, 20.0, 40.0, 80.0]

    assert pearson_correlation(left, right) == 1.0


def test_sliding_pearson_handles_small_lag() -> None:
    left = [1, 3, 9, 4, 2, 1, 1, 1]
    right = [1, 1, 1, 3, 9, 4, 2, 1]

    corr, lag, overlap = sliding_pearson(left, right, max_lag=3)

    assert corr > 0.99
    assert overlap >= 5
    assert lag != 0
