"""
Verdict 事件处理器
处理 CI 门禁生成的 verdict，发布事件并触发修复任务
"""

import json
from pathlib import Path
from typing import Optional

from .event_publisher import EventPublisher
from .models import EventType, Event
from .orchestrator import TaskOrchestrator
from .task_id_mapper import TaskIDMapper


class VerdictHandler:
    """Verdict 处理器"""
    
    def __init__(
        self,
        repo_root: Path,
        event_publisher: EventPublisher,
        orchestrator: TaskOrchestrator,
        task_id_mapper: TaskIDMapper,
    ):
        self.repo_root = repo_root
        self.event_publisher = event_publisher
        self.orchestrator = orchestrator
        self.task_id_mapper = task_id_mapper
    
    def process_verdict(self, verdict_path: Path) -> dict:
        """
        处理 CI 生成的 verdict.json
        
        Args:
            verdict_path: verdict.json 文件路径
            
        Returns:
            处理结果
        """
        if not verdict_path.exists():
            return {"success": False, "error": "Verdict file not found"}
        
        try:
            with open(verdict_path, encoding="utf-8") as f:
                verdict_data = json.load(f)
        except Exception as e:
            return {"success": False, "error": f"Failed to read verdict: {e}"}
        
        # 提取关键信息
        status_raw = verdict_data.get("status", "unknown")
        status = verdict_data.get("status_normalized") or self._normalize_status(status_raw)
        fail_codes = self._extract_fail_codes(verdict_data)
        task_code = verdict_data.get("task_code") or verdict_data.get("TaskCode")
        
        # 获取 task_id
        task_id = None
        if task_code:
            task_id = self.task_id_mapper.get_task_id(task_code)
            if not task_id:
                # 如果映射不存在，尝试从 verdict 中提取或生成
                # 这里简化处理，实际应该从 REPORT 文件解析
                task_id = self.task_id_mapper.ensure_task_id(task_code)
        
        if not task_id:
            return {"success": False, "error": "Cannot determine task_id from verdict"}
        
        # 发布 verdict 事件
        self.event_publisher.publish_verdict_event(
            task_id=task_id,
            task_code=task_code,
            status=status,
            fail_codes=fail_codes,
            verdict_data=verdict_data,
        )
        
        # 如果 verdict 失败，生成修复子任务
        if status == "fail" and fail_codes:
            repair_result = self._generate_repair_subtasks(task_id, fail_codes, verdict_data)
            return {
                "success": True,
                "task_id": task_id,
                "status": status,
                "fail_codes": fail_codes,
                "repair_subtasks_created": repair_result.get("created", False),
            }
        
        return {
            "success": True,
            "task_id": task_id,
            "status": status,
            "fail_codes": fail_codes,
        }

    @staticmethod
    def _normalize_status(status: str | None) -> str:
        """兼容 PASS/FAIL 与 pass/fail。"""
        if not status:
            return "unknown"
        s = str(status).strip().lower()
        if s in ("pass", "passed", "ok", "success"):
            return "pass"
        if s in ("fail", "failed", "error"):
            return "fail"
        # 兼容 MVM verdict.json 的 PASS/FAIL
        if s == "pass".upper().lower():  # no-op, kept for clarity
            return "pass"
        if s == "fail".upper().lower():
            return "fail"
        if s == "pass" or s == "fail":
            return s
        if s == "pass".lower():
            return "pass"
        if s == "fail".lower():
            return "fail"
        if str(status).strip().upper() == "PASS":
            return "pass"
        if str(status).strip().upper() == "FAIL":
            return "fail"
        return s

    @staticmethod
    def _extract_fail_codes(verdict_data: dict) -> list[str]:
        """优先读顶层 fail_codes，否则从 checks 派生。"""
        fail_codes = verdict_data.get("fail_codes", None)
        if isinstance(fail_codes, list) and all(isinstance(x, str) for x in fail_codes):
            return [x for x in fail_codes if x]

        derived: list[str] = []
        checks = verdict_data.get("checks", [])
        if isinstance(checks, list):
            for chk in checks:
                if not isinstance(chk, dict):
                    continue
                if chk.get("status") != "PASS":
                    name = chk.get("name")
                    if isinstance(name, str) and name:
                        derived.append(name.upper().replace("-", "_").replace(" ", "_"))
        # 去重保持顺序
        seen = set()
        out = []
        for c in derived:
            if c not in seen:
                seen.add(c)
                out.append(c)
        return out
    
    def _generate_repair_subtasks(
        self,
        task_id: str,
        fail_codes: list[str],
        verdict_data: dict,
    ) -> dict:
        """根据 fail_codes 生成修复子任务"""
        try:
            # 获取任务状态
            task_status = self.orchestrator.get_task_status(task_id, include_subtasks=True)
            if not task_status.get("success"):
                return {"created": False, "error": "Task not found"}
            
            # 获取任务文件路径
            task_file = self.orchestrator.tasks_dir / f"{task_id}.json"
            if not task_file.exists():
                return {"created": False, "error": "Task file not found"}
            
            # 读取任务文件
            import json
            from datetime import datetime, timezone
            with open(task_file, encoding="utf-8") as f:
                task_data = json.load(f)
            
            # 为每个 fail_code 创建一个修复子任务
            repair_subtasks = []
            now = datetime.now(timezone.utc).isoformat()
            
            # 确保 plan.subtasks 存在
            if "plan" not in task_data:
                task_data["plan"] = {}
            if "subtasks" not in task_data["plan"]:
                task_data["plan"]["subtasks"] = []
            
            # 获取现有子任务列表
            existing_subtasks = task_data["plan"]["subtasks"]
            existing_subtask_ids = {st.get("subtask_id") for st in existing_subtasks}
            
            # 为每个 fail_code 创建一个修复子任务
            for fail_code in fail_codes:
                subtask_id = f"{task_id}-REPAIR-{fail_code}"
                
                # 跳过已存在的修复子任务
                if subtask_id in existing_subtask_ids:
                    continue
                
                repair_description = self._get_repair_description(fail_code)
                
                # 创建修复子任务
                repair_subtask = {
                    "subtask_id": subtask_id,
                    "task_id": task_id,
                    "step_id": f"REPAIR-{fail_code}",
                    "role": "quant_dev_infra",
                    "action": "fix",
                    "inputs": {
                        "fail_code": fail_code,
                        "verdict_data": verdict_data,
                    },
                    "outputs": [
                        f"修复 {fail_code} 问题",
                        "更新任务状态",
                    ],
                    "depends_on": [],
                    "priority": "high",
                    "timeout": 3600,
                    "status": "pending",
                    "assigned_agent": None,
                    "result": None,
                    "error": None,
                    "started_at": None,
                    "completed_at": None,
                    "fail_code": fail_code,
                    "description": repair_description,
                }
                
                # 添加到现有子任务列表
                existing_subtasks.append(repair_subtask)
                repair_subtasks.append(repair_subtask)
            
            # 保存更新后的任务文件
            with open(task_file, "w", encoding="utf-8") as f:
                json.dump(task_data, f, ensure_ascii=False, indent=2)
            
            # 发布子任务创建事件
            for subtask in repair_subtasks:
                self.event_publisher.publish_event(
                    Event(
                        type=EventType.SUBTASK_CREATED,
                        correlation_id=subtask["subtask_id"],
                        payload={
                            "task_id": task_id,
                            "subtask": subtask,
                            "reason": "verdict_fail_repair",
                        },
                        source="verdict_handler",
                    )
                )
            
            return {"created": True, "subtasks": repair_subtasks}
        except Exception as e:
            import traceback
            traceback.print_exc()
            return {"created": False, "error": str(e)}
    
    def _get_repair_description(self, fail_code: str) -> str:
        """根据 fail_code 生成修复描述"""
        descriptions = {
            "SELFTEST_USER_SUPPLIED": "修复：移除用户提供的 selftest.log，仅使用 CI 生成的 ci_selftest_proof.json",
            "EVIDENCE_SCOPE_VIOLATION": "修复：确保所有 evidence_paths 都在 artifacts 目录下",
            "STAGE_MISSING": "修复：补充缺失的阶段文件",
            "STAGE_VALIDATION_FAILED": "修复：修正阶段文件验证错误",
            "ABSOLUTE_PATH_IN_EVIDENCE": "修复：将所有绝对路径改为相对路径",
        }
        return descriptions.get(fail_code, f"修复 CI 门禁失败：{fail_code}")
