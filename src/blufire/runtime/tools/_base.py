"""Helpers for declaring concrete Tool implementations.

The ``Tool`` Protocol in ``runtime/tool.py`` only requires four attributes
(name, description, input_schema, output_schema) and an ``invoke()`` method.
``BaseTool`` is a Generic class that lets a tool be declared as

    class MyTool(BaseTool[MyIn, MyOut]):
        name = "ns.my_tool"
        description = "..."
        input_schema = MyIn
        output_schema = MyOut

        def invoke(self, ctx: RunContext, payload: MyIn) -> MyOut:
            ...

without having to repeat the type variables on every method or duplicate
the schema references. ``isinstance(MyTool(), Tool)`` returns True because
the Protocol is ``runtime_checkable``.
"""

from __future__ import annotations

from typing import ClassVar, Generic, TypeVar

from pydantic import BaseModel

from blufire.runtime.context import RunContext

TIn = TypeVar("TIn", bound=BaseModel)
TOut = TypeVar("TOut", bound=BaseModel)


class BaseTool(Generic[TIn, TOut]):
    name: ClassVar[str]
    description: ClassVar[str]
    input_schema: ClassVar[type[BaseModel]]
    output_schema: ClassVar[type[BaseModel]]

    def invoke(self, ctx: RunContext, payload: TIn) -> TOut:
        raise NotImplementedError
