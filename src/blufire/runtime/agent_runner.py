"""Phase 1 agent runner: a thin wrapper around a Claude call that propagates
``RunContext`` and uses the central LLM client. Phase 2 will turn this into a
real tool-use loop driven by the ``CapabilityRegistry``."""

from __future__ import annotations

from typing import Any

from blufire.llm import build_client, complete
from blufire.runtime.capability import AgentBlueprint
from blufire.runtime.context import RunContext


def run_agent(
    ctx: RunContext,
    blueprint: AgentBlueprint,
    user_message: str,
    *,
    max_tokens: int = 1024,
    temperature: float = 0.7,
) -> dict[str, Any]:
    """Execute a single Claude turn for the agent. Returns a result dict."""
    log = ctx.log.bind(agent_domain=blueprint.domain)
    log.info("agent_run_start", capabilities=[c.name for c in blueprint.capabilities])

    settings = ctx.tenant.settings
    client = build_client(settings)
    model = blueprint.model or settings.models.default

    system = (
        f"You are {blueprint.name}, a specialized agent in the {blueprint.domain} domain. "
        f"{blueprint.description}"
    )

    text = complete(
        client,
        model=model,
        prompt=user_message,
        max_tokens=max_tokens,
        system=system,
        temperature=temperature,
    )

    log.info("agent_run_done", output_chars=len(text))
    return {
        "agent": blueprint.name,
        "domain": blueprint.domain,
        "model": model,
        "result": text,
    }
