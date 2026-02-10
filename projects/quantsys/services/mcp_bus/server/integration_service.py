"""
INTEGRATION_MVP 集成服务
统一管理所有集成组件：模型、队列、事件、映射
"""

from pathlib import Path
from typing import Optional

from .event_publisher import EventPublisher
from .message_queue import MessageQueue
from .models import TaskIDGenerator
from .orchestrator import TaskOrchestrator
from .task_id_mapper import TaskIDMapper
from .verdict_handler import VerdictHandler


class IntegrationService:
    """集成服务（单例）"""
    
    _instance = None
    
    def __new__(cls, repo_root: Optional[Path] = None):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self, repo_root: Optional[Path] = None):
        if self._initialized:
            return
        
        if repo_root is None:
            # 默认从环境变量或当前目录获取
            import os
            repo_root = Path(os.getenv("REPO_ROOT", ".")).resolve()
        
        self.repo_root = repo_root
        
        # 初始化组件
        self.task_id_mapper = TaskIDMapper(repo_root)
        self.message_queue = MessageQueue(
            repo_root / "docs" / "REPORT" / "ata" / "message_queue.db"
        )
        self.event_publisher = EventPublisher(repo_root, self.message_queue)
        self.orchestrator = TaskOrchestrator(repo_root)
        self.verdict_handler = VerdictHandler(
            repo_root,
            self.event_publisher,
            self.orchestrator,
            self.task_id_mapper,
        )
        
        self._initialized = True
    
    def get_task_id(self, taskcode: str, area: Optional[str] = None) -> str:
        """获取或生成 task_id"""
        return self.task_id_mapper.ensure_task_id(taskcode, area)
    
    def create_task_with_id(
        self,
        taskcode: str,
        goal: str,
        constraints: dict,
        acceptance: list[str],
        created_by: str,
        area: Optional[str] = None,
    ) -> dict:
        """创建任务（使用统一 task_id）"""
        # 生成或获取 task_id
        task_id = self.get_task_id(taskcode, area)
        
        # 创建任务（通过 orchestrator）
        # 这里需要更新 orchestrator 支持新模型
        result = self.orchestrator.create_task(
            task_description=goal,
            priority="normal",
        )
        
        # 更新 task_id（如果 orchestrator 生成了不同的 ID）
        if result.get("task_id") != task_id:
            # 建立映射
            self.task_id_mapper.create_mapping(taskcode, task_id)
            # 更新 orchestrator 中的 task_id
            # 这里简化处理，实际应该更新任务文件
        
        # 发布任务创建事件
        self.event_publisher.publish_task_created_event(
            task_id=task_id,
            task_code=taskcode,
            source=created_by,
            task_data={
                "goal": goal,
                "constraints": constraints,
                "acceptance": acceptance,
            },
        )
        
        return {
            "success": True,
            "task_id": task_id,
            "task_code": taskcode,
            **result,
        }
