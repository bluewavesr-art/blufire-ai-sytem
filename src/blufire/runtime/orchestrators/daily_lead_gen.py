"""Capability-driven runner for the daily_lead_gen agent.

Mirrors the Phase 1 logic in ``src/blufire/agents/daily_lead_gen.py`` but
routes every external call through the ToolRegistry. Differs from the
other Phase 2 orchestrators:

* The final delivery is a *draft* (``email.create_draft``) for human
  review, not a send. No SMTP. No List-Unsubscribe headers (those go
  on the actual outbound email, not on the draft preview).
* Multiple ``ProspectSearch`` configs run in sequence (different titles
  / locations / industries), with intra-run deduplication so the same
  prospect doesn't get drafted twice in a single run.

Compliance gating still applies — every draft passes through suppression,
send-caps, and consent recording before reaching the webhook.
"""

from __future__ import annotations

import time
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
)
from blufire.runtime.tools.crm import CreateContactInput, SearchContactsInput
from blufire.runtime.tools.email import CreateDraftInput
from blufire.runtime.tools.llm import DraftOutreachFromProspectInput
from blufire.runtime.tools.prospect import SearchPeopleInput
from blufire.settings import ProspectSearch

DRAFT_SOURCE = "daily-leadgen.draft.via-capability"

INTER_SEARCH_PAUSE_SEC = 1.0


def _required(registry: ToolRegistry, name: str) -> Tool[Any, Any]:
    tool = registry.get(name)
    if tool is None:
        raise CapabilityUnresolved(f"required tool not registered: {name}")
    return tool


def _hubspot_props_from_apollo(person: dict[str, Any]) -> dict[str, Any]:
    org = person.get("organization") or {}
    props: dict[str, Any] = {
        "firstname": person.get("first_name", ""),
        "lastname": person.get("last_name", ""),
        "email": person.get("email", ""),
        "company": org.get("name", ""),
        "jobtitle": person.get("title", ""),
        "city": person.get("city", ""),
        "state": person.get("state", ""),
        "lifecyclestage": "lead",
        "hs_lead_status": "NEW",
    }
    phones = person.get("phone_numbers") or []
    if phones and isinstance(phones[0], dict):
        sanitized = phones[0].get("sanitized_number")
        if sanitized:
            props["phone"] = sanitized
    return props


def run(
    ctx: RunContext,
    blueprint: AgentBlueprint,
    *,
    searches: list[ProspectSearch] | None = None,
    system_prompt: str | None = None,
    sleep_between_searches: float = INTER_SEARCH_PAUSE_SEC,
    registry: ToolRegistry | None = None,
) -> dict[str, int]:
    """Run the daily_lead_gen capability via the tool registry.

    Returns the same counter dict shape as the Phase 1 module so test
    suites can assert parity.
    """
    registry = registry or default_registry
    log = ctx.log.bind(via="capability", agent=blueprint.name)

    cap: Capability | None = next(
        (c for c in blueprint.capabilities if c.name == "daily_lead_gen.run"),
        None,
    )
    if cap is None:
        raise CapabilityUnresolved(
            f"blueprint {blueprint.name!r} does not declare daily_lead_gen.run"
        )
    tools = {name: _required(registry, name) for name in cap.tool_names}

    settings = ctx.tenant.settings
    searches = searches or list(settings.prospect_searches)

    counters: dict[str, int] = {
        "fetched": 0,
        "skipped_no_email": 0,
        "skipped_existing": 0,
        "skipped_suppressed": 0,
        "skipped_capped": 0,
        "drafted": 0,
        "errors": 0,
    }

    new_prospects: list[dict[str, Any]] = []
    seen_emails: set[str] = set()

    log.info("daily_leadgen_start", search_count=len(searches))

    # Phase 1: discovery + filter loop. We do NOT call the drafter or the
    # webhook here — drafting is expensive (Claude tokens) and we want to
    # apply every cheap filter (dedup, suppression, caps) first.
    for search in searches:
        search_out = tools["prospect.search_people"].invoke(
            ctx,
            SearchPeopleInput(
                person_titles=search.person_titles,
                keywords=search.keywords,
                locations=search.locations,
                industries=search.industries,
                max_results=search.per_page,
            ),
        )
        for person in search_out.people:
            counters["fetched"] += 1
            email = (person.email or "").strip().lower()
            if not email:
                counters["skipped_no_email"] += 1
                continue
            if email in seen_emails:
                continue
            seen_emails.add(email)

            rec_log = log.bind(recipient_hash=hash_recipient(email))

            existing = tools["crm.search_contacts"].invoke(ctx, SearchContactsInput(email=email))
            if existing.contacts:
                rec_log.info("skip_already_in_crm")
                counters["skipped_existing"] += 1
                continue

            sup = tools["compliance.check_suppression"].invoke(
                ctx, CheckSuppressionInput(email=email)
            )
            if sup.suppressed:
                rec_log.info("skip_suppressed")
                counters["skipped_suppressed"] += 1
                continue

            cap_out = tools["compliance.check_send_cap"].invoke(ctx, CheckSendCapInput(email=email))
            if not cap_out.allowed:
                rec_log.info("skip_capped", reason=cap_out.reason)
                counters["skipped_capped"] += 1
                continue

            new_prospects.append(person.raw)

        if sleep_between_searches > 0:
            time.sleep(sleep_between_searches)

    log.info("daily_leadgen_filtered", to_process=len(new_prospects), **counters)

    # Phase 2: per-survivor draft + webhook. Each iteration is independent;
    # a failure here only affects that one prospect.
    for person in new_prospects:
        email = (person.get("email") or "").strip().lower()
        rec_log = log.bind(recipient_hash=hash_recipient(email))

        # Best-effort CRM upsert. The dedup query above already proved this
        # email isn't in the CRM, but a 409 is still possible if a parallel
        # process raced us; treat that as already-existed and continue.
        create_out = tools["crm.create_contact"].invoke(
            ctx, CreateContactInput(properties=_hubspot_props_from_apollo(person))
        )
        if create_out.already_existed:
            rec_log.info("crm_contact_existed_at_create")

        try:
            draft = tools["llm.draft_outreach_email_from_prospect"].invoke(
                ctx,
                DraftOutreachFromProspectInput(person=person, system_prompt=system_prompt),
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
                basis=settings.compliance.legal_basis,
                source=DRAFT_SOURCE,
                evidence=person,
            ),
        )

        # Note: list_unsubscribe is intentionally NOT passed to create_draft.
        # The List-Unsubscribe header belongs on the outbound message that
        # the human eventually sends, not on the draft preview the webhook
        # shows them. The footer (which carries the unsubscribe link) is
        # already in the body.
        out = tools["email.create_draft"].invoke(
            ctx,
            CreateDraftInput(
                to=email,
                subject=draft.subject,
                body=footer_out.body_with_footer,
            ),
        )
        if out.created:
            counters["drafted"] += 1
        else:
            rec_log.warning("draft_webhook_failed", error_class=out.error)
            counters["errors"] += 1

    log.info("daily_leadgen_done", **counters)
    return counters
