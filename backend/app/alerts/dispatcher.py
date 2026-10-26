"""Turns recorded checks into alerts and sends them, exactly once per channel.

This code must never break the check pipeline: every error ends up in alert_events or the log.
"""

import asyncio
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.alerts.message import AlertMessage, AlertSendError
from app.alerts.sender import send_to_channel
from app.models import AlertChannel, AlertEvent, Monitor, MonitorAlertChannel
from app.services.results import RecordedCheck

logger = logging.getLogger(__name__)

SSL_THRESHOLDS_DAYS = (7, 14, 30)
SEND_TIMEOUT_SECONDS = 30
MAX_DETAIL_LENGTH = 300

SessionFactory = async_sessionmaker[AsyncSession]


@dataclass(frozen=True)
class PendingAlert:
    dedupe_key: str
    incident_id: UUID | None
    message: AlertMessage


def ssl_threshold(days_left: int) -> int | None:
    """The smallest warning threshold that covers this many days, or None if it is far away."""
    for threshold in SSL_THRESHOLDS_DAYS:
        if days_left <= threshold:
            return threshold
    return None


def _message(kind: str, title: str, text: str, monitor: Monitor) -> AlertMessage:
    return AlertMessage(
        kind=kind,
        title=title,
        text=text,
        monitor_id=str(monitor.id),
        monitor_name=monitor.name,
        url=monitor.url,
    )


def build_alerts(monitor: Monitor, recorded: RecordedCheck, now: datetime) -> list[PendingAlert]:
    alerts: list[PendingAlert] = []

    incident = recorded.opened
    if incident is not None:
        details = incident.details or {}
        failures = details.get("consecutive_failures", "several")
        text = f"{monitor.name} failed {failures} checks in a row. Cause: {incident.cause}."
        if details.get("error_detail"):
            text += f" {str(details['error_detail'])[:MAX_DETAIL_LENGTH]}"
        alerts.append(
            PendingAlert(
                f"opened:{incident.id}",
                incident.id,
                _message("opened", f"{monitor.name} is DOWN", text, monitor),
            )
        )

    incident = recorded.resolved
    if incident is not None:
        text = f"{monitor.name} is reachable again."
        alerts.append(
            PendingAlert(
                f"resolved:{incident.id}",
                incident.id,
                _message("resolved", f"{monitor.name} is back UP", text, monitor),
            )
        )

    # SSL dates only change on a successful check, so only a success can trigger a warning.
    if recorded.result.success and not monitor.is_paused and monitor.ssl_expires_at is not None:
        days_left = (monitor.ssl_expires_at - now).days
        threshold = ssl_threshold(days_left)
        if threshold is not None:
            when = monitor.ssl_expires_at.date().isoformat()
            if days_left < 0:
                text = f"The SSL certificate of {monitor.name} expired on {when}."
            else:
                text = (
                    f"The SSL certificate of {monitor.name} expires in {days_left} days ({when})."
                )
            alerts.append(
                PendingAlert(
                    f"ssl:{monitor.id}:{threshold}:{when}",
                    None,
                    _message(
                        "ssl_expiry", f"SSL certificate warning: {monitor.name}", text, monitor
                    ),
                )
            )
    return alerts


async def _deliver(
    session_factory: SessionFactory, channel: AlertChannel, alert: PendingAlert, monitor_id: UUID
) -> bool:
    """Claim the alert, send it, record the outcome. Returns False if it was already handled."""
    async with session_factory() as db:
        # The unique index decides who owns this alert. A conflict means it was already handled.
        event_id = await db.scalar(
            insert(AlertEvent)
            .values(
                id=uuid4(),
                incident_id=alert.incident_id,
                monitor_id=monitor_id,
                channel_id=channel.id,
                kind=alert.message.kind,
                dedupe_key=alert.dedupe_key,
                success=False,
            )
            .on_conflict_do_nothing(index_elements=["channel_id", "dedupe_key"])
            .returning(AlertEvent.id)
        )
        await db.commit()  # the claim is saved before the slow part starts
        if event_id is None:
            return False

        error = None
        try:
            async with asyncio.timeout(SEND_TIMEOUT_SECONDS):
                await send_to_channel(channel, alert.message)
        except AlertSendError as send_error:
            error = str(send_error)[:500]
        except TimeoutError:
            error = "The alert took too long to send."
        except Exception:
            logger.exception("Unexpected error while sending an alert")
            error = "Unexpected error while sending."

        await db.execute(
            update(AlertEvent)
            .where(AlertEvent.id == event_id)
            .values(success=error is None, error=error, sent_at=func.now())
        )
        await db.commit()
        return True


async def dispatch_recorded(
    session_factory: SessionFactory, recorded: RecordedCheck, *, now: datetime | None = None
) -> int:
    """Send the alerts that a recorded check calls for. Returns how many sends were attempted."""
    now = now or datetime.now(UTC)
    async with session_factory() as db:
        monitor = await db.get(Monitor, recorded.result.monitor_id)
        if monitor is None:
            return 0
        alerts = build_alerts(monitor, recorded, now)
        if not alerts:
            return 0
        channels = list(
            await db.scalars(
                select(AlertChannel)
                .join(MonitorAlertChannel, MonitorAlertChannel.channel_id == AlertChannel.id)
                .where(
                    MonitorAlertChannel.monitor_id == monitor.id,
                    AlertChannel.is_verified.is_(True),
                )
                .order_by(AlertChannel.created_at, AlertChannel.id)
            )
        )
    if not channels:
        return 0

    results = await asyncio.gather(
        *(_deliver(session_factory, c, a, monitor.id) for a in alerts for c in channels),
        return_exceptions=True,
    )
    attempted = 0
    for result in results:
        if isinstance(result, BaseException):
            logger.error("Alert delivery crashed", exc_info=result)
        elif result:
            attempted += 1
    return attempted
