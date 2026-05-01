"""Tool protocol + registry. Every external capability an agent uses MUST be a Tool."""

from __future__ import annotations

from typing import Any, Generic, Protocol, TypeVar, runtime_checkable

from pydantic import BaseModel

TIn = TypeVar("TIn", bound=BaseModel, contravariant=True)
TOut = TypeVar("TOut", bound=BaseModel, covariant=True)


@runtime_checkable
class Tool(Protocol, Generic[TIn, TOut]):
    """A typed callable with pydantic input/output schemas."""

    name: str
    description: str
    input_schema: type[BaseModel]
    output_schema: type[BaseModel]

    def invoke(self, ctx: Any, payload: TIn) -> TOut: ...


class ToolRegistry:
    """Process-wide registry of available tools, keyed by name."""

    def __init__(self) -> None:
        self._tools: dict[str, Tool[Any, Any]] = {}

    def register(self, tool: Tool[Any, Any]) -> None:
        if not isinstance(tool, Tool):
            raise TypeError(f"{tool!r} does not satisfy the Tool protocol")
        if tool.name in self._tools:
            raise ValueError(f"tool already registered: {tool.name}")
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool[Any, Any] | None:
        return self._tools.get(name)

    def names(self) -> list[str]:
        return sorted(self._tools)


# Module-level default registry (Phase 2 will populate this).
default_registry = ToolRegistry()
