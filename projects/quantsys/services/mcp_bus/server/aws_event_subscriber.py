"""
AWS 事件订阅器
订阅 T1 事件并同步到 AWS（供 Web Console 展示）
"""

import asyncio
import json
import logging
from pathlib import Path
from typing import Optional

from .aws_bridge import AWSBridge
from .aws_protocol_mapper import AWSProtocolMapper
from .event_publisher import EventPublisher
from .integration_service import IntegrationService
from .message_queue import MessageQueue

logger = logging.getLogger(__name__)


class AWSEventSubscriber:
    """AWS 事件订阅器（后台服务）"""
    
    def __init__(
        self,
        repo_root: Path,
        integration_service: IntegrationService,
        aws_bridge: AWSBridge,
        poll_interval: int = 5,
    ):
        self.repo_root = repo_root
        self.integration_service = integration_service
        self.aws_bridge = aws_bridge
        self.poll_interval = poll_interval
        self.running = False
    
    async def start(self) -> None:
        """启动订阅器（后台循环）"""
        self.running = True
        logger.info("AWS Event Subscriber started")
        
        while self.running:
            try:
                # 订阅 T1 事件并同步到 AWS
                self.aws_bridge.subscribe_t1_events_for_aws()
                await asyncio.sleep(self.poll_interval)
            except Exception as e:
                logger.error(f"AWS Event Subscriber error: {e}")
                await asyncio.sleep(self.poll_interval)
    
    def stop(self) -> None:
        """停止订阅器"""
        self.running = False
        logger.info("AWS Event Subscriber stopped")
    
    def register_t1_event_for_aws(self, t1_event: dict[str, Any]) -> None:
        """
        注册 T1 事件，准备同步到 AWS
        
        将事件放入消息队列（to_agent="aws_bridge"）
        """
        from .models import Event
        
        try:
            event = Event(**t1_event)
            # 转换 T1 Event -> AWS 格式
            aws_event = AWSProtocolMapper.convert_t1_event_to_aws(event)
            
            # 获取 AWS task_id（如果有映射）
            t1_task_id = event.correlation_id
            aws_task_id = self.aws_bridge._get_aws_task_id_from_t1(t1_task_id)
            if aws_task_id:
                aws_event["task_id"] = aws_task_id
            
            # 放入消息队列（to_agent="aws_bridge"）
            self.integration_service.message_queue.enqueue(
                message_id=event.event_id,
                task_id=t1_task_id,
                to_agent="aws_bridge",
                payload={
                    "event_type": event.type.value,
                    "event_data": aws_event,
                },
            )
        except Exception as e:
            logger.error(f"Failed to register T1 event for AWS: {e}")
