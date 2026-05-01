"""HubSpot-backed implementations of the ``crm.*`` tool contracts."""

from __future__ import annotations

from blufire.integrations.hubspot import (
    HubSpotClient,
    HubSpotContactExists,
    HubSpotError,
    HubSpotTaskError,
)
from blufire.runtime.context import RunContext
from blufire.runtime.tool import ToolRegistry
from blufire.runtime.tools._base import BaseTool
from blufire.runtime.tools.crm import (
    ContactRecord,
    CreateContactInput,
    CreateContactOutput,
    CreateDealInput,
    CreateDealOutput,
    CreateTaskInput,
    CreateTaskOutput,
    DealRecord,
    ListContactsInput,
    ListContactsOutput,
    ListDealsInput,
    ListDealsOutput,
    LogEmailInput,
    LogEmailOutput,
    SearchContactsInput,
    SearchContactsOutput,
    UpdateDealInput,
    UpdateDealOutput,
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


class HubSpotSearchContactsTool(BaseTool[SearchContactsInput, SearchContactsOutput]):
    name = "crm.search_contacts"
    description = "Find HubSpot contacts by exact-match email."
    input_schema = SearchContactsInput
    output_schema = SearchContactsOutput

    def invoke(self, ctx: RunContext, payload: SearchContactsInput) -> SearchContactsOutput:
        client = HubSpotClient(ctx.tenant.settings)
        filters = [{"propertyName": "email", "operator": "EQ", "value": payload.email}]
        results = client.search("contacts", filters, payload.properties, limit=1)
        records = [
            ContactRecord(id=str(r.get("id", "")), properties=r.get("properties") or {})
            for r in results
        ]
        return SearchContactsOutput(contacts=records)


class HubSpotCreateContactTool(BaseTool[CreateContactInput, CreateContactOutput]):
    name = "crm.create_contact"
    description = "Create a HubSpot contact; treat 409 (duplicate) as a soft no-op."
    input_schema = CreateContactInput
    output_schema = CreateContactOutput

    def invoke(self, ctx: RunContext, payload: CreateContactInput) -> CreateContactOutput:
        client = HubSpotClient(ctx.tenant.settings)
        try:
            result = client.create_contact(payload.properties)
        except HubSpotContactExists:
            return CreateContactOutput(contact_id=None, already_existed=True)
        return CreateContactOutput(contact_id=str(result.get("id", "")) or None)


class HubSpotListDealsTool(BaseTool[ListDealsInput, ListDealsOutput]):
    name = "crm.list_deals"
    description = "Page through HubSpot deals up to the supplied limit."
    input_schema = ListDealsInput
    output_schema = ListDealsOutput

    def invoke(self, ctx: RunContext, payload: ListDealsInput) -> ListDealsOutput:
        client = HubSpotClient(ctx.tenant.settings)
        records: list[DealRecord] = []
        for i, raw in enumerate(client.iter_objects("deals", payload.properties)):
            if i >= payload.limit:
                break
            records.append(
                DealRecord(id=str(raw.get("id", "")), properties=raw.get("properties") or {})
            )
        return ListDealsOutput(deals=records)


class HubSpotUpdateDealTool(BaseTool[UpdateDealInput, UpdateDealOutput]):
    name = "crm.update_deal"
    description = "Patch a HubSpot deal's properties."
    input_schema = UpdateDealInput
    output_schema = UpdateDealOutput

    def invoke(self, ctx: RunContext, payload: UpdateDealInput) -> UpdateDealOutput:
        client = HubSpotClient(ctx.tenant.settings)
        try:
            client.update_deal(payload.deal_id, payload.properties)
        except HubSpotError as exc:
            return UpdateDealOutput(updated=False, error=type(exc).__name__)
        return UpdateDealOutput(updated=True)


class HubSpotCreateDealTool(BaseTool[CreateDealInput, CreateDealOutput]):
    name = "crm.create_deal"
    description = "Create a HubSpot deal, optionally associated with a contact."
    input_schema = CreateDealInput
    output_schema = CreateDealOutput

    def invoke(self, ctx: RunContext, payload: CreateDealInput) -> CreateDealOutput:
        client = HubSpotClient(ctx.tenant.settings)
        try:
            result = client.create_deal(
                dealname=payload.dealname,
                stage=payload.stage,
                amount=payload.amount,
                contact_id=payload.contact_id,
            )
        except HubSpotError as exc:
            return CreateDealOutput(deal_id=None, error=type(exc).__name__)
        return CreateDealOutput(deal_id=str(result.get("id", "")) or None)


class HubSpotCreateTaskTool(BaseTool[CreateTaskInput, CreateTaskOutput]):
    name = "crm.create_task"
    description = "Create a HubSpot task, optionally associated with a contact."
    input_schema = CreateTaskInput
    output_schema = CreateTaskOutput

    def invoke(self, ctx: RunContext, payload: CreateTaskInput) -> CreateTaskOutput:
        client = HubSpotClient(ctx.tenant.settings)
        try:
            result = client.create_task(
                title=payload.title,
                contact_id=payload.contact_id,
                due_days=payload.due_days,
            )
        except HubSpotTaskError as exc:
            return CreateTaskOutput(task_id=None, created=False, error=type(exc).__name__)
        return CreateTaskOutput(task_id=str(result.get("id", "")) or None, created=True)


def register(tools: ToolRegistry) -> None:
    """Register HubSpot's CRM tools into ``tools``. Called by bootstrap when
    ``settings.crm.provider == "hubspot"``."""
    for tool_cls in (
        HubSpotListContactsTool,
        HubSpotLogEmailTool,
        HubSpotSearchContactsTool,
        HubSpotCreateContactTool,
        HubSpotListDealsTool,
        HubSpotUpdateDealTool,
        HubSpotCreateDealTool,
        HubSpotCreateTaskTool,
    ):
        tool = tool_cls()
        if tools.get(tool.name) is None:
            tools.register(tool)
