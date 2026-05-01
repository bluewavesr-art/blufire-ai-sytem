"""CRM Pipeline Agent — analyzes HubSpot deals and proposes follow-up tasks."""

from __future__ import annotations

from typing import Any

from blufire.integrations.hubspot import HubSpotClient, HubSpotTaskError
from blufire.llm import build_client, complete_json
from blufire.runtime.context import RunContext

DEAL_PROPS = [
    "dealname",
    "dealstage",
    "amount",
    "closedate",
    "pipeline",
    "hubspot_owner_id",
    "hs_lastmodifieddate",
]
MAX_DEALS_FOR_ANALYSIS = 50


def analyze_pipeline(ctx: RunContext, deals: list[dict[str, Any]]) -> dict[str, Any]:
    settings = ctx.tenant.settings
    client = build_client(settings)

    summaries = []
    for deal in deals[:20]:
        props = deal.get("properties") or {}
        summaries.append(
            f"- {props.get('dealname', 'Unnamed')}: "
            f"stage={props.get('dealstage', '?')}, "
            f"amount=${props.get('amount', '0')}, "
            f"close={props.get('closedate', 'none')}, "
            f"last_modified={props.get('hs_lastmodifieddate', '?')}"
        )
    pipeline_text = "\n".join(summaries) if summaries else "No deals found."

    prompt = (
        "Analyze this sales pipeline and provide actionable recommendations. "
        "Identify stale deals, suggest stage changes, and flag follow-ups needed.\n\n"
        f"Pipeline:\n{pipeline_text}\n\n"
        "Return a JSON object with:\n"
        "- 'summary': one-paragraph overview\n"
        "- 'actions': list of objects with 'deal_name', 'action', 'reason'"
    )
    payload = complete_json(
        client,
        model=settings.models.for_role("default"),
        prompt=prompt,
        max_tokens=1200,
        temperature=0.4,
    )
    if not isinstance(payload, dict):
        raise ValueError(f"analysis returned non-object: {type(payload).__name__}")
    return payload


def _validate_actions(raw: Any) -> list[dict[str, str]]:
    if not isinstance(raw, list):
        return []
    actions = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        deal_name = item.get("deal_name")
        action = item.get("action")
        reason = item.get("reason", "")
        if not deal_name or not action:
            continue
        actions.append({"deal_name": str(deal_name), "action": str(action), "reason": str(reason)})
    return actions


def run(ctx: RunContext, *, auto_tasks: bool = False) -> dict[str, Any]:
    log = ctx.log
    settings = ctx.tenant.settings
    hubspot = HubSpotClient(settings)

    deals = []
    for deal in hubspot.iter_objects("deals", DEAL_PROPS):
        deals.append(deal)
        if len(deals) >= MAX_DEALS_FOR_ANALYSIS:
            break

    log.info("pipeline_fetched", deal_count=len(deals))

    if not deals:
        log.info("pipeline_empty")
        return {"status": "no_deals", "summary": None, "actions": [], "tasks_created": 0}

    analysis = analyze_pipeline(ctx, deals)
    actions = _validate_actions(analysis.get("actions"))
    log.info(
        "pipeline_analyzed",
        actions_proposed=len(actions),
        summary_chars=len(analysis.get("summary") or ""),
    )

    tasks_created = 0
    if auto_tasks and actions:
        for action in actions:
            try:
                hubspot.create_task(title=f"[Blufire] {action['action']} - {action['deal_name']}")
                tasks_created += 1
            except HubSpotTaskError as exc:
                log.warning("task_create_failed", deal_name=action["deal_name"], error=str(exc))

    return {
        "status": "ok",
        "summary": analysis.get("summary"),
        "actions": actions,
        "tasks_created": tasks_created,
    }
