#!/usr/bin/env python3
"""Blufire Ruflo Orchestrator — Queens direct the swarm of agents."""

import os
import sys
import json
import time
import yaml
import logging
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

import anthropic
from dotenv import load_dotenv

load_dotenv("/root/.env")
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(), logging.FileHandler("logs/ruflo.log", mode="a")],
)
log = logging.getLogger("ruflo")

RUFLO_DIR = Path(__file__).parent
AGENTS_DIR = RUFLO_DIR / "agents"
QUEENS_DIR = RUFLO_DIR / "queens"
CONFIG_PATH = RUFLO_DIR / "config" / "ruflo.yaml"


class Agent:
    """Represents a single Ruflo agent."""

    def __init__(self, config_path):
        with open(config_path) as f:
            self.config = yaml.safe_load(f)
        self.name = self.config["name"]
        self.domain = self.config["domain"]
        self.capabilities = self.config.get("capabilities", [])
        self.status = "idle"
        self.task_count = 0
        self.error_count = 0

    def execute(self, task, client):
        """Execute a task using Claude AI."""
        self.status = "busy"
        try:
            system_prompt = (
                f"You are {self.name}, a specialized AI agent in the {self.domain} domain. "
                f"Your capabilities: {', '.join(self.capabilities)}. "
                f"Description: {self.config['description']}. "
                f"Execute the following task precisely and return structured results."
            )
            response = client.messages.create(
                model=self.config.get("model", "claude-sonnet-4-20250514"),
                max_tokens=self.config.get("max_tokens", 4096),
                system=system_prompt,
                messages=[{"role": "user", "content": task}],
            )
            self.task_count += 1
            self.status = "idle"
            return {"agent": self.name, "status": "success", "result": response.content[0].text}
        except Exception as e:
            self.error_count += 1
            self.status = "error"
            log.error(f"Agent {self.name} failed: {e}")
            return {"agent": self.name, "status": "error", "error": str(e)}

    def health_check(self):
        return {
            "name": self.name,
            "domain": self.domain,
            "status": self.status,
            "tasks_completed": self.task_count,
            "errors": self.error_count,
        }


class Queen:
    """Represents a Ruflo Queen that directs agents."""

    def __init__(self, config_path):
        with open(config_path) as f:
            self.config = yaml.safe_load(f)
        self.name = self.config["name"]
        self.role = self.config["role"]
        self.domains = self.config.get("domains", [])
        self.vote_weight = self.config.get("vote_weight", 3)
        self.agents = {}

    def assign_agent(self, agent):
        if agent.domain in self.domains or not self.domains:
            self.agents[agent.name] = agent

    def select_agent(self, task_description, capabilities_needed):
        """Select the best agent for a task based on capability match."""
        best_match = None
        best_score = 0
        for agent in self.agents.values():
            if agent.status != "idle":
                continue
            score = len(set(agent.capabilities) & set(capabilities_needed))
            if score > best_score:
                best_score = score
                best_match = agent
        return best_match

    def delegate(self, task, capabilities, client):
        """Delegate a task to the best-fit agent."""
        agent = self.select_agent(task, capabilities)
        if not agent:
            log.warning(f"Queen {self.name}: No available agent for capabilities {capabilities}")
            return {"status": "no_agent_available"}
        log.info(f"Queen {self.name} delegating to {agent.name}: {task[:80]}...")
        return agent.execute(task, client)

    def status_report(self):
        idle = sum(1 for a in self.agents.values() if a.status == "idle")
        busy = sum(1 for a in self.agents.values() if a.status == "busy")
        error = sum(1 for a in self.agents.values() if a.status == "error")
        return {
            "queen": self.name,
            "role": self.role,
            "total_agents": len(self.agents),
            "idle": idle,
            "busy": busy,
            "error": error,
        }


class RufloOrchestrator:
    """Main Ruflo orchestrator — manages queens and agent swarm."""

    def __init__(self):
        self.config = self._load_config()
        self.client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
        self.queens = {}
        self.agents = {}
        self._load_queens()
        self._load_agents()
        self._assign_agents_to_queens()
        log.info(f"Ruflo initialized: {len(self.queens)} queens, {len(self.agents)} agents")

    def _load_config(self):
        with open(CONFIG_PATH) as f:
            return yaml.safe_load(f)

    def _load_queens(self):
        for queen_file in QUEENS_DIR.glob("*.yaml"):
            queen = Queen(queen_file)
            self.queens[queen.name] = queen
            log.info(f"Loaded queen: {queen.name} ({queen.role})")

    def _load_agents(self):
        for domain_dir in AGENTS_DIR.iterdir():
            if not domain_dir.is_dir() or domain_dir.name.startswith("_"):
                continue
            for agent_file in domain_dir.glob("*.yaml"):
                agent = Agent(agent_file)
                self.agents[agent.name] = agent

    def _assign_agents_to_queens(self):
        domain_queen_map = {}
        swarm_path = RUFLO_DIR / "swarms" / "blufire-swarm.yaml"
        if swarm_path.exists():
            with open(swarm_path) as f:
                swarm = yaml.safe_load(f)
            for domain, cfg in swarm.get("domains", {}).items():
                domain_queen_map[domain] = cfg.get("queen")

        for agent in self.agents.values():
            queen_name = domain_queen_map.get(agent.domain)
            if queen_name and queen_name in self.queens:
                self.queens[queen_name].assign_agent(agent)
            else:
                # Default to tactical queen
                if "tactical-queen" in self.queens:
                    self.queens["tactical-queen"].assign_agent(agent)

    def route_task(self, task, domain=None, capabilities=None):
        """Route a task to the appropriate queen and agent."""
        capabilities = capabilities or []

        # Find the right queen for the domain
        if domain:
            for queen in self.queens.values():
                if domain in queen.domains:
                    return queen.delegate(task, capabilities, self.client)

        # Use strategic queen as default
        queen = self.queens.get("strategic-queen") or list(self.queens.values())[0]
        return queen.delegate(task, capabilities, self.client)

    def run_parallel(self, tasks, max_workers=5):
        """Run multiple tasks in parallel across the swarm."""
        results = []
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {}
            for task in tasks:
                future = executor.submit(
                    self.route_task,
                    task["description"],
                    task.get("domain"),
                    task.get("capabilities", []),
                )
                futures[future] = task

            for future in as_completed(futures):
                task = futures[future]
                try:
                    result = future.result()
                    results.append({"task": task, "result": result})
                except Exception as e:
                    results.append({"task": task, "result": {"status": "error", "error": str(e)}})

        return results

    def status(self):
        """Get full system status."""
        return {
            "platform": self.config.get("platform", {}).get("name"),
            "queens": [q.status_report() for q in self.queens.values()],
            "total_agents": len(self.agents),
            "agents_by_domain": self._agents_by_domain(),
        }

    def _agents_by_domain(self):
        domains = {}
        for agent in self.agents.values():
            domains.setdefault(agent.domain, 0)
            domains[agent.domain] += 1
        return domains


def main():
    os.makedirs("logs", exist_ok=True)

    print("=" * 60)
    print("  BLUFIRE AI SYSTEM — Ruflo Agent Orchestrator")
    print("=" * 60)

    orchestrator = RufloOrchestrator()
    status = orchestrator.status()

    print(f"\nPlatform: {status['platform']}")
    print(f"Total Agents: {status['total_agents']}")
    print(f"\nQueens:")
    for q in status["queens"]:
        print(f"  {q['queen']} ({q['role']}): {q['total_agents']} agents")
    print(f"\nAgents by Domain:")
    for domain, count in sorted(status["agents_by_domain"].items()):
        print(f"  {domain}: {count}")

    print("\n" + "=" * 60)
    print("  System ready. Use orchestrator.route_task() to dispatch work.")
    print("=" * 60)

    return orchestrator


if __name__ == "__main__":
    main()
