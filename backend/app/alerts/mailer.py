"""Sends email through the SMTP server named in the environment variables."""

import asyncio
import smtplib
import ssl
from email.message import EmailMessage

from app.alerts.message import AlertSendError
from app.core.config import settings

TIMEOUT_SECONDS = 10


def _send_sync(to: str, subject: str, body: str) -> None:
    if not settings.smtp_host or not settings.smtp_from:
        raise AlertSendError("Email is not configured on this server.")

    message = EmailMessage()
    message["From"] = settings.smtp_from
    message["To"] = to
    # Newlines in a header would let a monitor name inject extra headers.
    message["Subject"] = " ".join(subject.split())
    message.set_content(body)

    context = ssl.create_default_context()
    try:
        if settings.smtp_port == 465:
            server = smtplib.SMTP_SSL(
                settings.smtp_host, settings.smtp_port, timeout=TIMEOUT_SECONDS, context=context
            )
        else:
            server = smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=TIMEOUT_SECONDS)
        with server:
            if settings.smtp_port != 465:
                server.ehlo()
                server.starttls(context=context)  # encrypt before the password is sent
                server.ehlo()
            if settings.smtp_user:
                server.login(settings.smtp_user, settings.smtp_password)
            server.send_message(message)
    except (smtplib.SMTPException, OSError) as error:
        raise AlertSendError(f"The email could not be sent ({type(error).__name__}).") from None


async def send_email(to: str, subject: str, body: str) -> None:
    # smtplib is blocking, so it runs in a thread and does not freeze the scheduler.
    await asyncio.to_thread(_send_sync, to, subject, body)
