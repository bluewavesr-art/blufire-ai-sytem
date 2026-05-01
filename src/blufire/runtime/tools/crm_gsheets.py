"""Google Sheets-backed implementation of the ``crm.*`` tool contracts.

This treats one worksheet as the source-of-truth contact list:
- ``crm.search_contacts`` looks up by email
- ``crm.create_contact`` appends a row
- ``crm.list_contacts`` returns every row

Operations that don't apply to a flat sheet (deals, tasks, email logs)
return soft "not supported" responses rather than raising — the
orchestrator already treats those as best-effort.

The schema of the worksheet is fixed: a header row in row 1, with
columns ``email, first_name, last_name, company, title, phone, address,
city, state, status, notes, created_at``. Operators can add columns
beyond these but must not rename or reorder these. The column order is
also the order ``create_contact`` writes its row.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from blufire.integrations.gsheets import GSheetsClient, GSheetsError
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

LEADS_COLUMNS = (
    "email",
    "first_name",
    "last_name",
    "company",
    "title",
    "phone",
    "address",
    "city",
    "state",
    "status",
    "notes",
    "created_at",
)


def _row_from_props(props: dict[str, Any]) -> list[Any]:
    return [props.get(col, "") for col in LEADS_COLUMNS[:-1]] + [
        datetime.now(UTC).isoformat(timespec="seconds")
    ]


def _record_from_row(row: dict[str, Any]) -> ContactRecord:
    """Sheet rows are dicts keyed by header. Use the row index as the id
    (``contact_id`` for downstream calls); we don't have a real backend id."""
    return ContactRecord(
        id=str(row.get("__row_index__", row.get("email", "?"))),
        properties={k: v for k, v in row.items() if not k.startswith("__")},
    )


class GSheetsListContactsTool(BaseTool[ListContactsInput, ListContactsOutput]):
    name = "crm.list_contacts"
    description = "Read every row from the configured leads worksheet."
    input_schema = ListContactsInput
    output_schema = ListContactsOutput

    def invoke(self, ctx: RunContext, payload: ListContactsInput) -> ListContactsOutput:
        s = ctx.tenant.settings
        if s.gsheets.spreadsheet_url is None:
            raise GSheetsError("gsheets.spreadsheet_url is not configured")
        client = GSheetsClient(s)
        rows = client.list_rows(str(s.gsheets.spreadsheet_url), s.gsheets.leads_worksheet)
        records = []
        for i, row in enumerate(rows):
            if i >= payload.limit:
                break
            row["__row_index__"] = i + 2  # +2 because of header + 1-indexed
            records.append(_record_from_row(row))
        return ListContactsOutput(contacts=records)


class GSheetsSearchContactsTool(BaseTool[SearchContactsInput, SearchContactsOutput]):
    name = "crm.search_contacts"
    description = "Linear search the leads worksheet by exact-match email."
    input_schema = SearchContactsInput
    output_schema = SearchContactsOutput

    def invoke(self, ctx: RunContext, payload: SearchContactsInput) -> SearchContactsOutput:
        s = ctx.tenant.settings
        if s.gsheets.spreadsheet_url is None:
            raise GSheetsError("gsheets.spreadsheet_url is not configured")
        client = GSheetsClient(s)
        rows = client.list_rows(str(s.gsheets.spreadsheet_url), s.gsheets.leads_worksheet)
        target = payload.email.strip().lower()
        for i, row in enumerate(rows):
            row_email = str(row.get("email", "")).strip().lower()
            if row_email == target:
                row["__row_index__"] = i + 2
                return SearchContactsOutput(contacts=[_record_from_row(row)])
        return SearchContactsOutput(contacts=[])


class GSheetsCreateContactTool(BaseTool[CreateContactInput, CreateContactOutput]):
    name = "crm.create_contact"
    description = (
        "Append a row to the leads worksheet. Returns already_existed when a "
        "row with this email is already present."
    )
    input_schema = CreateContactInput
    output_schema = CreateContactOutput

    def invoke(self, ctx: RunContext, payload: CreateContactInput) -> CreateContactOutput:
        s = ctx.tenant.settings
        if s.gsheets.spreadsheet_url is None:
            raise GSheetsError("gsheets.spreadsheet_url is not configured")
        client = GSheetsClient(s)
        url = str(s.gsheets.spreadsheet_url)

        # Pre-check for duplicates so we never double-append. The check is
        # racy under concurrent runs, but the daily cron is single-process.
        target = str(payload.properties.get("email", "")).strip().lower()
        if target:
            rows = client.list_rows(url, s.gsheets.leads_worksheet)
            for row in rows:
                if str(row.get("email", "")).strip().lower() == target:
                    return CreateContactOutput(contact_id=None, already_existed=True)

        client.append_row(url, s.gsheets.leads_worksheet, _row_from_props(payload.properties))
        return CreateContactOutput(contact_id=target or None)


class GSheetsLogEmailTool(BaseTool[LogEmailInput, LogEmailOutput]):
    name = "crm.log_email"
    description = "Sheets has no engagement log; soft no-op so the orchestrator continues."
    input_schema = LogEmailInput
    output_schema = LogEmailOutput

    def invoke(self, ctx: RunContext, payload: LogEmailInput) -> LogEmailOutput:
        return LogEmailOutput(logged=False, error="not_supported_by_provider")


class GSheetsListDealsTool(BaseTool[ListDealsInput, ListDealsOutput]):
    name = "crm.list_deals"
    description = "Sheets-as-CRM has no deals. Returns empty so crm_pipeline degrades gracefully."
    input_schema = ListDealsInput
    output_schema = ListDealsOutput

    def invoke(self, ctx: RunContext, payload: ListDealsInput) -> ListDealsOutput:
        return ListDealsOutput(deals=[])


class GSheetsUpdateDealTool(BaseTool[UpdateDealInput, UpdateDealOutput]):
    name = "crm.update_deal"
    description = "Sheets-as-CRM has no deals; soft no-op."
    input_schema = UpdateDealInput
    output_schema = UpdateDealOutput

    def invoke(self, ctx: RunContext, payload: UpdateDealInput) -> UpdateDealOutput:
        return UpdateDealOutput(updated=False, error="not_supported_by_provider")


class GSheetsCreateDealTool(BaseTool[CreateDealInput, CreateDealOutput]):
    name = "crm.create_deal"
    description = "Sheets-as-CRM has no deals; soft no-op."
    input_schema = CreateDealInput
    output_schema = CreateDealOutput

    def invoke(self, ctx: RunContext, payload: CreateDealInput) -> CreateDealOutput:
        return CreateDealOutput(deal_id=None, error="not_supported_by_provider")


class GSheetsCreateTaskTool(BaseTool[CreateTaskInput, CreateTaskOutput]):
    name = "crm.create_task"
    description = "Sheets-as-CRM has no tasks; soft no-op."
    input_schema = CreateTaskInput
    output_schema = CreateTaskOutput

    def invoke(self, ctx: RunContext, payload: CreateTaskInput) -> CreateTaskOutput:
        return CreateTaskOutput(task_id=None, created=False, error="not_supported_by_provider")


def register(tools: ToolRegistry) -> None:
    """Register Google Sheets CRM tools. Called by bootstrap when
    ``settings.crm.provider == "gsheets"``."""
    for tool_cls in (
        GSheetsListContactsTool,
        GSheetsSearchContactsTool,
        GSheetsCreateContactTool,
        GSheetsLogEmailTool,
        GSheetsListDealsTool,
        GSheetsUpdateDealTool,
        GSheetsCreateDealTool,
        GSheetsCreateTaskTool,
    ):
        tool = tool_cls()
        if tools.get(tool.name) is None:
            tools.register(tool)
