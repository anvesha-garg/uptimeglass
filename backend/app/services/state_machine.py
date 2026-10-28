"""The rules that turn check outcomes into monitor states. No database code here."""

from dataclasses import dataclass
from datetime import datetime, timedelta

from app.models import Monitor
from app.services.anomaly import SLOW_STREAK, detect_anomaly
from app.services.checker import CheckOutcome

FAILURE_THRESHOLD = 3  # failures in a row before a monitor is DOWN
RECOVERY_THRESHOLD = 2  # successes in a row before a DOWN monitor is UP again
RETRY_DELAY_SECONDS = 20  # quick re-check while confirming a failure or a recovery


@dataclass(frozen=True)
class Transition:
    old_status: str
    new_status: str
    went_down: bool = False  # the monitor just entered DOWN: open an incident
    recovered: bool = False  # the monitor just left DOWN or PENDING for UP: resolve any incident


def apply_outcome(
    monitor: Monitor,
    outcome: CheckOutcome,
    now: datetime,
    baseline: list[int] | None = None,
) -> Transition:
    """Update the monitor's status, counters and next check time. Does not touch the database.

    baseline: recent successful latencies (not including this check), for DEGRADED detection.
    """
    old_status = monitor.status
    if monitor.is_paused:
        # A result that arrives after the user paused the monitor changes nothing.
        return Transition(old_status, old_status)

    monitor.last_checked_at = now
    if outcome.ssl_expires_at is not None:
        monitor.ssl_expires_at = outcome.ssl_expires_at  # never erased by a failed check

    interval = timedelta(seconds=monitor.interval_seconds)
    retry = timedelta(seconds=min(RETRY_DELAY_SECONDS, monitor.interval_seconds))

    if outcome.success:
        monitor.consecutive_failures = 0
        monitor.consecutive_successes += 1
        slow = outcome.latency_ms is not None and detect_anomaly(outcome.latency_ms, baseline or [])
        monitor.consecutive_slow = monitor.consecutive_slow + 1 if slow else 0
        if old_status == "DOWN" and monitor.consecutive_successes < RECOVERY_THRESHOLD:
            wait = retry  # still DOWN, confirming the recovery
        else:
            # Slow but answering: DEGRADED. This never opens an incident.
            monitor.status = "DEGRADED" if monitor.consecutive_slow >= SLOW_STREAK else "UP"
            wait = interval
    else:
        monitor.consecutive_successes = 0
        monitor.consecutive_slow = 0
        monitor.consecutive_failures += 1
        if old_status == "DOWN":
            wait = interval  # already DOWN: no new incident, normal schedule
        elif monitor.consecutive_failures >= FAILURE_THRESHOLD:
            monitor.status = "DOWN"
            wait = interval
        else:
            wait = retry  # confirming the failure

    monitor.next_check_at = now + wait
    return Transition(
        old_status=old_status,
        new_status=monitor.status,
        went_down=old_status != "DOWN" and monitor.status == "DOWN",
        # Leaving DEGRADED needs no incident work, because DEGRADED never opens one.
        recovered=outcome.success
        and monitor.status in ("UP", "DEGRADED")
        and old_status in ("DOWN", "PENDING"),
    )
