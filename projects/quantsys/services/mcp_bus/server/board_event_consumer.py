
"""
看板事件消费器
消费事件并自动更新看板状态
"""

import json
from pathlib import Path
from typing import Optional

from .event_publisher import EventPublisher
from .message_queue import MessageQueue
from .models import Event, EventType
from .task_id_mapper import TaskIDMapper


class BoardEventConsumer:
    """看板事件消费器"""
    
    def __init__(
        self,
        repo_root: Path,
        message_queue: MessageQueue,
        task_id_mapper: TaskIDMapper,
        board_file: Optional[Path] = None,
    ):
        self.repo_root = repo_root
        self.message_queue = message_queue
        self.task_id_mapper = task_id_mapper
        if board_file is None:
            board_file = repo_root / "docs" / "REPORT" / "QCC-PROGRAM-BOARD-v0.1.md"
        self.board_file = board_file
    
    def consume_events(self, limit: int = 10) -> int:
        """消费事件并更新看板"""
        # 从队列获取待处理消息（to_agent="board"）
        messages = self.message_queue.get_pending_messages(limit)
        processed = 0
        
        for msg in messages:
            if msg.get("to_agent") != "board":
                continue
            
            payload = msg.get("payload", {})
            event_data = payload.get("event_data")
            if not event_data:
                continue
            
            try:
                event = Event(**event_data)
                if self._process_event(event):
                    # 标记消息已确认
                    self.message_queue.mark_acked(msg["message_id"])
                    processed += 1
                else:
                    # 标记消息未确认（需要重试）
                    self.message_queue.mark_nacked(msg["message_id"], "Failed to process event")
            except Exception as e:
                # 标记消息失败
                self.message_queue.mark_nacked(msg["message_id"], str(e))
        
        return processed
    
    def _process_event(self, event: Event) -> bool:
        """处理单个事件"""
        try:
            if event.type == EventType.TASK_CREATED:
                return self._handle_task_created(event)
            elif event.type == EventType.TASK_UPDATED:
                return self._handle_task_updated(event)
            elif event.type == EventType.VERDICT_GENERATED:
                return self._handle_verdict_generated(event)
            elif event.type == EventType.SUBTASK_COMPLETED:
                return self._handle_subtask_completed(event)
            elif event.type in (EventType.PERF_METRIC, EventType.DEVLOOP_METRIC):
                return True
            return False
        except Exception:
            return False
    
    def _handle_task_created(self, event: Event) -> bool:
        """处理任务创建事件"""
        payload = event.payload
        task_id = payload.get("task_id")
        task_code = payload.get("task_code")
        
        if not task_id or not task_code:
            return False
        
        # 更新看板（添加任务条目）
        return self._update_board_status(task_code, "ACTIVE", None)
    
    def _handle_task_updated(self, event: Event) -> bool:
        """处理任务更新事件"""
        task_id = event.correlation_id
        task_code = self.task_id_mapper.get_taskcode(task_id)
        
        if not task_code:
            return False
        
        payload = event.payload
        status = payload.get("status")
        
        if status:
            return self._update_board_status(task_code, status.upper(), None)
        
        return False
    
    def _handle_verdict_generated(self, event: Event) -> bool:
        """处理 verdict 事件"""
        payload = event.payload
        status = payload.get("status", "").upper()
        task_code = payload.get("task_code")
        fail_codes = payload.get("fail_codes", [])
        
        if not task_code:
            return False
        
        # 根据 verdict 状态更新看板
        board_status = "FAILED" if status == "FAIL" else "DONE"
        artifacts = f"fail_codes: {', '.join(fail_codes)}" if fail_codes else None
        
        return self._update_board_status(task_code, board_status, artifacts)
    
    def _handle_subtask_completed(self, event: Event) -> bool:
        """处理子任务完成事件"""
        payload = event.payload
        task_id = payload.get("task_id")
        task_code = self.task_id_mapper.get_taskcode(task_id)
        
        if not task_code:
            return False
        
        # 子任务完成不影响看板主状态，但可以记录
        return True
    
    def _update_board_status(self, task_code: str, status: str, artifacts: Optional[str]) -> bool:
        """更新看板状态"""
        if not self.board_file.exists():
            self.board_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.board_file, "w", encoding="utf-8") as f:
                f.write(f"# QCC Program Board v0.1\n\n## {task_code}\n\n**Status:** {status}\n")
                if artifacts:
                    f.write(f"**Artifacts:** {artifacts}\n")
            return True
        
        with open(self.board_file, encoding="utf-8") as f:
            content = f.read()
        
        task_marker = f"**Task Code:** {task_code}"
        if task_marker not in content:
            # 添加新任务
            content += f"\n\n## {task_code}\n\n**Task Code:** {task_code}\n**Status:** {status}\n"
            if artifacts:
                content += f"**Artifacts:** {artifacts}\n"
        else:
            # 更新现有任务状态
            lines = content.split("\n")
            updated_lines = []
            for i, line in enumerate(lines):
                updated_lines.append(line)
                if task_marker in line:
                    # 查找并更新状态
                    for j in range(i + 1, min(i + 10, len(lines))):
                        if lines[j].strip().startswith("**Status:**"):
                            updated_lines[-1] = lines[j]
                            updated_lines.append(f"**Status:** {status}")
                            if artifacts and j + 1 < len(lines) and not lines[j + 1].strip().startswith("**Artifacts:**"):
                                updated_lines.append(f"**Artifacts:** {artifacts}")
                            break
            
            content = "\n".join(updated_lines)
        
        with open(self.board_file, "w", encoding="utf-8") as f:
            f.write(content)
        
        return True
