"""Email-delivery tool *contracts*. Implementations live in sibling modules
(``email_gmail.py``, ``email_mailgun.py``, ``email_sendgrid.py``,
``email_ses.py``, …) and are wired into the registry by
``runtime/bootstrap.py`` based on ``settings.email.provider``."""

from __future__ import annotations

from pydantic import BaseModel


class SendEmailInput(BaseModel):
    to: str
    subject: str
    body: str
    list_unsubscribe: str | None = None


class SendEmailOutput(BaseModel):
    sent: bool = True
