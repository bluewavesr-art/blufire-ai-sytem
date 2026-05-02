from __future__ import annotations

from unittest.mock import patch

import responses

from blufire.agents import lead_generation
from blufire.integrations.apollo import APOLLO_BASE
from blufire.integrations.hubspot import HUBSPOT_BASE
from blufire.runtime.context import RunContext, TenantContext


def _ctx(settings) -> RunContext:
    return RunContext(tenant=TenantContext(settings=settings), agent="lead_generation", run_id="r1")


@responses.activate
def test_lead_generation_run(tmp_settings) -> None:
    responses.add(
        responses.POST,
        f"{APOLLO_BASE}/mixed_people/search",
        json={
            "people": [
                {
                    "first_name": "A",
                    "last_name": "B",
                    "email": "a@x.test",
                    "title": "CEO",
                    "city": "Dallas",
                    "state": "TX",
                    "country": "US",
                    "organization": {
                        "name": "Acme",
                        "industry": "Tech",
                        "estimated_num_employees": 50,
                    },
                },
                {
                    "first_name": "C",
                    "last_name": "D",
                    "email": "c@x.test",
                    "title": "CTO",
                    "city": "Dallas",
                    "state": "TX",
                    "country": "US",
                    "organization": {
                        "name": "Beta",
                        "industry": "Tech",
                        "estimated_num_employees": 10,
                    },
                },
            ]
        },
        status=200,
    )
    responses.add(
        responses.POST,
        f"{APOLLO_BASE}/mixed_people/search",
        json={"people": []},
        status=200,
    )
    responses.add(
        responses.POST,
        f"{HUBSPOT_BASE}/crm/v3/objects/contacts",
        json={"id": "100"},
        status=201,
    )
    responses.add(
        responses.POST,
        f"{HUBSPOT_BASE}/crm/v3/objects/contacts",
        json={"id": "101"},
        status=201,
    )

    with patch.object(
        lead_generation, "score_lead", return_value={"score": 8, "reason": "good fit"}
    ):
        out = lead_generation.run(
            _ctx(tmp_settings),
            job_titles=["CEO"],
            limit=5,
        )

    assert len(out) == 2
    assert all(r["score"]["score"] == 8 for r in out)


def test_safe_phone_handles_missing() -> None:
    from blufire.agents.lead_generation import _safe_phone

    assert _safe_phone({}) is None
    assert _safe_phone({"phone_numbers": []}) is None
    assert _safe_phone({"phone_numbers": [{"sanitized_number": "+1-555-0100"}]}) == "+1-555-0100"
