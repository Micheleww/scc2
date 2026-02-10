from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class RoutingDecision:
    owner_role: str
    agent_id: str | None
    rule_id: str
    reasoning: str


class ATARouter:
    def __init__(self, repo_root: Path, coordinator=None):
        self.repo_root = repo_root
        self.coordinator = coordinator
        self.rules_path = self.repo_root / "tools" / "mcp_bus" / "server" / "ata_router_rules.json"
        self.rules = self._load_rules()

    def route(self, task: dict[str, Any]) -> RoutingDecision:
        text = self._normalize_text(task)
        for rule in self.rules:
            if self._match_rule(rule, text, task):
                return self._decision_from_rule(rule, task)
        return self._default_decision(task)

    def _load_rules(self) -> list[dict[str, Any]]:
        if self.rules_path.exists():
            try:
                return json.loads(self.rules_path.read_text(encoding="utf-8")).get("rules", [])
            except Exception:
                return self._default_rules()
        return self._default_rules()

    def _default_rules(self) -> list[dict[str, Any]]:
        return [
            {
                "id": "infra_ops",
                "keywords": ["server", "ops", "monitor", "deploy", "infra", "mcp"],
                "owner_role": "infra_ops",
            },
            {
                "id": "data_engineer",
                "keywords": ["data", "dataset", "pipeline", "etl", "ingest", "download"],
                "owner_role": "data_engineer",
            },
            {
                "id": "trading",
                "keywords": ["strategy", "backtest", "freqtrade", "trading", "portfolio"],
                "owner_role": "trading",
            },
            {
                "id": "doc_writer",
                "keywords": ["doc", "report", "documentation", "readme", "spec"],
                "owner_role": "doc_writer",
            },
            {
                "id": "infra_quality",
                "keywords": ["ci", "gate", "guard", "verdict", "audit"],
                "owner_role": "infra_quality",
            },
        ]

    def _normalize_text(self, task: dict[str, Any]) -> str:
        parts = [
            str(task.get("goal", "")),
            str(task.get("capsule", "")),
            str(task.get("how_to_repro", "")),
            str(task.get("expected", "")),
            str(task.get("metadata", "")),
        ]
        return " ".join(parts).lower()

    def _match_rule(self, rule: dict[str, Any], text: str, task: dict[str, Any]) -> bool:
        keywords = rule.get("keywords", [])
        if keywords and any(keyword.lower() in text for keyword in keywords):
            return True
        return False

    def _decision_from_rule(self, rule: dict[str, Any], task: dict[str, Any]) -> RoutingDecision:
        owner_role = rule.get("owner_role", "implementer")
        agent_id = self._find_agent(owner_role)
        return RoutingDecision(
            owner_role=owner_role,
            agent_id=agent_id,
            rule_id=rule.get("id", "rule"),
            reasoning=f"matched_keywords={rule.get('keywords', [])}",
        )

    def _default_decision(self, task: dict[str, Any]) -> RoutingDecision:
        owner_role = task.get("owner_role") or "implementer"
        agent_id = self._find_agent(owner_role)
        return RoutingDecision(
            owner_role=owner_role,
            agent_id=agent_id,
            rule_id="default",
            reasoning="no_rule_match",
        )

    def _find_agent(self, owner_role: str) -> str | None:
        if not self.coordinator:
            return None
        # Prefer coordinator helper if available
        if hasattr(self.coordinator, "find_agent_for_role"):
            agent = self.coordinator.find_agent_for_role(owner_role)
            return agent.agent_id if agent else None
        # Fallback to registry search for older coordinator versions
        registry = getattr(self.coordinator, "registry", None)
        if registry and hasattr(registry, "find_agents"):
            agents = registry.find_agents(role=owner_role, available_only=True)
            if agents:
                return agents[0].agent_id
        return None
