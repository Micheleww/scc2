"""
AWS 统一入口桥接器 (T2)
实现 AWS <-> T1 事件总线的双向桥接
- 外部（AWS）-> 内部（T1总线）：将 AWS intake 转成 T1 Event 并 publish
- 内部（T1总线）-> 外部（AWS）：订阅 T1 Event，同步状态/日志/结果给 AWS
"""

import json
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from .event_publisher import EventPublisher
from .message_queue import MessageQueue
from .models import Event, EventType, Task, TaskIDGenerator, TaskStatus

logger = logging.getLogger(__name__)


class AWSBridge:
    """AWS 统一入口桥接器"""
    
    def __init__(
        self,
        repo_root: Path,
        message_queue: MessageQueue,
        event_publisher: EventPublisher,
        aws_endpoint: Optional[str] = None,
        aws_api_key: Optional[str] = None,
    ):
        self.repo_root = repo_root
        self.message_queue = message_queue
        self.event_publisher = event_publisher
        self.aws_endpoint = aws_endpoint
        self.aws_api_key = aws_api_key
        
        # 幂等去重表（基于 AWS request_id + task_id）
        self.dedupe_file = repo_root / "docs" / "REPORT" / "ata" / "aws_bridge_dedupe.jsonl"
        self.dedupe_file.parent.mkdir(parents=True, exist_ok=True)
        
        # 任务类型白名单
        self.allowed_task_types = {
            "TASK_CREATION",
            "TASK_UPDATE",
            "LOG_APPEND",
            "STATUS_UPDATE",
        }
        
        # AWS task_id -> T1 task_id 映射表
        self.task_id_mapping_file = repo_root / "docs" / "REPORT" / "ata" / "aws_task_id_mapping.json"
        self._load_task_id_mapping()
    
    def _load_task_id_mapping(self) -> dict[str, str]:
        """加载 AWS task_id -> T1 task_id 映射"""
        if self.task_id_mapping_file.exists():
            with open(self.task_id_mapping_file, encoding="utf-8") as f:
                return json.load(f)
        return {}
    
    def _save_task_id_mapping(self, mapping: dict[str, str]) -> None:
        """保存映射表"""
        with open(self.task_id_mapping_file, "w", encoding="utf-8") as f:
            json.dump(mapping, f, indent=2, ensure_ascii=False)
    
    def _is_duplicate(self, request_id: str, task_id: str) -> bool:
        """检查请求是否重复（幂等）"""
        if not self.dedupe_file.exists():
            return False
        
        key = f"{request_id}:{task_id}"
        with open(self.dedupe_file, encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    record = json.loads(line)
                    if record.get("key") == key:
                        return True
        return False
    
    def _record_dedupe(self, request_id: str, task_id: str) -> None:
        """记录去重键"""
        key = f"{request_id}:{task_id}"
        record = {
            "key": key,
            "request_id": request_id,
            "task_id": task_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        with open(self.dedupe_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    
    def handle_aws_task_creation(self, aws_payload: dict[str, Any]) -> dict[str, Any]:
        """
        处理 AWS 任务创建请求
        
        AWS payload 格式:
        {
            "request_id": "aws-xxx",
            "task_id": "aws-task-123" (可选，如果AWS已生成),
            "task_code": "TASK_CODE__20260124",
            "goal": "任务目标",
            "acceptance": ["验收1", "验收2"],
            "created_by": "user_id",
            "task_type": "TASK_CREATION"
        }
        
        Returns:
            {
                "success": bool,
                "task_id": str,  # T1统一task_id
                "message": str
            }
        """
        request_id = aws_payload.get("request_id", str(uuid.uuid4()))
        aws_task_id = aws_payload.get("task_id")
        task_code = aws_payload.get("task_code")
        task_type = aws_payload.get("task_type", "TASK_CREATION")
        
        # 白名单检查
        if task_type not in self.allowed_task_types:
            return {
                "success": False,
                "message": f"Task type '{task_type}' not in whitelist",
            }
        
        # 生成或映射 task_id
        if aws_task_id:
            # AWS 已生成 task_id，需要映射到 T1 格式
            # 解析 task_code 获取 area 和 date
            if task_code:
                # task_code 格式: AREA__YYYYMMDD
                parts = task_code.split("__")
                if len(parts) >= 2:
                    area = parts[0]
                    date = parts[1]
                    # 生成 T1 task_id
                    t1_task_id = TaskIDGenerator.generate(area, date)
                else:
                    t1_task_id = TaskIDGenerator.generate("AWS_INTAKE")
            else:
                t1_task_id = TaskIDGenerator.generate("AWS_INTAKE")
            
            # 保存映射
            mapping = self._load_task_id_mapping()
            mapping[aws_task_id] = t1_task_id
            self._save_task_id_mapping(mapping)
        else:
            # AWS 未生成，使用 T1 生成规则
            if task_code:
                parts = task_code.split("__")
                if len(parts) >= 2:
                    area = parts[0]
                    date = parts[1]
                    t1_task_id = TaskIDGenerator.generate(area, date)
                else:
                    t1_task_id = TaskIDGenerator.generate("AWS_INTAKE")
            else:
                t1_task_id = TaskIDGenerator.generate("AWS_INTAKE")
        
        # 幂等检查
        if self._is_duplicate(request_id, t1_task_id):
            logger.warning(f"Duplicate request: {request_id} for task {t1_task_id}")
            return {
                "success": True,
                "task_id": t1_task_id,
                "message": "Duplicate request (idempotent)",
            }
        
        # 构建 T1 Task 对象
        task_data = {
            "task_id": t1_task_id,
            "task_code": task_code or f"AWS-{t1_task_id}",
            "goal": aws_payload.get("goal", ""),
            "acceptance": aws_payload.get("acceptance", []),
            "status": TaskStatus.PENDING.value,
            "created_by": aws_payload.get("created_by", "aws_user"),
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        
        # 发布 T1 TaskCreated 事件
        success = self.event_publisher.publish_task_created_event(
            task_id=t1_task_id,
            task_code=task_data["task_code"],
            source="aws_bridge",
            task_data=task_data,
        )
        
        if success:
            # 记录去重
            self._record_dedupe(request_id, t1_task_id)
            return {
                "success": True,
                "task_id": t1_task_id,
                "message": "Task created successfully",
            }
        else:
            return {
                "success": False,
                "message": "Failed to publish task creation event",
            }
    
    def handle_aws_log_append(self, aws_payload: dict[str, Any]) -> dict[str, Any]:
        """
        处理 AWS 日志追加请求
        
        AWS payload:
        {
            "request_id": "aws-xxx",
            "task_id": "aws-task-123" (或 T1 task_id),
            "log_level": "info",
            "message": "日志内容",
            "timestamp": "2026-01-24T10:00:00Z"
        }
        """
        request_id = aws_payload.get("request_id", str(uuid.uuid4()))
        aws_task_id = aws_payload.get("task_id")
        
        # 映射 AWS task_id -> T1 task_id
        mapping = self._load_task_id_mapping()
        t1_task_id = mapping.get(aws_task_id, aws_task_id)  # 如果未映射，假设就是 T1 task_id
        
        # 幂等检查
        if self._is_duplicate(request_id, t1_task_id):
            return {"success": True, "message": "Duplicate request (idempotent)"}
        
        # 发布 LogAppend 事件（使用 TASK_UPDATED 类型，payload 包含 log）
        event = Event(
            type=EventType.TASK_UPDATED,
            correlation_id=t1_task_id,
            payload={
                "log_append": {
                    "level": aws_payload.get("log_level", "info"),
                    "message": aws_payload.get("message", ""),
                    "timestamp": aws_payload.get("timestamp", datetime.now(timezone.utc).isoformat()),
                }
            },
            source="aws_bridge",
        )
        
        success = self.event_publisher.publish_event(event)
        if success:
            self._record_dedupe(request_id, t1_task_id)
            return {"success": True, "message": "Log appended successfully"}
        else:
            return {"success": False, "message": "Failed to publish log event"}
    
    def handle_aws_status_update(self, aws_payload: dict[str, Any]) -> dict[str, Any]:
        """
        处理 AWS 状态更新请求
        
        AWS payload:
        {
            "request_id": "aws-xxx",
            "task_id": "aws-task-123",
            "status": "running",
            "progress": 50
        }
        """
        request_id = aws_payload.get("request_id", str(uuid.uuid4()))
        aws_task_id = aws_payload.get("task_id")
        
        # 映射 task_id
        mapping = self._load_task_id_mapping()
        t1_task_id = mapping.get(aws_task_id, aws_task_id)
        
        # 幂等检查
        if self._is_duplicate(request_id, t1_task_id):
            return {"success": True, "message": "Duplicate request (idempotent)"}
        
        # 发布状态更新事件
        success = self.event_publisher.publish_task_updated_event(
            task_id=t1_task_id,
            source="aws_bridge",
            updates={
                "status": aws_payload.get("status"),
                "progress": aws_payload.get("progress"),
            },
        )
        
        if success:
            self._record_dedupe(request_id, t1_task_id)
            return {"success": True, "message": "Status updated successfully"}
        else:
            return {"success": False, "message": "Failed to publish status update"}
    
    def consume_t1_events_for_aws(self, limit: int = 10) -> int:
        """
        消费 T1 事件并同步到 AWS（供 Web Console 展示）
        
        从消息队列获取 to_agent="aws_bridge" 的消息，转换为 AWS 格式并推送
        """
        messages = self.message_queue.get_pending_messages(limit)
        processed = 0
        
        for msg in messages:
            if msg.get("to_agent") != "aws_bridge":
                continue
            
            payload = msg.get("payload", {})
            event_data = payload.get("event_data")
            if not event_data:
                continue
            
            try:
                event = Event(**event_data)
                
                # 转换为 AWS 格式并推送
                aws_payload = self._convert_t1_event_to_aws(event)
                if aws_payload and self._push_to_aws(aws_payload):
                    self.message_queue.mark_acked(msg["message_id"])
                    processed += 1
                else:
                    self.message_queue.mark_nacked(msg["message_id"], "Failed to push to AWS")
            except Exception as e:
                logger.error(f"Error processing event for AWS: {e}")
                self.message_queue.mark_nacked(msg["message_id"], str(e))
        
        return processed
    
    def _convert_t1_event_to_aws(self, event: Event) -> Optional[dict[str, Any]]:
        """将 T1 Event 转换为 AWS 格式"""
        task_id = event.correlation_id
        
        # 映射 T1 task_id -> AWS task_id（如果有映射）
        mapping = self._load_task_id_mapping()
        aws_task_id = None
        for aws_id, t1_id in mapping.items():
            if t1_id == task_id:
                aws_task_id = aws_id
                break
        
        if event.type == EventType.TASK_CREATED:
            return {
                "event_type": "task_created",
                "task_id": aws_task_id or task_id,
                "t1_task_id": task_id,
                "task_code": event.payload.get("task_code"),
                "status": "pending",
                "timestamp": event.timestamp,
            }
        elif event.type == EventType.TASK_UPDATED:
            return {
                "event_type": "task_updated",
                "task_id": aws_task_id or task_id,
                "t1_task_id": task_id,
                "status": event.payload.get("status"),
                "progress": event.payload.get("progress"),
                "timestamp": event.timestamp,
            }
        elif event.type == EventType.VERDICT_GENERATED:
            return {
                "event_type": "verdict_generated",
                "task_id": aws_task_id or task_id,
                "t1_task_id": task_id,
                "status": event.payload.get("status"),
                "fail_codes": event.payload.get("fail_codes", []),
                "timestamp": event.timestamp,
            }
        elif event.type == EventType.SUBTASK_COMPLETED:
            return {
                "event_type": "subtask_completed",
                "task_id": aws_task_id or task_id,
                "t1_task_id": task_id,
                "subtask_id": event.payload.get("subtask_id"),
                "result": event.payload.get("result"),
                "timestamp": event.timestamp,
            }
        
        return None
    
    def _push_to_aws(self, aws_payload: dict[str, Any]) -> bool:
        """
        推送事件到 AWS（实际实现需要调用 AWS API）
        
        这里先实现为日志记录，实际需要：
        1. 调用 AWS API Gateway / Lambda
        2. 或通过 WebSocket/SSE 推送到 Web Console
        3. 或写入 AWS SQS/SNS
        """
        if not self.aws_endpoint:
            # 如果没有配置 AWS endpoint，只记录日志
            logger.info(f"Would push to AWS: {json.dumps(aws_payload, ensure_ascii=False)}")
            return True
        
        # TODO: 实现实际的 AWS API 调用
        # 示例：
        # import requests
        # response = requests.post(
        #     f"{self.aws_endpoint}/events",
        #     json=aws_payload,
        #     headers={"Authorization": f"Bearer {self.aws_api_key}"}
        # )
        # return response.status_code == 200
        
        logger.info(f"Pushing to AWS {self.aws_endpoint}: {json.dumps(aws_payload, ensure_ascii=False)}")
        return True
