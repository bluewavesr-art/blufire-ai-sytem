"""Capability registry. Maps YAML capability strings to one-or-more Tool names.

Phase 1: unresolved capabilities log a warning and don't fail boot.
Phase 2: this becomes strict (raise ``CapabilityUnresolved``).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from blufire.logging_setup import get_logger
from blufire.runtime.tool import ToolRegistry, default_registry


class CapabilityUnresolved(LookupError):
    """Raised in strict mode (Phase 2) when no Tool backs a capability."""


@dataclass(frozen=True)
class Capability:
    name: str
    tool_names: tuple[str, ...] = ()
    required: bool = False


@dataclass(frozen=True)
class AgentBlueprint:
    name: str
    domain: str
    description: str
    capabilities: tuple[Capability, ...] = field(default_factory=tuple)
    model: str | None = None


class CapabilityRegistry:
    def __init__(self, tools: ToolRegistry | None = None, *, strict: bool = False) -> None:
        self._tools = tools or default_registry
        self._strict = strict
        self._capabilities: dict[str, Capability] = {}
        self._log = get_logger("blufire.runtime.capability")

    def register(self, capability: Capability) -> None:
        self._capabilities[capability.name] = capability

    def resolve(self, agent_yaml: dict[str, Any]) -> AgentBlueprint:
        name = agent_yaml.get("name", "<unnamed>")
        domain = agent_yaml.get("domain", "<unknown>")
        description = agent_yaml.get("description", "")
        model = agent_yaml.get("model")

        resolved: list[Capability] = []
        unresolved: list[str] = []
        for cap_name in agent_yaml.get("capabilities", []) or []:
            cap = self._capabilities.get(cap_name)
            if cap is None:
                unresolved.append(cap_name)
                resolved.append(Capability(name=cap_name, tool_names=(), required=False))
                continue
            missing = [t for t in cap.tool_names if self._tools.get(t) is None]
            if missing:
                unresolved.append(f"{cap_name} (missing tools: {','.join(missing)})")
            resolved.append(cap)

        if unresolved:
            msg = "capability_unresolved"
            self._log.warning(msg, agent=name, unresolved=unresolved)
            if self._strict:
                raise CapabilityUnresolved(f"agent {name!r}: unresolved capabilities {unresolved}")

        return AgentBlueprint(
            name=name,
            domain=domain,
            description=description,
            capabilities=tuple(resolved),
            model=model,
        )
