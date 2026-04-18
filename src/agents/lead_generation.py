"""Lead Generation Agent — finds and enriches leads via Apollo, syncs to HubSpot."""

import requests
import anthropic
from src.utils.config import HUBSPOT_API_KEY, ANTHROPIC_API_KEY, APOLLO_API_KEY

HUBSPOT_BASE = "https://api.hubapi.com"
APOLLO_BASE = "https://api.apollo.io/v1"


def hubspot_headers():
    return {"Authorization": f"Bearer {HUBSPOT_API_KEY}", "Content-Type": "application/json"}


def search_apollo_leads(job_titles, location, industry, per_page=25):
    """Search Apollo for leads matching criteria."""
    resp = requests.post(
        f"{APOLLO_BASE}/mixed_people/search",
        json={
            "api_key": APOLLO_API_KEY,
            "person_titles": job_titles,
            "person_locations": [location] if location else [],
            "q_organization_industry_tag_ids": [industry] if industry else [],
            "per_page": per_page,
        },
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json().get("people", [])


def enrich_apollo_contact(email):
    """Enrich a single contact via Apollo."""
    resp = requests.post(
        f"{APOLLO_BASE}/people/match",
        json={"api_key": APOLLO_API_KEY, "email": email},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json().get("person", {})


def create_hubspot_contact(first_name, last_name, email, company, job_title, phone=None):
    """Create a contact in HubSpot CRM."""
    properties = {
        "firstname": first_name,
        "lastname": last_name,
        "email": email,
        "company": company,
        "jobtitle": job_title,
    }
    if phone:
        properties["phone"] = phone

    resp = requests.post(
        f"{HUBSPOT_BASE}/crm/v3/objects/contacts",
        headers=hubspot_headers(),
        json={"properties": properties},
        timeout=15,
    )
    if resp.status_code == 409:
        print(f"  [skip] Contact {email} already exists in HubSpot")
        return None
    resp.raise_for_status()
    return resp.json()


def score_lead(person):
    """Use Claude to score a lead's fit based on their profile."""
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    profile = (
        f"Name: {person.get('first_name')} {person.get('last_name')}\n"
        f"Title: {person.get('title')}\n"
        f"Company: {person.get('organization', {}).get('name', 'Unknown')}\n"
        f"Industry: {person.get('organization', {}).get('industry', 'Unknown')}\n"
        f"Company Size: {person.get('organization', {}).get('estimated_num_employees', 'Unknown')}\n"
        f"Location: {person.get('city')}, {person.get('state')}, {person.get('country')}"
    )
    msg = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=200,
        messages=[
            {
                "role": "user",
                "content": (
                    f"Score this lead 1-10 for a B2B SaaS sales outreach. "
                    f"Return ONLY a JSON object with 'score' (int) and 'reason' (one sentence).\n\n{profile}"
                ),
            }
        ],
    )
    return msg.content[0].text


def run(job_titles, location=None, industry=None, per_page=10):
    """Run the lead generation pipeline."""
    print(f"=== LEAD GENERATION AGENT ===")
    print(f"Searching Apollo for: {job_titles}")

    leads = search_apollo_leads(job_titles, location, industry, per_page)
    print(f"Found {len(leads)} leads")

    results = []
    for person in leads:
        email = person.get("email")
        if not email:
            continue

        print(f"\nProcessing: {person.get('first_name')} {person.get('last_name')} ({email})")

        # Score the lead
        score_result = score_lead(person)
        print(f"  Score: {score_result}")

        # Sync to HubSpot
        contact = create_hubspot_contact(
            first_name=person.get("first_name", ""),
            last_name=person.get("last_name", ""),
            email=email,
            company=person.get("organization", {}).get("name", ""),
            job_title=person.get("title", ""),
            phone=person.get("phone_numbers", [{}])[0].get("sanitized_number") if person.get("phone_numbers") else None,
        )
        if contact:
            print(f"  Synced to HubSpot: {contact['id']}")

        results.append({"person": person, "score": score_result, "hubspot_contact": contact})

    print(f"\n=== Processed {len(results)} leads ===")
    return results


if __name__ == "__main__":
    run(job_titles=["CEO", "CTO", "VP of Marketing"], location="United States", per_page=5)
