
from __future__ import annotations

import re
from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, validator


TASK_CODE_PATTERN = re.compile(r"^[A-Z0-9-]+__[0-9]{8}$")


class ATAStatus(str, Enum):
    CREATED = "created"
    ROUTED = "routed"
    ASSIGNED = "assigned"
    RUNNING = "running"
    EVIDENCE = "evidence"
    CI = "ci"
    DONE = "done"
    FAILED = "failed"
    CANCELLED = "cancelled"
    BLOCKED = "blocked"


ALLOWED_TRANSITIONS: dict[ATAStatus, set[ATAStatus]] = {
    ATAStatus.CREATED: {ATAStatus.ROUTED, ATAStatus.CANCELLED},
    ATAStatus.ROUTED: {ATAStatus.ASSIGNED, ATAStatus.CANCELLED, ATAStatus.BLOCKED},
    ATAStatus.ASSIGNED: {ATAStatus.RUNNING, ATAStatus.CANCELLED, ATAStatus.BLOCKED},
    ATAStatus.RUNNING: {ATAStatus.EVIDENCE, ATAStatus.FAILED, ATAStatus.CANCELLED},
    ATAStatus.EVIDENCE: {ATAStatus.CI, ATAStatus.FAILED, ATAStatus.CANCELLED},
    ATAStatus.CI: {ATAStatus.DONE, ATAStatus.FAILED, ATAStatus.BLOCKED},
    ATAStatus.DONE: set(),
    ATAStatus.FAILED: set(),
    ATAStatus.CANCELLED: set(),
    ATAStatus.BLOCKED: set(),
}


def generate_task_code(prefix: str = "ATA-TASK") -> str:
    date_str = datetime.utcnow().strftime("%Y%m%d")
    return f"{prefix}__{date_str}"


def is_valid_transition(current: ATAStatus, target: ATAStatus) -> bool:
    if current == target:
        return True
    return target in ALLOWED_TRANSITIONS.get(current, set())


def map_a2a_status(status: str | None) -> ATAStatus:
    if not status:
        return ATAStatus.CREATED
    normalized = status.upper()
    if normalized == "PENDING":
        return ATAStatus.ASSIGNED
    if normalized == "RUNNING":
        return ATAStatus.RUNNING
    if normalized == "DONE":
        return ATAStatus.DONE
    if normalized == "FAIL":
        return ATAStatus.FAILED
    if normalized == "DLQ":
        return ATAStatus.BLOCKED
    return ATAStatus.CREATED


class ATATaskContext(BaseModel):
    schema_version: str = Field(default="v0.2", description="ATA context schema version")
    task_code: str = Field(..., description="Unique task identifier")
    date: str = Field(..., description="Task date in YYYYMMDD format")
    owner_role: str = Field(..., description="Role of task owner")
    goal: str = Field(..., description="Task goal")
    scope_files: list[str] = Field(default_factory=list, description="Repo-relative scope files")
    how_to_repro: str = Field(..., description="Reproduction steps")
    expected: str = Field(..., description="Expected outcome")
    actual: str = Field(..., description="Actual outcome")
    next_actions: list[str] = Field(default_factory=list, description="Next actions")
    evidence_paths: list[str] = Field(default_factory=list, description="Evidence paths")
    rollback: str = Field(..., description="Rollback plan")
    area: str | None = Field(default=None, description="Task area/domain")
    priority: int | None = Field(default=None, description="Priority 0-3")
    owner: str | None = Field(default=None, description="Owner name/id")
    task_type: str | None = Field(default=None, description="Task type")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Additional metadata")

    @validator("task_code")
    def validate_task_code(cls, value: str) -> str:
        if not TASK_CODE_PATTERN.match(value):
            raise ValueError("task_code must match PATTERN: PREFIX__YYYYMMDD")
        return value


class ATATaskCreate(BaseModel):
    task_code: str | None = Field(default=None, description="Task code (optional)")
    owner_role: str = Field(..., description="Owner role for routing")
    area: str = Field(default="ata", description="Task area/domain")
    priority: int = Field(default=1, description="Priority 0-3")
    goal: str = Field(..., description="Task goal")
    capsule: str = Field(..., description="Task capsule/instructions")
    how_to_repro: str = Field(..., description="Reproduction steps")
    expected: str = Field(..., description="Expected outcome")
    actual: str = Field(default="pending", description="Actual outcome")
    evidence_requirements: str = Field(..., description="Evidence requirements")
    scope_files: list[str] = Field(default_factory=list, description="Repo-relative scope files")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Additional metadata")
    deadline: str | None = Field(default=None, description="Optional deadline")
    owner: str | None = Field(default=None, description="Owner name/id")
    task_type: str | None = Field(default=None, description="Task type")

    @validator("task_code", always=True)
    def default_task_code(cls, value: str | None) -> str:
        if value:
            if not TASK_CODE_PATTERN.match(value):
                raise ValueError("task_code must match PATTERN: PREFIX__YYYYMMDD")
            return value
        return generate_task_code()

    @validator("priority")
    def validate_priority(cls, value: int) -> int:
        if value < 0:
            return 0
        if value > 3:
            return 3
        return value

    def to_a2a_payload(self) -> dict[str, Any]:
        instructions = f"{self.goal}\n\n{self.capsule}".strip()
        return {
            "task_code": self.task_code,
            "area": self.area,
            "owner_role": self.owner_role,
            "priority": self.priority,
            "instructions": instructions,
            "how_to_repro": self.how_to_repro,
            "expected": self.expected,
            "evidence_requirements": self.evidence_requirements,
            "deadline": self.deadline,
            "dependencies": self.metadata.get("dependencies", []),
            "timeout_seconds": self.metadata.get("timeout_seconds"),
            "max_retries": self.metadata.get("max_retries"),
            "retry_backoff_sec": self.metadata.get("retry_backoff_sec"),
        }

    def to_context(self, evidence_paths: list[str]) -> ATATaskContext:
        date_str = datetime.utcnow().strftime("%Y%m%d")
        return ATATaskContext(
            task_code=self.task_code or generate_task_code(),
            date=date_str,
            owner_role=self.owner_role,
            goal=self.goal,
            scope_files=self.scope_files,
            how_to_repro=self.how_to_repro,
            expected=self.expected,
            actual=self.actual,
            next_actions=self.metadata.get("next_actions", []),
            evidence_paths=evidence_paths,
            rollback=self.metadata.get("rollback", "N/A"),
            area=self.area,
            priority=self.priority,
            owner=self.owner,
            task_type=self.task_type,
            metadata=self.metadata,
        )


class ATAEvent(BaseModel):
    task_code: str = Field(..., description="Task code")
    status: ATAStatus = Field(..., description="ATA status")
    timestamp: str = Field(..., description="ISO timestamp")
    actor: str = Field(..., description="Actor id")
    message: str = Field(..., description="Event message")
    details: dict[str, Any] = Field(default_factory=dict, description="Event details")
