"""Make.com-webhook implementation of ``email.create_draft``.

Posts a ``{to, subject, body}`` JSON payload to the URL configured at
``settings.outreach.webhook.gmail_draft_url``. The expectation is that
Make.com (or Zapier or a custom backend) consumes the webhook and creates
a Gmail draft for the operator to review/edit/send. Idempotency is the
consumer's responsibility; we just deliver.
"""

from __future__ import annotations

from typing import Any

from blufire.http import build_session, retry_external
from blufire.runtime.context import RunContext
from blufire.runtime.tool import ToolRegistry
from blufire.runtime.tools._base import BaseTool
from blufire.runtime.tools.email import CreateDraftInput, CreateDraftOutput


@retry_external()
def _post(session: Any, url: str, payload: dict[str, Any]) -> int:
    resp = session.post(url, json=payload, timeout=(5, 30))
    return int(resp.status_code)


class MakeWebhookCreateDraftTool(BaseTool[CreateDraftInput, CreateDraftOutput]):
    name = "email.create_draft"
    description = (
        "POST a draft payload to outreach.webhook.gmail_draft_url; the consumer "
        "(Make.com / Zapier / custom backend) is responsible for creating the "
        "actual draft in Gmail / Outlook / etc."
    )
    input_schema = CreateDraftInput
    output_schema = CreateDraftOutput

    def invoke(self, ctx: RunContext, payload: CreateDraftInput) -> CreateDraftOutput:
        url = ctx.tenant.settings.outreach.webhook.gmail_draft_url
        if url is None:
            # Settings already gates this when prospect_searches is set, but be
            # defensive: explicit error beats a confusing requests stack trace.
            return CreateDraftOutput(created=False, error="webhook_not_configured")

        session = build_session()
        body: dict[str, Any] = {
            "to": payload.to,
            "subject": payload.subject,
            "body": payload.body,
        }
        if payload.list_unsubscribe:
            body["list_unsubscribe"] = payload.list_unsubscribe

        try:
            status = _post(session, str(url), body)
        except Exception as exc:
            return CreateDraftOutput(created=False, error=type(exc).__name__)

        if status in (200, 201, 202, 204):
            return CreateDraftOutput(created=True)
        return CreateDraftOutput(created=False, error=f"http_{status}")


def register(tools: ToolRegistry) -> None:
    """Register the Make.com webhook draft tool. Called by bootstrap when
    ``settings.email.draft_provider == "make_webhook"``."""
    if tools.get("email.create_draft") is None:
        tools.register(MakeWebhookCreateDraftTool())
