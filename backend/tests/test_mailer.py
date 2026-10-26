import smtplib

import pytest

from app.alerts.mailer import send_email
from app.alerts.message import AlertSendError
from app.core.config import settings


class FakeSMTP:
    instances: list["FakeSMTP"] = []
    fail_on_login = False

    def __init__(self, host, port, timeout=None, context=None):
        self.kind = type(self).__name__
        self.host, self.port = host, port
        self.steps: list[str] = []
        self.sent = []
        FakeSMTP.instances.append(self)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def ehlo(self):
        self.steps.append("ehlo")

    def starttls(self, context=None):
        self.steps.append("starttls")

    def login(self, user, password):
        if FakeSMTP.fail_on_login:
            raise smtplib.SMTPAuthenticationError(535, b"bad credentials")
        self.steps.append(f"login:{user}")

    def send_message(self, message):
        self.sent.append(message)


class FakeSMTPSSL(FakeSMTP):
    pass


@pytest.fixture
def smtp(monkeypatch):
    FakeSMTP.instances = []
    FakeSMTP.fail_on_login = False
    monkeypatch.setattr(smtplib, "SMTP", FakeSMTP)
    monkeypatch.setattr(smtplib, "SMTP_SSL", FakeSMTPSSL)
    for name, value in {
        "smtp_host": "smtp.test",
        "smtp_port": 587,
        "smtp_user": "user",
        "smtp_password": "pw",
        "smtp_from": "alerts@example.com",
    }.items():
        monkeypatch.setattr(settings, name, value)
    return FakeSMTP


async def test_email_is_sent_with_starttls_and_login(smtp):
    await send_email("me@example.com", "Hello", "Body text")

    (server,) = smtp.instances
    assert server.kind == "FakeSMTP"
    assert server.steps == ["ehlo", "starttls", "ehlo", "login:user"]
    (message,) = server.sent
    assert message["To"] == "me@example.com"
    assert message["From"] == "alerts@example.com"
    assert message["Subject"] == "Hello"
    assert "Body text" in message.get_content()


async def test_port_465_uses_ssl_without_starttls(smtp, monkeypatch):
    monkeypatch.setattr(settings, "smtp_port", 465)
    await send_email("me@example.com", "Hello", "Body")

    (server,) = smtp.instances
    assert server.kind == "FakeSMTPSSL"
    assert "starttls" not in server.steps


async def test_newlines_in_the_subject_cannot_inject_headers(smtp):
    await send_email("me@example.com", "Down\r\nBcc: evil@example.com", "Body")
    message = smtp.instances[0].sent[0]
    assert message["Subject"] == "Down Bcc: evil@example.com"
    assert message["Bcc"] is None


async def test_missing_configuration_is_an_error(smtp, monkeypatch):
    monkeypatch.setattr(settings, "smtp_host", "")
    with pytest.raises(AlertSendError, match="not configured"):
        await send_email("me@example.com", "Hello", "Body")
    assert smtp.instances == []


async def test_smtp_errors_become_alert_errors_without_the_password(smtp):
    smtp.fail_on_login = True
    with pytest.raises(AlertSendError) as error:
        await send_email("me@example.com", "Hello", "Body")
    assert "SMTPAuthenticationError" in str(error.value)
    assert "pw" not in str(error.value)
