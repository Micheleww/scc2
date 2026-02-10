"""
AWS <-> T1 协议映射层
定义字段映射表和转换规则
"""

from typing import Any, Optional

from .models import Event, EventType, Task, TaskConstraints, TaskStatus


class AWSProtocolMapper:
    """AWS <-> T1 协议映射器"""
    
    # ==================== 字段映射表 ====================
    
    # AWS Task Create -> T1 Task 字段映射
    AWS_TO_T1_TASK_MAPPING = {
        # AWS 字段 -> T1 字段
        "task_id": "task_id",  # 如果 AWS 已生成，需要映射
        "task_code": "task_code",
        "goal": "goal",
        "instructions": "goal",  # 兼容字段
        "prompt": "goal",  # 兼容字段
        "area": "area",  # 用于生成 task_id
        "constraints": "constraints",
        "law_ref": "constraints.law_ref",
        "allowed_paths": "constraints.allowed_paths",
        "acceptance": "acceptance",
        "expected": "acceptance",  # 兼容字段
        "created_by": "created_by",
        "user_id": "created_by",  # 兼容字段
        "priority": "priority",
    }
    
    # T1 Event -> AWS Event 字段映射
    T1_TO_AWS_EVENT_MAPPING = {
        "event_id": "event_id",
        "type": "event_type",
        "correlation_id": "task_id",  # 需要转换为 AWS task_id
        "payload": "payload",
        "timestamp": "timestamp",
        "source": "source",
    }
    
    # ==================== 转换方法 ====================
    
    @staticmethod
    def convert_aws_task_to_t1(
        aws_payload: dict[str, Any],
        t1_task_id: str,
        task_code: Optional[str],
    ) -> Task:
        """
        转换 AWS 任务创建请求 -> T1 Task
        
        Args:
            aws_payload: AWS 任务负载
            t1_task_id: T1 统一 task_id
            task_code: 任务代码
        
        Returns:
            T1 Task 对象
        """
        from datetime import datetime, timezone
        
        # 提取字段（按映射表）
        goal = (
            aws_payload.get("goal")
            or aws_payload.get("instructions")
            or aws_payload.get("prompt", "")
        )
        
        constraints = TaskConstraints(
            law_ref=aws_payload.get("law_ref"),
            allowed_paths=aws_payload.get("allowed_paths", []),
        )
        
        acceptance = aws_payload.get("acceptance") or aws_payload.get("expected", [])
        if isinstance(acceptance, str):
            acceptance = [acceptance]
        
        created_by = (
            aws_payload.get("created_by")
            or aws_payload.get("user_id")
            or "aws_user"
        )
        
        return Task(
            task_id=t1_task_id,
            task_code=task_code or t1_task_id,
            goal=goal,
            constraints=constraints,
            acceptance=acceptance,
            status=TaskStatus.PENDING,
            created_by=created_by,
            created_at=datetime.now(timezone.utc).isoformat(),
        )
    
    @staticmethod
    def convert_t1_event_to_aws(
        t1_event: Event,
        aws_task_id: Optional[str] = None,
    ) -> dict[str, Any]:
        """
        转换 T1 Event -> AWS 事件格式
        
        Args:
            t1_event: T1 事件对象
            aws_task_id: AWS task_id（如果有映射）
        
        Returns:
            AWS 事件字典
        """
        aws_event = {
            "event_id": t1_event.event_id,
            "event_type": t1_event.type.value,
            "task_id": aws_task_id or t1_event.correlation_id,
            "t1_task_id": t1_event.correlation_id,  # 保留用于追溯
            "timestamp": t1_event.timestamp,
            "source": t1_event.source,
            "payload": t1_event.payload,
        }
        
        # 根据事件类型添加特定字段
        if t1_event.type == EventType.VERDICT_GENERATED:
            aws_event["verdict"] = {
                "status": t1_event.payload.get("status"),
                "fail_codes": t1_event.payload.get("fail_codes", []),
                "task_code": t1_event.payload.get("task_code"),
            }
        elif t1_event.type == EventType.SUBTASK_COMPLETED:
            aws_event["subtask"] = {
                "subtask_id": t1_event.payload.get("subtask_id"),
                "result": t1_event.payload.get("result"),
                "status": t1_event.payload.get("result", {}).get("status"),
            }
        elif t1_event.type == EventType.TASK_UPDATED:
            # 处理日志追加和状态更新
            update_type = t1_event.payload.get("update_type")
            if update_type == "log_append":
                aws_event["log"] = t1_event.payload.get("log_data")
            elif update_type == "status_update":
                aws_event["status"] = t1_event.payload.get("status")
        
        return aws_event
    
    @staticmethod
    def validate_aws_task_payload(aws_payload: dict[str, Any]) -> tuple[bool, Optional[str]]:
        """
        验证 AWS 任务负载
        
        Returns:
            (is_valid, error_message)
        """
        # 检查必填字段
        required_fields = ["task_type"]
        missing_fields = [f for f in required_fields if f not in aws_payload]
        if missing_fields:
            return False, f"Missing required fields: {missing_fields}"
        
        # 检查任务类型白名单
        allowed_types = {"RUN_PROMPT", "RUN_SCRIPT", "COLLECT_STATUS"}
        if aws_payload.get("task_type") not in allowed_types:
            return (
                False,
                f"Task type '{aws_payload.get('task_type')}' not in whitelist: {allowed_types}",
            )
        
        return True, None
