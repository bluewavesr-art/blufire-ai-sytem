"""HubSpot CRM client. Single source of auth headers, paginated reads, typed errors."""

from __future__ import annotations

import time
from collections.abc import Iterator
from typing import Any

import requests

from blufire.http import ExternalServiceError, build_session, retry_external
from blufire.logging_setup import get_logger
from blufire.settings import Settings

HUBSPOT_BASE = "https://api.hubapi.com"
_DEFAULT_PAGE_SIZE = 100


class HubSpotError(ExternalServiceError):
    """Generic HubSpot error."""


class HubSpotTaskError(HubSpotError):
    """Task creation failed."""


class HubSpotContactExists(HubSpotError):
    """Contact already exists (HTTP 409)."""


class HubSpotClient:
    def __init__(self, settings: Settings, session: requests.Session | None = None) -> None:
        if settings.secrets.hubspot_api_key is None:
            raise RuntimeError("HUBSPOT_API_KEY is not configured.")
        self._token = settings.secrets.hubspot_api_key.get_secret_value()
        self._session = session or build_session()
        self._log = get_logger("blufire.integrations.hubspot").bind(tenant_id=settings.tenant.id)

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._token}",
            "Content-Type": "application/json",
        }

    @retry_external()
    def _request(
        self,
        method: str,
        path: str,
        *,
        expected: tuple[int, ...] = (200, 201),
        **kwargs: Any,
    ) -> dict[str, Any]:
        url = f"{HUBSPOT_BASE}{path}"
        resp = self._session.request(
            method, url, headers=self._headers(), timeout=(5, 30), **kwargs
        )
        if resp.status_code in expected:
            return resp.json() if resp.content else {}
        raise HubSpotError(f"{method} {path} → {resp.status_code}: {resp.text[:200]}")

    def iter_objects(
        self,
        object_type: str,
        properties: list[str],
        *,
        page_size: int = _DEFAULT_PAGE_SIZE,
    ) -> Iterator[dict[str, Any]]:
        """Yield every object across all pages of an object type."""
        after: str | None = None
        while True:
            params: dict[str, Any] = {
                "limit": page_size,
                "properties": ",".join(properties),
            }
            if after:
                params["after"] = after
            data = self._request("GET", f"/crm/v3/objects/{object_type}", params=params)
            yield from data.get("results", [])
            cursor = data.get("paging", {}).get("next", {}).get("after")
            if not cursor:
                return
            after = cursor

    def search(
        self,
        object_type: str,
        filters: list[dict[str, Any]],
        properties: list[str],
        *,
        limit: int = 1,
    ) -> list[dict[str, Any]]:
        """POST-based search (HubSpot search API)."""
        payload = {
            "filterGroups": [{"filters": filters}],
            "properties": properties,
            "limit": limit,
        }
        data = self._request("POST", f"/crm/v3/objects/{object_type}/search", json=payload)
        return list(data.get("results", []))

    def create_contact(self, properties: dict[str, Any]) -> dict[str, Any]:
        """Create a contact. Raises ``HubSpotContactExists`` on duplicate (409)."""
        url = "/crm/v3/objects/contacts"
        try:
            return self._request("POST", url, json={"properties": properties})
        except HubSpotError as exc:
            if "→ 409" in str(exc):
                raise HubSpotContactExists(str(exc)) from exc
            raise

    def update_deal(self, deal_id: str, properties: dict[str, Any]) -> dict[str, Any]:
        return self._request(
            "PATCH", f"/crm/v3/objects/deals/{deal_id}", json={"properties": properties}
        )

    def create_deal(
        self,
        dealname: str,
        stage: str,
        amount: float | None = None,
        contact_id: str | None = None,
    ) -> dict[str, Any]:
        properties: dict[str, Any] = {"dealname": dealname, "dealstage": stage}
        if amount is not None:
            properties["amount"] = str(amount)
        payload: dict[str, Any] = {"properties": properties}
        if contact_id:
            payload["associations"] = [
                {
                    "to": {"id": contact_id},
                    "types": [{"associationCategory": "HUBSPOT_DEFINED", "associationTypeId": 3}],
                }
            ]
        return self._request("POST", "/crm/v3/objects/deals", json=payload)

    def get_deal_contacts(self, deal_id: str) -> list[dict[str, Any]]:
        url = f"/crm/v4/objects/deals/{deal_id}/associations/contacts"
        data = self._request("GET", url, expected=(200, 404))
        return list(data.get("results", []))

    def get_contact(self, contact_id: str) -> dict[str, Any] | None:
        url = f"/crm/v3/objects/contacts/{contact_id}"
        try:
            return self._request(
                "GET",
                url,
                params={"properties": "firstname,lastname,email,company,jobtitle"},
            )
        except HubSpotError as exc:
            if "→ 404" in str(exc):
                return None
            raise

    def create_task(
        self, title: str, contact_id: str | None = None, due_days: int = 3
    ) -> dict[str, Any]:
        """Create a HubSpot task. Raises ``HubSpotTaskError`` on failure (no silent None)."""
        due_timestamp = str(int((time.time() + due_days * 86400) * 1000))
        payload: dict[str, Any] = {
            "properties": {
                "hs_task_subject": title,
                "hs_task_status": "NOT_STARTED",
                "hs_task_priority": "MEDIUM",
                "hs_timestamp": due_timestamp,
            }
        }
        if contact_id:
            payload["associations"] = [
                {
                    "to": {"id": contact_id},
                    "types": [{"associationCategory": "HUBSPOT_DEFINED", "associationTypeId": 204}],
                }
            ]
        try:
            return self._request("POST", "/crm/v3/objects/tasks", json=payload)
        except HubSpotError as exc:
            raise HubSpotTaskError(str(exc)) from exc

    def log_email(
        self,
        contact_id: str,
        subject: str,
        body: str,
        *,
        timestamp_ms: int | None = None,
    ) -> dict[str, Any]:
        """Log a sent email as an engagement."""
        ts = timestamp_ms if timestamp_ms is not None else int(time.time() * 1000)
        payload = {
            "properties": {
                "hs_timestamp": str(ts),
                "hs_email_direction": "EMAIL",
                "hs_email_subject": subject,
                "hs_email_text": body,
                "hs_email_status": "SENT",
            },
            "associations": [
                {
                    "to": {"id": contact_id},
                    "types": [{"associationCategory": "HUBSPOT_DEFINED", "associationTypeId": 198}],
                }
            ],
        }
        return self._request("POST", "/crm/v3/objects/emails", json=payload)
