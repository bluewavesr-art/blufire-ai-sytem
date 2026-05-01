"""Compliance-layer Tools: suppression check, send-cap check, send/consent
recording, footer rendering. Thin pydantic-typed wrappers around the
existing Phase 1 modules so an orchestrator can drive them by name."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from blufire.compliance.consent import ConsentLog
from blufire.compliance.footer import build_outreach_body
from blufire.compliance.send_caps import SendCapStore
from blufire.compliance.suppression import SuppressionList
from blufire.compliance.unsubscribe import UnsubscribeSigner
from blufire.runtime.context import RunContext
from blufire.runtime.tools._base import BaseTool

# ---------------------------------------------------------------------------
# compliance.check_suppression
# ---------------------------------------------------------------------------


class CheckSuppressionInput(BaseModel):
    email: str


class CheckSuppressionOutput(BaseModel):
    suppressed: bool
    reason: str | None = None


class CheckSuppressionTool(BaseTool[CheckSuppressionInput, CheckSuppressionOutput]):
    name = "compliance.check_suppression"
    description = "True if the recipient is on the tenant's suppression list."
    input_schema = CheckSuppressionInput
    output_schema = CheckSuppressionOutput

    def invoke(self, ctx: RunContext, payload: CheckSuppressionInput) -> CheckSuppressionOutput:
        s = ctx.tenant.settings
        store = SuppressionList(s.suppression_db_path, s.tenant.id)
        suppressed = store.is_suppressed(payload.email)
        return CheckSuppressionOutput(suppressed=suppressed, reason="dnc" if suppressed else None)


# ---------------------------------------------------------------------------
# compliance.check_send_cap
# ---------------------------------------------------------------------------


class CheckSendCapInput(BaseModel):
    email: str


class CheckSendCapOutput(BaseModel):
    allowed: bool
    reason: str | None = None


class CheckSendCapTool(BaseTool[CheckSendCapInput, CheckSendCapOutput]):
    name = "compliance.check_send_cap"
    description = "Enforces daily / per-domain / send-window caps for the tenant."
    input_schema = CheckSendCapInput
    output_schema = CheckSendCapOutput

    def invoke(self, ctx: RunContext, payload: CheckSendCapInput) -> CheckSendCapOutput:
        s = ctx.tenant.settings
        caps = SendCapStore(s.send_log_db_path, s.tenant.id, s.outreach)
        decision = caps.can_send(payload.email, tz_name=s.tenant.timezone)
        return CheckSendCapOutput(allowed=decision.allowed, reason=decision.reason)


# ---------------------------------------------------------------------------
# compliance.record_send
# ---------------------------------------------------------------------------


class RecordSendInput(BaseModel):
    email: str
    subject: str
    source: str


class RecordSendOutput(BaseModel):
    recorded: bool = True


class RecordSendTool(BaseTool[RecordSendInput, RecordSendOutput]):
    name = "compliance.record_send"
    description = "Persist a send event for cap enforcement (subject is hashed)."
    input_schema = RecordSendInput
    output_schema = RecordSendOutput

    def invoke(self, ctx: RunContext, payload: RecordSendInput) -> RecordSendOutput:
        s = ctx.tenant.settings
        caps = SendCapStore(s.send_log_db_path, s.tenant.id, s.outreach)
        caps.record_send(
            payload.email,
            subject=payload.subject,
            source=payload.source,
            tz_name=s.tenant.timezone,
        )
        return RecordSendOutput()


# ---------------------------------------------------------------------------
# compliance.record_consent
# ---------------------------------------------------------------------------


class RecordConsentInput(BaseModel):
    email: str
    basis: str
    source: str
    evidence: dict[str, Any] = Field(default_factory=dict)


class RecordConsentOutput(BaseModel):
    evidence_hash: str


class RecordConsentTool(BaseTool[RecordConsentInput, RecordConsentOutput]):
    name = "compliance.record_consent"
    description = "Append a consent record (evidence is sha256-hashed, not stored plaintext)."
    input_schema = RecordConsentInput
    output_schema = RecordConsentOutput

    def invoke(self, ctx: RunContext, payload: RecordConsentInput) -> RecordConsentOutput:
        s = ctx.tenant.settings
        log = ConsentLog(s.consent_log_db_path, s.tenant.id)
        rec = log.record(
            payload.email,
            basis=payload.basis,
            source=payload.source,
            evidence=payload.evidence,
        )
        return RecordConsentOutput(evidence_hash=rec.evidence_hash)


# ---------------------------------------------------------------------------
# compliance.build_footer
# ---------------------------------------------------------------------------


class BuildFooterInput(BaseModel):
    body: str
    recipient_email: str


class BuildFooterOutput(BaseModel):
    body_with_footer: str
    list_unsubscribe: str | None = None


class BuildFooterTool(BaseTool[BuildFooterInput, BuildFooterOutput]):
    name = "compliance.build_footer"
    description = "Append CAN-SPAM/CASL footer and produce the RFC 8058 List-Unsubscribe header."
    input_schema = BuildFooterInput
    output_schema = BuildFooterOutput

    def invoke(self, ctx: RunContext, payload: BuildFooterInput) -> BuildFooterOutput:
        s = ctx.tenant.settings
        signer = UnsubscribeSigner(s)
        body, list_unsub = build_outreach_body(
            payload.body, s, signer, recipient_email=payload.recipient_email
        )
        return BuildFooterOutput(body_with_footer=body, list_unsubscribe=list_unsub)
