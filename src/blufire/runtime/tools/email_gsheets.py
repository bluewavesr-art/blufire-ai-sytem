"""Google Sheets-backed implementation of ``email.create_draft``.

Appends a row to the configured Drafts worksheet. The operator reviews
each row, copies the subject + body into Gmail, and sends from their
own account. No SMTP send happens here — this is human-in-the-loop
delivery."""

from __future__ import annotations

from datetime import UTC, datetime

from blufire.integrations.gsheets import GSheetsClient, GSheetsError
from blufire.runtime.context import RunContext
from blufire.runtime.tool import ToolRegistry
from blufire.runtime.tools._base import BaseTool
from blufire.runtime.tools.email import CreateDraftInput, CreateDraftOutput

DRAFTS_COLUMNS = ("created_at", "to", "subject", "body", "list_unsubscribe", "status")


class GSheetsCreateDraftTool(BaseTool[CreateDraftInput, CreateDraftOutput]):
    name = "email.create_draft"
    description = "Append a draft row to the configured Drafts worksheet for human review."
    input_schema = CreateDraftInput
    output_schema = CreateDraftOutput

    def invoke(self, ctx: RunContext, payload: CreateDraftInput) -> CreateDraftOutput:
        s = ctx.tenant.settings
        if s.gsheets.spreadsheet_url is None:
            return CreateDraftOutput(created=False, error="spreadsheet_url_not_configured")
        client = GSheetsClient(s)
        row = [
            datetime.now(UTC).isoformat(timespec="seconds"),
            payload.to,
            payload.subject,
            payload.body,
            payload.list_unsubscribe or "",
            "draft",  # initial status; operator updates to sent/replied
        ]
        try:
            client.append_row(str(s.gsheets.spreadsheet_url), s.gsheets.drafts_worksheet, row)
        except GSheetsError as exc:
            return CreateDraftOutput(created=False, error=type(exc).__name__)
        return CreateDraftOutput(created=True)


def register(tools: ToolRegistry) -> None:
    """Register the Google Sheets draft tool. Called by bootstrap when
    ``settings.email.draft_provider == "gsheets"``."""
    if tools.get("email.create_draft") is None:
        tools.register(GSheetsCreateDraftTool())
