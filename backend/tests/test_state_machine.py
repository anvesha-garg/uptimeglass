from datetime import UTC, datetime, timedelta

from app.models import Monitor
from app.services.checker import CheckOutcome
from app.services.state_machine import RETRY_DELAY_SECONDS, apply_outcome

NOW = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
OK = CheckOutcome(success=True, status_code=200, latency_ms=50)
FAIL = CheckOutcome(success=False, error_type="timeout", error_detail="No answer.")


def make_monitor(**overrides) -> Monitor:
    """An unsaved monitor: the state machine never needs a database."""
    values = {
        "status": "UP",
        "is_paused": False,
        "interval_seconds": 300,
        "consecutive_failures": 0,
        "consecutive_successes": 0,
        "consecutive_slow": 0,
        "next_check_at": NOW,
        "last_checked_at": None,
        "ssl_expires_at": None,
    }
    values.update(overrides)
    return Monitor(**values)


def test_success_keeps_monitor_up_and_waits_a_full_interval():
    monitor = make_monitor()
    transition = apply_outcome(monitor, OK, NOW)
    assert monitor.status == "UP"
    assert monitor.next_check_at == NOW + timedelta(seconds=300)
    assert transition.went_down is False
    assert transition.recovered is False


def test_first_failure_does_not_mark_down():
    monitor = make_monitor()
    transition = apply_outcome(monitor, FAIL, NOW)
    assert monitor.status == "UP"
    assert monitor.consecutive_failures == 1
    assert monitor.next_check_at == NOW + timedelta(seconds=RETRY_DELAY_SECONDS)
    assert transition.went_down is False


def test_retry_delay_is_never_longer_than_the_interval():
    monitor = make_monitor(interval_seconds=10)
    apply_outcome(monitor, FAIL, NOW)
    assert monitor.next_check_at == NOW + timedelta(seconds=10)


def test_third_failure_marks_down_and_flags_one_incident():
    monitor = make_monitor(consecutive_failures=2)
    transition = apply_outcome(monitor, FAIL, NOW)
    assert monitor.status == "DOWN"
    assert transition.went_down is True
    assert transition.old_status == "UP"
    assert transition.new_status == "DOWN"
    # Once DOWN, checks go back to the normal schedule.
    assert monitor.next_check_at == NOW + timedelta(seconds=300)


def test_more_failures_while_down_do_not_open_another_incident():
    monitor = make_monitor(status="DOWN", consecutive_failures=3)
    transition = apply_outcome(monitor, FAIL, NOW)
    assert monitor.status == "DOWN"
    assert monitor.consecutive_failures == 4
    assert transition.went_down is False


def test_one_success_is_not_enough_to_recover():
    monitor = make_monitor(status="DOWN", consecutive_failures=3)
    transition = apply_outcome(monitor, OK, NOW)
    assert monitor.status == "DOWN"
    assert monitor.consecutive_successes == 1
    assert monitor.consecutive_failures == 0
    assert transition.recovered is False
    assert monitor.next_check_at == NOW + timedelta(seconds=RETRY_DELAY_SECONDS)


def test_second_success_recovers():
    monitor = make_monitor(status="DOWN", consecutive_successes=1)
    transition = apply_outcome(monitor, OK, NOW)
    assert monitor.status == "UP"
    assert transition.recovered is True
    assert monitor.next_check_at == NOW + timedelta(seconds=300)


def test_failure_during_recovery_resets_the_success_streak():
    monitor = make_monitor(status="DOWN", consecutive_successes=1)
    transition = apply_outcome(monitor, FAIL, NOW)
    assert monitor.status == "DOWN"
    assert monitor.consecutive_successes == 0
    assert transition.went_down is False
    assert transition.recovered is False


def test_success_resets_the_failure_streak():
    monitor = make_monitor(consecutive_failures=2)
    apply_outcome(monitor, OK, NOW)
    assert monitor.consecutive_failures == 0
    assert monitor.status == "UP"


def test_first_success_moves_pending_to_up():
    monitor = make_monitor(status="PENDING")
    transition = apply_outcome(monitor, OK, NOW)
    assert monitor.status == "UP"
    # "recovered" also covers PENDING: it resolves any leftover open incident.
    assert transition.recovered is True


def test_paused_monitor_is_left_alone():
    monitor = make_monitor(status="PAUSED", is_paused=True)
    transition = apply_outcome(monitor, FAIL, NOW)
    assert monitor.status == "PAUSED"
    assert monitor.consecutive_failures == 0
    assert monitor.last_checked_at is None
    assert transition.went_down is False
    assert transition.recovered is False


def test_ssl_expiry_is_copied_and_never_erased():
    expires = datetime(2030, 6, 1, tzinfo=UTC)
    monitor = make_monitor()
    apply_outcome(monitor, CheckOutcome(success=True, ssl_expires_at=expires), NOW)
    assert monitor.ssl_expires_at == expires
    apply_outcome(monitor, FAIL, NOW)  # a failed check has no certificate information
    assert monitor.ssl_expires_at == expires


def test_last_checked_is_set():
    monitor = make_monitor()
    apply_outcome(monitor, OK, NOW)
    assert monitor.last_checked_at == NOW


def test_full_cycle_up_down_up():
    monitor = make_monitor()
    events = []
    for outcome in [FAIL, FAIL, FAIL, OK, OK]:
        transition = apply_outcome(monitor, outcome, NOW)
        events.append((monitor.status, transition.went_down, transition.recovered))
    assert events == [
        ("UP", False, False),
        ("UP", False, False),
        ("DOWN", True, False),
        ("DOWN", False, False),
        ("UP", False, True),
    ]


def test_leaving_degraded_for_up_does_not_resolve_incidents():
    monitor = make_monitor(status="DEGRADED", consecutive_slow=3)
    transition = apply_outcome(monitor, OK, NOW)
    assert monitor.status == "UP"
    assert transition.recovered is False


def test_a_failure_in_degraded_follows_the_normal_down_rules():
    monitor = make_monitor(status="DEGRADED", consecutive_slow=3, consecutive_failures=2)
    transition = apply_outcome(monitor, FAIL, NOW)
    assert monitor.status == "DOWN"
    assert monitor.consecutive_slow == 0
    assert transition.went_down is True
