"""Apollo client. The API key goes in the ``X-Api-Key`` header — never in the body —
so it can't leak to upstream proxies or logs.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import requests

from blufire.http import ExternalServiceError, build_session, retry_external
from blufire.logging_setup import get_logger
from blufire.settings import Settings

APOLLO_BASE = "https://api.apollo.io/api/v1"
_DEFAULT_PAGE_SIZE = 100


class ApolloError(ExternalServiceError):
    pass


class ApolloClient:
    def __init__(self, settings: Settings, session: requests.Session | None = None) -> None:
        if settings.secrets.apollo_api_key is None:
            raise RuntimeError("APOLLO_API_KEY is not configured.")
        self._key = settings.secrets.apollo_api_key.get_secret_value()
        self._session = session or build_session()
        self._log = get_logger("blufire.integrations.apollo").bind(tenant_id=settings.tenant.id)

    def _headers(self) -> dict[str, str]:
        return {
            "X-Api-Key": self._key,
            "Cache-Control": "no-cache",
            "Content-Type": "application/json",
        }

    @retry_external()
    def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        url = f"{APOLLO_BASE}{path}"
        resp = self._session.post(url, headers=self._headers(), json=payload, timeout=(5, 30))
        if resp.status_code in (200, 201):
            return resp.json()  # type: ignore[no-any-return]
        raise ApolloError(f"POST {path} → {resp.status_code}: {resp.text[:200]}")

    def search_people(
        self,
        *,
        person_titles: list[str] | None = None,
        keywords: list[str] | None = None,
        locations: list[str] | None = None,
        industries: list[str] | None = None,
        page_size: int = _DEFAULT_PAGE_SIZE,
        max_results: int | None = None,
    ) -> Iterator[dict[str, Any]]:
        """Yield matching people across all pages.

        Note: ``api_key`` is intentionally NOT included in the request body.
        """
        page = 0
        yielded = 0
        while True:
            page += 1
            payload: dict[str, Any] = {"page": page, "per_page": page_size}
            if person_titles:
                payload["person_titles"] = person_titles
            if keywords:
                payload["q_keywords"] = " ".join(keywords)
            if locations:
                payload["person_locations"] = locations
            if industries:
                payload["q_organization_industry_tag_ids"] = industries

            data = self._post("/mixed_people/search", payload)
            people: list[dict[str, Any]] = data.get("people", [])
            if not people:
                return
            for person in people:
                yield person
                yielded += 1
                if max_results and yielded >= max_results:
                    return

    def enrich_person(self, email: str) -> dict[str, Any]:
        """Enrich a single contact by email."""
        data = self._post("/people/match", {"email": email})
        return dict(data.get("person", {}))
