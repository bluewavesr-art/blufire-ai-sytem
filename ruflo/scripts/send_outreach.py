#!/usr/bin/env python3
"""Blufire Outreach — Send personalized 20-min meeting request emails to NEW HubSpot leads."""

import json
import time
import requests
from dotenv import load_dotenv
import os

load_dotenv("/root/.env")

HUBSPOT_KEY = os.getenv("HUBSPOT_API_KEY")
WEBHOOK_URL = "https://hook.us2.make.com/kg8xwq3y9biyfvex626484dti93g902h"
SKIP_EMAILS = {"jane.doe.roofing.test2@example.com", "jane.doe.roofing.test@example.com", "test@test.com"}


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
            "properties": ["firstname", "lastname", "email", "company", "jobtitle"],
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


def detect_business_type(company):
    lower = company.lower()
    if "roof" in lower:
        return "roofing"
    elif "fence" in lower or "fencing" in lower:
        return "fencing"
    elif "air" in lower or "heating" in lower or "hvac" in lower or "joplin" in lower:
        return "HVAC"
    elif "electric" in lower:
        return "electrical"
    return "contracting"


def draft_email(contact):
    p = contact["properties"]
    firstname = p.get("firstname", "there")
    company = p.get("company", "your company")
    biz_type = detect_business_type(company)

    subject = f"Quick question for {company}"
    body = (
        f"Hi {firstname},<br><br>"
        f"I came across {company} and wanted to reach out directly. "
        f"We work with {biz_type} companies in the DFW area to help them "
        f"get more leads through Google Business Profile optimization, "
        f"SEO, and AI-powered outreach.<br><br>"
        f"Would you be open to a quick 20-minute call this week? "
        f"No pitch deck, no pressure — just a conversation to see if "
        f"there's a fit.<br><br>"
        f"Either way, I appreciate your time.<br><br>"
        f"Steve Russell<br>"
        f"Blufire Marketing<br>"
        f"steve@blufiremarketing.com"
    )
    return subject, body


def send_email(to, subject, body):
    """Send via Make.com Blufire Email Sender webhook."""
    r = requests.post(
        WEBHOOK_URL,
        json={"to": to, "subject": subject, "body": body},
        timeout=15,
    )
    return r.status_code == 200


def main():
    print("=" * 50)
    print("  BLUFIRE OUTREACH — 20-Minute Meeting Request")
    print("=" * 50)

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

        subject, body = draft_email(contact)

        if send_email(email, subject, body):
            update_lead_status(contact["id"])
            print(f"  SENT: {name} <{email}>")
            sent += 1
        else:
            print(f"  FAIL: {name} <{email}>")
            failed += 1

        time.sleep(1)

    print(f"\n{'=' * 50}")
    print(f"  DONE: {sent} sent, {failed} failed")
    print(f"{'=' * 50}")


if __name__ == "__main__":
    main()
