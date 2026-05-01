"""SMTP sender: redaction + retry. Mocks ``smtplib.SMTP_SSL`` directly so we
never touch a real Gmail server."""

from __future__ import annotations

import smtplib

import pytest

from blufire.integrations.smtp import EmailHeaders, SmtpAuthError, SmtpSender


def test_password_not_in_exception_message(tmp_settings, monkeypatch: pytest.MonkeyPatch) -> None:
    class _BoomSmtp:
        def __init__(self, *a, **kw):
            raise smtplib.SMTPAuthenticationError(535, b"bad")

    monkeypatch.setattr(smtplib, "SMTP_SSL", _BoomSmtp)
    sender = SmtpSender(tmp_settings)
    with pytest.raises(SmtpAuthError) as exc_info:
        sender.send(to="a@example.com", subject="s", body="b")
    assert "test-app-password" not in str(exc_info.value)


def test_list_unsubscribe_headers_attached(tmp_settings, monkeypatch: pytest.MonkeyPatch) -> None:
    captured: list[object] = []

    class _Server:
        def __init__(self, *a, **kw): ...
        def __enter__(self):
            return self

        def __exit__(self, *a): ...
        def login(self, *a): ...
        def send_message(self, msg):
            captured.append(msg)

    monkeypatch.setattr(smtplib, "SMTP_SSL", _Server)
    sender = SmtpSender(tmp_settings)
    sender.send(
        to="a@example.com",
        subject="s",
        body="hello",
        headers=EmailHeaders(list_unsubscribe="<https://u/x>"),
    )
    assert captured, "send_message was not called"
    msg = captured[0]
    assert msg["List-Unsubscribe"] == "<https://u/x>"
    assert msg["List-Unsubscribe-Post"] == "List-Unsubscribe=One-Click"


def test_retries_on_disconnect(tmp_settings, monkeypatch: pytest.MonkeyPatch) -> None:
    calls = {"n": 0}

    class _Flaky:
        def __init__(self, *a, **kw):
            calls["n"] += 1
            if calls["n"] < 2:
                raise smtplib.SMTPServerDisconnected("bye")

        def __enter__(self):
            return self

        def __exit__(self, *a): ...
        def login(self, *a): ...
        def send_message(self, msg): ...

    monkeypatch.setattr(smtplib, "SMTP_SSL", _Flaky)
    SmtpSender(tmp_settings).send(to="a@example.com", subject="s", body="b")
    assert calls["n"] == 2
