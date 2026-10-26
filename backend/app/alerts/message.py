"""What an alert says, and the error used when sending fails."""

from dataclasses import dataclass

MAX_TEXT_LENGTH = 4000  # Telegram's limit is 4096 characters


class AlertSendError(Exception):
    """A message could not be delivered. The text is safe to show to the user."""


@dataclass(frozen=True)
class AlertMessage:
    kind: str  # opened | resolved | ssl_expiry | test
    title: str
    text: str
    monitor_id: str | None = None
    monitor_name: str | None = None
    url: str | None = None

    def to_payload(self) -> dict:
        return {
            "event": self.kind,
            "title": self.title,
            "text": self.text,
            "monitor": {"id": self.monitor_id, "name": self.monitor_name, "url": self.url},
        }


def format_plain(message: AlertMessage) -> str:
    """Plain text for email and Telegram."""
    lines = [message.title, "", message.text]
    if message.url:
        lines += ["", message.url]
    return "\n".join(lines)[:MAX_TEXT_LENGTH]


def make_test_message() -> AlertMessage:
    return AlertMessage(
        kind="test",
        title="UptimeGlass test alert",
        text="This is a test alert. Your channel works.",
    )
