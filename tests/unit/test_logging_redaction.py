from __future__ import annotations

from blufire.logging_setup import _scrub_processor


def test_scrubs_known_secret_keys() -> None:
    out = _scrub_processor(
        None,
        "info",
        {  # type: ignore[arg-type]
            "anthropic_api_key": "abc-123",
            "hubspot_api_key": "secret",
            "gmail_app_password": "p",
            "innocuous": "fine",
        },
    )
    assert out["anthropic_api_key"] == "***REDACTED***"
    assert out["hubspot_api_key"] == "***REDACTED***"
    assert out["gmail_app_password"] == "***REDACTED***"
    assert out["innocuous"] == "fine"


def test_scrubs_bearer_tokens_in_strings() -> None:
    out = _scrub_processor(
        None,
        "info",
        {  # type: ignore[arg-type]
            "msg": "Authorization: Bearer abcdef123 from upstream",
        },
    )
    assert "abcdef123" not in out["msg"]
    assert "REDACTED" in out["msg"]


def test_hash_recipient_stable_and_short() -> None:
    from blufire.logging_setup import hash_recipient

    a = hash_recipient("alice@example.com")
    b = hash_recipient("Alice@Example.com")
    assert a == b
    assert len(a) == 16
