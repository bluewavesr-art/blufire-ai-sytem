"""Email-delivery tool *contracts*. Two distinct contracts live here:

* ``email.send_smtp`` — send a finished email immediately. Backed by
  Gmail/Mailgun/SendGrid/SES/etc. Selected by ``settings.email.provider``.
* ``email.create_draft`` — create a draft for human review (no immediate
  send). Backed by a Make.com webhook that produces a Gmail draft, or
  directly by the Gmail/Outlook draft API, or GHL. Selected by
  ``settings.email.draft_provider``.

These are deliberately separate contracts because they have different
semantics: one delivers, the other queues for human review. A tenant may
configure both (auto-send for some campaigns, drafts for others) or
just one."""

from __future__ import annotations

from pydantic import BaseModel

# ---------------------------------------------------------------------------
# email.send_smtp
# ---------------------------------------------------------------------------


class SendEmailInput(BaseModel):
    to: str
    subject: str
    body: str
    list_unsubscribe: str | None = None


class SendEmailOutput(BaseModel):
    sent: bool = True


# ---------------------------------------------------------------------------
# email.create_draft
# ---------------------------------------------------------------------------


class CreateDraftInput(BaseModel):
    to: str
    subject: str
    body: str
    list_unsubscribe: str | None = None


class CreateDraftOutput(BaseModel):
    """``created=False`` is a soft failure (provider returned non-2xx).
    The orchestrator increments its error counter but continues with the
    next prospect — one failed webhook should not abort an entire run."""

    created: bool
    error: str | None = None
