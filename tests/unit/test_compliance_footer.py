from __future__ import annotations

from blufire.compliance.footer import build_outreach_body, render_footer
from blufire.compliance.unsubscribe import UnsubscribeSigner


def test_footer_has_required_elements(tmp_settings) -> None:
    footer = render_footer(tmp_settings, "https://unsub.example.com/u/abc")
    assert "Test Co" in footer
    assert "1 Test Way" in footer
    assert "Unsubscribe: https://unsub.example.com/u/abc" in footer


def test_build_outreach_body_appends_footer_and_returns_header(tmp_settings) -> None:
    signer = UnsubscribeSigner(tmp_settings)
    body, header = build_outreach_body(
        "Hi there.\n", tmp_settings, signer, recipient_email="alice@example.com"
    )
    assert body.startswith("Hi there.")
    assert "Unsubscribe:" in body
    assert header.startswith("<https://unsub.example.com/u/")


def test_casl_jurisdiction_adds_sender_line(tmp_settings) -> None:
    tmp_settings.compliance.jurisdiction.append("CA")
    footer = render_footer(tmp_settings, "https://unsub.example.com/u/abc")
    assert "Sender: Test Sender (sender@example.com)" in footer
