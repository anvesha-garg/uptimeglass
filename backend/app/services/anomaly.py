"""Latency anomaly detection with a robust baseline (median + MAD)."""

from statistics import median

BASELINE_SIZE = 50  # successful latencies kept as the baseline
MIN_HISTORY = 20  # no verdicts until there are this many
MAD_FACTOR = 5.0  # how many scaled MADs above the median counts as an outlier
MAD_SCALE = 1.4826  # makes MAD comparable to a standard deviation
MIN_RATIO = 1.5  # also at least this many times the median
MIN_EXTRA_MS = 100  # and at least this much slower in absolute terms
SLOW_STREAK = 3  # consecutive outliers before a monitor is DEGRADED


def detect_anomaly(latency_ms: int | float, baseline: list[int] | list[float]) -> bool:
    """True if this latency is an outlier against the baseline. Pure, no database."""
    if len(baseline) < MIN_HISTORY:
        return False
    mid = median(baseline)
    mad = median(abs(value - mid) for value in baseline)
    threshold = mid + MAD_FACTOR * MAD_SCALE * mad
    # The floors matter when MAD is zero or tiny: a very steady site must not be
    # flagged for a harmless 10 ms wobble.
    return (
        latency_ms > threshold and latency_ms > mid * MIN_RATIO and latency_ms > mid + MIN_EXTRA_MS
    )
