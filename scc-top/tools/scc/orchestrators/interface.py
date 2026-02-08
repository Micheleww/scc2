from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Literal, Optional, Protocol


ActionType = Literal["tool_call", "subtask", "patch", "finish", "noop"]
OrchestratorMode = Literal["auto", "plan", "chat", "fullagent"]


@dataclass(frozen=True)
class OrchestratorContext:
    """
    Minimal, stable context object for orchestrators.

    Note: orchestrators must be deterministic given (state, observation) unless
    explicitly configured otherwise. No model calls in this version.
    """

    task_id: str
    repo_root: str
    now_utc: str
    capabilities: List[str] = field(default_factory=list)


@dataclass(frozen=True)
class PlanGraph:
    """
    A minimal, inspectable plan representation.

    - nodes: stable ids
    - edges: (from, to)
    - meta: optional annotations
    """

    nodes: List[str]
    edges: List[List[str]]
    meta: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class Observation:
    """
    Observation from the environment/capabilities (tool results, state snapshots).
    """

    kind: str
    payload: Dict[str, Any]


@dataclass(frozen=True)
class OrchestratorState:
    """
    Serializable orchestrator state snapshot.
    """

    step: int
    phase: str
    data: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class OrchestratorAction:
    type: ActionType
    payload: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class OrchestratorOutcome:
    ok: bool
    verdict: Literal["PASS", "FAIL", "UNKNOWN"]
    summary: str
    evidence_paths: List[str] = field(default_factory=list)


class Orchestrator(Protocol):
    name: str

    def plan(self, ctx: OrchestratorContext, task_contract: Dict[str, Any]) -> PlanGraph: ...

    def initial_state(self, ctx: OrchestratorContext, task_contract: Dict[str, Any]) -> OrchestratorState: ...

    def step(self, ctx: OrchestratorContext, state: OrchestratorState, obs: Observation) -> OrchestratorAction: ...

    def done(self, ctx: OrchestratorContext, state: OrchestratorState) -> Optional[OrchestratorOutcome]: ...
