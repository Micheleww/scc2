from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional

from tools.scc.orchestrators.interface import Observation, Orchestrator, OrchestratorAction, OrchestratorContext, OrchestratorOutcome, OrchestratorState, PlanGraph


@dataclass(frozen=True)
class CCLikeOrchestratorV0:
    """
    CC-like orchestration scaffold (no model calls).

    Purpose:
    - Provide a stable, inspectable state machine shape that matches "plan/chat/fullagent".
    - Keep the loop deterministic until SCC_MODEL_ENABLED is turned on.
    """

    name: str = "cc_like_v0"

    def plan(self, ctx: OrchestratorContext, task_contract: Dict[str, Any]) -> PlanGraph:
        nodes = ["goal", "explore", "plan", "execute", "verify", "done"]
        edges = [["goal", "explore"], ["explore", "plan"], ["plan", "execute"], ["execute", "verify"], ["verify", "done"]]
        meta = {
            "orchestrator": self.name,
            "capabilities": list(ctx.capabilities or []),
            "goal": str(task_contract.get("goal") or "").strip(),
        }
        return PlanGraph(nodes=nodes, edges=edges, meta=meta)

    def initial_state(self, ctx: OrchestratorContext, task_contract: Dict[str, Any]) -> OrchestratorState:
        profile = str((task_contract.get("orchestrator") or {}).get("profile") or task_contract.get("profile") or "plan")
        return OrchestratorState(
            step=0,
            phase="init",
            data={
                "profile": profile,
                "goal": str(task_contract.get("goal") or "").strip(),
                "last_obs": None,
            },
        )

    def step(self, ctx: OrchestratorContext, state: OrchestratorState, obs: Observation) -> OrchestratorAction:
        profile = str(state.data.get("profile") or "plan")
        phase = str(state.phase or "init")

        if phase == "init":
            return OrchestratorAction(type="noop", payload={"next_phase": "explore"})
        if phase == "explore":
            return OrchestratorAction(type="noop", payload={"next_phase": "plan"})
        if phase == "plan":
            if profile in ("plan", "chat"):
                return OrchestratorAction(type="finish", payload={"verdict": "UNKNOWN", "summary": "dry-run scaffold complete"})
            return OrchestratorAction(type="noop", payload={"next_phase": "execute"})
        if phase == "execute":
            return OrchestratorAction(type="noop", payload={"next_phase": "verify"})
        if phase == "verify":
            return OrchestratorAction(type="finish", payload={"verdict": "UNKNOWN", "summary": "no-model verify complete"})
        return OrchestratorAction(type="noop", payload={})

    def done(self, ctx: OrchestratorContext, state: OrchestratorState) -> Optional[OrchestratorOutcome]:
        if str(state.phase) != "done":
            return None
        verdict = str(state.data.get("verdict") or "UNKNOWN").upper()
        if verdict not in ("PASS", "FAIL", "UNKNOWN"):
            verdict = "UNKNOWN"
        return OrchestratorOutcome(ok=(verdict == "PASS"), verdict=verdict, summary=str(state.data.get("summary") or "done"))

