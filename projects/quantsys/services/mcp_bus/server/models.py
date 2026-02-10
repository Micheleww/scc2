"""
统一数据模型 - INTEGRATION_MVP
定义 Task/Subtask/Event 的统一 Schema（JSON Schema + Pydantic）
"""

import uuid
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator


# ==================== Enums ====================

class TaskStatus(str, Enum):
    """任务状态"""
    PENDING = "pending"
    RUNNING = "running"
    WAITING = "waiting"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class SubTaskStatus(str, Enum):
    """子任务状态"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class EventType(str, Enum):
    """事件类型"""
    TASK_CREATED = "task_created"
    TASK_UPDATED = "task_updated"
    SUBTASK_CREATED = "subtask_created"
    SUBTASK_COMPLETED = "subtask_completed"
    VERDICT_GENERATED = "verdict_generated"
    MESSAGE_SENT = "message_sent"
    MESSAGE_RECEIVED = "message_received"
    PERF_METRIC = "perf_metric"
    DEVLOOP_METRIC = "devloop_metric"


# ==================== Task Model ====================

class TaskConstraints(BaseModel):
    """任务约束条件"""
    law_ref: Optional[str] = None
    allowed_paths: list[str] = Field(default_factory=list)


class Task(BaseModel):
    """统一任务模型"""
    task_id: str = Field(..., description="统一任务标识符，格式: {area}-{date}-{seq}")
    task_code: str = Field(..., description="任务代码，用于显示和引用")
    goal: str = Field(..., description="任务目标描述")
    constraints: TaskConstraints = Field(default_factory=TaskConstraints)
    acceptance: list[str] = Field(..., description="验收标准列表")
    status: TaskStatus = Field(default=TaskStatus.PENDING, description="任务状态")
    created_by: str = Field(..., description="创建者标识（user_id或agent_id）")
    created_at: str = Field(..., description="创建时间（ISO8601）")
    updated_at: Optional[str] = Field(None, description="更新时间（ISO8601）")

    @field_validator("created_at", "updated_at", mode="before")
    @classmethod
    def validate_timestamp(cls, v):
        if v is None:
            return None
        if isinstance(v, datetime):
            return v.isoformat()
        return v

    def model_post_init(self, __context: Any) -> None:
        """初始化后处理"""
        if not self.updated_at:
            self.updated_at = self.created_at


# ==================== Subtask Model ====================

class SubTask(BaseModel):
    """统一子任务模型"""
    subtask_id: str = Field(..., description="子任务标识符")
    task_id: str = Field(..., description="所属任务ID")
    assigned_agent: Optional[str] = Field(None, description="分配的Agent标识")
    expected_outputs: list[str] = Field(..., description="期望输出列表")
    status: SubTaskStatus = Field(default=SubTaskStatus.PENDING, description="子任务状态")
    started_at: Optional[str] = Field(None, description="开始时间（ISO8601）")
    completed_at: Optional[str] = Field(None, description="完成时间（ISO8601）")
    result: Optional[dict[str, Any]] = Field(None, description="执行结果")
    error: Optional[str] = Field(None, description="错误信息")

    @field_validator("started_at", "completed_at", mode="before")
    @classmethod
    def validate_timestamp(cls, v):
        if v is None:
            return None
        if isinstance(v, datetime):
            return v.isoformat()
        return v


# ==================== Event Model ====================

class Event(BaseModel):
    """统一事件模型"""
    event_id: str = Field(default_factory=lambda: str(uuid.uuid4()), description="事件唯一标识符（UUID）")
    type: EventType = Field(..., description="事件类型")
    correlation_id: str = Field(..., description="关联ID（task_id或subtask_id）")
    payload: dict[str, Any] = Field(..., description="事件负载数据")
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat(), description="事件时间戳（ISO8601）")
    source: str = Field(..., description="事件源（agent_id）")

    @field_validator("timestamp", mode="before")
    @classmethod
    def validate_timestamp(cls, v):
        if v is None:
            return datetime.now(timezone.utc).isoformat()
        if isinstance(v, datetime):
            return v.isoformat()
        return v


# ==================== Verdict Event Model ====================

class VerdictEvent(BaseModel):
    """CI Verdict 事件模型（继承自 Event）"""
    event_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    type: EventType = Field(default=EventType.VERDICT_GENERATED)
    correlation_id: str = Field(..., description="关联的 task_id")
    payload: dict[str, Any] = Field(..., description="Verdict 数据")
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    source: str = Field(default="ci_gate", description="事件源（CI门禁）")

    # Verdict 特定字段
    status: str = Field(..., description="verdict 状态: pass/fail")
    fail_codes: list[str] = Field(default_factory=list, description="失败代码列表")
    task_code: Optional[str] = Field(None, description="任务代码（兼容旧字段）")

    def to_event(self) -> Event:
        """转换为标准 Event"""
        return Event(
            event_id=self.event_id,
            type=self.type,
            correlation_id=self.correlation_id,
            payload={
                **self.payload,
                "status": self.status,
                "fail_codes": self.fail_codes,
                "task_code": self.task_code,
            },
            timestamp=self.timestamp,
            source=self.source,
        )


# ==================== Message Model (兼容旧格式) ====================

class ATAMessage(BaseModel):
    """ATA 消息模型（兼容旧格式，内部使用 task_id）"""
    message_id: str = Field(default_factory=lambda: str(uuid.uuid4()), description="消息唯一标识符")
    task_id: Optional[str] = Field(None, description="统一任务ID（新字段）")
    taskcode: Optional[str] = Field(None, description="任务代码（旧字段，兼容）")
    from_agent: str = Field(..., description="发送代理")
    to_agent: str = Field(..., description="接收代理")
    kind: str = Field(default="request", description="消息类型")
    payload: dict[str, Any] = Field(..., description="消息内容")
    prev_sha256: Optional[str] = Field(None, description="前一条消息的 SHA256")
    priority: str = Field(default="normal", description="优先级")
    requires_response: bool = Field(default=True, description="是否需要响应")
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat(), description="创建时间")

    def model_post_init(self, __context: Any) -> None:
        """初始化后处理：确保 task_id 存在"""
        # 如果只有 taskcode，尝试从 taskcode 生成 task_id（兼容旧格式）
        if not self.task_id and self.taskcode:
            # 简单映射：taskcode -> task_id（实际应该从映射表获取）
            # 这里先保持兼容，后续由映射表处理
            pass


# ==================== Task ID Manager ====================

from .task_id_manager import TaskIDManager, get_task_id_manager

# 使用单例模式获取task_id管理器
task_id_manager = get_task_id_manager()

# 保留旧的TaskIDGenerator接口以保持向后兼容
class TaskIDGenerator:
    """统一 task_id 生成器（向后兼容）"""
    
    @staticmethod
    def generate(area: str, date: Optional[str] = None, seq: Optional[int] = None) -> str:
        """
        生成统一 task_id
        
        格式: {area}-{date}-{seq:03d}
        示例: INTEGRATION_AUDIT-20260124-001
        """
        return task_id_manager.generate(area, date, seq)
    
    @staticmethod
    def parse(task_id: str) -> dict[str, str]:
        """解析 task_id"""
        return task_id_manager.parse(task_id)


# ==================== Schema Validation ====================

def validate_task(data: dict[str, Any]) -> Task:
    """验证并创建 Task 对象"""
    return Task(**data)


def validate_subtask(data: dict[str, Any]) -> SubTask:
    """验证并创建 SubTask 对象"""
    return SubTask(**data)


def validate_event(data: dict[str, Any]) -> Event:
    """验证并创建 Event 对象"""
    return Event(**data)


def validate_ata_message(data: dict[str, Any]) -> ATAMessage:
    """验证并创建 ATA Message 对象（兼容旧格式）"""
    return ATAMessage(**data)
