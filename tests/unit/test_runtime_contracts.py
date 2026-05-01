from __future__ import annotations

from pydantic import BaseModel

from blufire.runtime.capability import Capability, CapabilityRegistry, CapabilityUnresolved
from blufire.runtime.tool import ToolRegistry


class _IO(BaseModel):
    x: int


class _GoodTool:
    name = "good"
    description = "ok"
    input_schema = _IO
    output_schema = _IO

    def invoke(self, ctx, payload):  # type: ignore[no-untyped-def]
        return _IO(x=payload.x + 1)


def test_tool_registry_register_and_get() -> None:
    reg = ToolRegistry()
    reg.register(_GoodTool())  # type: ignore[arg-type]
    assert reg.get("good") is not None
    assert reg.get("missing") is None
    assert "good" in reg.names()


def test_capability_unresolved_logs_in_phase1_does_not_raise(tmp_settings) -> None:
    tools = ToolRegistry()
    caps = CapabilityRegistry(tools, strict=False)
    caps.register(Capability(name="advertised", tool_names=("missing_tool",)))
    bp = caps.resolve(
        {
            "name": "agent_a",
            "domain": "core",
            "description": "x",
            "capabilities": ["advertised", "totally_unknown"],
        }
    )
    assert bp.name == "agent_a"
    assert {c.name for c in bp.capabilities} == {"advertised", "totally_unknown"}


def test_capability_unresolved_raises_in_strict_mode() -> None:
    import pytest

    tools = ToolRegistry()
    caps = CapabilityRegistry(tools, strict=True)
    with pytest.raises(CapabilityUnresolved):
        caps.resolve({"name": "x", "domain": "core", "description": "", "capabilities": ["nope"]})
