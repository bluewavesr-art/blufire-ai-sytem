"""Capability-driven runner for the lead_generation agent.

Mirrors the Phase 1 logic in ``src/blufire/agents/lead_generation.py`` but
routes every external call through the ToolRegistry. The Phase 1 module
remains the production path; this orchestrator is the Phase 2 path that
proves the runtime contracts hold for a multi-step agent shape distinct
from email_outreach (no SMTP, no compliance gating, but external
prospect-search → LLM scoring → CRM dedup → CRM create).

Why CRM dedup happens here in Python (not in the LLM): we don't want the
scorer wasting tokens on prospects we already have in the CRM, and we
need an idempotent guarantee that re-runs of the same search don't
double-create contacts.
"""

from __future__ import annotations

from typing import Any

from blufire.runtime.capability import AgentBlueprint, Capability, CapabilityUnresolved
from blufire.runtime.context import RunContext
from blufire.runtime.tool import Tool, ToolRegistry, default_registry
from blufire.runtime.tools.crm import (
    CreateContactInput,
    SearchContactsInput,
)
from blufire.runtime.tools.llm import ScoreProspectInput
from blufire.runtime.tools.prospect import SearchPeopleInput


def _required(registry: ToolRegistry, name: str) -> Tool[Any, Any]:
    tool = registry.get(name)
    if tool is None:
        raise CapabilityUnresolved(f"required tool not registered: {name}")
    return tool


def _safe_phone(person: dict[str, Any]) -> str | None:
    phones = person.get("phone_numbers") or []
    if not phones:
        return None
    first = phones[0] if isinstance(phones[0], dict) else {}
    return first.get("sanitized_number")


def run(
    ctx: RunContext,
    blueprint: AgentBlueprint,
    *,
    job_titles: list[str],
    location: str | None = None,
    industry: str | None = None,
    limit: int = 25,
    score_threshold: int = 0,
    registry: ToolRegistry | None = None,
) -> dict[str, Any]:
    """Run the lead_generation capability via the tool registry.

    Returns ``{"results": [...], "counters": {...}}`` where each result
    carries the scored person + the resulting (or pre-existing) CRM
    contact id. ``score_threshold`` lets callers skip the CRM upsert
    for low-scoring prospects (default 0 = upsert everything that has
    an email).
    """
    registry = registry or default_registry
    log = ctx.log.bind(via="capability", agent=blueprint.name)

    cap: Capability | None = next(
        (c for c in blueprint.capabilities if c.name == "lead_generation.score_and_sync"),
        None,
    )
    if cap is None:
        raise CapabilityUnresolved(
            f"blueprint {blueprint.name!r} does not declare lead_generation.score_and_sync"
        )
    tools = {name: _required(registry, name) for name in cap.tool_names}

    counters: dict[str, int] = {
        "fetched": 0,
        "skipped_no_email": 0,
        "skipped_below_threshold": 0,
        "skipped_existing": 0,
        "created": 0,
        "score_failures": 0,
    }
    results: list[dict[str, Any]] = []

    log.info("lead_gen_start", job_titles=job_titles, location=location, limit=limit)

    search_out = tools["prospect.search_people"].invoke(
        ctx,
        SearchPeopleInput(
            person_titles=job_titles,
            locations=[location] if location else [],
            industries=[industry] if industry else [],
            max_results=limit,
        ),
    )

    for person in search_out.people:
        counters["fetched"] += 1
        if not person.email:
            counters["skipped_no_email"] += 1
            continue

        try:
            score_out = tools["llm.score_prospect"].invoke(
                ctx, ScoreProspectInput(person=person.raw)
            )
            score_payload = {"score": score_out.score, "reason": score_out.reason}
        except Exception as exc:
            log.warning("lead_gen_score_failed", error_class=type(exc).__name__)
            counters["score_failures"] += 1
            score_payload = {"score": 0, "reason": "score-failed"}

        if score_payload["score"] < score_threshold:
            counters["skipped_below_threshold"] += 1
            results.append(
                {"person": person.raw, "score": score_payload, "hubspot_contact_id": None}
            )
            continue

        # Dedup: skip the CRM create call entirely if we already have this
        # contact. The CRM may also enforce a unique-email constraint, but
        # checking here avoids burning create-quota on duplicates.
        existing = tools["crm.search_contacts"].invoke(ctx, SearchContactsInput(email=person.email))
        if existing.contacts:
            counters["skipped_existing"] += 1
            results.append(
                {
                    "person": person.raw,
                    "score": score_payload,
                    "hubspot_contact_id": existing.contacts[0].id,
                }
            )
            continue

        org = person.raw.get("organization") or {}
        properties: dict[str, Any] = {
            "firstname": person.first_name or "",
            "lastname": person.last_name or "",
            "email": person.email,
            "company": person.company or org.get("name", ""),
            "jobtitle": person.title or "",
        }
        phone = _safe_phone(person.raw)
        if phone:
            properties["phone"] = phone

        create_out = tools["crm.create_contact"].invoke(
            ctx, CreateContactInput(properties=properties)
        )
        if create_out.already_existed:
            counters["skipped_existing"] += 1
        elif create_out.contact_id:
            counters["created"] += 1
        results.append(
            {
                "person": person.raw,
                "score": score_payload,
                "hubspot_contact_id": create_out.contact_id,
            }
        )

    log.info("lead_gen_done", **counters)
    return {"results": results, "counters": counters}
