"""Google Places (Maps) API client.

Single-tenant: each tenant supplies its own ``GPLACES_API_KEY``.
Used for local-business discovery — name, address, phone, website. The
API does NOT return email addresses; pair with the ``enrich.find_email``
tool to attempt email discovery from the business's website.

Cost note: Places API charges per request and per detail field returned.
The default field mask in this wrapper is the minimum we need for
outreach (name, formatted_address, formatted_phone_number, website,
business_status, types). Don't enable photos/reviews/etc. unless you
actually use them — they're billed separately.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import googlemaps  # type: ignore[import-untyped]
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential_jitter,
)

from blufire.http import ExternalServiceError
from blufire.logging_setup import get_logger
from blufire.settings import Settings

# Field mask sent to the Places Details endpoint. Each field has a
# separate billing tier — keep this list tight.
DEFAULT_DETAIL_FIELDS = (
    "name",
    "formatted_address",
    "formatted_phone_number",
    "website",
    "business_status",
    "type",
    "place_id",
)


class GPlacesError(ExternalServiceError):
    pass


class GPlacesAuthError(GPlacesError):
    """Bad / missing API key. Don't include the key value in any message."""


class GPlacesClient:
    """Thin wrapper around ``googlemaps.Client`` for the single workflow we
    have: text-search businesses by query, return enriched details for
    each match."""

    def __init__(self, settings: Settings) -> None:
        if settings.secrets.gplaces_api_key is None:
            raise GPlacesAuthError("GPLACES_API_KEY is not configured.")
        self._client = googlemaps.Client(key=settings.secrets.gplaces_api_key.get_secret_value())
        self._log = get_logger("blufire.integrations.gplaces").bind(tenant_id=settings.tenant.id)

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential_jitter(initial=1.0, max=15.0),
        retry=retry_if_exception_type(googlemaps.exceptions.HTTPError),
        reraise=True,
    )
    def _places(self, query: str, location: str | None = None) -> dict[str, Any]:
        """Single-page text search. Returns the raw API response."""
        kwargs: dict[str, Any] = {"query": query}
        if location:
            kwargs["location"] = location
        return self._client.places(**kwargs)  # type: ignore[no-any-return]

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential_jitter(initial=1.0, max=15.0),
        retry=retry_if_exception_type(googlemaps.exceptions.HTTPError),
        reraise=True,
    )
    def _details(self, place_id: str) -> dict[str, Any]:
        """Fetch the configured detail fields for a place."""
        resp = self._client.place(place_id=place_id, fields=list(DEFAULT_DETAIL_FIELDS))
        result = resp.get("result")
        return dict(result) if isinstance(result, dict) else {}

    def search(
        self,
        query: str,
        *,
        location: str | None = None,
        max_results: int = 25,
    ) -> Iterator[dict[str, Any]]:
        """Yield enriched place dicts matching ``query``.

        ``location`` is a free-form string ("Fort Worth, TX") — the Places
        API geocodes it into a bias center. Each yielded dict has the
        fields listed in ``DEFAULT_DETAIL_FIELDS``."""
        yielded = 0
        page = self._places(query, location=location)
        while True:
            for hit in page.get("results", []):
                if yielded >= max_results:
                    return
                place_id = hit.get("place_id")
                if not place_id:
                    continue
                details = self._details(place_id)
                # Merge the search hit's basic fields with the details so
                # callers can rely on either being present.
                merged = {**hit, **details}
                yield merged
                yielded += 1
            next_token = page.get("next_page_token")
            if not next_token or yielded >= max_results:
                return
            # Places API requires a brief delay before next_page_token works.
            import time as _time

            _time.sleep(2.0)
            page = self._client.places(query=query, page_token=next_token)
