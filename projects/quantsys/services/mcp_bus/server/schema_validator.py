"""
Schema 验证中间件 - INTEGRATION_MVP
对所有入站消息/事件进行 Schema 验证
"""

import json
import logging
from pathlib import Path
from typing import Any

from fastapi import HTTPException, Request
from starlette.middleware.base import BaseHTTPMiddleware

from .models import (
    ATAMessage,
    Event,
    SubTask,
    Task,
    TaskIDGenerator,
    validate_ata_message,
    validate_event,
    validate_subtask,
    validate_task,
)

logger = logging.getLogger(__name__)


class SchemaValidationMiddleware(BaseHTTPMiddleware):
    """Schema 验证中间件"""

    async def dispatch(self, request: Request, call_next):
        """验证请求中的消息/事件 Schema"""
        # 跳过非 API 请求
        if not request.url.path.startswith("/mcp/tools/call"):
            return await call_next(request)

        # 读取请求体
        body = await request.body()
        if not body:
            return await call_next(request)

        try:
            data = json.loads(body)
            tool_name = data.get("name", "")
            arguments = data.get("arguments", {})

            # 根据工具名称验证不同的 Schema
            if tool_name == "ata_send":
                # 验证 ATA 消息
                try:
                    message = validate_ata_message(arguments)
                    # 确保 task_id 存在（从 taskcode 映射或生成）
                    if not message.task_id and message.taskcode:
                        message.task_id = self._get_or_create_task_id(message.taskcode)
                    # 确保兼容旧格式，补全所有必要字段
                    message = self._ensure_ata_message_compatibility(message)
                    # 将验证后的消息放回 arguments
                    arguments = message.model_dump(exclude_none=True)
                    data["arguments"] = arguments
                except Exception as e:
                    logger.error(f"ATA message validation failed: {e}")
                    raise HTTPException(status_code=400, detail=f"Invalid ATA message schema: {e}")

            elif tool_name == "task_create":
                # 验证 Task
                try:
                    task = validate_task(arguments)
                    arguments = task.model_dump(exclude_none=True)
                    data["arguments"] = arguments
                except Exception as e:
                    logger.error(f"Task validation failed: {e}")
                    raise HTTPException(status_code=400, detail=f"Invalid task schema: {e}")
            
            elif tool_name == "event_publish":
                # 验证 Event
                try:
                    event = validate_event(arguments)
                    arguments = event.model_dump(exclude_none=True)
                    data["arguments"] = arguments
                except Exception as e:
                    logger.error(f"Event validation failed: {e}")
                    raise HTTPException(status_code=400, detail=f"Invalid event schema: {e}")
            
            elif tool_name == "subtask_create":
                # 验证 SubTask
                try:
                    subtask = validate_subtask(arguments)
                    arguments = subtask.model_dump(exclude_none=True)
                    data["arguments"] = arguments
                except Exception as e:
                    logger.error(f"SubTask validation failed: {e}")
                    raise HTTPException(status_code=400, detail=f"Invalid subtask schema: {e}")
            
            elif tool_name == "verdict_publish":
                # 验证 VerdictEvent
                try:
                    from models import VerdictEvent
                    verdict_event = VerdictEvent(**arguments)
                    arguments = verdict_event.model_dump(exclude_none=True)
                    data["arguments"] = arguments
                except Exception as e:
                    logger.error(f"VerdictEvent validation failed: {e}")
                    raise HTTPException(status_code=400, detail=f"Invalid verdict event schema: {e}")

            # 重新构建请求体
            import io
            request._body = json.dumps(data).encode()

        except json.JSONDecodeError:
            # 不是 JSON，跳过验证
            pass
        except Exception as e:
            logger.error(f"Schema validation error: {e}")
            raise HTTPException(status_code=400, detail=f"Invalid schema: {e}")

        return await call_next(request)

    def _get_or_create_task_id(self, taskcode: str) -> str:
        """从 taskcode 获取或创建 task_id"""
        # 从映射表获取（如果存在）
        mapping = TaskIDMappingService()
        task_id = mapping.get_task_id_by_code(taskcode)
        if task_id:
            return task_id

        # 如果不存在，从 taskcode 解析生成
        # taskcode 格式通常是: AREA__YYYYMMDD 或 AREA-YYYYMMDD-XXX
        # 尝试解析
        if "__" in taskcode:
            parts = taskcode.split("__")
            area = parts[0]
            date_part = parts[1] if len(parts) > 1 else ""
        elif "-" in taskcode:
            parts = taskcode.split("-")
            area = parts[0]
            date_part = parts[1] if len(parts) > 1 else ""
        else:
            area = taskcode
            date_part = ""

        # 提取日期（YYYYMMDD）
        date = ""
        if len(date_part) >= 8:
            date = date_part[:8]
        else:
            date = None

        # 生成 task_id
        task_id = TaskIDGenerator.generate(area=area, date=date)
        
        # 保存映射
        mapping.save_mapping(taskcode, task_id)
        
        return task_id


class TaskIDMappingService:
    """Task ID 映射服务（taskcode <-> task_id）"""

    def __init__(self, repo_root: Path | None = None):
        if repo_root is None:
            # 默认从环境变量或当前目录推断
            import os
            repo_root = Path(os.getenv("REPO_ROOT", ".")).resolve()
        self.repo_root = repo_root
        self.mapping_file = self.repo_root / "docs" / "REPORT" / "ata" / "task_id_mapping.json"
        self.mapping_file.parent.mkdir(parents=True, exist_ok=True)

    def get_task_id_by_code(self, taskcode: str) -> str | None:
        """从 taskcode 获取 task_id"""
        mapping = self._load_mapping()
        return mapping.get(taskcode)

    def get_code_by_task_id(self, task_id: str) -> str | None:
        """从 task_id 获取 taskcode"""
        mapping = self._load_mapping()
        # 反向查找
        for code, tid in mapping.items():
            if tid == task_id:
                return code
        return None

    def save_mapping(self, taskcode: str, task_id: str) -> None:
        """保存映射"""
        mapping = self._load_mapping()
        mapping[taskcode] = task_id
        self._save_mapping(mapping)

    def _load_mapping(self) -> dict[str, str]:
        """加载映射表"""
        if not self.mapping_file.exists():
            return {}
        try:
            with open(self.mapping_file, encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Failed to load task_id mapping: {e}")
            return {}

    def _ensure_ata_message_compatibility(self, message):
        """确保ATA消息兼容新格式，补全必要字段"""
        from models import ATAMessage
        
        # 确保消息具有所有必要字段
        message_dict = message.model_dump()
        
        # 补全ATA消息的必要字段，确保向后兼容
        if not message_dict.get("message_id"):
            import uuid
            message_dict["message_id"] = str(uuid.uuid4())
        
        if not message_dict.get("kind"):
            message_dict["kind"] = "request"
        
        if not message_dict.get("priority"):
            message_dict["priority"] = "normal"
        
        if "requires_response" not in message_dict:
            message_dict["requires_response"] = True
        
        if not message_dict.get("created_at"):
            from datetime import datetime, timezone
            message_dict["created_at"] = datetime.now(timezone.utc).isoformat()
        
        # 确保task_id或taskcode至少有一个存在
        if not message_dict.get("task_id") and not message_dict.get("taskcode"):
            # 如果都没有，生成一个临时task_id
            message_dict["task_id"] = self._get_or_create_task_id("TEMP")
        
        return ATAMessage(**message_dict)
    
    def _save_mapping(self, mapping: dict[str, str]) -> None:
        """保存映射表"""
        try:
            with open(self.mapping_file, "w", encoding="utf-8") as f:
                json.dump(mapping, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Failed to save task_id mapping: {e}")
