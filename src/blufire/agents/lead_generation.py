"""Lead Generation Agent — Apollo search → score → HubSpot sync."""

from __future__ import annotations

from typing import Any

from blufire.integrations.apollo import ApolloClient
from blufire.integrations.hubspot import HubSpotClient, HubSpotContactExists
from blufire.llm import build_client, complete_json
from blufire.runtime.context import RunContext

DEFAULT_LIMIT = 25


def _safe_phone(person: dict[str, Any]) -> str | None:
    phones = person.get("phone_numbers") or []
    if not phones:
        return None
    first = phones[0] if isinstance(phones[0], dict) else {}
    return first.get("sanitized_number")


def score_lead(ctx: RunContext, person: dict[str, Any]) -> dict[str, Any]:
    settings = ctx.tenant.settings
    client = build_client(settings)
    org = person.get("organization") or {}
    profile = (
        f"Name: {person.get('first_name')} {person.get('last_name')}\n"
        f"Title: {person.get('title')}\n"
        f"Company: {org.get('name', 'Unknown')}\n"
        f"Industry: {org.get('industry', 'Unknown')}\n"
        f"Company Size: {org.get('estimated_num_employees', 'Unknown')}\n"
        f"Location: {person.get('city')}, {person.get('state')}, {person.get('country')}"
    )
    prompt = (
        "Score this lead 1-10 for a B2B SaaS sales outreach. "
        "Return ONLY a JSON object with 'score' (int 1-10) and 'reason' (one sentence)."
        f"\n\n{profile}"
    )
    return complete_json(
        client,
        model=settings.models.for_role("scoring"),
        prompt=prompt,
        max_tokens=200,
        temperature=0.3,
    )


def run(
    ctx: RunContext,
    *,
    job_titles: list[str],
    location: str | None = None,
    industry: str | None = None,
    limit: int = DEFAULT_LIMIT,
) -> list[dict[str, Any]]:
    log = ctx.log
    settings = ctx.tenant.settings

    apollo = ApolloClient(settings)
    hubspot = HubSpotClient(settings)

    log.info("lead_gen_start", job_titles=job_titles, location=location, limit=limit)

    results: list[dict[str, Any]] = []
    seen = 0
    for person in apollo.search_people(
        person_titles=job_titles,
        locations=[location] if location else None,
        industries=[industry] if industry else None,
        max_results=limit,
    ):
        seen += 1
        email = person.get("email")
        if not email:
            log.debug("lead_gen_skip_no_email")
            continue

        try:
            score = score_lead(ctx, person)
        except Exception as exc:
            log.warning("lead_gen_score_failed", error=type(exc).__name__)
            score = {"score": 0, "reason": "score-failed"}

        try:
            contact = hubspot.create_contact(
                {
                    "firstname": person.get("first_name", ""),
                    "lastname": person.get("last_name", ""),
                    "email": email,
                    "company": (person.get("organization") or {}).get("name", ""),
                    "jobtitle": person.get("title", ""),
                    **({"phone": phone} if (phone := _safe_phone(person)) else {}),
                }
            )
            contact_id = contact.get("id")
        except HubSpotContactExists:
            log.info("lead_gen_contact_exists")
            contact_id = None

        results.append({"person": person, "score": score, "hubspot_contact_id": contact_id})

    log.info("lead_gen_done", processed=len(results), seen=seen)
    return results
