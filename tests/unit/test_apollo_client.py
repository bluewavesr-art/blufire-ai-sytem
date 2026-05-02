"""Apollo client: API key MUST live in headers, NEVER in the JSON body."""

from __future__ import annotations

import json

import responses

from blufire.integrations.apollo import APOLLO_BASE, ApolloClient


@responses.activate
def test_api_key_in_header_not_body(tmp_settings) -> None:
    responses.add(
        responses.POST,
        f"{APOLLO_BASE}/mixed_people/search",
        json={"people": []},
        status=200,
    )
    client = ApolloClient(tmp_settings)
    list(client.search_people(person_titles=["CEO"]))

    call = responses.calls[0]
    assert call.request.headers["X-Api-Key"] == "apollo-test-key"
    body = json.loads(call.request.body)
    assert "api_key" not in body, "Apollo API key must not be in request body"


@responses.activate
def test_pagination_yields_all(tmp_settings) -> None:
    responses.add(
        responses.POST,
        f"{APOLLO_BASE}/mixed_people/search",
        json={"people": [{"email": "a@x.test"}, {"email": "b@x.test"}]},
        status=200,
    )
    responses.add(
        responses.POST,
        f"{APOLLO_BASE}/mixed_people/search",
        json={"people": [{"email": "c@x.test"}]},
        status=200,
    )
    responses.add(
        responses.POST,
        f"{APOLLO_BASE}/mixed_people/search",
        json={"people": []},
        status=200,
    )
    client = ApolloClient(tmp_settings)
    emails = [p["email"] for p in client.search_people(person_titles=["CEO"], page_size=2)]
    assert emails == ["a@x.test", "b@x.test", "c@x.test"]


@responses.activate
def test_max_results_truncates(tmp_settings) -> None:
    responses.add(
        responses.POST,
        f"{APOLLO_BASE}/mixed_people/search",
        json={"people": [{"email": "a@x.test"}, {"email": "b@x.test"}, {"email": "c@x.test"}]},
        status=200,
    )
    client = ApolloClient(tmp_settings)
    out = list(client.search_people(person_titles=["CEO"], max_results=2))
    assert len(out) == 2
