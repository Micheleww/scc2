from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Literal, Sequence


def is_command_concurrency_safe(cmd: str) -> bool:
    """
    Minimal heuristic: treat a small set of read-only commands as concurrency-safe.

    This is used for generating an execution plan (SCC still executes sequentially).
    """
    c = f" {str(cmd or '').strip().lower()} "
    if not c.strip():
        return False
    read_only_markers = [
        " rg ",
        " ripgrep ",
        " ls ",
        " dir ",
        " cat ",
        " type ",
        " head ",
        " tail ",
        " wc ",
        " git status",
        " git diff",
        " git show",
    ]
    return any(m in c for m in read_only_markers)


@dataclass(frozen=True)
class PlannedStep:
    idx: int
    kind: str
    cmd: str
    risk: Literal["allow", "review", "deny"] = "allow"
    concurrency_safe: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ExecutionGroup:
    concurrent: List[int] = field(default_factory=list)
    sequential: List[int] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ExecutionPlan:
    steps: List[PlannedStep]
    groups: List[ExecutionGroup]
    summary: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "steps": [s.to_dict() for s in self.steps],
            "groups": [g.to_dict() for g in self.groups],
            "summary": dict(self.summary),
        }


def group_steps_for_execution(steps: Sequence[PlannedStep]) -> List[ExecutionGroup]:
    """
    Kode-style grouping:
    - consecutive concurrency_safe steps can be executed concurrently
    - any non-concurrency_safe step breaks the group into a sequential-only group
    """
    groups: List[ExecutionGroup] = []
    current = ExecutionGroup(concurrent=[], sequential=[])

    def flush() -> None:
        nonlocal current
        if current.concurrent or current.sequential:
            groups.append(ExecutionGroup(concurrent=list(current.concurrent), sequential=list(current.sequential)))
            current = ExecutionGroup(concurrent=[], sequential=[])

    for s in steps:
        if s.concurrency_safe:
            current.concurrent.append(int(s.idx))
        else:
            flush()
            groups.append(ExecutionGroup(concurrent=[], sequential=[int(s.idx)]))

    flush()
    return groups


def build_execution_plan(*, steps: List[PlannedStep]) -> ExecutionPlan:
    groups = group_steps_for_execution(steps)
    summary = {
        "total_steps": len(steps),
        "concurrency_safe_steps": sum(1 for s in steps if s.concurrency_safe),
        "sequential_steps": sum(1 for s in steps if not s.concurrency_safe),
        "group_count": len(groups),
        "has_denies": any(s.risk == "deny" for s in steps),
        "has_reviews": any(s.risk == "review" for s in steps),
    }
    return ExecutionPlan(steps=steps, groups=groups, summary=summary)
