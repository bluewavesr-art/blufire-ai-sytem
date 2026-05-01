"""Boot the orchestrator with the shipped queens + sample agent YAMLs."""

from __future__ import annotations

import pytest
from ruflo.orchestrator import RufloOrchestrator


def test_orchestrator_boots_and_reports_status(tmp_settings) -> None:
    orch = RufloOrchestrator(tmp_settings)
    status = orch.status()
    assert status["total_agents"] >= 1, "At least one agent YAML should be loaded"
    assert isinstance(status["queens"], list)
    assert "agents_by_domain" in status


def test_orchestrator_route_task_picks_agent(tmp_settings) -> None:
    orch = RufloOrchestrator(tmp_settings)
    if not orch.agents:
        pytest.skip("no agents shipped under ruflo/agents/")
    # Pick the first domain we have an agent for.
    sample_domain = next(iter(orch.agents.values())).blueprint.domain
    bp = orch._select_agent(sample_domain, capabilities=[])
    assert bp is not None
    assert bp.domain == sample_domain
