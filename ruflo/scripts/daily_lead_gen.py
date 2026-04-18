#!/usr/bin/env python3
"""Blufire Ruflo Lead Gen Agent — Daily fresh prospect pipeline.

Apollo prospect search → Enrichment → HubSpot sync → Claude drafting → Gmail Drafts.
Runs daily via cron. Nothing sends without Steve's approval.
"""

import json
import time
import requests
import anthropic
from dotenv import load_dotenv
import os
from datetime import datetime

load_dotenv("/root/.env")

HUBSPOT_KEY = os.getenv("HUBSPOT_API_KEY")
ANTHROPIC_KEY = os.getenv("ANTHROPIC_API_KEY")
APOLLO_KEY = os.getenv("APOLLO_API_KEY")
DRAFT_WEBHOOK_URL = "https://hook.us2.make.com/5dmfd2o0fgtzr193adsylp6dzy1yri87"

# Target industries and titles for DFW contractors
PROSPECT_SEARCHES = [
    {
        "name": "Roofing Contractors DFW",
        "person_titles": ["Owner", "President", "CEO", "Founder", "General Manager"],
        "q_organization_keyword_tags": ["roofing"],
        "person_locations": ["Dallas, Texas, United States", "Fort Worth, Texas, United States"],
        "per_page": 10,
    },
    {
        "name": "Fencing Contractors DFW",
        "person_titles": ["Owner", "President", "CEO", "Founder", "General Manager"],
        "q_organization_keyword_tags": ["fencing", "fence"],
        "person_locations": ["Dallas, Texas, United States", "Fort Worth, Texas, United States"],
        "per_page": 10,
    },
    {
        "name": "HVAC Contractors DFW",
        "person_titles": ["Owner", "President", "CEO", "Founder", "General Manager"],
        "q_organization_keyword_tags": ["hvac", "heating", "air conditioning"],
        "person_locations": ["Dallas, Texas, United States", "Fort Worth, Texas, United States"],
        "per_page": 5,
    },
]

AGENT_SYSTEM_PROMPT = """You are the Blufire Email Outreach Agent. You write cold outreach emails for Steve Russell at Blufire Marketing.

STRICT RULES:
- NEVER use "Quick question" as a subject line. Ever.
- NEVER sound like a template or mass email.
- NEVER use "I came across", "I wanted to reach out", "hope this finds you well", "just reaching out", or "I'd love to".
- Write like Steve personally researched this person and their business.
- Reference specific details from the enrichment data: company size, revenue range, industry specifics, their role, years in business.
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


def search_apollo_prospects(search_config):
    """Search Apollo for fresh prospects."""
    try:
        r = requests.post(
            "https://api.apollo.io/v1/mixed_people/search",
            headers={"Content-Type": "application/json"},
            json={
                "api_key": APOLLO_KEY,
                "person_titles": search_config["person_titles"],
                "q_organization_keyword_tags": search_config.get("q_organization_keyword_tags", []),
                "person_locations": search_config.get("person_locations", []),
                "per_page": search_config.get("per_page", 10),
            },
            timeout=30,
        )
        if r.status_code == 200:
            return r.json().get("people", [])
        else:
            print(f"    Apollo search error: {r.status_code} — {r.text[:200]}")
    except Exception as e:
        print(f"    Apollo search error: {e}")
    return []


def check_hubspot_exists(email):
    """Check if contact already exists in HubSpot."""
    try:
        r = requests.post(
            "https://api.hubapi.com/crm/v3/objects/contacts/search",
            headers={
                "Authorization": f"Bearer {HUBSPOT_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "filterGroups": [
                    {"filters": [{"propertyName": "email", "operator": "EQ", "value": email}]}
                ],
                "limit": 1,
            },
            timeout=10,
        )
        if r.status_code == 200:
            return r.json().get("total", 0) > 0
    except Exception:
        pass
    return False


def create_hubspot_contact(person):
    """Create a new contact in HubSpot from Apollo data."""
    org = person.get("organization", {})
    properties = {
        "firstname": person.get("first_name", ""),
        "lastname": person.get("last_name", ""),
        "email": person.get("email", ""),
        "company": org.get("name", ""),
        "jobtitle": person.get("title", ""),
        "city": person.get("city", ""),
        "state": person.get("state", ""),
        "phone": "",
        "lifecyclestage": "lead",
        "hs_lead_status": "NEW",
    }
    phones = person.get("phone_numbers", [])
    if phones:
        properties["phone"] = phones[0].get("sanitized_number", "")

    try:
        r = requests.post(
            "https://api.hubapi.com/crm/v3/objects/contacts",
            headers={
                "Authorization": f"Bearer {HUBSPOT_KEY}",
                "Content-Type": "application/json",
            },
            json={"properties": properties},
            timeout=10,
        )
        if r.status_code in (200, 201):
            return r.json()
        elif r.status_code == 409:
            return None  # Already exists
    except Exception as e:
        print(f"    HubSpot create error: {e}")
    return None


def draft_email_with_claude(person):
    """Use Claude to craft a unique email using Apollo enrichment data."""
    org = person.get("organization", {})
    client = anthropic.Anthropic(api_key=ANTHROPIC_KEY)

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
    """Create a Gmail draft via Make.com webhook."""
    r = requests.post(
        DRAFT_WEBHOOK_URL,
        json={"to": to, "subject": subject, "body": body},
        timeout=15,
    )
    return r.status_code == 200


def main():
    today = datetime.now().strftime("%A, %B %d, %Y")
    print("=" * 60)
    print(f"  BLUFIRE RUFLO DAILY LEAD GEN — {today}")
    print("  Apollo Search → Enrich → HubSpot → Claude → Gmail Drafts")
    print("=" * 60)

    new_prospects = []

    # Step 1: Search Apollo for fresh prospects
    for search in PROSPECT_SEARCHES:
        print(f"\n  Searching: {search['name']}...")
        people = search_apollo_prospects(search)
        print(f"    Found {len(people)} results from Apollo")

        for person in people:
            email = person.get("email")
            if not email:
                continue

            name = f"{person.get('first_name', '')} {person.get('last_name', '')}".strip()
            company = person.get("organization", {}).get("name", "")

            # Skip if already in HubSpot
            if check_hubspot_exists(email):
                print(f"    SKIP (exists): {name} — {company}")
                continue

            new_prospects.append(person)
            print(f"    NEW: {name} — {company} ({person.get('title', '')})")

        time.sleep(1)

    print(f"\n{'=' * 60}")
    print(f"  {len(new_prospects)} new prospects to process")
    print(f"{'=' * 60}\n")

    if not new_prospects:
        print("  No new prospects found. Try expanding search criteria.")
        return

    drafted = 0
    failed = 0

    for person in new_prospects:
        email = person.get("email")
        name = f"{person.get('first_name', '')} {person.get('last_name', '')}".strip()
        company = person.get("organization", {}).get("name", "")

        print(f"  [{drafted + failed + 1}/{len(new_prospects)}] {name} ({company})")

        # Step 2: Add to HubSpot
        print(f"    Adding to HubSpot...", end=" ", flush=True)
        hs_contact = create_hubspot_contact(person)
        if hs_contact:
            print(f"OK — ID {hs_contact['id']}")
        else:
            print("Skipped (already exists or error)")

        # Step 3: Claude drafts the email
        print(f"    Drafting with Claude...", end=" ", flush=True)
        try:
            email_data = draft_email_with_claude(person)
            subject = email_data["subject"]
            body = email_data["body"]
            print(f"OK — \"{subject}\"")
        except Exception as e:
            print(f"ERROR: {e}")
            failed += 1
            continue

        # Step 4: Create Gmail draft
        print(f"    Creating Gmail draft...", end=" ", flush=True)
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
    print(f"  Check Gmail Drafts folder to review and send.")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
