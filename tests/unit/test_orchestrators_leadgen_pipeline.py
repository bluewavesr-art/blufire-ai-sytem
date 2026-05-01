"""Tests for the Phase 2 lead_generation and crm_pipeline orchestrators.

Stub every Tool the orchestrators depend on so we exercise the full
control flow (search → score → dedup → create) and (list_deals → analyze
→ create_task) without hitting any external service. Parity with the
Phase 1 module path is asserted via counter / result shape.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from blufire.runtime.bootstrap import (
    CRM_PIPELINE_BLUEPRINT,
    LEAD_GENERATION_BLUEPRINT,
    PROSPECT_PROVIDERS,
    ProviderNotImplemented,
    bootstrap,
)
from blufire.runtime.capability import CapabilityRegistry, CapabilityUnresolved
from blufire.runtime.context import RunContext, TenantContext
from blufire.runtime.orchestrators import crm_pipeline as pipe_orch
from blufire.runtime.orchestrators import lead_generation as lg_orch
from blufire.runtime.tool import Tool, ToolRegistry
from blufire.runtime.tools.crm import (
    ContactRecord,
    CreateContactOutput,
    CreateTaskOutput,
    DealRecord,
    ListDealsOutput,
    SearchContactsOutput,
)
from blufire.runtime.tools.llm import (
    AnalyzePipelineOutput,
    PipelineAction,
    ScoreProspectOutput,
)
from blufire.runtime.tools.prospect import PersonRecord, SearchPeopleOutput


def _stub(name: str, output: Any) -> Any:
    tool = MagicMock(spec=Tool)
    tool.name = name
    tool.invoke.return_value = output
    return tool


def _ctx(settings: Any, agent: str) -> RunContext:
    return RunContext(tenant=TenantContext(settings=settings), agent=agent, run_id="r-1")


# ---------------------------------------------------------------------------
# lead_generation orchestrator
# ---------------------------------------------------------------------------


def _lg_registry(
    people: list[dict[str, Any]],
    *,
    score: int = 8,
    existing_emails: set[str] | None = None,
) -> ToolRegistry:
    """Build a registry with stubs sized to the prospect list. ``existing_emails``
    drives the dedup branch — if a person's email is in the set, the search
    tool returns a hit and the orchestrator should skip the create call."""
    existing_emails = existing_emails or set()
    person_records = [
        PersonRecord(
            email=p.get("email"),
            first_name=p.get("first_name"),
            last_name=p.get("last_name"),
            title=p.get("title"),
            company=(p.get("organization") or {}).get("name"),
            raw=p,
        )
        for p in people
    ]
    reg = ToolRegistry()
    reg.register(_stub("prospect.search_people", SearchPeopleOutput(people=person_records)))
    reg.register(_stub("llm.score_prospect", ScoreProspectOutput(score=score, reason="ok")))

    # Per-call dedup: a single MagicMock with side_effect mapping email → result.
    search_tool = MagicMock(spec=Tool)
    search_tool.name = "crm.search_contacts"

    def search_side_effect(_ctx: Any, payload: Any) -> SearchContactsOutput:
        if payload.email in existing_emails:
            return SearchContactsOutput(
                contacts=[ContactRecord(id=f"existing-{payload.email}", properties={})]
            )
        return SearchContactsOutput(contacts=[])

    search_tool.invoke.side_effect = search_side_effect
    reg.register(search_tool)

    create_tool = MagicMock(spec=Tool)
    create_tool.name = "crm.create_contact"
    create_tool.invoke.return_value = CreateContactOutput(contact_id="new-id")
    reg.register(create_tool)
    return reg


def test_leadgen_full_path_creates_one_contact_per_person(tmp_settings: Any) -> None:
    people = [
        {"first_name": "A", "last_name": "X", "email": "a@x.test", "title": "CEO"},
        {"first_name": "B", "last_name": "Y", "email": "b@y.test", "title": "Owner"},
    ]
    reg = _lg_registry(people)
    out = lg_orch.run(
        _ctx(tmp_settings, "lead_generation"),
        LEAD_GENERATION_BLUEPRINT,
        job_titles=["CEO"],
        registry=reg,
    )
    counters = out["counters"]
    assert counters["fetched"] == 2
    assert counters["created"] == 2
    assert counters["skipped_existing"] == 0
    assert counters["skipped_no_email"] == 0
    assert counters["score_failures"] == 0
    assert reg.get("crm.create_contact").invoke.call_count == 2  # type: ignore[union-attr]


def test_leadgen_dedup_skips_existing_contacts(tmp_settings: Any) -> None:
    people = [
        {"first_name": "A", "last_name": "X", "email": "old@x.test"},
        {"first_name": "B", "last_name": "Y", "email": "new@y.test"},
    ]
    reg = _lg_registry(people, existing_emails={"old@x.test"})
    out = lg_orch.run(
        _ctx(tmp_settings, "lead_generation"),
        LEAD_GENERATION_BLUEPRINT,
        job_titles=["CEO"],
        registry=reg,
    )
    counters = out["counters"]
    assert counters["skipped_existing"] == 1
    assert counters["created"] == 1
    # The dedup'd contact still appears in results, with the existing id.
    existing_result = next(r for r in out["results"] if r["person"]["email"] == "old@x.test")
    assert existing_result["hubspot_contact_id"] == "existing-old@x.test"


def test_leadgen_skips_no_email_before_scoring(tmp_settings: Any) -> None:
    people = [
        {"first_name": "Nameless", "last_name": "X", "email": None},
        {"first_name": "Has", "last_name": "Email", "email": "ok@x.test"},
    ]
    reg = _lg_registry(people)
    out = lg_orch.run(
        _ctx(tmp_settings, "lead_generation"),
        LEAD_GENERATION_BLUEPRINT,
        job_titles=["CEO"],
        registry=reg,
    )
    assert out["counters"]["skipped_no_email"] == 1
    # Scorer was only called for the prospect with an email.
    assert reg.get("llm.score_prospect").invoke.call_count == 1  # type: ignore[union-attr]


def test_leadgen_score_threshold_skips_low_scorers(tmp_settings: Any) -> None:
    people = [{"first_name": "Low", "last_name": "Score", "email": "low@x.test"}]
    reg = _lg_registry(people, score=3)
    out = lg_orch.run(
        _ctx(tmp_settings, "lead_generation"),
        LEAD_GENERATION_BLUEPRINT,
        job_titles=["CEO"],
        score_threshold=7,
        registry=reg,
    )
    assert out["counters"]["skipped_below_threshold"] == 1
    assert out["counters"]["created"] == 0
    # Search + create were skipped entirely.
    assert reg.get("crm.search_contacts").invoke.call_count == 0  # type: ignore[union-attr]
    assert reg.get("crm.create_contact").invoke.call_count == 0  # type: ignore[union-attr]


def test_leadgen_score_failure_doesnt_abort_run(tmp_settings: Any) -> None:
    people = [
        {"first_name": "A", "last_name": "X", "email": "a@x.test"},
        {"first_name": "B", "last_name": "Y", "email": "b@y.test"},
    ]
    reg = _lg_registry(people)
    failing_scorer = MagicMock(spec=Tool)
    failing_scorer.name = "llm.score_prospect"
    failing_scorer.invoke.side_effect = [
        RuntimeError("LLM down"),
        ScoreProspectOutput(score=8, reason="ok"),
    ]
    # Replace the scorer
    reg = ToolRegistry()
    reg.register(
        _stub(
            "prospect.search_people",
            SearchPeopleOutput(people=[PersonRecord(email=p["email"], raw=p) for p in people]),
        )
    )
    reg.register(failing_scorer)
    reg.register(_stub("crm.search_contacts", SearchContactsOutput(contacts=[])))
    reg.register(_stub("crm.create_contact", CreateContactOutput(contact_id="x")))

    out = lg_orch.run(
        _ctx(tmp_settings, "lead_generation"),
        LEAD_GENERATION_BLUEPRINT,
        job_titles=["CEO"],
        registry=reg,
    )
    assert out["counters"]["score_failures"] == 1
    assert out["counters"]["fetched"] == 2


def test_leadgen_raises_when_required_tool_missing(tmp_settings: Any) -> None:
    with pytest.raises(CapabilityUnresolved):
        lg_orch.run(
            _ctx(tmp_settings, "lead_generation"),
            LEAD_GENERATION_BLUEPRINT,
            job_titles=["CEO"],
            registry=ToolRegistry(),
        )


# ---------------------------------------------------------------------------
# crm_pipeline orchestrator
# ---------------------------------------------------------------------------


def _pipe_registry(
    deals: list[dict[str, Any]],
    *,
    actions: list[dict[str, str]] | None = None,
    summary: str = "Pipeline looks healthy.",
    task_create_succeeds: bool = True,
) -> ToolRegistry:
    actions = actions or []
    deal_records = [DealRecord(id=str(d["id"]), properties=d.get("properties", {})) for d in deals]
    pipeline_actions = [PipelineAction(**a) for a in actions]
    reg = ToolRegistry()
    reg.register(_stub("crm.list_deals", ListDealsOutput(deals=deal_records)))
    reg.register(
        _stub(
            "llm.analyze_pipeline",
            AnalyzePipelineOutput(summary=summary, actions=pipeline_actions),
        )
    )
    reg.register(
        _stub(
            "crm.create_task",
            CreateTaskOutput(task_id="t-1", created=task_create_succeeds, error=None),
        )
    )
    return reg


def test_pipeline_no_deals_returns_no_deals_status(tmp_settings: Any) -> None:
    reg = _pipe_registry([])
    out = pipe_orch.run(_ctx(tmp_settings, "crm_pipeline"), CRM_PIPELINE_BLUEPRINT, registry=reg)
    assert out["status"] == "no_deals"
    # Analysis is NOT called when there are no deals — saves a Claude token.
    assert reg.get("llm.analyze_pipeline").invoke.call_count == 0  # type: ignore[union-attr]
    # Task creation likewise skipped.
    assert reg.get("crm.create_task").invoke.call_count == 0  # type: ignore[union-attr]


def test_pipeline_read_only_does_not_create_tasks(tmp_settings: Any) -> None:
    actions = [{"deal_name": "Acme", "action": "Follow up", "reason": "stale"}]
    reg = _pipe_registry([{"id": "1", "properties": {"dealname": "Acme"}}], actions=actions)
    out = pipe_orch.run(
        _ctx(tmp_settings, "crm_pipeline"),
        CRM_PIPELINE_BLUEPRINT,
        auto_tasks=False,
        registry=reg,
    )
    assert out["status"] == "ok"
    assert out["tasks_created"] == 0
    assert len(out["actions"]) == 1
    assert reg.get("crm.create_task").invoke.call_count == 0  # type: ignore[union-attr]


def test_pipeline_auto_tasks_creates_one_per_action(tmp_settings: Any) -> None:
    actions = [
        {"deal_name": "Acme", "action": "Follow up", "reason": "stale"},
        {"deal_name": "Globex", "action": "Send proposal", "reason": "ready"},
    ]
    reg = _pipe_registry([{"id": "1", "properties": {"dealname": "Acme"}}], actions=actions)
    out = pipe_orch.run(
        _ctx(tmp_settings, "crm_pipeline"),
        CRM_PIPELINE_BLUEPRINT,
        auto_tasks=True,
        registry=reg,
    )
    assert out["tasks_created"] == 2
    assert reg.get("crm.create_task").invoke.call_count == 2  # type: ignore[union-attr]


def test_pipeline_task_failure_does_not_abort_run(tmp_settings: Any) -> None:
    actions = [
        {"deal_name": "A", "action": "x", "reason": ""},
        {"deal_name": "B", "action": "y", "reason": ""},
    ]
    reg = _pipe_registry([{"id": "1", "properties": {}}], actions=actions)
    # First task creation fails, second succeeds.
    failing_task = MagicMock(spec=Tool)
    failing_task.name = "crm.create_task"
    failing_task.invoke.side_effect = [
        CreateTaskOutput(task_id=None, created=False, error="HubSpotTaskError"),
        CreateTaskOutput(task_id="t-2", created=True),
    ]
    # Swap the task tool
    reg2 = ToolRegistry()
    reg2.register(reg.get("crm.list_deals"))  # type: ignore[arg-type]
    reg2.register(reg.get("llm.analyze_pipeline"))  # type: ignore[arg-type]
    reg2.register(failing_task)

    out = pipe_orch.run(
        _ctx(tmp_settings, "crm_pipeline"),
        CRM_PIPELINE_BLUEPRINT,
        auto_tasks=True,
        registry=reg2,
    )
    assert out["tasks_created"] == 1
    assert len(out["actions"]) == 2  # both actions still surfaced to caller


def test_pipeline_raises_when_required_tool_missing(tmp_settings: Any) -> None:
    with pytest.raises(CapabilityUnresolved):
        pipe_orch.run(
            _ctx(tmp_settings, "crm_pipeline"),
            CRM_PIPELINE_BLUEPRINT,
            registry=ToolRegistry(),
        )


# ---------------------------------------------------------------------------
# Prospect provider dispatch
# ---------------------------------------------------------------------------


def test_apollo_is_default_prospect_provider(tmp_settings: Any) -> None:
    assert tmp_settings.prospect.provider == "apollo"
    tools = ToolRegistry()
    bootstrap(tmp_settings, tools, CapabilityRegistry(tools))
    tool = tools.get("prospect.search_people")
    assert tool is not None
    assert type(tool).__name__ == "ApolloSearchPeopleTool"


def test_unimplemented_prospect_provider_raises(tmp_settings: Any) -> None:
    tmp_settings.prospect.provider = "zoominfo"  # type: ignore[assignment]
    tools = ToolRegistry()
    with pytest.raises(ProviderNotImplemented, match="prospect.provider='zoominfo'"):
        bootstrap(tmp_settings, tools, CapabilityRegistry(tools))


def test_prospect_dispatch_table_only_contains_runtime_paths() -> None:
    for provider, module_path in PROSPECT_PROVIDERS.items():
        assert isinstance(provider, str) and provider
        assert module_path.startswith("blufire.runtime.tools.")
