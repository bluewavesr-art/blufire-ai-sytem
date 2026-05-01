"""LLM-backed Tools (drafting, scoring, etc.)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from blufire.agents.email_outreach import draft_email
from blufire.runtime.context import RunContext
from blufire.runtime.tools._base import BaseTool


class DraftOutreachEmailInput(BaseModel):
    contact_props: dict[str, Any] = Field(default_factory=dict)
    campaign_context: str
    system_prompt: str | None = None


class DraftOutreachEmailOutput(BaseModel):
    subject: str
    body: str


class DraftOutreachEmailTool(BaseTool[DraftOutreachEmailInput, DraftOutreachEmailOutput]):
    name = "llm.draft_outreach_email"
    description = "Ask Claude for a personalized cold-outreach {subject, body}."
    input_schema = DraftOutreachEmailInput
    output_schema = DraftOutreachEmailOutput

    def invoke(self, ctx: RunContext, payload: DraftOutreachEmailInput) -> DraftOutreachEmailOutput:
        # Reuse the Phase 1 drafting helper rather than reimplementing the prompt.
        # If/when the prompt needs to diverge, fork it here.
        result = draft_email(
            ctx,
            payload.contact_props,
            campaign_context=payload.campaign_context,
            system_prompt=payload.system_prompt,
        )
        return DraftOutreachEmailOutput(subject=result["subject"], body=result["body"])
