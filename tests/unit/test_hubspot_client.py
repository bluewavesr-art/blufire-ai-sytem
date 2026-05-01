from __future__ import annotations

import pytest
import responses

from blufire.integrations.hubspot import (
    HUBSPOT_BASE,
    HubSpotClient,
    HubSpotContactExists,
    HubSpotTaskError,
)


@responses.activate
def test_create_contact_409_raises_exists(tmp_settings) -> None:
    responses.add(
        responses.POST,
        f"{HUBSPOT_BASE}/crm/v3/objects/contacts",
        status=409,
        json={"message": "duplicate"},
    )
    client = HubSpotClient(tmp_settings)
    with pytest.raises(HubSpotContactExists):
        client.create_contact({"email": "a@x.test"})


@responses.activate
def test_create_task_failure_raises_task_error(tmp_settings) -> None:
    responses.add(
        responses.POST,
        f"{HUBSPOT_BASE}/crm/v3/objects/tasks",
        status=500,
        json={"message": "boom"},
    )
    client = HubSpotClient(tmp_settings)
    with pytest.raises(HubSpotTaskError):
        client.create_task("test")


@responses.activate
def test_pagination(tmp_settings) -> None:
    responses.add(
        responses.GET,
        f"{HUBSPOT_BASE}/crm/v3/objects/deals",
        json={
            "results": [{"id": "1"}, {"id": "2"}],
            "paging": {"next": {"after": "cursor1"}},
        },
        status=200,
    )
    responses.add(
        responses.GET,
        f"{HUBSPOT_BASE}/crm/v3/objects/deals",
        json={"results": [{"id": "3"}]},
        status=200,
    )
    client = HubSpotClient(tmp_settings)
    ids = [d["id"] for d in client.iter_objects("deals", ["dealname"])]
    assert ids == ["1", "2", "3"]


@responses.activate
def test_authorization_header(tmp_settings) -> None:
    responses.add(
        responses.GET,
        f"{HUBSPOT_BASE}/crm/v3/objects/contacts",
        json={"results": []},
        status=200,
    )
    client = HubSpotClient(tmp_settings)
    list(client.iter_objects("contacts", ["email"]))
    assert responses.calls[0].request.headers["Authorization"] == "Bearer hs-test-key"
