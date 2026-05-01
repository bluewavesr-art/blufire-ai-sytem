"""Email-delivery Tools."""

from __future__ import annotations

from pydantic import BaseModel

from blufire.integrations.smtp import EmailHeaders, SmtpSender
from blufire.runtime.context import RunContext
from blufire.runtime.tools._base import BaseTool


class SendEmailInput(BaseModel):
    to: str
    subject: str
    body: str
    list_unsubscribe: str | None = None


class SendEmailOutput(BaseModel):
    sent: bool = True


class SendEmailTool(BaseTool[SendEmailInput, SendEmailOutput]):
    name = "email.send_smtp"
    description = "Send an email via the tenant's configured SMTP relay."
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
