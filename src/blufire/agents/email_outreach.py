"""Email outreach agent — drafts personalized cold emails, gates them through
the compliance layer (suppression + send caps + footer), and either sends via
SMTP or hands off the draft to a webhook (Make.com, Gmail, etc.)."""

from __future__ import annotations

from typing import Any

from blufire.compliance.consent import ConsentLog
from blufire.compliance.footer import build_outreach_body
from blufire.compliance.send_caps import SendCapStore
from blufire.compliance.suppression import SuppressionList
from blufire.compliance.unsubscribe import UnsubscribeSigner
from blufire.integrations.hubspot import HubSpotClient
from blufire.integrations.smtp import EmailHeaders, SmtpSender
from blufire.llm import build_client, complete_json
from blufire.logging_setup import hash_recipient
from blufire.runtime.context import RunContext

DRAFT_SOURCE_LIVE = "outreach.live"
DRAFT_SOURCE_DRY_RUN = "outreach.dry-run"


def draft_email(
    ctx: RunContext,
    contact_props: dict[str, Any],
    *,
    campaign_context: str,
    system_prompt: str | None = None,
) -> dict[str, str]:
    """Ask Claude for ``{subject, body}``. Raises ``LLMOutputError`` on parse failure."""
    settings = ctx.tenant.settings
    client = build_client(settings)
    name = f"{contact_props.get('firstname', '')} {contact_props.get('lastname', '')}".strip()
    prompt = (
        f"Write a short, personalized cold outreach email (3-4 paragraphs max). "
        f"Be conversational, not salesy. No placeholder brackets.\n\n"
        f"Sender: {settings.sender.name}, {settings.sender.company}\n"
        f"Sender email: {settings.sender.email}\n\n"
        f"Recipient info:\n"
        f"- Name: {name}\n"
        f"- Company: {contact_props.get('company', 'their company')}\n"
        f"- Title: {contact_props.get('jobtitle', '')}\n\n"
        f"Campaign context: {campaign_context}\n\n"
        f"Return ONLY a JSON object with 'subject' and 'body' keys. "
        f"The body should be plain text with newlines."
    )
    payload = complete_json(
        client,
        model=settings.models.for_role("drafting"),
        prompt=prompt,
        max_tokens=600,
        system=system_prompt,
        temperature=0.8,
    )
    if not isinstance(payload, dict):
        raise ValueError(f"LLM returned non-object: {type(payload).__name__}")
    if "subject" not in payload or "body" not in payload:
        raise ValueError(f"LLM missing required keys: {sorted(payload)}")
    return {"subject": str(payload["subject"]), "body": str(payload["body"])}


def run(
    ctx: RunContext,
    *,
    campaign_context: str,
    limit: int = 10,
    dry_run: bool = False,
    system_prompt: str | None = None,
) -> dict[str, int]:
    log = ctx.log.bind(dry_run=dry_run)
    settings = ctx.tenant.settings

    hubspot = HubSpotClient(settings)
    sender = SmtpSender(settings) if not dry_run else None
    suppression = SuppressionList(settings.suppression_db_path, settings.tenant.id)
    caps = SendCapStore(settings.send_log_db_path, settings.tenant.id, settings.outreach)
    consent = ConsentLog(settings.consent_log_db_path, settings.tenant.id)
    signer = UnsubscribeSigner(settings)

    properties = ["firstname", "lastname", "email", "company", "jobtitle"]
    counters = {
        "sent": 0,
        "skipped_suppressed": 0,
        "skipped_capped": 0,
        "drafted_dry_run": 0,
        "skipped_no_email": 0,
        "errors": 0,
    }

    log.info("outreach_start", campaign=campaign_context[:80], limit=limit)

    for i, contact in enumerate(hubspot.iter_objects("contacts", properties)):
        if i >= limit:
            break

        props = contact.get("properties") or {}
        email = (props.get("email") or "").strip().lower()
        if not email:
            counters["skipped_no_email"] += 1
            continue

        recipient_log = log.bind(recipient_hash=hash_recipient(email))

        if suppression.is_suppressed(email):
            recipient_log.info("suppressed_skip", reason="dnc")
            counters["skipped_suppressed"] += 1
            continue

        if not dry_run:
            decision = caps.can_send(email, tz_name=settings.tenant.timezone)
            if not decision.allowed:
                recipient_log.info("cap_skip", reason=decision.reason)
                counters["skipped_capped"] += 1
                continue

        try:
            draft = draft_email(
                ctx,
                props,
                campaign_context=campaign_context,
                system_prompt=system_prompt,
            )
        except Exception as exc:
            recipient_log.warning("draft_failed", error_class=type(exc).__name__)
            counters["errors"] += 1
            continue

        body, list_unsub = build_outreach_body(
            draft["body"], settings, signer, recipient_email=email
        )
        consent.record(
            email,
            basis=settings.compliance.legal_basis,
            source=DRAFT_SOURCE_DRY_RUN if dry_run else DRAFT_SOURCE_LIVE,
            evidence={"contact_id": contact.get("id"), "campaign": campaign_context},
        )

        if dry_run:
            recipient_log.info("dry_run_draft", subject_len=len(draft["subject"]))
            counters["drafted_dry_run"] += 1
            continue

        assert sender is not None
        sender.send(
            to=email,
            subject=draft["subject"],
            body=body,
            headers=EmailHeaders(list_unsubscribe=list_unsub),
        )
        try:
            hubspot.log_email(contact["id"], draft["subject"], body)
        except Exception as exc:
            recipient_log.warning("hubspot_log_failed", error_class=type(exc).__name__)
        caps.record_send(
            email,
            subject=draft["subject"],
            source=DRAFT_SOURCE_LIVE,
            tz_name=settings.tenant.timezone,
        )
        counters["sent"] += 1

    log.info("outreach_done", **counters)
    return counters
