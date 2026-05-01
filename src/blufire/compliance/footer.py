"""CAN-SPAM / CASL / GDPR-aware footer + body builder.

Required elements (per CAN-SPAM):
  • Sender's valid physical postal address
  • A clear way to opt out (link OR mailto)
  • Identification of the message as commercial / outreach

CASL (Canada) additionally requires unambiguous identification of the sender.
"""

from __future__ import annotations

from blufire.compliance.unsubscribe import UnsubscribeSigner
from blufire.settings import Settings

_BASIS_TEXT = {
    "consent": "you opted in to hear from us",
    "legitimate_interest": (
        "we believe you may be interested in our services based on your professional role"
    ),
}


def render_footer(settings: Settings, unsubscribe_link: str) -> str:
    sender = settings.sender
    basis_text = _BASIS_TEXT.get(
        settings.compliance.legal_basis, _BASIS_TEXT["legitimate_interest"]
    )
    lines = [
        "",
        "----",
        f"You're receiving this because {basis_text}.",
        f"{sender.company} • {sender.physical_address}",
        f"Unsubscribe: {unsubscribe_link}",
    ]
    if "CA" in settings.compliance.jurisdiction:
        lines.append(f"Sender: {sender.name} ({sender.email})")
    return "\n".join(lines)


def build_outreach_body(
    body: str,
    settings: Settings,
    signer: UnsubscribeSigner,
    *,
    recipient_email: str,
) -> tuple[str, str]:
    """Return ``(body_with_footer, list_unsubscribe_header)`` for one recipient."""
    link = signer.build_link(recipient_email)
    full_body = body.rstrip() + "\n" + render_footer(settings, link)
    list_unsub = signer.build_list_unsubscribe(recipient_email, mailto=settings.sender.reply_to)
    return full_body, list_unsub
