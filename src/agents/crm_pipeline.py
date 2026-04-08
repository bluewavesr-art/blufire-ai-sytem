"""CRM Pipeline Agent — manages HubSpot deals, tracks follow-ups, updates pipeline stages."""

import json
import time

import requests
import anthropic
from src.utils.config import HUBSPOT_API_KEY, ANTHROPIC_API_KEY

HUBSPOT_BASE = "https://api.hubapi.com"


def hubspot_headers():
    return {"Authorization": f"Bearer {HUBSPOT_API_KEY}", "Content-Type": "application/json"}


def get_deals(limit=50, properties=None):
    """Fetch deals from HubSpot pipeline."""
    props = properties or [
        "dealname", "dealstage", "amount", "closedate",
        "pipeline", "hubspot_owner_id", "hs_lastmodifieddate",
    ]
    resp = requests.get(
        f"{HUBSPOT_BASE}/crm/v3/objects/deals",
        headers=hubspot_headers(),
        params={"limit": limit, "properties": ",".join(props)},
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json().get("results", [])


def get_deal_contacts(deal_id):
    """Get contacts associated with a deal."""
    resp = requests.get(
        f"{HUBSPOT_BASE}/crm/v4/objects/deals/{deal_id}/associations/contacts",
        headers=hubspot_headers(),
        timeout=15,
    )
    if resp.status_code == 200:
        return resp.json().get("results", [])
    return []


def get_contact(contact_id):
    """Get contact details by ID."""
    resp = requests.get(
        f"{HUBSPOT_BASE}/crm/v3/objects/contacts/{contact_id}",
        headers=hubspot_headers(),
        params={"properties": "firstname,lastname,email,company,jobtitle"},
        timeout=15,
    )
    if resp.status_code == 200:
        return resp.json()
    return None


def update_deal(deal_id, properties):
    """Update deal properties in HubSpot."""
    resp = requests.patch(
        f"{HUBSPOT_BASE}/crm/v3/objects/deals/{deal_id}",
        headers=hubspot_headers(),
        json={"properties": properties},
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()


def create_deal(dealname, stage, amount=None, contact_id=None):
    """Create a new deal in HubSpot."""
    properties = {"dealname": dealname, "dealstage": stage}
    if amount:
        properties["amount"] = str(amount)

    payload = {"properties": properties}
    if contact_id:
        payload["associations"] = [
            {
                "to": {"id": contact_id},
                "types": [{"associationCategory": "HUBSPOT_DEFINED", "associationTypeId": 3}],
            }
        ]

    resp = requests.post(
        f"{HUBSPOT_BASE}/crm/v3/objects/deals",
        headers=hubspot_headers(),
        json=payload,
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()


def create_task(title, contact_id=None, due_days=3):
    """Create a follow-up task in HubSpot."""
    due_timestamp = str(int((time.time() + due_days * 86400) * 1000))
    payload = {
        "properties": {
            "hs_task_subject": title,
            "hs_task_status": "NOT_STARTED",
            "hs_task_priority": "MEDIUM",
            "hs_timestamp": due_timestamp,
        },
    }
    if contact_id:
        payload["associations"] = [
            {
                "to": {"id": contact_id},
                "types": [{"associationCategory": "HUBSPOT_DEFINED", "associationTypeId": 204}],
            }
        ]

    resp = requests.post(
        f"{HUBSPOT_BASE}/crm/v3/objects/tasks",
        headers=hubspot_headers(),
        json=payload,
        timeout=15,
    )
    if resp.status_code in (200, 201):
        return resp.json()
    print(f"  Warning: Failed to create task ({resp.status_code})")
    return None


def analyze_pipeline(deals):
    """Use Claude to analyze the pipeline and recommend actions."""
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    deal_summaries = []
    for deal in deals[:20]:
        props = deal.get("properties", {})
        deal_summaries.append(
            f"- {props.get('dealname', 'Unnamed')}: "
            f"stage={props.get('dealstage', '?')}, "
            f"amount=${props.get('amount', '0')}, "
            f"close={props.get('closedate', 'none')}, "
            f"last_modified={props.get('hs_lastmodifieddate', '?')}"
        )

    pipeline_text = "\n".join(deal_summaries) if deal_summaries else "No deals found."

    msg = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=800,
        messages=[
            {
                "role": "user",
                "content": (
                    f"Analyze this sales pipeline and provide actionable recommendations. "
                    f"Identify stale deals, suggest stage changes, and flag follow-ups needed.\n\n"
                    f"Pipeline:\n{pipeline_text}\n\n"
                    f"Return a JSON object with:\n"
                    f"- 'summary': one paragraph overview\n"
                    f"- 'actions': list of objects with 'deal_name', 'action', 'reason'"
                ),
            }
        ],
    )
    return msg.content[0].text


def run(auto_tasks=False):
    """Run the CRM pipeline management agent."""
    print("=== CRM PIPELINE AGENT ===\n")

    # Fetch deals
    deals = get_deals(limit=50)
    print(f"Found {len(deals)} deals in pipeline\n")

    if not deals:
        print("No deals found. Create deals first via Lead Generation Agent.")
        return

    # Analyze pipeline with Claude
    print("Analyzing pipeline with AI...\n")
    analysis_raw = analyze_pipeline(deals)

    try:
        analysis = json.loads(analysis_raw)
    except json.JSONDecodeError:
        start = analysis_raw.find("{")
        end = analysis_raw.rfind("}") + 1
        if start >= 0 and end > start:
            analysis = json.loads(analysis_raw[start:end])
        else:
            print(f"Analysis:\n{analysis_raw}")
            return

    print(f"Summary: {analysis.get('summary', 'N/A')}\n")

    actions = analysis.get("actions", [])
    print(f"Recommended actions ({len(actions)}):")
    for action in actions:
        print(f"  - {action.get('deal_name')}: {action.get('action')} ({action.get('reason')})")

    # Auto-create follow-up tasks if enabled
    if auto_tasks and actions:
        print("\nCreating follow-up tasks...")
        for action in actions:
            task = create_task(
                title=f"[Blufire] {action.get('action', 'Follow up')} - {action.get('deal_name', '')}",
            )
            if task:
                print(f"  Created task: {task['id']}")

    print("\n=== Pipeline analysis complete ===")


if __name__ == "__main__":
    run(auto_tasks=False)
