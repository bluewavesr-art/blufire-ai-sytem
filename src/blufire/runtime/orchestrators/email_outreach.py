"""Capability-driven runner for the email_outreach agent.

Mirrors the Phase 1 logic in ``src/blufire/agents/email_outreach.py`` but
routes every external call through the ToolRegistry. The Phase 1 module
remains the production code path for v1.0.0; this orchestrator is the
Phase 2 path that proves the runtime contracts end-to-end and forms the
seed for the broader swarm runtime.

Why the gating logic lives here (not in Claude / not in YAML):

* CAN-SPAM / RFC 8058 compliance is non-negotiable. We do NOT trust an
  LLM to gate sends through suppression / send-caps / consent / footer.
  Those tools are still called from deterministic Python.
* The win we DO get from the registry is replaceability: a tenant can
  swap the SMTP tool for a Mailgun tool, or the HubSpot tool for a
  Salesforce tool, without touching this orchestrator.
"""

from __future__ import annotations

from typing import Any

from blufire.logging_setup import hash_recipient
from blufire.runtime.capability import AgentBlueprint, Capability, CapabilityUnresolved
from blufire.runtime.context import RunContext
from blufire.runtime.tool import Tool, ToolRegistry, default_registry
from blufire.runtime.tools.compliance import (
    BuildFooterInput,
    CheckSendCapInput,
    CheckSuppressionInput,
    RecordConsentInput,
    RecordSendInput,
)
from blufire.runtime.tools.crm import ListContactsInput, LogEmailInput
from blufire.runtime.tools.email import SendEmailInput
from blufire.runtime.tools.llm import DraftOutreachEmailInput

DRAFT_SOURCE_LIVE = "outreach.live.via-capability"
DRAFT_SOURCE_DRY_RUN = "outreach.dry-run.via-capability"


def _required(registry: ToolRegistry, name: str) -> Tool[Any, Any]:
    tool = registry.get(name)
    if tool is None:
        raise CapabilityUnresolved(f"required tool not registered: {name}")
    return tool


def run(
    ctx: RunContext,
    blueprint: AgentBlueprint,
    *,
    campaign_context: str,
    limit: int = 10,
    dry_run: bool = False,
    system_prompt: str | None = None,
    registry: ToolRegistry | None = None,
) -> dict[str, int]:
    """Run the email_outreach capability via the tool registry.

    Returns the same counter dict shape as the Phase 1 ``agents.email_outreach.run``
    so test suites can assert parity.
    """
    registry = registry or default_registry
    log = ctx.log.bind(dry_run=dry_run, via="capability", agent=blueprint.name)

    # Resolve the email_outreach.send capability and verify all required
    # tools are registered. Raise eagerly on misconfiguration.
    cap: Capability | None = next(
        (c for c in blueprint.capabilities if c.name == "email_outreach.send"), None
    )
    if cap is None:
        raise CapabilityUnresolved(
            f"blueprint {blueprint.name!r} does not declare email_outreach.send"
        )
    tools = {name: _required(registry, name) for name in cap.tool_names}

    counters: dict[str, int] = {
        "sent": 0,
        "skipped_suppressed": 0,
        "skipped_capped": 0,
        "drafted_dry_run": 0,
        "skipped_no_email": 0,
        "errors": 0,
    }
    log.info("outreach_start", campaign=campaign_context[:80], limit=limit)

    contacts_out = tools["crm.list_contacts"].invoke(ctx, ListContactsInput(limit=limit))

    for contact in contacts_out.contacts:
        props = contact.properties
        email = (props.get("email") or "").strip().lower()
        if not email:
            counters["skipped_no_email"] += 1
            continue

        rec_log = log.bind(recipient_hash=hash_recipient(email))

        sup = tools["compliance.check_suppression"].invoke(ctx, CheckSuppressionInput(email=email))
        if sup.suppressed:
            rec_log.info("suppressed_skip", reason=sup.reason)
            counters["skipped_suppressed"] += 1
            continue

        if not dry_run:
            cap_out = tools["compliance.check_send_cap"].invoke(ctx, CheckSendCapInput(email=email))
            if not cap_out.allowed:
                rec_log.info("cap_skip", reason=cap_out.reason)
                counters["skipped_capped"] += 1
                continue

        try:
            draft = tools["llm.draft_outreach_email"].invoke(
                ctx,
                DraftOutreachEmailInput(
                    contact_props=props,
                    campaign_context=campaign_context,
                    system_prompt=system_prompt,
                ),
            )
        except Exception as exc:
            rec_log.warning("draft_failed", error_class=type(exc).__name__)
            counters["errors"] += 1
            continue

        footer_out = tools["compliance.build_footer"].invoke(
            ctx, BuildFooterInput(body=draft.body, recipient_email=email)
        )
        tools["compliance.record_consent"].invoke(
            ctx,
            RecordConsentInput(
                email=email,
                basis=ctx.tenant.settings.compliance.legal_basis,
                source=DRAFT_SOURCE_DRY_RUN if dry_run else DRAFT_SOURCE_LIVE,
                evidence={"contact_id": contact.id, "campaign": campaign_context},
            ),
        )

        if dry_run:
            rec_log.info("dry_run_draft", subject_len=len(draft.subject))
            counters["drafted_dry_run"] += 1
            continue

        tools["email.send_smtp"].invoke(
            ctx,
            SendEmailInput(
                to=email,
                subject=draft.subject,
                body=footer_out.body_with_footer,
                list_unsubscribe=footer_out.list_unsubscribe,
            ),
        )
        log_out = tools["crm.log_email"].invoke(
            ctx,
            LogEmailInput(
                contact_id=contact.id, subject=draft.subject, body=footer_out.body_with_footer
            ),
        )
        if not log_out.logged:
            rec_log.warning("hubspot_log_failed", error_class=log_out.error)
        tools["compliance.record_send"].invoke(
            ctx,
            RecordSendInput(email=email, subject=draft.subject, source=DRAFT_SOURCE_LIVE),
        )
        counters["sent"] += 1

    log.info("outreach_done", **counters)
    return counters
