"""Tenant + run context propagated through every Tool invocation."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

import structlog

from blufire.settings import Settings


@dataclass(frozen=True)
class TenantContext:
    settings: Settings

    @property
    def id(self) -> str:
        return self.settings.tenant.id


@dataclass(frozen=True)
class RunContext:
    tenant: TenantContext
    agent: str
    run_id: str = field(default_factory=lambda: str(uuid.uuid4()))

    @property
    def log(self) -> structlog.stdlib.BoundLogger:
        return structlog.get_logger("blufire.runtime").bind(
            tenant_id=self.tenant.id,
            agent=self.agent,
            run_id=self.run_id,
        )

    def child(self, agent: str) -> RunContext:
        """Spawn a child context (same run_id, different agent name)."""
        return RunContext(tenant=self.tenant, agent=agent, run_id=self.run_id)
