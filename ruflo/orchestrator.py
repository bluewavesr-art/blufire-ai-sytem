#!/usr/bin/env python3
"""Blufire Ruflo Orchestrator.

Phase 1: routes tasks to YAML-defined agents through ``blufire.runtime``.
Queens are loaded but their consensus/learning fields are NOT yet enforced;
that's Phase 2 work. The 147 pre-generated agent YAMLs in ``ruflo/agents/`` are
treated as scaffolding (capabilities log a warning if unresolved).
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from concurrent.futures import TimeoutError as FutureTimeout
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from blufire.logging_setup import configure, get_logger, new_run_id
from blufire.runtime.agent_runner import run_agent
from blufire.runtime.capability import AgentBlueprint, CapabilityRegistry
from blufire.runtime.context import RunContext, TenantContext
from blufire.runtime.tool import default_registry
from blufire.settings import Settings, get_settings

RUFLO_DIR = Path(__file__).parent
AGENTS_DIR = RUFLO_DIR / "agents"
QUEENS_DIR = RUFLO_DIR / "queens"
SWARM_PATH = RUFLO_DIR / "swarms" / "blufire-swarm.yaml"
RUFLO_CONFIG = RUFLO_DIR / "config" / "ruflo.yaml"

DEFAULT_AGENT_TIMEOUT = 120.0


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    with path.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    return data if isinstance(data, dict) else {}


@dataclass
class Queen:
    name: str
    role: str
    domains: list[str] = field(default_factory=list)

    @classmethod
    def from_yaml(cls, path: Path) -> Queen:
        data = _load_yaml(path)
        return cls(
            name=data.get("name", path.stem),
            role=data.get("role", "queen"),
            domains=list(data.get("domains", []) or []),
        )


@dataclass
class LoadedAgent:
    blueprint: AgentBlueprint
    raw: dict[str, Any]


class RufloOrchestrator:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.config = _load_yaml(RUFLO_CONFIG)
        self.capabilities = CapabilityRegistry(default_registry, strict=False)
        self.queens: dict[str, Queen] = {}
        self.agents: dict[str, LoadedAgent] = {}
        self.domain_to_queen: dict[str, str] = {}
        self._tenant = TenantContext(settings=self.settings)
        self._log = get_logger("blufire.ruflo").bind(tenant_id=self.settings.tenant.id)

        self._load_queens()
        self._load_agents()
        self._load_swarm()
        self._log.info(
            "ruflo_initialized",
            queens=len(self.queens),
            agents=len(self.agents),
            domains=len({a.blueprint.domain for a in self.agents.values()}),
        )

    def _load_queens(self) -> None:
        if not QUEENS_DIR.is_dir():
            return
        for path in sorted(QUEENS_DIR.glob("*.yaml")):
            queen = Queen.from_yaml(path)
            self.queens[queen.name] = queen

    def _load_agents(self) -> None:
        if not AGENTS_DIR.is_dir():
            return
        for domain_dir in sorted(AGENTS_DIR.iterdir()):
            if not domain_dir.is_dir() or domain_dir.name.startswith("_"):
                continue
            for path in sorted(domain_dir.glob("*.yaml")):
                raw = _load_yaml(path)
                if not raw:
                    continue
                blueprint = self.capabilities.resolve(raw)
                self.agents[blueprint.name] = LoadedAgent(blueprint=blueprint, raw=raw)

    def _load_swarm(self) -> None:
        swarm = _load_yaml(SWARM_PATH)
        for domain, cfg in (swarm.get("domains") or {}).items():
            queen_name = (cfg or {}).get("queen")
            if queen_name:
                self.domain_to_queen[domain] = queen_name

    def _select_agent(self, domain: str | None, capabilities: list[str]) -> AgentBlueprint | None:
        candidates = list(self.agents.values())
        if domain:
            candidates = [a for a in candidates if a.blueprint.domain == domain] or candidates
        if not candidates:
            return None
        if not capabilities:
            return candidates[0].blueprint
        wanted = set(capabilities)
        scored = [
            (sum(1 for c in a.blueprint.capabilities if c.name in wanted), a.blueprint)
            for a in candidates
        ]
        scored.sort(key=lambda pair: pair[0], reverse=True)
        return scored[0][1] if scored else None

    def route_task(
        self,
        task: str,
        *,
        domain: str | None = None,
        capabilities: list[str] | None = None,
        run_id: str | None = None,
    ) -> dict[str, Any]:
        capabilities = capabilities or []
        blueprint = self._select_agent(domain, capabilities)
        if blueprint is None:
            return {"status": "no_agent", "domain": domain}
        ctx = RunContext(
            tenant=self._tenant,
            agent=blueprint.name,
            run_id=run_id or new_run_id(),
        )
        try:
            return run_agent(ctx, blueprint, task)
        except Exception as exc:
            ctx.log.exception("agent_run_failed", error_class=type(exc).__name__)
            return {"status": "error", "agent": blueprint.name, "error": str(exc)}

    def run_parallel(
        self,
        tasks: list[dict[str, Any]],
        *,
        max_workers: int = 5,
        timeout: float = DEFAULT_AGENT_TIMEOUT,
    ) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            future_to_task = {
                pool.submit(
                    self.route_task,
                    task["description"],
                    domain=task.get("domain"),
                    capabilities=task.get("capabilities"),
                ): task
                for task in tasks
            }
            for future in as_completed(future_to_task, timeout=timeout):
                task = future_to_task[future]
                try:
                    results.append({"task": task, "result": future.result(timeout=timeout)})
                except FutureTimeout:
                    results.append({"task": task, "result": {"status": "timeout"}})
                except Exception as exc:
                    results.append({"task": task, "result": {"status": "error", "error": str(exc)}})
        return results

    def status(self) -> dict[str, Any]:
        domains: dict[str, int] = {}
        for agent in self.agents.values():
            domains[agent.blueprint.domain] = domains.get(agent.blueprint.domain, 0) + 1
        return {
            "platform": (self.config.get("platform") or {}).get("name"),
            "queens": [
                {"name": q.name, "role": q.role, "domains": q.domains} for q in self.queens.values()
            ],
            "total_agents": len(self.agents),
            "agents_by_domain": domains,
        }


def main() -> None:
    settings = get_settings()
    configure(settings)
    orchestrator = RufloOrchestrator(settings)
    status = orchestrator.status()
    log = get_logger("blufire.ruflo").bind(tenant_id=settings.tenant.id)
    log.info("ruflo_ready", **status)


if __name__ == "__main__":
    main()
