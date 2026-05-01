from __future__ import annotations

from unittest.mock import patch

from blufire.runtime.agent_runner import run_agent
from blufire.runtime.capability import AgentBlueprint
from blufire.runtime.context import RunContext, TenantContext


def test_run_agent_invokes_complete(tmp_settings) -> None:
    bp = AgentBlueprint(
        name="agent_x",
        domain="core",
        description="test agent",
        capabilities=(),
        model="claude-sonnet-4-20250514",
    )
    ctx = RunContext(tenant=TenantContext(settings=tmp_settings), agent="agent_x", run_id="r1")

    with (
        patch("blufire.runtime.agent_runner.complete", return_value="ok-result") as mocked,
        patch("blufire.runtime.agent_runner.build_client", return_value=object()),
    ):
        result = run_agent(ctx, bp, "do the thing")

    mocked.assert_called_once()
    assert result["agent"] == "agent_x"
    assert result["result"] == "ok-result"
    assert result["model"] == "claude-sonnet-4-20250514"
