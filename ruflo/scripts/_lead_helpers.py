"""Shared helpers for Blufire Apollo → HubSpot → Claude → Gmail lead-gen scripts.

Used by:
- daily_lead_gen.py (small DFW contractors)
- apollo_dfw_contractors.py (11–50 employee DFW trades w/ MarTech)
"""

import json
import os
import requests
import anthropic

HUBSPOT_BASE = "https://api.hubapi.com"
APOLLO_BASE = "https://api.apollo.io/v1"


def apollo_search_people(api_key, payload, timeout=30):
    """POST to Apollo mixed_people/search. Returns (people, organizations) lists.

    The org payload is returned alongside because Apollo embeds it on each person,
    but we may also need the standalone org list to inspect tech stack on Basic
    plans where the technology filter is silently ignored.
    """
    body = {"api_key": api_key, **payload}
    r = requests.post(
        f"{APOLLO_BASE}/mixed_people/search",
        headers={"Content-Type": "application/json"},
        json=body,
        timeout=timeout,
    )
    if r.status_code != 200:
        print(f"    Apollo error {r.status_code}: {r.text[:200]}")
        return [], []
    data = r.json()
    return data.get("people", []), data.get("organizations", [])


def hubspot_contact_exists(api_key, email):
    try:
        r = requests.post(
            f"{HUBSPOT_BASE}/crm/v3/objects/contacts/search",
            headers={
                "Authorization": f"Bearer {api_key}",
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


def hubspot_create_contact(api_key, properties):
    try:
        r = requests.post(
            f"{HUBSPOT_BASE}/crm/v3/objects/contacts",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={"properties": properties},
            timeout=10,
        )
        if r.status_code in (200, 201):
            return r.json()
        if r.status_code == 409:
            return None
        print(f"    HubSpot create error {r.status_code}: {r.text[:200]}")
    except Exception as e:
        print(f"    HubSpot create error: {e}")
    return None


def hubspot_ensure_property(api_key, name, label, group_name="contactinformation",
                            field_type="number", property_type="number"):
    """Idempotently create a custom contact property. Safe to call every run."""
    try:
        r = requests.get(
            f"{HUBSPOT_BASE}/crm/v3/properties/contacts/{name}",
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=10,
        )
        if r.status_code == 200:
            return True
        if r.status_code != 404:
            print(f"    HubSpot property check error {r.status_code}: {r.text[:200]}")
            return False
    except Exception as e:
        print(f"    HubSpot property check error: {e}")
        return False

    try:
        r = requests.post(
            f"{HUBSPOT_BASE}/crm/v3/properties/contacts",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "name": name,
                "label": label,
                "type": property_type,
                "fieldType": field_type,
                "groupName": group_name,
            },
            timeout=10,
        )
        if r.status_code in (200, 201):
            print(f"    Created HubSpot property: {name}")
            return True
        print(f"    HubSpot property create error {r.status_code}: {r.text[:200]}")
    except Exception as e:
        print(f"    HubSpot property create error: {e}")
    return False


def claude_draft_email(anthropic_key, system_prompt, prospect_info, model="claude-sonnet-4-20250514"):
    client = anthropic.Anthropic(api_key=anthropic_key)
    msg = client.messages.create(
        model=model,
        max_tokens=400,
        system=system_prompt,
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


def make_gmail_draft(webhook_url, to, subject, body, timeout=15):
    r = requests.post(
        webhook_url,
        json={"to": to, "subject": subject, "body": body},
        timeout=timeout,
    )
    return r.status_code == 200


def person_to_hubspot_properties(person, extra=None):
    """Map an Apollo person record to HubSpot contact properties."""
    org = person.get("organization", {}) or {}
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
    phones = person.get("phone_numbers", []) or []
    if phones:
        properties["phone"] = phones[0].get("sanitized_number", "") or ""
    if extra:
        properties.update(extra)
    return properties
