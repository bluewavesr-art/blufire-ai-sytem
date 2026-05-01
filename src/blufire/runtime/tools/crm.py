"""CRM Tools backed by HubSpot."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from blufire.integrations.hubspot import HubSpotClient, HubSpotError
from blufire.runtime.context import RunContext
from blufire.runtime.tools._base import BaseTool

DEFAULT_CONTACT_PROPERTIES = ["firstname", "lastname", "email", "company", "jobtitle"]


# ---------------------------------------------------------------------------
# crm.list_contacts
# ---------------------------------------------------------------------------


class ListContactsInput(BaseModel):
    properties: list[str] = Field(default_factory=lambda: list(DEFAULT_CONTACT_PROPERTIES))
    limit: int = Field(default=10, ge=1, le=500)


class ContactRecord(BaseModel):
    id: str
    properties: dict[str, Any] = Field(default_factory=dict)


class ListContactsOutput(BaseModel):
    contacts: list[ContactRecord] = Field(default_factory=list)


class ListContactsTool(BaseTool[ListContactsInput, ListContactsOutput]):
    name = "crm.list_contacts"
    description = "Page through HubSpot contacts up to the supplied limit."
    input_schema = ListContactsInput
    output_schema = ListContactsOutput

    def invoke(self, ctx: RunContext, payload: ListContactsInput) -> ListContactsOutput:
        client = HubSpotClient(ctx.tenant.settings)
        records: list[ContactRecord] = []
        for i, raw in enumerate(client.iter_objects("contacts", payload.properties)):
            if i >= payload.limit:
                break
            records.append(
                ContactRecord(id=str(raw.get("id", "")), properties=raw.get("properties") or {})
            )
        return ListContactsOutput(contacts=records)


# ---------------------------------------------------------------------------
# crm.log_email
# ---------------------------------------------------------------------------


class LogEmailInput(BaseModel):
    contact_id: str
    subject: str
    body: str


class LogEmailOutput(BaseModel):
    logged: bool
    error: str | None = None


class LogEmailTool(BaseTool[LogEmailInput, LogEmailOutput]):
    name = "crm.log_email"
    description = "Log a sent email as a HubSpot engagement (best-effort)."
    input_schema = LogEmailInput
    output_schema = LogEmailOutput

    def invoke(self, ctx: RunContext, payload: LogEmailInput) -> LogEmailOutput:
        client = HubSpotClient(ctx.tenant.settings)
        try:
            client.log_email(payload.contact_id, payload.subject, payload.body)
        except HubSpotError as exc:
            # Don't fail the whole run if HubSpot times out — caller decides.
            return LogEmailOutput(logged=False, error=type(exc).__name__)
        return LogEmailOutput(logged=True)
