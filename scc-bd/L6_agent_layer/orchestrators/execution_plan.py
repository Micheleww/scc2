from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Literal, Sequence


def is_command_concurrency_safe(cmd: str) -> bool:
    """Determine if a command is safe to execute concurrently with other commands.

    Uses a heuristic based on command patterns known to be read-only.
    Currently recognized safe commands include:
    - Search: rg, ripgrep
    - Listing: ls, dir
    - Reading: cat, type, head, tail
    - Git inspection: git status, git diff, git show

    Args:
        cmd: Command string to check

    Returns:
        True if command appears to be read-only and concurrency-safe

    Note:
        This is used for generating execution plans. SCC still executes
        commands sequentially by default for safety.
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
    """A single step in an execution plan.

    Attributes:
        idx: Step index (1-based)
        kind: Step type/category (e.g., "hint", "command")
        cmd: The command to execute
        risk: Risk level assessment ("allow", "review", or "deny")
        concurrency_safe: Whether this step can run concurrently with others
    """
    idx: int
    kind: str
    cmd: str
    risk: Literal["allow", "review", "deny"] = "allow"
    concurrency_safe: bool = False

    def to_dict(self) -> Dict[str, Any]:
        """Convert step to dictionary representation."""
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
    """Group steps into execution groups based on concurrency safety.

    Implements a Kode-style grouping algorithm where:
    - Consecutive concurrency-safe steps are grouped for concurrent execution
    - Non-concurrency-safe steps break the group and run sequentially

    Args:
        steps: Sequence of planned steps to group

    Returns:
        List of execution groups, each containing concurrent and sequential step indices

    Example:
        >>> steps = [
        ...     PlannedStep(idx=1, kind="cmd", cmd="ls", concurrency_safe=True),
        ...     PlannedStep(idx=2, kind="cmd", cmd="cat file", concurrency_safe=True),
        ...     PlannedStep(idx=3, kind="cmd", cmd="rm file", concurrency_safe=False),
        ... ]
        >>> groups = group_steps_for_execution(steps)
        >>> len(groups)
        2  # First group has concurrent steps 1,2; second has sequential step 3
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
    """Build a complete execution plan from a list of steps.

    Groups steps for optimal execution and generates a summary of the plan.

    Args:
        steps: List of planned steps to execute

    Returns:
        ExecutionPlan containing grouped steps and execution summary

    Summary includes:
        - total_steps: Total number of steps
        - concurrency_safe_steps: Count of steps that can run concurrently
        - sequential_steps: Count of steps that must run sequentially
        - group_count: Number of execution groups
        - has_denies: Whether any step has risk="deny"
        - has_reviews: Whether any step has risk="review"
    """
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
