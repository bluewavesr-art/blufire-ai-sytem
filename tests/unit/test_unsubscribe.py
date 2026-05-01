from __future__ import annotations

import time

import pytest

from blufire.compliance.unsubscribe import TokenInvalid, UnsubscribeSigner


def test_round_trip(tmp_settings) -> None:
    signer = UnsubscribeSigner(tmp_settings)
    token = signer.sign("alice@example.com")
    payload = signer.verify(token)
    assert payload.email == "alice@example.com"


def test_tampered_signature(tmp_settings) -> None:
    signer = UnsubscribeSigner(tmp_settings)
    token = signer.sign("alice@example.com")
    payload, sig = token.split(".", 1)
    tampered = f"{payload}.{sig[:-2]}AA"
    with pytest.raises(TokenInvalid):
        signer.verify(tampered)


def test_expired(tmp_settings, monkeypatch: pytest.MonkeyPatch) -> None:
    signer = UnsubscribeSigner(tmp_settings, ttl_seconds=1)
    token = signer.sign("a@example.com")
    real_time = time.time
    monkeypatch.setattr("blufire.compliance.unsubscribe.time.time", lambda: real_time() + 10)
    with pytest.raises(TokenInvalid):
        signer.verify(token)


def test_link_uses_base_url(tmp_settings) -> None:
    signer = UnsubscribeSigner(tmp_settings)
    link = signer.build_link("a@example.com")
    assert link.startswith("https://unsub.example.com/u/")


def test_list_unsubscribe_header_format(tmp_settings) -> None:
    signer = UnsubscribeSigner(tmp_settings)
    header = signer.build_list_unsubscribe("a@example.com", mailto="reply@example.com")
    assert header.startswith("<https://unsub.example.com/u/")
    assert "<mailto:reply@example.com" in header
