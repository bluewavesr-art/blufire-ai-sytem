"""Capability-driven runner for the crm_pipeline agent.

Mirrors the Phase 1 logic in ``src/blufire/agents/crm_pipeline.py`` but
routes every external call through the ToolRegistry. Different shape from
email_outreach (no SMTP, no compliance) and lead_generation (no external
prospect search, no per-record loop): the agent reads the deal pipeline,
asks the LLM for a holistic analysis, and (optionally) creates one task
per recommended action.

The ``auto_tasks`` flag is the same kill-switch as Phase 1: with it off,
the agent is read-only and just returns the analysis. With it on, each
LLM-recommended action becomes a CRM task. Task creation failures are
logged per-deal but do NOT fail the run.
"""

from __future__ import annotations

from typing import Any

from blufire.runtime.capability import AgentBlueprint, Capability, CapabilityUnresolved
from blufire.runtime.context import RunContext
from blufire.runtime.tool import Tool, ToolRegistry, default_registry
from blufire.runtime.tools.crm import CreateTaskInput, ListDealsInput
from blufire.runtime.tools.llm import AnalyzePipelineInput

MAX_DEALS_FOR_ANALYSIS = 50


def _required(registry: ToolRegistry, name: str) -> Tool[Any, Any]:
    tool = registry.get(name)
    if tool is None:
        raise CapabilityUnresolved(f"required tool not registered: {name}")
    return tool


def run(
    ctx: RunContext,
    blueprint: AgentBlueprint,
    *,
    auto_tasks: bool = False,
    limit: int = MAX_DEALS_FOR_ANALYSIS,
    registry: ToolRegistry | None = None,
) -> dict[str, Any]:
    """Run the crm_pipeline capability via the tool registry.

    Returns ``{"status": ..., "summary": ..., "actions": [...], "tasks_created": int}``
    matching the Phase 1 module's shape so test suites can assert parity.
    """
    registry = registry or default_registry
    log = ctx.log.bind(via="capability", agent=blueprint.name, auto_tasks=auto_tasks)

    cap: Capability | None = next(
        (c for c in blueprint.capabilities if c.name == "crm_pipeline.analyze_and_act"),
        None,
    )
    if cap is None:
        raise CapabilityUnresolved(
            f"blueprint {blueprint.name!r} does not declare crm_pipeline.analyze_and_act"
        )
    tools = {name: _required(registry, name) for name in cap.tool_names}

    deals_out = tools["crm.list_deals"].invoke(ctx, ListDealsInput(limit=limit))
    log.info("pipeline_fetched", deal_count=len(deals_out.deals))

    if not deals_out.deals:
        log.info("pipeline_empty")
        return {"status": "no_deals", "summary": None, "actions": [], "tasks_created": 0}

    # The Phase 1 LLM tool wants a list of native deal dicts (not our
    # provider-agnostic DealRecord). Pass through {id, properties} as the
    # analyzer keys off properties.
    analyzer_input = [{"id": d.id, "properties": d.properties} for d in deals_out.deals]
    analysis = tools["llm.analyze_pipeline"].invoke(ctx, AnalyzePipelineInput(deals=analyzer_input))
    log.info(
        "pipeline_analyzed",
        actions_proposed=len(analysis.actions),
        summary_chars=len(analysis.summary),
    )

    actions = [
        {"deal_name": a.deal_name, "action": a.action, "reason": a.reason} for a in analysis.actions
    ]

    tasks_created = 0
    if auto_tasks and actions:
        for action in actions:
            task_out = tools["crm.create_task"].invoke(
                ctx,
                CreateTaskInput(title=f"[Blufire] {action['action']} - {action['deal_name']}"),
            )
            if task_out.created:
                tasks_created += 1
            else:
                log.warning(
                    "task_create_failed",
                    deal_name=action["deal_name"],
                    error_class=task_out.error,
                )

    return {
        "status": "ok",
        "summary": analysis.summary,
        "actions": actions,
        "tasks_created": tasks_created,
    }
