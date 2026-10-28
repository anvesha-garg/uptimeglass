import pytest

from app.services.anomaly import MIN_HISTORY, detect_anomaly

STEADY = [100, 102, 98, 101, 99] * 6  # 30 values around 100 ms


def test_too_little_history_never_flags():
    assert detect_anomaly(10_000, [100] * (MIN_HISTORY - 1)) is False


def test_exactly_minimum_history_can_flag():
    assert detect_anomaly(1_000, [100, 101] * (MIN_HISTORY // 2)) is True


def test_normal_latency_is_not_an_outlier():
    assert detect_anomaly(105, STEADY) is False


def test_big_slowdown_is_an_outlier():
    assert detect_anomaly(500, STEADY) is True


def test_zero_mad_uses_the_floors_not_division():
    flat = [100] * 30  # MAD is 0
    assert detect_anomaly(110, flat) is False  # slower, but below the floors
    assert detect_anomaly(149, flat) is False  # under 1.5x
    assert detect_anomaly(201, flat) is True


@pytest.mark.parametrize("latency", [90, 50, 1])
def test_faster_than_usual_is_never_an_anomaly(latency):
    assert detect_anomaly(latency, STEADY) is False


def test_one_spike_in_the_baseline_barely_changes_the_verdict():
    noisy = STEADY[:-1] + [9_000]  # a single huge spike (the mean would be ruined)
    assert detect_anomaly(105, noisy) is False
    assert detect_anomaly(500, noisy) is True


def test_noisy_site_needs_a_bigger_jump():
    noisy = [100, 300, 120, 280, 110, 290] * 5  # high variance
    assert detect_anomaly(350, noisy) is False
    assert detect_anomaly(2_000, noisy) is True
