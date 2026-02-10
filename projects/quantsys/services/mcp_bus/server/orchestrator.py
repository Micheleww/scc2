"""
任务编排器 (Task Orchestrator)
管理复杂的多 Agent 协作任务，包括任务分析、分解、执行计划和状态跟踪
"""

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

# 引入统一数据模型
from .models import Task, SubTask as NewSubTask, Event, TaskStatus as NewTaskStatus, SubTaskStatus as NewSubTaskStatus, validate_task, validate_event


# 使用统一的任务状态枚举
TaskStatus = NewTaskStatus
SubTaskStatus = NewSubTaskStatus


@dataclass
class TaskAnalysis:
    """任务分析结果"""

    task_id: str
    required_roles: list[str]
    required_capabilities: list[str]
    complexity: str  # simple, medium, complex
    estimated_duration: float  # seconds
    dependencies: list[str]
    can_parallelize: bool


@dataclass
class SubTask:
    """子任务定义"""

    subtask_id: str
    task_id: str
    step_id: str
    role: str
    action: str
    inputs: dict[str, Any]
    outputs: list[str]
    depends_on: list[str]
    priority: str  # low, normal, high, urgent
    timeout: float  # seconds
    status: SubTaskStatus = SubTaskStatus.PENDING
    assigned_agent: str | None = None
    result: dict[str, Any] | None = None
    error: str | None = None
    started_at: str | None = None
    completed_at: str | None = None


@dataclass
class ExecutionPlan:
    """执行计划"""

    task_id: str
    subtasks: list[SubTask]
    dependencies: dict[str, list[str]]
    parallel_groups: list[list[str]]
    estimated_duration: float
    created_at: str


class TaskAnalyzer:
    """任务分析器"""

    def __init__(self, repo_root: Path):
        self.repo_root = repo_root
        self.role_capabilities = self._load_role_capabilities()

    def _load_role_capabilities(self) -> dict[str, list[str]]:
        """加载角色能力定义"""
        subagents_file = self.repo_root / ".cursor" / "subagents.json"
        if not subagents_file.exists():
            return {}

        try:
            with open(subagents_file, encoding="utf-8") as f:
                config = json.load(f)

            roles = config.get("roles", {})
            capabilities = {}
            for role_id, role_config in roles.items():
                capabilities[role_id] = role_config.get("capabilities", [])
            return capabilities
        except Exception:
            return {}

    def analyze_task(self, task_description: str, task_id: str | None = None) -> TaskAnalysis:
        """分析任务，识别所需角色和能力"""
        if not task_id:
            # 使用统一的task_id生成规则：{area}-{date}-{seq}
            area = "ORCH"
            date = datetime.now().strftime("%Y%m%d")
            # 简化实现，实际应该从持久化存储获取seq
            seq = 1
            task_id = f"{area}-{date}-{seq:03d}"

        # 简单的关键词匹配识别角色
        description_lower = task_description.lower()
        required_roles = []
        required_capabilities = []

        # 角色关键词映射
        role_keywords = {
            "quant_researcher": ["research", "alpha", "signal", "strategy", "model", "回测"],
            "quant_dev_trading": ["implement", "code", "backtest", "optimize", "实现", "代码"],
            "quant_dev_infra": ["pipeline", "data", "infrastructure", "api", "管道", "数据"],
            "quant_trader": ["trade", "execute", "monitor", "risk", "交易", "执行"],
            "risk_manager": ["risk", "limit", "compliance", "压力测试", "风险"],
            "architect": ["design", "architecture", "system", "设计", "架构"],
            "backend_dev": ["api", "backend", "service", "database", "后端"],
            "frontend_dev": ["ui", "frontend", "interface", "前端", "界面"],
            "devops": ["ci/cd", "deploy", "infrastructure", "监控", "部署"],
            "data_engineer": ["etl", "data pipeline", "warehouse", "数据", "管道"],
            "reviewer": ["review", "code review", "审查", "代码审查"],
            "tester": ["test", "qa", "quality", "测试", "质量"],
        }

        # 识别角色
        for role, keywords in role_keywords.items():
            if any(keyword in description_lower for keyword in keywords):
                if role not in required_roles:
                    required_roles.append(role)
                    # 添加角色对应的能力
                    if role in self.role_capabilities:
                        required_capabilities.extend(self.role_capabilities[role])

        # 如果没有识别到角色，使用默认角色
        if not required_roles:
            required_roles = ["implementer"]

        # 评估复杂度
        complexity = "simple"
        if len(required_roles) > 2:
            complexity = "complex"
        elif len(required_roles) > 1:
            complexity = "medium"

        # 估算时间（分钟）
        estimated_duration = len(required_roles) * 30 * 60  # 每个角色30分钟

        # 可以并行化
        can_parallelize = len(required_roles) > 1

        return TaskAnalysis(
            task_id=task_id,
            required_roles=required_roles,
            required_capabilities=list(set(required_capabilities)),
            complexity=complexity,
            estimated_duration=estimated_duration,
            dependencies=[],
            can_parallelize=can_parallelize,
        )


class TaskDecomposer:
    """任务分解器"""

    def decompose_task(
        self, task_analysis: TaskAnalysis, workflow_template: dict[str, Any] | None = None
    ) -> list[SubTask]:
        """将任务分解为子任务"""
        subtasks = []

        if workflow_template:
            # 使用工作流模板
            steps = workflow_template.get("steps", [])
            for idx, step in enumerate(steps):
                subtask_id = f"{task_analysis.task_id}-ST{idx + 1:03d}"
                subtask = SubTask(
                    subtask_id=subtask_id,
                    task_id=task_analysis.task_id,
                    step_id=step.get("step_id", f"step_{idx + 1}"),
                    role=step.get("role", "implementer"),
                    action=step.get("action", "execute"),
                    inputs=step.get("inputs", {}),
                    outputs=step.get("outputs", []),
                    depends_on=step.get("depends_on", []),
                    priority=step.get("priority", "normal"),
                    timeout=step.get("timeout", 1800),
                )
                subtasks.append(subtask)
        else:
            # 简单分解：为每个角色创建一个子任务
            for idx, role in enumerate(task_analysis.required_roles):
                subtask_id = f"{task_analysis.task_id}-ST{idx + 1:03d}"
                subtask = SubTask(
                    subtask_id=subtask_id,
                    task_id=task_analysis.task_id,
                    step_id=f"step_{idx + 1}",
                    role=role,
                    action="execute",
                    inputs={},
                    outputs=[],
                    depends_on=[],
                    priority="normal",
                    timeout=1800,
                )
                subtasks.append(subtask)

        return subtasks


class TaskOrchestrator:
    """任务编排器"""

    def __init__(self, repo_root: Path):
        self.repo_root = repo_root
        self.tasks_dir = self.repo_root / "docs" / "REPORT" / "ata" / "tasks"
        self.tasks_dir.mkdir(parents=True, exist_ok=True)

        self.analyzer = TaskAnalyzer(repo_root)
        self.decomposer = TaskDecomposer()

        # 内存中的任务状态
        self.task_states: dict[str, dict[str, Any]] = {}

    def validate_task_data(self, task_data: dict[str, Any]) -> dict[str, Any]:
        """验证任务数据符合统一schema"""
        try:
            # 使用统一数据模型验证
            task_obj = {
                "task_id": task_data["task_id"],
                "task_code": task_data["task_id"],  # 兼容旧字段
                "goal": task_data["description"],
                "constraints": {
                    "law_ref": None,
                    "allowed_paths": []
                },
                "acceptance": [],  # 暂时留空，后续可从模板或配置获取
                "status": task_data["status"],
                "created_by": "orchestrator",
                "created_at": task_data["created_at"],
                "updated_at": task_data["created_at"]
            }
            validate_task(task_obj)
            return {"success": True, "message": "Task data is valid"}
        except Exception as e:
            return {"success": False, "error": f"Invalid task data: {str(e)}"}
    
    def create_task(
        self,
        task_description: str,
        workflow_template: str | None = None,
        priority: str = "normal",
        timeout: float | None = None,
        required_roles: list[str] | None = None,
    ) -> dict[str, Any]:
        """创建协作任务"""
        # 分析任务
        task_analysis = self.analyzer.analyze_task(task_description)

        # 如果指定了角色，覆盖分析结果
        if required_roles:
            task_analysis.required_roles = required_roles

        # 加载工作流模板
        workflow = None
        if workflow_template:
            workflow = self._load_workflow_template(workflow_template)

        # 分解任务
        subtasks = self.decomposer.decompose_task(task_analysis, workflow)

        # 创建执行计划
        plan = ExecutionPlan(
            task_id=task_analysis.task_id,
            subtasks=subtasks,
            dependencies=self._build_dependencies(subtasks),
            parallel_groups=self._identify_parallel_groups(subtasks),
            estimated_duration=task_analysis.estimated_duration,
            created_at=datetime.now(timezone.utc).isoformat(),
        )

        # 保存任务
        task_data = {
            "task_id": task_analysis.task_id,
            "description": task_description,
            "status": TaskStatus.PENDING.value,
            "priority": priority,
            "timeout": timeout or task_analysis.estimated_duration,
            "created_at": plan.created_at,
            "updated_at": plan.created_at,
            "analysis": asdict(task_analysis),
            "plan": {
                "subtasks": [asdict(st) for st in subtasks],
                "dependencies": plan.dependencies,
                "parallel_groups": plan.parallel_groups,
                "estimated_duration": plan.estimated_duration,
            },
        }

        # 验证任务数据
        validation = self.validate_task_data(task_data)
        if not validation["success"]:
            return {"success": False, "error": validation["error"]}

        task_file = self.tasks_dir / f"{task_analysis.task_id}.json"
        with open(task_file, "w", encoding="utf-8") as f:
            json.dump(task_data, f, ensure_ascii=False, indent=2)

        # 保存到内存
        self.task_states[task_analysis.task_id] = task_data

        # 生成并发布创建事件
        event = Event(
            type="task_created",
            correlation_id=task_analysis.task_id,
            payload={"task_data": task_data},
            timestamp=plan.created_at,
            source="orchestrator"
        )

        return {
            "success": True,
            "task_id": task_analysis.task_id,
            "status": TaskStatus.PENDING.value,
            "subtasks_count": len(subtasks),
            "estimated_duration": task_analysis.estimated_duration,
            "can_parallelize": task_analysis.can_parallelize,
        }

    def get_task_status(self, task_id: str, include_subtasks: bool = True) -> dict[str, Any]:
        """查询任务状态"""
        # 从文件加载
        task_file = self.tasks_dir / f"{task_id}.json"
        if not task_file.exists():
            return {"success": False, "error": f"Task {task_id} not found"}

        with open(task_file, encoding="utf-8") as f:
            task_data = json.load(f)

        # 更新子任务状态
        if include_subtasks:
            subtasks = task_data.get("plan", {}).get("subtasks", [])
            task_data["subtasks"] = subtasks

        return {
            "success": True,
            "task_id": task_id,
            "status": task_data.get("status", TaskStatus.PENDING.value),
            "description": task_data.get("description", ""),
            "priority": task_data.get("priority", "normal"),
            "created_at": task_data.get("created_at", ""),
            "subtasks": task_data.get("subtasks", []) if include_subtasks else [],
            "progress": self._calculate_progress(task_data),
        }

    def update_subtask_status(
        self,
        task_id: str,
        subtask_id: str,
        status: str,
        assigned_agent: str | None = None,
        result: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> dict[str, Any]:
        """更新子任务状态"""
        task_file = self.tasks_dir / f"{task_id}.json"
        if not task_file.exists():
            return {"success": False, "error": f"Task {task_id} not found"}

        with open(task_file, encoding="utf-8") as f:
            task_data = json.load(f)

        # 更新子任务
        subtasks = task_data.get("plan", {}).get("subtasks", [])
        updated_subtask = None
        for subtask in subtasks:
            if subtask.get("subtask_id") == subtask_id:
                subtask["status"] = status
                if assigned_agent:
                    subtask["assigned_agent"] = assigned_agent
                if result:
                    subtask["result"] = result
                if error:
                    subtask["error"] = error

                now = datetime.now(timezone.utc).isoformat()
                if status == SubTaskStatus.RUNNING.value:
                    subtask["started_at"] = now
                elif status in [
                    SubTaskStatus.COMPLETED.value,
                    SubTaskStatus.FAILED.value,
                    SubTaskStatus.SKIPPED.value,
                ]:
                    subtask["completed_at"] = now
                updated_subtask = subtask
                break

        if updated_subtask:
            # 更新任务状态
            task_status = self._update_task_status(task_data)
            task_data["status"] = task_status.value
            task_data["updated_at"] = datetime.now(timezone.utc).isoformat()

            # 保存
            with open(task_file, "w", encoding="utf-8") as f:
                json.dump(task_data, f, ensure_ascii=False, indent=2)

            # 生成并发布子任务更新事件
            event_type = "subtask_completed" if status == SubTaskStatus.COMPLETED.value else "subtask_updated"
            event = Event(
                type=event_type,
                correlation_id=task_id,
                payload={
                    "subtask_id": subtask_id,
                    "task_id": task_id,
                    "status": status,
                    "assigned_agent": assigned_agent,
                    "result": result,
                    "error": error,
                    "updated_at": task_data["updated_at"]
                },
                timestamp=task_data["updated_at"],
                source="orchestrator"
            )

            return {"success": True, "task_id": task_id, "subtask_id": subtask_id, "status": status}

        return {"success": False, "error": f"Subtask {subtask_id} not found"}

    def _load_workflow_template(self, template_name: str) -> dict[str, Any] | None:
        """加载工作流模板"""
        templates_file = self.repo_root / ".cursor" / "workflow_templates.json"
        if not templates_file.exists():
            return None

        try:
            with open(templates_file, encoding="utf-8") as f:
                templates = json.load(f)
            return templates.get("templates", {}).get(template_name)
        except Exception:
            return None

    def _build_dependencies(self, subtasks: list[SubTask]) -> dict[str, list[str]]:
        """构建依赖关系"""
        dependencies = {}
        for subtask in subtasks:
            if subtask.depends_on:
                dependencies[subtask.subtask_id] = subtask.depends_on
        return dependencies

    def _identify_parallel_groups(self, subtasks: list[SubTask]) -> list[list[str]]:
        """识别可并行执行的组"""
        parallel_groups = []
        processed = set()

        for subtask in subtasks:
            if subtask.subtask_id in processed:
                continue

            # 如果没有依赖，可以并行
            if not subtask.depends_on:
                group = [subtask.subtask_id]
                # 查找其他没有依赖的子任务
                for other in subtasks:
                    if other.subtask_id != subtask.subtask_id and other.subtask_id not in processed:
                        if not other.depends_on:
                            group.append(other.subtask_id)
                            processed.add(other.subtask_id)

                if len(group) > 1:
                    parallel_groups.append(group)
                    processed.update(group)

        return parallel_groups

    def _calculate_progress(self, task_data: dict[str, Any]) -> dict[str, Any]:
        """计算任务进度"""
        subtasks = task_data.get("plan", {}).get("subtasks", [])
        if not subtasks:
            return {"total": 0, "completed": 0, "failed": 0, "percentage": 0}

        total = len(subtasks)
        completed = sum(1 for st in subtasks if st.get("status") == SubTaskStatus.COMPLETED.value)
        failed = sum(1 for st in subtasks if st.get("status") == SubTaskStatus.FAILED.value)
        percentage = int((completed / total) * 100) if total > 0 else 0

        return {
            "total": total,
            "completed": completed,
            "failed": failed,
            "pending": total - completed - failed,
            "percentage": percentage,
        }

    def _update_task_status(self, task_data: dict[str, Any]) -> TaskStatus:
        """更新任务状态"""
        subtasks = task_data.get("plan", {}).get("subtasks", [])
        if not subtasks:
            return TaskStatus.PENDING

        statuses = [st.get("status") for st in subtasks]

        # 如果所有子任务都完成，任务完成
        if all(st == SubTaskStatus.COMPLETED.value for st in statuses):
            return TaskStatus.COMPLETED

        # 如果有失败的子任务，任务失败
        if any(st == SubTaskStatus.FAILED.value for st in statuses):
            return TaskStatus.FAILED

        # 如果有运行中的子任务，任务运行中
        if any(st == SubTaskStatus.RUNNING.value for st in statuses):
            return TaskStatus.RUNNING

        # 如果有等待依赖的子任务，任务等待中
        if any(st == SubTaskStatus.PENDING.value for st in statuses):
            return TaskStatus.WAITING

        return TaskStatus.PENDING

    def get_all_tasks(self) -> list[dict[str, Any]]:
        """获取所有任务"""
        tasks = []

        # 从文件系统加载所有任务
        if self.tasks_dir.exists():
            for task_file in self.tasks_dir.glob("*.json"):
                try:
                    with open(task_file, encoding="utf-8") as f:
                        task_data = json.load(f)
                        # 计算进度
                        progress = self._calculate_progress(task_data)
                        # 获取状态
                        status = task_data.get("status", "pending")

                        task_info = {
                            "task_id": task_data.get("task_id"),
                            "description": task_data.get("description", ""),
                            "status": status,
                            "progress": progress,
                            "created_at": task_data.get("created_at"),
                            "updated_at": task_data.get("updated_at"),
                        }
                        tasks.append(task_info)
                except Exception:
                    continue

        # 按创建时间倒序排序
        tasks.sort(key=lambda x: x.get("created_at", ""), reverse=True)
        return tasks
