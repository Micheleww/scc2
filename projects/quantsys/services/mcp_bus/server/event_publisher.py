"""
事件发布服务
处理事件发布到消息总线，供看板和编排器消费
"""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .models import Event, EventType, VerdictEvent
from .message_queue import MessageQueue


class EventPublisher:
    """事件发布器"""
    
    def __init__(self, repo_root: Path, message_queue: Optional[MessageQueue] = None):
        self.repo_root = repo_root
        self.events_dir = repo_root / "docs" / "REPORT" / "ata" / "events"
        self.events_dir.mkdir(parents=True, exist_ok=True)
        self.message_queue = message_queue
    
    def publish_event(self, event: Event) -> bool:
        """
        发布事件
        
        1. 保存事件到文件系统（持久化）
        2. 如果配置了消息队列，也发送到队列（供实时消费）
        """
        # 保存到文件系统
        event_file = self.events_dir / f"{event.event_id}.json"
        with open(event_file, "w", encoding="utf-8") as f:
            json.dump(event.model_dump(), f, ensure_ascii=False, indent=2)
        
        # 发送到消息队列（如果配置）
        if self.message_queue:
            # 发布到看板消费者
            self.message_queue.enqueue(
                message_id=event.event_id,
                task_id=event.correlation_id,
                to_agent="board",
                payload={
                    "event_type": event.type.value,
                    "event_data": event.model_dump(),
                }
            )
            
            # 发布到编排器消费者
            self.message_queue.enqueue(
                message_id=f"{event.event_id}-orchestrator",
                task_id=event.correlation_id,
                to_agent="orchestrator",
                payload={
                    "event_type": event.type.value,
                    "event_data": event.model_dump(),
                }
            )
            
            # 发布到 AWS 桥接器（T2: AWS 统一入口接入）
            self.message_queue.enqueue(
                message_id=f"{event.event_id}-aws",
                task_id=event.correlation_id,
                to_agent="aws_bridge",
                payload={
                    "event_type": event.type.value,
                    "event_data": event.model_dump(),
                }
            )
        
        return True
    
    def publish_verdict_event(
        self,
        task_id: str,
        task_code: Optional[str],
        status: str,
        fail_codes: list[str],
        verdict_data: dict,
    ) -> bool:
        """发布 Verdict 事件"""
        verdict_event = VerdictEvent(
            correlation_id=task_id,
            payload=verdict_data,
            status=status,
            fail_codes=fail_codes,
            task_code=task_code,
            source="ci_gate",
        )
        
        return self.publish_event(verdict_event.to_event())
    
    def publish_task_created_event(
        self,
        task_id: str,
        task_code: str,
        source: str,
        task_data: dict,
    ) -> bool:
        """发布任务创建事件"""
        event = Event(
            type=EventType.TASK_CREATED,
            correlation_id=task_id,
            payload={
                "task_id": task_id,
                "task_code": task_code,
                "task_data": task_data,
            },
            source=source,
        )
        return self.publish_event(event)
    
    def publish_task_updated_event(
        self,
        task_id: str,
        source: str,
        updates: dict,
    ) -> bool:
        """发布任务更新事件"""
        event = Event(
            type=EventType.TASK_UPDATED,
            correlation_id=task_id,
            payload=updates,
            source=source,
        )
        return self.publish_event(event)
    
    def publish_subtask_completed_event(
        self,
        task_id: str,
        subtask_id: str,
        source: str,
        result: dict,
    ) -> bool:
        """发布子任务完成事件"""
        event = Event(
            type=EventType.SUBTASK_COMPLETED,
            correlation_id=subtask_id,
            payload={
                "task_id": task_id,
                "subtask_id": subtask_id,
                "result": result,
            },
            source=source,
        )
        return self.publish_event(event)

    def publish_perf_metric(
        self,
        task_id: str,
        source: str,
        mode: str,
        metrics: dict,
    ) -> bool:
        """发布启动性能指标事件（T3）"""
        event = Event(
            type=EventType.PERF_METRIC,
            correlation_id=task_id,
            payload={
                "metric_type": "startup_performance",
                "mode": mode,
                "metrics": metrics,
            },
            source=source,
        )
        return self.publish_event(event)

    def publish_devloop_metric(
        self,
        task_id: str,
        source: str,
        metrics: dict,
    ) -> bool:
        """发布开发迭代指标事件（T4）"""
        event = Event(
            type=EventType.DEVLOOP_METRIC,
            correlation_id=task_id,
            payload={
                "metric_type": "devloop_performance",
                "metrics": metrics,
            },
            source=source,
        )
        return self.publish_event(event)
