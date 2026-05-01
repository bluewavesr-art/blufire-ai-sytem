from __future__ import annotations

import pytest
import requests
import responses

from blufire.http import ExternalServiceError, build_session, request_json, retry_external


@responses.activate
def test_request_json_happy_path() -> None:
    responses.add(responses.GET, "https://api.test/x", json={"ok": True}, status=200)
    s = build_session()
    out = request_json(s, "GET", "https://api.test/x")
    assert out == {"ok": True}


@responses.activate
def test_request_json_bad_status_raises() -> None:
    responses.add(responses.GET, "https://api.test/y", status=400, json={"err": "no"})
    s = build_session()
    with pytest.raises(ExternalServiceError):
        request_json(s, "GET", "https://api.test/y")


@responses.activate
def test_request_json_non_json_raises() -> None:
    responses.add(responses.GET, "https://api.test/z", body="not json", status=200)
    s = build_session()
    with pytest.raises(ExternalServiceError):
        request_json(s, "GET", "https://api.test/z")


def test_retry_external_retries_on_connection_error() -> None:
    calls = {"n": 0}

    @retry_external(max_attempts=3, initial=0.01, maximum=0.05)
    def flaky() -> str:
        calls["n"] += 1
        if calls["n"] < 3:
            raise requests.ConnectionError("nope")
        return "ok"

    assert flaky() == "ok"
    assert calls["n"] == 3
