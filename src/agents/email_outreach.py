"""Email Outreach Agent — drafts personalized emails with Claude and sends via Gmail SMTP."""

import smtplib
import json
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

import requests
import anthropic
from src.utils.config import (
    HUBSPOT_API_KEY,
    ANTHROPIC_API_KEY,
    GMAIL_USER,
    GMAIL_APP_PASSWORD,
)

HUBSPOT_BASE = "https://api.hubapi.com"


def hubspot_headers():
    return {"Authorization": f"Bearer {HUBSPOT_API_KEY}", "Content-Type": "application/json"}


def get_hubspot_contacts(limit=10, properties=None):
    """Fetch contacts from HubSpot for outreach."""
    props = properties or ["firstname", "lastname", "email", "company", "jobtitle"]
    resp = requests.get(
        f"{HUBSPOT_BASE}/crm/v3/objects/contacts",
        headers=hubspot_headers(),
        params={"limit": limit, "properties": ",".join(props)},
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json().get("results", [])


def draft_email(contact_info, campaign_context):
    """Use Claude to draft a personalized outreach email."""
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    prompt = (
        f"Write a short, personalized cold outreach email (3-4 paragraphs max). "
        f"Be conversational, not salesy. No placeholder brackets.\n\n"
        f"Sender: Steve Russell, Bluewave Strategic Resources\n"
        f"Sender email: {GMAIL_USER}\n\n"
        f"Recipient info:\n"
        f"- Name: {contact_info.get('firstname', '')} {contact_info.get('lastname', '')}\n"
        f"- Company: {contact_info.get('company', 'their company')}\n"
        f"- Title: {contact_info.get('jobtitle', '')}\n\n"
        f"Campaign context: {campaign_context}\n\n"
        f"Return ONLY a JSON object with 'subject' and 'body' keys. "
        f"The body should be plain text with newlines."
    )

    msg = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=500,
        messages=[{"role": "user", "content": prompt}],
    )
    return msg.content[0].text


def send_email(to_email, subject, body):
    """Send an email via Gmail SMTP."""
    msg = MIMEMultipart()
    msg["From"] = GMAIL_USER
    msg["To"] = to_email
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=15) as server:
        server.login(GMAIL_USER, GMAIL_APP_PASSWORD)
        server.send_message(msg)

    print(f"  Sent to {to_email}")


def log_email_to_hubspot(contact_id, subject, body):
    """Log the sent email as an engagement in HubSpot."""
    resp = requests.post(
        f"{HUBSPOT_BASE}/crm/v3/objects/emails",
        headers=hubspot_headers(),
        json={
            "properties": {
                "hs_timestamp": str(int(__import__("time").time() * 1000)),
                "hs_email_direction": "EMAIL",
                "hs_email_subject": subject,
                "hs_email_text": body,
                "hs_email_status": "SENT",
            },
            "associations": [
                {
                    "to": {"id": contact_id},
                    "types": [{"associationCategory": "HUBSPOT_DEFINED", "associationTypeId": 198}],
                }
            ],
        },
        timeout=15,
    )
    if resp.status_code in (200, 201):
        print(f"  Logged in HubSpot for contact {contact_id}")
    else:
        print(f"  Warning: Failed to log in HubSpot ({resp.status_code})")


def run(campaign_context, limit=10, dry_run=False):
    """Run the email outreach pipeline."""
    print("=== EMAIL OUTREACH AGENT ===")
    print(f"Campaign: {campaign_context}")
    print(f"Mode: {'DRY RUN' if dry_run else 'LIVE'}\n")

    contacts = get_hubspot_contacts(limit=limit)
    print(f"Fetched {len(contacts)} contacts from HubSpot\n")

    sent_count = 0
    for contact in contacts:
        props = contact.get("properties", {})
        email = props.get("email")
        if not email:
            continue

        name = f"{props.get('firstname', '')} {props.get('lastname', '')}".strip()
        print(f"Drafting email for: {name} <{email}>")

        raw = draft_email(props, campaign_context)
        try:
            email_data = json.loads(raw)
        except json.JSONDecodeError:
            # Try to extract JSON from Claude's response
            start = raw.find("{")
            end = raw.rfind("}") + 1
            if start >= 0 and end > start:
                email_data = json.loads(raw[start:end])
            else:
                print(f"  [error] Could not parse email draft, skipping")
                continue

        subject = email_data["subject"]
        body = email_data["body"]
        print(f"  Subject: {subject}")

        if dry_run:
            print(f"  [dry run] Would send to {email}")
            print(f"  Preview:\n{body[:200]}...\n")
        else:
            send_email(email, subject, body)
            log_email_to_hubspot(contact["id"], subject, body)
            sent_count += 1

    print(f"\n=== Completed: {sent_count} emails {'drafted' if dry_run else 'sent'} ===")


if __name__ == "__main__":
    run(
        campaign_context="Introducing our AI-powered business solutions for growing companies",
        limit=5,
        dry_run=True,
    )
