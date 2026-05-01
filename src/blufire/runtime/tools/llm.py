"""LLM-backed Tools (drafting, scoring, analysis)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from blufire.agents.crm_pipeline import analyze_pipeline
from blufire.agents.daily_lead_gen import _draft_with_claude as draft_from_apollo
from blufire.agents.daily_lead_gen import _load_system_prompt as load_default_system_prompt
from blufire.agents.email_outreach import draft_email
from blufire.agents.lead_generation import score_lead
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
        result = draft_email(
            ctx,
            payload.contact_props,
            campaign_context=payload.campaign_context,
            system_prompt=payload.system_prompt,
        )
        return DraftOutreachEmailOutput(subject=result["subject"], body=result["body"])


# ---------------------------------------------------------------------------
# llm.score_prospect
# ---------------------------------------------------------------------------


class ScoreProspectInput(BaseModel):
    """Apollo person dict plus optional org info. We pass the full raw record
    rather than a normalized shape so the scorer can use any field the
    upstream provider exposes."""

    person: dict[str, Any] = Field(default_factory=dict)


class ScoreProspectOutput(BaseModel):
    score: int = Field(default=0, ge=0, le=10)
    reason: str = ""


class ScoreProspectTool(BaseTool[ScoreProspectInput, ScoreProspectOutput]):
    name = "llm.score_prospect"
    description = "Score a prospect 1-10 for sales-fit; include a one-sentence reason."
    input_schema = ScoreProspectInput
    output_schema = ScoreProspectOutput

    def invoke(self, ctx: RunContext, payload: ScoreProspectInput) -> ScoreProspectOutput:
        result = score_lead(ctx, payload.person)
        # The Phase 1 helper returns a free-form dict; coerce defensively.
        score = result.get("score", 0) if isinstance(result, dict) else 0
        reason = result.get("reason", "") if isinstance(result, dict) else ""
        try:
            score_int = max(0, min(10, int(score)))
        except (TypeError, ValueError):
            score_int = 0
        return ScoreProspectOutput(score=score_int, reason=str(reason))


# ---------------------------------------------------------------------------
# llm.analyze_pipeline
# ---------------------------------------------------------------------------


class AnalyzePipelineInput(BaseModel):
    deals: list[dict[str, Any]] = Field(default_factory=list)


class PipelineAction(BaseModel):
    deal_name: str
    action: str
    reason: str = ""


class AnalyzePipelineOutput(BaseModel):
    summary: str = ""
    actions: list[PipelineAction] = Field(default_factory=list)


class AnalyzePipelineTool(BaseTool[AnalyzePipelineInput, AnalyzePipelineOutput]):
    name = "llm.analyze_pipeline"
    description = "Analyze a CRM pipeline and propose follow-up actions."
    input_schema = AnalyzePipelineInput
    output_schema = AnalyzePipelineOutput

    def invoke(self, ctx: RunContext, payload: AnalyzePipelineInput) -> AnalyzePipelineOutput:
        result = analyze_pipeline(ctx, payload.deals)
        summary = str(result.get("summary") or "")
        raw_actions = result.get("actions") if isinstance(result, dict) else None
        actions: list[PipelineAction] = []
        if isinstance(raw_actions, list):
            for item in raw_actions:
                if not isinstance(item, dict):
                    continue
                deal_name = item.get("deal_name")
                action = item.get("action")
                if not deal_name or not action:
                    continue
                actions.append(
                    PipelineAction(
                        deal_name=str(deal_name),
                        action=str(action),
                        reason=str(item.get("reason") or ""),
                    )
                )
        return AnalyzePipelineOutput(summary=summary, actions=actions)


# ---------------------------------------------------------------------------
# llm.draft_outreach_email_from_prospect
#
# Distinct from llm.draft_outreach_email because the input shape is different:
# this one takes a rich Apollo enrichment record (firmographics, headline,
# industry, etc.) rather than a sparse HubSpot contact dict. Used by the
# daily_lead_gen flow whose prompt is tuned for Apollo's data.
# ---------------------------------------------------------------------------


class DraftOutreachFromProspectInput(BaseModel):
    person: dict[str, Any] = Field(default_factory=dict)
    system_prompt: str | None = None


class DraftOutreachFromProspectOutput(BaseModel):
    subject: str
    body: str


class DraftOutreachFromProspectTool(
    BaseTool[DraftOutreachFromProspectInput, DraftOutreachFromProspectOutput]
):
    name = "llm.draft_outreach_email_from_prospect"
    description = "Draft a cold-outreach {subject, body} from a rich prospect record."
    input_schema = DraftOutreachFromProspectInput
    output_schema = DraftOutreachFromProspectOutput

    def invoke(
        self, ctx: RunContext, payload: DraftOutreachFromProspectInput
    ) -> DraftOutreachFromProspectOutput:
        prompt = payload.system_prompt or load_default_system_prompt(ctx)
        result = draft_from_apollo(ctx, payload.person, prompt)
        return DraftOutreachFromProspectOutput(
            subject=str(result["subject"]), body=str(result["body"])
        )
