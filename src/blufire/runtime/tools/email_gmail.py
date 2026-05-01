"""Gmail/SMTP implementation of ``email.send_smtp``."""

from __future__ import annotations

from blufire.integrations.smtp import EmailHeaders, SmtpSender
from blufire.runtime.context import RunContext
from blufire.runtime.tool import ToolRegistry
from blufire.runtime.tools._base import BaseTool
from blufire.runtime.tools.email import SendEmailInput, SendEmailOutput


class GmailSendEmailTool(BaseTool[SendEmailInput, SendEmailOutput]):
    name = "email.send_smtp"
    description = "Send an email via the tenant's configured Gmail SMTP relay."
    input_schema = SendEmailInput
    output_schema = SendEmailOutput

    def invoke(self, ctx: RunContext, payload: SendEmailInput) -> SendEmailOutput:
        sender = SmtpSender(ctx.tenant.settings)
        sender.send(
            to=payload.to,
            subject=payload.subject,
            body=payload.body,
            headers=EmailHeaders(list_unsubscribe=payload.list_unsubscribe),
        )
        return SendEmailOutput()


def register(tools: ToolRegistry) -> None:
    """Register Gmail's email tools. Called by bootstrap when
    ``settings.email.provider == "gmail"``."""
    if tools.get("email.send_smtp") is None:
        tools.register(GmailSendEmailTool())
