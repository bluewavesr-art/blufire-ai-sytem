"""Capability-driven runner for the daily_lead_gen agent.

Mirrors the Phase 1 logic in ``src/blufire/agents/daily_lead_gen.py`` but
routes every external call through the ToolRegistry. Differs from the
other Phase 2 orchestrators in two important ways:

* **The final delivery is a draft for human review, not a send.** No
  SMTP. No List-Unsubscribe headers (those go on the actual outbound
  email, not on the draft preview).
* **Bifurcation by email availability.** Some prospect providers
  (Google Places) return businesses without a contact email. We attempt
  enrichment via ``enrich.find_email``; if that fails too, the lead is
  routed to a "Call List" sink (via ``crm.append_call_lead``) so the
  team can phone them instead of letting the lead fall on the floor.

Compliance gating still applies to every email path — every draft
passes through suppression, send-caps, and consent recording before
reaching the webhook.
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
from blufire.runtime.tools.crm import (
    AppendCallLeadInput,
    CreateContactInput,
    SearchContactsInput,
)
from blufire.runtime.tools.email import CreateDraftInput
from blufire.runtime.tools.enrich import FindEmailInput
from blufire.runtime.tools.llm import DraftOutreachFromProspectInput
from blufire.runtime.tools.prospect import PersonRecord, SearchPeopleInput
from blufire.settings import ProspectSearch

DRAFT_SOURCE = "daily-leadgen.draft.via-capability"

INTER_SEARCH_PAUSE_SEC = 1.0


def _required(registry: ToolRegistry, name: str) -> Tool[Any, Any]:
    tool = registry.get(name)
    if tool is None:
        raise CapabilityUnresolved(f"required tool not registered: {name}")
    return tool


def _person_props_for_crm(person: PersonRecord) -> dict[str, Any]:
    """Map a normalized PersonRecord into the CRM's create_contact properties.
    Provider-agnostic — no Apollo or Places specifics."""
    return {
        "email": person.email or "",
        "first_name": person.first_name or "",
        "last_name": person.last_name or "",
        "company": person.company or "",
        "title": person.title or "",
        "phone": person.phone or "",
        "address": person.address or "",
        "city": person.city or "",
        "state": person.state or "",
        "status": "new",
    }


def _talking_points(person: PersonRecord) -> str:
    """One-line opener hint for the call-list sheet. Deterministic — no
    LLM call. The team can always rewrite, but a starter line beats a
    blank cell."""
    bits = []
    if person.company:
        bits.append(person.company)
    if person.city or person.state:
        loc = ", ".join(p for p in [person.city, person.state] if p)
        bits.append(f"in {loc}")
    head = " ".join(bits) if bits else "this prospect"
    return (
        f"Storm-damage fence inspection / repair pitch for {head}. "
        "Free on-site assessment, fast quote, insurance-claim-friendly paperwork."
    )


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

    Returns a counter dict including the new ``routed_to_call_list`` and
    ``enriched_email_found`` counters alongside the legacy ones.
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
        "enriched_email_found": 0,
        "routed_to_call_list": 0,
        "skipped_unreachable": 0,  # no email AND no phone
        "skipped_existing": 0,
        "skipped_suppressed": 0,
        "skipped_capped": 0,
        "drafted": 0,
        "errors": 0,
    }

    # Phase 1: discovery. Collect normalized PersonRecords, dedup by
    # whatever identifier is available (email if present, else company+phone).
    discovered: list[PersonRecord] = []
    seen_keys: set[str] = set()

    log.info("daily_leadgen_start", search_count=len(searches))

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
            key = (person.email or f"{person.company or ''}|{person.phone or ''}").lower().strip()
            if not key or key == "|":
                # Truly empty record; nothing to do.
                counters["skipped_unreachable"] += 1
                continue
            if key in seen_keys:
                continue
            seen_keys.add(key)
            discovered.append(person)
        if sleep_between_searches > 0:
            time.sleep(sleep_between_searches)

    log.info("daily_leadgen_discovered", discovered=len(discovered))

    # Phase 2: per-prospect routing.
    for person in discovered:
        # Try enrichment if no email AND we have a website to scrape.
        if not person.email and person.website:
            try:
                enriched = tools["enrich.find_email"].invoke(
                    ctx, FindEmailInput(website_url=person.website)
                )
            except Exception as exc:
                log.warning(
                    "enrich_failed",
                    error_class=type(exc).__name__,
                    company=person.company,
                )
                enriched = None
            if enriched and enriched.email:
                counters["enriched_email_found"] += 1
                # Mutate the working copy — keep the rest of the record intact.
                person = person.model_copy(update={"email": enriched.email})

        # No email after enrichment → call-list path.
        if not person.email:
            if not person.phone:
                counters["skipped_unreachable"] += 1
                continue
            call_out = tools["crm.append_call_lead"].invoke(
                ctx,
                AppendCallLeadInput(
                    company=person.company,
                    phone=person.phone,
                    address=person.address,
                    city=person.city,
                    state=person.state,
                    website=person.website,
                    talking_points=_talking_points(person),
                ),
            )
            if call_out.appended:
                counters["routed_to_call_list"] += 1
            else:
                log.warning("call_list_append_failed", error_class=call_out.error)
                counters["errors"] += 1
            continue

        # Email path: dedup → suppression → cap → CRM upsert → draft → sink.
        email = person.email.strip().lower()
        rec_log = log.bind(recipient_hash=hash_recipient(email))

        existing = tools["crm.search_contacts"].invoke(ctx, SearchContactsInput(email=email))
        if existing.contacts:
            rec_log.info("skip_already_in_crm")
            counters["skipped_existing"] += 1
            continue

        sup = tools["compliance.check_suppression"].invoke(ctx, CheckSuppressionInput(email=email))
        if sup.suppressed:
            rec_log.info("skip_suppressed")
            counters["skipped_suppressed"] += 1
            continue

        cap_out = tools["compliance.check_send_cap"].invoke(ctx, CheckSendCapInput(email=email))
        if not cap_out.allowed:
            rec_log.info("skip_capped", reason=cap_out.reason)
            counters["skipped_capped"] += 1
            continue

        # Best-effort CRM upsert.
        create_out = tools["crm.create_contact"].invoke(
            ctx, CreateContactInput(properties=_person_props_for_crm(person))
        )
        if create_out.already_existed:
            rec_log.info("crm_contact_existed_at_create")

        try:
            draft = tools["llm.draft_outreach_email_from_prospect"].invoke(
                ctx,
                DraftOutreachFromProspectInput(person=person.raw, system_prompt=system_prompt),
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
                evidence=person.raw,
            ),
        )

        # Note: list_unsubscribe is intentionally NOT passed to create_draft.
        # The List-Unsubscribe header belongs on the outbound message the
        # human eventually sends, not on the draft preview the sink shows.
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
            rec_log.warning("draft_sink_failed", error_class=out.error)
            counters["errors"] += 1

    log.info("daily_leadgen_done", **counters)
    return counters
