"""End-to-end: outreach respects suppression + caps without touching real services."""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

import responses

from blufire.compliance.suppression import SuppressionList
from blufire.integrations.hubspot import HUBSPOT_BASE
from blufire.runtime.context import RunContext, TenantContext


def _ctx(settings) -> RunContext:
    return RunContext(tenant=TenantContext(settings=settings), agent="email_outreach", run_id="r1")


@responses.activate
def test_suppressed_recipient_is_skipped(tmp_settings, monkeypatch) -> None:
    """Adding a recipient to the suppression list must skip the LLM and SMTP layers."""
    SuppressionList(tmp_settings.suppression_db_path, tmp_settings.tenant.id).add(
        "alice@example.com", reason="manual"
    )
    responses.add(
        responses.GET,
        f"{HUBSPOT_BASE}/crm/v3/objects/contacts",
        json={
            "results": [
                {
                    "id": "1",
                    "properties": {
                        "email": "alice@example.com",
                        "firstname": "Alice",
                        "lastname": "X",
                        "company": "Acme",
                        "jobtitle": "CEO",
                    },
                }
            ]
        },
        status=200,
    )

    drafts: list[Any] = []

    def _fake_draft(*args, **kwargs):
        drafts.append((args, kwargs))
        return {"subject": "s", "body": "b"}

    from blufire.agents import email_outreach

    with patch.object(email_outreach, "draft_email", side_effect=_fake_draft):
        counters = email_outreach.run(
            _ctx(tmp_settings),
            campaign_context="test",
            limit=10,
            dry_run=True,
        )

    assert counters["skipped_suppressed"] == 1
    assert counters["drafted_dry_run"] == 0
    assert drafts == [], "draft_email must not be called for suppressed recipients"


@responses.activate
def test_dry_run_does_not_send(tmp_settings) -> None:
    responses.add(
        responses.GET,
        f"{HUBSPOT_BASE}/crm/v3/objects/contacts",
        json={
            "results": [
                {
                    "id": str(i),
                    "properties": {
                        "email": f"bob{i}@example.com",
                        "firstname": "Bob",
                        "lastname": "Y",
                        "company": "Acme",
                        "jobtitle": "Owner",
                    },
                }
                for i in range(3)
            ]
        },
        status=200,
    )

    from blufire.agents import email_outreach

    def _fake_draft(*args, **kwargs):
        return {"subject": "Hello", "body": "Hi there"}

    with patch.object(email_outreach, "draft_email", side_effect=_fake_draft):
        counters = email_outreach.run(
            _ctx(tmp_settings),
            campaign_context="test",
            limit=3,
            dry_run=True,
        )

    assert counters["drafted_dry_run"] == 3
    assert counters["sent"] == 0
