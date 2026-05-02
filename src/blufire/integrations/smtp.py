"""SMTP sender (Gmail by default). Adds ``List-Unsubscribe`` headers and
redacts credentials from any logged exception."""

from __future__ import annotations

import smtplib
from dataclasses import dataclass
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential_jitter,
)

from blufire.logging_setup import get_logger, hash_recipient
from blufire.settings import Settings

DEFAULT_HOST = "smtp.gmail.com"
DEFAULT_PORT = 465


class SmtpAuthError(RuntimeError):
    """Authentication failed. Do NOT include the password in the message."""


class SmtpSendError(RuntimeError):
    """Send failed after retries. Do NOT include the password."""


@dataclass(frozen=True)
class EmailHeaders:
    list_unsubscribe: str | None = None
    list_unsubscribe_post: str | None = "List-Unsubscribe=One-Click"


class SmtpSender:
    def __init__(
        self,
        settings: Settings,
        *,
        host: str = DEFAULT_HOST,
        port: int = DEFAULT_PORT,
        timeout: float = 15.0,
    ) -> None:
        if not settings.secrets.gmail_user:
            raise RuntimeError("GMAIL_USER is not configured.")
        if settings.secrets.gmail_app_password is None:
            raise RuntimeError("GMAIL_APP_PASSWORD is not configured.")
        self._host = host
        self._port = port
        self._timeout = timeout
        self._user = settings.secrets.gmail_user
        self._password = settings.secrets.gmail_app_password.get_secret_value()
        self._log = get_logger("blufire.integrations.smtp").bind(
            tenant_id=settings.tenant.id, smtp_host=host
        )

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential_jitter(initial=2.0, max=20.0),
        retry=retry_if_exception_type(
            (smtplib.SMTPServerDisconnected, smtplib.SMTPConnectError, OSError)
        ),
        reraise=True,
    )
    def send(
        self,
        *,
        to: str,
        subject: str,
        body: str,
        headers: EmailHeaders | None = None,
    ) -> None:
        msg = MIMEMultipart()
        msg["From"] = self._user
        msg["To"] = to
        msg["Subject"] = subject
        if headers and headers.list_unsubscribe:
            msg["List-Unsubscribe"] = headers.list_unsubscribe
            if headers.list_unsubscribe_post:
                msg["List-Unsubscribe-Post"] = headers.list_unsubscribe_post
        msg.attach(MIMEText(body, "plain", "utf-8"))

        log = self._log.bind(recipient_hash=hash_recipient(to))

        # Auth failures convert to SmtpAuthError so the password never appears
        # in any log/traceback. Connection / disconnect failures bubble up so
        # tenacity (above) can retry. Other SMTP errors convert to a redacted
        # SmtpSendError. Order matters: SMTPAuthenticationError is a subclass
        # of SMTPException, so it must be caught FIRST.
        try:
            with smtplib.SMTP_SSL(self._host, self._port, timeout=self._timeout) as server:
                server.login(self._user, self._password)
                server.send_message(msg)
        except smtplib.SMTPAuthenticationError:
            log.error("smtp_auth_failed")
            raise SmtpAuthError("SMTP authentication failed (check GMAIL_APP_PASSWORD)") from None
        except (smtplib.SMTPServerDisconnected, smtplib.SMTPConnectError, OSError):
            raise  # tenacity retries
        except smtplib.SMTPException as exc:
            log.error("smtp_send_failed", error_class=type(exc).__name__)
            raise SmtpSendError(f"SMTP send failed: {type(exc).__name__}") from None

        log.info("smtp_sent")
