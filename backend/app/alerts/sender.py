"""One entry point for sending a message to any kind of channel."""

from app.alerts.mailer import send_email
from app.alerts.message import AlertMessage, AlertSendError, format_plain
from app.alerts.telegram import send_telegram
from app.alerts.webhook import send_webhook
from app.models import AlertChannel


async def send_to_channel(channel: AlertChannel, message: AlertMessage) -> None:
    """Raises AlertSendError if the message cannot be delivered."""
    if not channel.is_verified:
        raise AlertSendError("The channel is not verified.")
    config = channel.config
    if channel.type == "webhook":
        await send_webhook(config, message)
    elif channel.type == "email":
        await send_email(config["address"], message.title, format_plain(message))
    elif channel.type == "telegram":
        await send_telegram(config["chat_id"], format_plain(message))
    else:
        raise AlertSendError("Unknown channel type.")
