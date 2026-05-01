"""Daily lead-gen pipeline: Apollo search → HubSpot dedup → Claude draft → Gmail draft webhook.

Compliance-gated: every prospect is checked against the suppression list and
the daily/per-domain caps before any draft is created.
"""

from __future__ import annotations

import time
from datetime import datetime
from typing import Any

import requests

from blufire.compliance.consent import ConsentLog
from blufire.compliance.footer import build_outreach_body
from blufire.compliance.send_caps import SendCapStore
from blufire.compliance.suppression import SuppressionList
from blufire.compliance.unsubscribe import UnsubscribeSigner
from blufire.http import build_session, retry_external
from blufire.integrations.apollo import ApolloClient
from blufire.integrations.hubspot import HubSpotClient, HubSpotContactExists
from blufire.llm import build_client, complete_json
from blufire.logging_setup import hash_recipient
from blufire.runtime.context import RunContext
from blufire.settings import ProspectSearch

DRAFT_SOURCE = "daily-leadgen.draft"

DEFAULT_SYSTEM_PROMPT = """You are a B2B email outreach agent.

STRICT RULES:
- NEVER use "Quick question" as a subject line.
- NEVER sound like a template. Be specific.
- NEVER use clichés like "I came across", "I wanted to reach out",
  "hope this finds you well", "just reaching out".
- Reference specific details from the enrichment data: company size, revenue, industry, role.
- Be direct about what your service does and why it matters to THEIR situation.
- Keep it under 100 words. Short paragraphs. No fluff.
- The ask: a 20-minute call this week.
- Sound like a peer, not a salesperson.
- Each email must be genuinely unique.

Return ONLY a JSON object with "subject" and "body" keys.
The body must be plain text with newlines between paragraphs.
"""


def _load_system_prompt(ctx: RunContext) -> str:
    path = ctx.tenant.settings.outreach.system_prompt_path
    if path and path.is_file():
        return path.read_text(encoding="utf-8")
    return DEFAULT_SYSTEM_PROMPT


def _hubspot_has_email(hubspot: HubSpotClient, email: str) -> bool:
    rows = hubspot.search(
        "contacts",
        filters=[{"propertyName": "email", "operator": "EQ", "value": email}],
        properties=["email"],
        limit=1,
    )
    return bool(rows)


def _draft_with_claude(
    ctx: RunContext, person: dict[str, Any], system_prompt: str
) -> dict[str, str]:
    settings = ctx.tenant.settings
    client = build_client(settings)
    org = person.get("organization") or {}
    prospect_info = (
        f"Name: {person.get('first_name', '')} {person.get('last_name', '')}\n"
        f"Email: {person.get('email', '')}\n"
        f"Title: {person.get('title', '')}\n"
        f"Headline: {person.get('headline', '')}\n"
        f"City: {person.get('city', '')}, {person.get('state', '')}\n"
        f"LinkedIn: {person.get('linkedin_url', '')}\n"
        f"\n--- COMPANY ---\n"
        f"Company: {org.get('name', '')}\n"
        f"Industry: {org.get('industry', '')}\n"
        f"Employees: {org.get('estimated_num_employees', '')}\n"
        f"Revenue: {org.get('annual_revenue_printed', '')}\n"
        f"Description: {org.get('short_description', '')}\n"
        f"Website: {org.get('website_url', '')}\n"
        f"Founded: {org.get('founded_year', '')}\n"
        f"HQ: {org.get('city', '')}, {org.get('state', '')}\n"
    )
    payload = complete_json(
        client,
        model=settings.models.for_role("drafting"),
        prompt=(
            "Write a cold outreach email to this prospect asking for a 20-minute meeting:"
            f"\n\n{prospect_info}"
        ),
        system=system_prompt,
        max_tokens=500,
        temperature=0.85,
    )
    if not isinstance(payload, dict) or "subject" not in payload or "body" not in payload:
        raise ValueError(f"LLM draft missing required keys: {payload!r}")
    return {"subject": str(payload["subject"]), "body": str(payload["body"])}


@retry_external()
def _post_draft(session: requests.Session, url: str, payload: dict[str, Any]) -> bool:
    resp = session.post(url, json=payload, timeout=(5, 30))
    return resp.status_code in (200, 201, 202, 204)


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


def run(ctx: RunContext, searches: list[ProspectSearch] | None = None) -> dict[str, int]:
    log = ctx.log
    settings = ctx.tenant.settings

    apollo = ApolloClient(settings)
    hubspot = HubSpotClient(settings)
    suppression = SuppressionList(settings.suppression_db_path, settings.tenant.id)
    caps = SendCapStore(settings.send_log_db_path, settings.tenant.id, settings.outreach)
    consent = ConsentLog(settings.consent_log_db_path, settings.tenant.id)
    signer = UnsubscribeSigner(settings)
    session = build_session()

    webhook_url = (
        str(settings.outreach.webhook.gmail_draft_url)
        if settings.outreach.webhook.gmail_draft_url
        else None
    )
    if not webhook_url:
        raise RuntimeError(
            "outreach.webhook.gmail_draft_url is not configured. "
            "Set MAKE_DRAFT_WEBHOOK_URL or outreach.webhook.gmail_draft_url."
        )

    system_prompt = _load_system_prompt(ctx)
    today = datetime.now(tz=None).date().isoformat()
    log.info(
        "daily_leadgen_start",
        date=today,
        searches=len(searches or settings.prospect_searches),
    )

    counters = {
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

    for search in searches or settings.prospect_searches:
        for person in apollo.search_people(
            person_titles=search.person_titles or None,
            keywords=search.keywords or None,
            locations=search.locations or None,
            industries=search.industries or None,
            page_size=search.per_page,
            max_results=search.per_page,
        ):
            counters["fetched"] += 1
            email = (person.get("email") or "").strip().lower()
            if not email:
                counters["skipped_no_email"] += 1
                continue
            if email in seen_emails:
                continue
            seen_emails.add(email)

            recipient_log = log.bind(recipient_hash=hash_recipient(email))

            if _hubspot_has_email(hubspot, email):
                recipient_log.info("skip_already_in_hubspot")
                counters["skipped_existing"] += 1
                continue

            if suppression.is_suppressed(email):
                recipient_log.info("skip_suppressed")
                counters["skipped_suppressed"] += 1
                continue

            decision = caps.can_send(email, tz_name=settings.tenant.timezone)
            if not decision.allowed:
                recipient_log.info("skip_capped", reason=decision.reason)
                counters["skipped_capped"] += 1
                continue

            new_prospects.append(person)
        time.sleep(1)  # gentle pause between searches

    log.info("daily_leadgen_filtered", to_process=len(new_prospects), **counters)

    for person in new_prospects:
        email = (person.get("email") or "").strip().lower()
        recipient_log = log.bind(recipient_hash=hash_recipient(email))

        try:
            hubspot.create_contact(_hubspot_props_from_apollo(person))
        except HubSpotContactExists:
            recipient_log.info("hubspot_contact_exists")

        try:
            draft = _draft_with_claude(ctx, person, system_prompt)
        except Exception as exc:
            recipient_log.warning("draft_failed", error_class=type(exc).__name__)
            counters["errors"] += 1
            continue

        body, _ = build_outreach_body(draft["body"], settings, signer, recipient_email=email)
        consent.record(
            email,
            basis=settings.compliance.legal_basis,
            source=DRAFT_SOURCE,
            evidence=person,
        )

        try:
            ok = _post_draft(
                session,
                webhook_url,
                {"to": email, "subject": draft["subject"], "body": body},
            )
        except Exception as exc:
            recipient_log.warning("draft_webhook_failed", error_class=type(exc).__name__)
            counters["errors"] += 1
            continue

        if ok:
            counters["drafted"] += 1
        else:
            counters["errors"] += 1

    log.info("daily_leadgen_done", **counters)
    return counters
