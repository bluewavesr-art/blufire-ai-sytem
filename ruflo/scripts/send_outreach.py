#!/usr/bin/env python3
"""Blufire Ruflo Outreach Agent — AI-crafted personalized emails for each prospect."""

import json
import time
import requests
import anthropic
from dotenv import load_dotenv
import os

load_dotenv("/root/.env")

HUBSPOT_KEY = os.getenv("HUBSPOT_API_KEY")
ANTHROPIC_KEY = os.getenv("ANTHROPIC_API_KEY")
WEBHOOK_URL = "https://hook.us2.make.com/kg8xwq3y9biyfvex626484dti93g902h"
SKIP_EMAILS = {"jane.doe.roofing.test2@example.com", "jane.doe.roofing.test@example.com", "test@test.com"}

AGENT_SYSTEM_PROMPT = """You are the Blufire Email Outreach Agent. You write cold outreach emails for Steve Russell at Blufire Marketing.

RULES:
- NEVER use "Quick question" as a subject line. Ever.
- NEVER sound like a template or mass email.
- Write like a real person who actually looked at their business.
- Be direct about what you do and why it matters to THEM specifically.
- Reference something specific about their company, industry, or role.
- Keep it under 100 words. Short paragraphs.
- The ask: a 20-minute call this week.
- No buzzwords, no hype, no "I'd love to", no "just reaching out", no "hope this finds you well".
- Sound like a peer, not a salesperson.
- Sign off as Steve Russell, Blufire Marketing.

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
        headers={"Authorization": f"Bearer {HUBSPOT_KEY}", "Content-Type": "application/json"},
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
            "properties": ["firstname", "lastname", "email", "company", "jobtitle", "city", "state"],
            "limit": 100,
        },
        timeout=15,
    )
    r.raise_for_status()
    return r.json().get("results", [])


def update_lead_status(contact_id):
    """Mark contact as IN_PROGRESS in HubSpot."""
    requests.patch(
        f"https://api.hubapi.com/crm/v3/objects/contacts/{contact_id}",
        headers={"Authorization": f"Bearer {HUBSPOT_KEY}", "Content-Type": "application/json"},
        json={"properties": {"hs_lead_status": "IN_PROGRESS"}},
        timeout=10,
    )


def draft_email_with_claude(contact):
    """Use Claude to craft a unique, personalized email for this prospect."""
    p = contact["properties"]
    client = anthropic.Anthropic(api_key=ANTHROPIC_KEY)

    prospect_info = (
        f"Name: {p.get('firstname', '')} {p.get('lastname', '')}\n"
        f"Company: {p.get('company', '')}\n"
        f"Title: {p.get('jobtitle', '')}\n"
        f"City: {p.get('city', '')}\n"
        f"State: {p.get('state', '')}"
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


def send_email(to, subject, body):
    """Send via Make.com Blufire Email Sender webhook."""
    r = requests.post(
        WEBHOOK_URL,
        json={"to": to, "subject": subject, "body": body},
        timeout=15,
    )
    return r.status_code == 200


def main():
    print("=" * 60)
    print("  BLUFIRE RUFLO OUTREACH AGENT")
    print("  Each email crafted by Claude AI — no templates")
    print("=" * 60)

    leads = get_new_leads()
    real_leads = [
        c for c in leads
        if c["properties"].get("email") not in SKIP_EMAILS
        and c["properties"].get("company")
        and c["properties"].get("firstname")
    ]

    print(f"\nFound {len(real_leads)} NEW leads to contact\n")

    sent = 0
    failed = 0

    for contact in real_leads:
        p = contact["properties"]
        email = p["email"]
        name = f"{p.get('firstname', '')} {p.get('lastname', '')}".strip()
        company = p.get("company", "")

        print(f"  Drafting for {name} ({company})...", end=" ", flush=True)

        try:
            email_data = draft_email_with_claude(contact)
            subject = email_data["subject"]
            body = email_data["body"]

            if send_email(email, subject, body):
                update_lead_status(contact["id"])
                print(f"SENT — \"{subject}\"")
                sent += 1
            else:
                print("SEND FAILED")
                failed += 1
        except Exception as e:
            print(f"ERROR: {e}")
            failed += 1

        time.sleep(2)  # Rate limit for API + webhook

    print(f"\n{'=' * 60}")
    print(f"  DONE: {sent} sent, {failed} failed")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
