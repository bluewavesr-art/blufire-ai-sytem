#!/usr/bin/env python3
"""Blufire Ruflo Outreach Agent — Apollo enrichment + Claude drafting → Gmail Drafts for review."""

import json
import time
import requests
import anthropic
from dotenv import load_dotenv
import os

load_dotenv("/root/.env")

HUBSPOT_KEY = os.getenv("HUBSPOT_API_KEY")
ANTHROPIC_KEY = os.getenv("ANTHROPIC_API_KEY")
APOLLO_KEY = os.getenv("APOLLO_API_KEY")

# Creates Gmail DRAFTS — not sends. Steve reviews and sends manually.
DRAFT_WEBHOOK_URL = "https://hook.us2.make.com/5dmfd2o0fgtzr193adsylp6dzy1yri87"

SKIP_EMAILS = {
    "jane.doe.roofing.test2@example.com",
    "jane.doe.roofing.test@example.com",
    "test@test.com",
}

AGENT_SYSTEM_PROMPT = """You are the Blufire Email Outreach Agent. You write cold outreach emails for Steve Russell at Blufire Marketing.

STRICT RULES:
- NEVER use "Quick question" as a subject line. Ever.
- NEVER sound like a template or mass email.
- NEVER use "I came across", "I wanted to reach out", "hope this finds you well", "just reaching out", or "I'd love to".
- Write like Steve personally researched this person and their business.
- Reference specific details from the enrichment data: company size, revenue range, industry specifics, their role.
- Be direct about what Blufire does and why it matters to THEIR specific situation.
- Keep it under 100 words. Short paragraphs. No fluff.
- The ask: a 20-minute call this week.
- Sound like a peer who runs a business, not a salesperson.
- Each email must be genuinely unique — vary the structure, opening, and angle.
- Sign off as Steve Russell, Blufire Marketing, steve@blufiremarketing.com

ABOUT BLUFIRE:
Blufire Marketing helps contractors and local service businesses in the DFW area grow through:
- Google Business Profile optimization and management
- Local SEO that actually ranks
- AI-powered lead generation and outreach automation
- Website builds for contractors who need a real online presence
Steve has real results: clients getting 3-5x more leads within 90 days.

Return ONLY a JSON object with "subject" and "body" keys. The body should use <br> for line breaks. No markdown, no backticks, no explanation."""


def get_new_leads():
    """Fetch all NEW leads from HubSpot."""
    r = requests.post(
        "https://api.hubapi.com/crm/v3/objects/contacts/search",
        headers={
            "Authorization": f"Bearer {HUBSPOT_KEY}",
            "Content-Type": "application/json",
        },
        json={
            "filterGroups": [
                {
                    "filters": [
                        {"propertyName": "lifecyclestage", "operator": "EQ", "value": "lead"},
                        {"propertyName": "hs_lead_status", "operator": "EQ", "value": "NEW"},
                        {"propertyName": "email", "operator": "HAS_PROPERTY"},
                    ]
                }
            ],
            "properties": [
                "firstname", "lastname", "email", "company",
                "jobtitle", "city", "state", "phone",
            ],
            "limit": 100,
        },
        timeout=15,
    )
    r.raise_for_status()
    return r.json().get("results", [])


def enrich_with_apollo(email):
    """Enrich a contact using Apollo people match."""
    try:
        r = requests.post(
            "https://api.apollo.io/v1/people/match",
            json={"api_key": APOLLO_KEY, "email": email},
            timeout=15,
        )
        if r.status_code == 200:
            person = r.json().get("person", {})
            org = person.get("organization", {})
            return {
                "title": person.get("title", ""),
                "headline": person.get("headline", ""),
                "linkedin_url": person.get("linkedin_url", ""),
                "city": person.get("city", ""),
                "state": person.get("state", ""),
                "company_name": org.get("name", ""),
                "company_industry": org.get("industry", ""),
                "company_size": org.get("estimated_num_employees", ""),
                "company_revenue": org.get("annual_revenue_printed", ""),
                "company_description": org.get("short_description", ""),
                "company_website": org.get("website_url", ""),
                "company_founded": org.get("founded_year", ""),
                "company_city": org.get("city", ""),
                "company_state": org.get("state", ""),
            }
    except Exception as e:
        print(f"    Apollo error: {e}")
    return {}


def draft_email_with_claude(contact, enrichment):
    """Use Claude to craft a unique, personalized email using enriched data."""
    p = contact["properties"]
    client = anthropic.Anthropic(api_key=ANTHROPIC_KEY)

    prospect_info = (
        f"Name: {p.get('firstname', '')} {p.get('lastname', '')}\n"
        f"Email: {p.get('email', '')}\n"
        f"Company: {p.get('company', '')}\n"
        f"Title from HubSpot: {p.get('jobtitle', '')}\n"
        f"Location: {p.get('city', '')}, {p.get('state', '')}\n"
    )

    if enrichment:
        prospect_info += (
            f"\n--- APOLLO ENRICHMENT ---\n"
            f"Title: {enrichment.get('title', '')}\n"
            f"Headline: {enrichment.get('headline', '')}\n"
            f"Company: {enrichment.get('company_name', '')}\n"
            f"Industry: {enrichment.get('company_industry', '')}\n"
            f"Employees: {enrichment.get('company_size', '')}\n"
            f"Revenue: {enrichment.get('company_revenue', '')}\n"
            f"Description: {enrichment.get('company_description', '')}\n"
            f"Website: {enrichment.get('company_website', '')}\n"
            f"Founded: {enrichment.get('company_founded', '')}\n"
            f"HQ: {enrichment.get('company_city', '')}, {enrichment.get('company_state', '')}\n"
        )
    else:
        prospect_info += "\nNo enrichment data available — use HubSpot data only.\n"

    msg = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=400,
        system=AGENT_SYSTEM_PROMPT,
        messages=[
            {
                "role": "user",
                "content": f"Write a cold outreach email to this prospect asking for a 20-minute meeting:\n\n{prospect_info}",
            }
        ],
    )

    raw = msg.content[0].text
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        start = raw.find("{")
        end = raw.rfind("}") + 1
        if start >= 0 and end > start:
            return json.loads(raw[start:end])
        raise ValueError(f"Claude returned invalid JSON: {raw[:200]}")


def create_draft(to, subject, body):
    """Create a Gmail draft via Make.com webhook — does NOT send."""
    r = requests.post(
        DRAFT_WEBHOOK_URL,
        json={"to": to, "subject": subject, "body": body},
        timeout=15,
    )
    return r.status_code == 200


def main():
    print("=" * 60)
    print("  BLUFIRE RUFLO OUTREACH AGENT")
    print("  Apollo Enrichment → Claude Drafting → Gmail DRAFTS")
    print("  Nothing sends — Steve reviews and approves each one")
    print("=" * 60)

    leads = get_new_leads()
    real_leads = [
        c for c in leads
        if c["properties"].get("email") not in SKIP_EMAILS
        and c["properties"].get("company")
        and c["properties"].get("firstname")
    ]

    print(f"\nFound {len(real_leads)} NEW leads to process\n")

    drafted = 0
    failed = 0

    for contact in real_leads:
        p = contact["properties"]
        email = p["email"]
        name = f"{p.get('firstname', '')} {p.get('lastname', '')}".strip()
        company = p.get("company", "")

        print(f"  [{drafted + failed + 1}/{len(real_leads)}] {name} ({company})")

        # Step 1: Apollo enrichment
        print(f"    Enriching via Apollo...", end=" ", flush=True)
        enrichment = enrich_with_apollo(email)
        if enrichment and enrichment.get("company_name"):
            print(f"OK — {enrichment.get('company_industry', '?')}, {enrichment.get('company_size', '?')} employees")
        else:
            print("No data found — using HubSpot only")

        # Step 2: Claude drafts the email
        print(f"    Drafting with Claude...", end=" ", flush=True)
        try:
            email_data = draft_email_with_claude(contact, enrichment)
            subject = email_data["subject"]
            body = email_data["body"]
            print(f"OK — \"{subject}\"")
        except Exception as e:
            print(f"ERROR: {e}")
            failed += 1
            continue

        # Step 3: Create Gmail draft (NOT send)
        print(f"    Creating draft...", end=" ", flush=True)
        if create_draft(email, subject, body):
            print("DRAFT CREATED")
            drafted += 1
        else:
            print("FAILED")
            failed += 1

        time.sleep(2)
        print()

    print(f"{'=' * 60}")
    print(f"  DONE: {drafted} drafts created, {failed} failed")
    print(f"  Check your Gmail Drafts folder to review and send.")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
