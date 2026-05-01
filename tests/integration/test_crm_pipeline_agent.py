from __future__ import annotations

from unittest.mock import patch

import responses

from blufire.agents import crm_pipeline
from blufire.integrations.hubspot import HUBSPOT_BASE
from blufire.runtime.context import RunContext, TenantContext


def _ctx(settings) -> RunContext:
    return RunContext(tenant=TenantContext(settings=settings), agent="crm_pipeline", run_id="r1")


@responses.activate
def test_pipeline_no_deals(tmp_settings) -> None:
    responses.add(
        responses.GET,
        f"{HUBSPOT_BASE}/crm/v3/objects/deals",
        json={"results": []},
        status=200,
    )
    out = crm_pipeline.run(_ctx(tmp_settings))
    assert out["status"] == "no_deals"
    assert out["actions"] == []


@responses.activate
def test_pipeline_proposes_actions(tmp_settings) -> None:
    responses.add(
        responses.GET,
        f"{HUBSPOT_BASE}/crm/v3/objects/deals",
        json={
            "results": [
                {
                    "id": "1",
                    "properties": {
                        "dealname": "Big deal",
                        "dealstage": "qualified",
                        "amount": "10000",
                        "closedate": "2026-06-01",
                    },
                },
            ]
        },
        status=200,
    )

    fake_analysis = {
        "summary": "One stale deal needs follow-up.",
        "actions": [
            {"deal_name": "Big deal", "action": "Send follow-up", "reason": "Idle 14d"},
            "garbage row that should be filtered out",
        ],
    }
    with patch.object(crm_pipeline, "analyze_pipeline", return_value=fake_analysis):
        out = crm_pipeline.run(_ctx(tmp_settings), auto_tasks=False)

    assert out["status"] == "ok"
    assert len(out["actions"]) == 1
    assert out["actions"][0]["deal_name"] == "Big deal"


@responses.activate
def test_pipeline_auto_tasks(tmp_settings) -> None:
    responses.add(
        responses.GET,
        f"{HUBSPOT_BASE}/crm/v3/objects/deals",
        json={
            "results": [
                {"id": "1", "properties": {"dealname": "X", "dealstage": "q"}},
            ]
        },
        status=200,
    )
    responses.add(
        responses.POST,
        f"{HUBSPOT_BASE}/crm/v3/objects/tasks",
        json={"id": "task-1"},
        status=201,
    )
    fake_analysis = {
        "summary": "follow up",
        "actions": [{"deal_name": "X", "action": "ping", "reason": "stale"}],
    }
    with patch.object(crm_pipeline, "analyze_pipeline", return_value=fake_analysis):
        out = crm_pipeline.run(_ctx(tmp_settings), auto_tasks=True)
    assert out["tasks_created"] == 1
