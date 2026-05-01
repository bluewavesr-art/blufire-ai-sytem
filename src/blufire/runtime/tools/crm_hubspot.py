"""HubSpot-backed implementations of the ``crm.*`` tool contracts."""

from __future__ import annotations

from blufire.integrations.hubspot import HubSpotClient, HubSpotError
from blufire.runtime.context import RunContext
from blufire.runtime.tool import ToolRegistry
from blufire.runtime.tools._base import BaseTool
from blufire.runtime.tools.crm import (
    ContactRecord,
    ListContactsInput,
    ListContactsOutput,
    LogEmailInput,
    LogEmailOutput,
)


class HubSpotListContactsTool(BaseTool[ListContactsInput, ListContactsOutput]):
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


class HubSpotLogEmailTool(BaseTool[LogEmailInput, LogEmailOutput]):
    name = "crm.log_email"
    description = "Log a sent email as a HubSpot engagement (best-effort)."
    input_schema = LogEmailInput
    output_schema = LogEmailOutput

    def invoke(self, ctx: RunContext, payload: LogEmailInput) -> LogEmailOutput:
        client = HubSpotClient(ctx.tenant.settings)
        try:
            client.log_email(payload.contact_id, payload.subject, payload.body)
        except HubSpotError as exc:
            return LogEmailOutput(logged=False, error=type(exc).__name__)
        return LogEmailOutput(logged=True)


def register(tools: ToolRegistry) -> None:
    """Register HubSpot's CRM tools into ``tools``. Called by bootstrap when
    ``settings.crm.provider == "hubspot"``."""
    if tools.get("crm.list_contacts") is None:
        tools.register(HubSpotListContactsTool())
    if tools.get("crm.log_email") is None:
        tools.register(HubSpotLogEmailTool())
