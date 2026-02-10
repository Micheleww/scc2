"""
工作流引擎 (Workflow Engine)
定义和执行可复用的多 Agent 工作流，支持条件分支和循环
"""

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any


class StepStatus(str, Enum):
    """步骤状态"""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class WorkflowStatus(str, Enum):
    """工作流状态"""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class RetryPolicy:
    """重试策略"""

    max_retries: int = 3
    retry_delay: int = 60  # 秒
    backoff_multiplier: float = 2.0


@dataclass
class WorkflowStep:
    """工作流步骤"""

    step_id: str
    role: str
    action: str
    inputs: dict[str, Any]
    outputs: list[str]
    depends_on: list[str]
    timeout: float  # 秒
    retry_policy: RetryPolicy | None = None
    condition: str | None = None  # 条件表达式
    status: StepStatus = StepStatus.PENDING
    retry_count: int = 0
    assigned_agent: str | None = None
    result: dict[str, Any] | None = None
    error: str | None = None
    started_at: str | None = None
    completed_at: str | None = None


@dataclass
class WorkflowDefinition:
    """工作流定义"""

    name: str
    description: str
    steps: list[WorkflowStep]
    default_timeout: float = 3600  # 秒
    default_retry_policy: RetryPolicy | None = None


@dataclass
class WorkflowInstance:
    """工作流实例"""

    instance_id: str
    workflow_name: str
    task_id: str | None
    inputs: dict[str, Any]
    status: WorkflowStatus
    current_step: str | None
    steps: list[WorkflowStep]
    outputs: dict[str, Any]
    created_at: str
    started_at: str | None = None
    completed_at: str | None = None


class WorkflowTemplateManager:
    """工作流模板管理器"""

    def __init__(self, repo_root: Path):
        self.repo_root = repo_root
        self.templates_file = self.repo_root / ".cursor" / "workflow_templates.json"
        self.templates: dict[str, dict[str, Any]] = {}
        self.load_templates()

    def load_templates(self):
        """加载工作流模板"""
        if self.templates_file.exists():
            try:
                with open(self.templates_file, encoding="utf-8") as f:
                    data = json.load(f)
                self.templates = data.get("templates", {})
            except Exception:
                self.templates = {}
        else:
            # 创建默认模板
            self._create_default_templates()

    def save_templates(self):
        """保存工作流模板"""
        self.templates_file.parent.mkdir(parents=True, exist_ok=True)
        data = {"templates": self.templates}
        with open(self.templates_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def get_template(self, template_name: str) -> dict[str, Any] | None:
        """获取工作流模板"""
        return self.templates.get(template_name)

    def list_templates(self) -> list[str]:
        """列出所有模板"""
        return list(self.templates.keys())

    def _create_default_templates(self):
        """创建默认模板"""
        self.templates = {
            "quant_research_to_code": {
                "name": "量化研究到代码",
                "description": "从量化研究到代码实现的完整流程",
                "steps": [
                    {
                        "step_id": "research",
                        "role": "quant_researcher",
                        "action": "design_strategy",
                        "inputs": {},
                        "outputs": ["strategy_design"],
                        "depends_on": [],
                        "timeout": 1800,
                        "retry_policy": {"max_retries": 2, "retry_delay": 60},
                    },
                    {
                        "step_id": "implement",
                        "role": "quant_dev_trading",
                        "action": "implement_strategy",
                        "inputs": {"strategy_design": "${research.strategy_design}"},
                        "outputs": ["code"],
                        "depends_on": ["research"],
                        "timeout": 3600,
                    },
                    {
                        "step_id": "review",
                        "role": "reviewer",
                        "action": "review_code",
                        "inputs": {"code": "${implement.code}"},
                        "outputs": ["review_report"],
                        "depends_on": ["implement"],
                        "timeout": 900,
                    },
                ],
                "default_timeout": 3600,
            },
            "multi_agent_collaboration": {
                "name": "多 Agent 协作开发流程",
                "description": "标准化的 Architect→Implementer→Reviewer→Tester 完整开发流程，所有步骤通过 ATA 代发+审核机制执行",
                "steps": [
                    {
                        "step_id": "architect",
                        "role": "architect",
                        "action": "design_system",
                        "inputs": {"requirement": "${workflow_inputs.requirement}"},
                        "outputs": ["design_doc", "architecture_spec"],
                        "depends_on": [],
                        "timeout": 3600,
                        "ata_message_kind": "request",
                        "ata_taskcode_prefix": "ARCH",
                    },
                    {
                        "step_id": "implementer",
                        "role": "implementer",
                        "action": "implement_code",
                        "inputs": {
                            "design_doc": "${architect.design_doc}",
                            "architecture_spec": "${architect.architecture_spec}",
                        },
                        "outputs": ["code", "implementation_report"],
                        "depends_on": ["architect"],
                        "timeout": 7200,
                        "ata_message_kind": "request",
                        "ata_taskcode_prefix": "IMPL",
                    },
                    {
                        "step_id": "reviewer",
                        "role": "reviewer",
                        "action": "review_code",
                        "inputs": {
                            "code": "${implementer.code}",
                            "implementation_report": "${implementer.implementation_report}",
                        },
                        "outputs": ["review_report", "approval_status"],
                        "depends_on": ["implementer"],
                        "timeout": 1800,
                        "ata_message_kind": "request",
                        "ata_taskcode_prefix": "REVIEW",
                    },
                    {
                        "step_id": "tester",
                        "role": "tester",
                        "action": "test_code",
                        "inputs": {
                            "code": "${implementer.code}",
                            "review_report": "${reviewer.review_report}",
                        },
                        "outputs": ["test_report", "test_results"],
                        "depends_on": ["reviewer"],
                        "timeout": 1800,
                        "ata_message_kind": "request",
                        "ata_taskcode_prefix": "TEST",
                    },
                ],
                "default_timeout": 14400,
            },
            "parallel_exploration": {
                "name": "并行探索多个方案",
                "description": "同时启动多个 Architect 探索不同方案，各自独立证据链，最后汇总决策",
                "steps": [
                    {
                        "step_id": "arch_parallel_1",
                        "role": "architect",
                        "action": "explore_approach_1",
                        "inputs": {
                            "requirement": "${workflow_inputs.requirement}",
                            "approach": "approach_1",
                        },
                        "outputs": ["design_1", "evidence_1"],
                        "depends_on": [],
                        "timeout": 3600,
                        "ata_message_kind": "request",
                        "ata_taskcode_prefix": "ARCH-PARALLEL-1",
                        "parallel_group": "exploration",
                    },
                    {
                        "step_id": "arch_parallel_2",
                        "role": "architect",
                        "action": "explore_approach_2",
                        "inputs": {
                            "requirement": "${workflow_inputs.requirement}",
                            "approach": "approach_2",
                        },
                        "outputs": ["design_2", "evidence_2"],
                        "depends_on": [],
                        "timeout": 3600,
                        "ata_message_kind": "request",
                        "ata_taskcode_prefix": "ARCH-PARALLEL-2",
                        "parallel_group": "exploration",
                    },
                    {
                        "step_id": "arch_parallel_3",
                        "role": "architect",
                        "action": "explore_approach_3",
                        "inputs": {
                            "requirement": "${workflow_inputs.requirement}",
                            "approach": "approach_3",
                        },
                        "outputs": ["design_3", "evidence_3"],
                        "depends_on": [],
                        "timeout": 3600,
                        "ata_message_kind": "request",
                        "ata_taskcode_prefix": "ARCH-PARALLEL-3",
                        "parallel_group": "exploration",
                    },
                    {
                        "step_id": "aggregate_decision",
                        "role": "architect",
                        "action": "aggregate_and_decide",
                        "inputs": {
                            "design_1": "${arch_parallel_1.design_1}",
                            "design_2": "${arch_parallel_2.design_2}",
                            "design_3": "${arch_parallel_3.design_3}",
                            "evidence_1": "${arch_parallel_1.evidence_1}",
                            "evidence_2": "${arch_parallel_2.evidence_2}",
                            "evidence_3": "${arch_parallel_3.evidence_3}",
                        },
                        "outputs": ["final_design", "decision_report"],
                        "depends_on": ["arch_parallel_1", "arch_parallel_2", "arch_parallel_3"],
                        "timeout": 1800,
                        "ata_message_kind": "request",
                        "ata_taskcode_prefix": "AGGREGATE",
                    },
                ],
                "default_timeout": 10800,
            },
            "quality_assurance": {
                "name": "质量保证流程",
                "description": "强制质量审查流程：REVIEW→TEST→CI Gate，所有步骤必须附带三件套（REPORT/selftest.log/artifacts）",
                "steps": [
                    {
                        "step_id": "code_review",
                        "role": "reviewer",
                        "action": "comprehensive_review",
                        "inputs": {
                            "code": "${workflow_inputs.code}",
                            "context": "${workflow_inputs.context}",
                        },
                        "outputs": ["review_report", "issues_found", "approval_status"],
                        "depends_on": [],
                        "timeout": 1800,
                        "ata_message_kind": "request",
                        "ata_taskcode_prefix": "QA-REVIEW",
                        "requires_audit_triplet": True,
                    },
                    {
                        "step_id": "test_execution",
                        "role": "tester",
                        "action": "run_tests",
                        "inputs": {
                            "code": "${workflow_inputs.code}",
                            "review_report": "${code_review.review_report}",
                        },
                        "outputs": ["test_report", "test_results", "coverage"],
                        "depends_on": ["code_review"],
                        "timeout": 3600,
                        "ata_message_kind": "request",
                        "ata_taskcode_prefix": "QA-TEST",
                        "requires_audit_triplet": True,
                    },
                    {
                        "step_id": "ci_gate_check",
                        "role": "ci_complete",
                        "action": "run_ci_checks",
                        "inputs": {
                            "code": "${workflow_inputs.code}",
                            "test_report": "${test_execution.test_report}",
                            "review_report": "${code_review.review_report}",
                        },
                        "outputs": ["ci_status", "gate_result", "verdict"],
                        "depends_on": ["test_execution"],
                        "timeout": 1800,
                        "ata_message_kind": "request",
                        "ata_taskcode_prefix": "QA-CI-GATE",
                        "requires_audit_triplet": True,
                        "ci_checks": ["agent-registry", "validate-ata", "fast-gate"],
                    },
                ],
                "default_timeout": 7200,
            },
        }
        self.save_templates()


class WorkflowExecutor:
    """工作流执行器"""

    def __init__(self, repo_root: Path, coordinator=None, tool_executor=None):
        self.repo_root = repo_root
        self.coordinator = coordinator
        self.tool_executor = tool_executor  # Reference to ToolExecutor for ATA operations
        self.template_manager = WorkflowTemplateManager(repo_root)
        self.instances_dir = self.repo_root / "docs" / "REPORT" / "ata" / "workflows"
        self.instances_dir.mkdir(parents=True, exist_ok=True)

        # 内存中的实例状态
        self.running_instances: dict[str, WorkflowInstance] = {}

    def execute_workflow(
        self, workflow_name: str, inputs: dict[str, Any], task_id: str | None = None
    ) -> dict[str, Any]:
        """执行工作流"""
        # 获取工作流模板
        template = self.template_manager.get_template(workflow_name)
        if not template:
            return {"success": False, "error": f"Workflow template '{workflow_name}' not found"}

        # 创建实例
        instance_id = f"WF-{datetime.now().strftime('%Y%m%d%H%M%S')}-{hashlib.md5(workflow_name.encode()).hexdigest()[:8]}"

        # 构建步骤
        steps = []
        for step_data in template.get("steps", []):
            retry_policy = None
            if "retry_policy" in step_data:
                retry_data = step_data["retry_policy"]
                retry_policy = RetryPolicy(**retry_data)

            step = WorkflowStep(
                step_id=step_data.get("step_id"),
                role=step_data.get("role"),
                action=step_data.get("action"),
                inputs=self._resolve_inputs(step_data.get("inputs", {}), inputs),
                outputs=step_data.get("outputs", []),
                depends_on=step_data.get("depends_on", []),
                timeout=step_data.get("timeout", template.get("default_timeout", 3600)),
                retry_policy=retry_policy,
            )
            steps.append(step)

        # 创建实例
        instance = WorkflowInstance(
            instance_id=instance_id,
            workflow_name=workflow_name,
            task_id=task_id,
            inputs=inputs,
            status=WorkflowStatus.PENDING,
            current_step=None,
            steps=steps,
            outputs={},
            created_at=datetime.now().isoformat() + "Z",
        )

        # 保存实例
        self._save_instance(instance)

        # 开始执行
        self._start_execution(instance)

        return {
            "success": True,
            "instance_id": instance_id,
            "workflow_name": workflow_name,
            "status": instance.status.value,
            "steps_count": len(steps),
        }

    def get_workflow_status(self, instance_id: str) -> dict[str, Any]:
        """获取工作流状态"""
        instance_file = self.instances_dir / f"{instance_id}.json"
        if not instance_file.exists():
            return {"success": False, "error": f"Workflow instance {instance_id} not found"}

        with open(instance_file, encoding="utf-8") as f:
            instance_data = json.load(f)

        return {
            "success": True,
            "instance_id": instance_id,
            "status": instance_data.get("status"),
            "current_step": instance_data.get("current_step"),
            "steps": instance_data.get("steps", []),
            "outputs": instance_data.get("outputs", {}),
            "progress": self._calculate_progress(instance_data),
        }

    def _resolve_inputs(
        self, input_template: dict[str, Any], workflow_inputs: dict[str, Any]
    ) -> dict[str, Any]:
        """解析输入模板"""
        resolved = {}

        for key, value in input_template.items():
            if isinstance(value, str) and value.startswith("${"):
                # 解析引用：${step.output}
                ref = value[2:-1]  # 去掉 ${}
                parts = ref.split(".")
                if len(parts) == 2:
                    step_id, output_key = parts
                    # 这里应该从之前的步骤结果中获取
                    # 简化实现：直接使用 workflow_inputs
                    resolved[key] = workflow_inputs.get(output_key)
                else:
                    resolved[key] = workflow_inputs.get(ref, value)
            else:
                resolved[key] = value

        return resolved

    def _start_execution(self, instance: WorkflowInstance):
        """开始执行"""
        instance.status = WorkflowStatus.RUNNING
        instance.started_at = datetime.now().isoformat() + "Z"

        # 查找可执行的步骤（没有依赖或依赖已完成）
        ready_steps = self._find_ready_steps(instance)

        if ready_steps:
            # 执行第一个就绪的步骤
            step = ready_steps[0]
            instance.current_step = step.step_id
            self._execute_step(instance, step)

        self._save_instance(instance)

    def _find_ready_steps(self, instance: WorkflowInstance) -> list[WorkflowStep]:
        """查找可执行的步骤"""
        ready = []

        for step in instance.steps:
            # 跳过已完成的步骤
            if step.status == StepStatus.COMPLETED:
                continue

            # 跳过失败的步骤
            if step.status == StepStatus.FAILED:
                continue

            # 检查依赖
            if step.depends_on:
                all_deps_completed = all(
                    any(
                        s.step_id == dep and s.status == StepStatus.COMPLETED
                        for s in instance.steps
                    )
                    for dep in step.depends_on
                )
                if not all_deps_completed:
                    continue

            ready.append(step)

        return ready

    def _execute_step(self, instance: WorkflowInstance, step: WorkflowStep):
        """执行步骤：通过 ATA 代发机制执行"""
        step.status = StepStatus.RUNNING
        step.started_at = datetime.now().isoformat() + "Z"

        # 如果 coordinator 可用，分配 Agent
        to_agent_id = None
        if self.coordinator:
            agents = self.coordinator.find_agents(role=step.role, available_only=True)
            if agents:
                to_agent_id = agents[0].agent_id
                step.assigned_agent = to_agent_id

        if not to_agent_id:
            step.status = StepStatus.FAILED
            step.error = f"No available agent found for role: {step.role}"
            step.completed_at = datetime.now().isoformat() + "Z"
            instance.status = WorkflowStatus.FAILED
            self._save_instance(instance)
            return

        # 通过 ATA 代发机制执行步骤
        if self.tool_executor:
            # 生成 TaskCode
            taskcode_prefix = step.inputs.get("ata_taskcode_prefix") or step.step_id.upper()
            taskcode = f"{taskcode_prefix}-{instance.instance_id[:8]}"

            # 构建消息 payload
            from datetime import datetime as dt

            date_str = dt.now().strftime("%Y%m%d")

            # 生成三件套路径（如果步骤要求）
            report_path = None
            selftest_log_path = None
            evidence_dir = None
            if step.inputs.get("requires_audit_triplet", False):
                area = "ata"
                artifacts_base = self.repo_root / "docs" / "REPORT" / area / "artifacts" / taskcode
                artifacts_base.mkdir(parents=True, exist_ok=True)
                report_path = f"docs/REPORT/{area}/REPORT__{taskcode}__{date_str}.md"
                selftest_log_path = f"docs/REPORT/{area}/artifacts/{taskcode}/selftest.log"
                evidence_dir = f"docs/REPORT/{area}/artifacts/{taskcode}/"

            # 构建消息文本（必须包含 @对方#NN）
            to_agent_obj = (
                self.coordinator.registry.get_agent(to_agent_id) if self.coordinator else None
            )
            to_display = (
                f"{to_agent_id}#{int(to_agent_obj.numeric_code):02d}"
                if to_agent_obj and getattr(to_agent_obj, "numeric_code", None)
                else to_agent_id
            )

            message_text = f"@{to_display} 【工作流步骤】{step.step_id}: {step.action}\n\n"
            message_text += f"工作流: {instance.workflow_name}\n"
            message_text += f"实例ID: {instance.instance_id}\n"
            message_text += f"步骤输入: {json.dumps(step.inputs, ensure_ascii=False, indent=2)}\n"
            if step.inputs.get("requires_audit_triplet"):
                message_text += "\n【强制要求】本步骤必须附带三件套：\n"
                message_text += f"- REPORT: {report_path}\n"
                message_text += f"- selftest.log: {selftest_log_path}\n"
                message_text += f"- artifacts: {evidence_dir}\n"

            payload = {
                "message": message_text,
                "text": message_text,
                "workflow_instance_id": instance.instance_id,
                "workflow_name": instance.workflow_name,
                "step_id": step.step_id,
                "step_action": step.action,
                "step_inputs": step.inputs,
                "from_display": "workflow_engine",
                "to_display": to_display,
                "ata_comm_rule": "name_with_code_v1",
            }

            # 调用 ata_send_request（入队，等待管理员审核）
            from .tools import ATASendRequestParams

            request_params = ATASendRequestParams(
                taskcode=taskcode,
                from_agent="workflow_engine",
                to_agent=to_agent_id,
                kind=step.inputs.get("ata_message_kind", "request"),
                payload=payload,
                priority="normal",
                requires_response=True,
                report_path=report_path,
                selftest_log_path=selftest_log_path,
                evidence_dir=evidence_dir,
            )

            request_result = self.tool_executor.ata_send_request(
                request_params, caller="workflow_engine", trace_id=instance.instance_id
            )

            if request_result.get("success"):
                step.result = {
                    "status": "pending_review",
                    "request_id": request_result.get("request_id"),
                    "message": "Step queued for admin review via ATA outbox",
                }
                # 步骤状态保持 RUNNING，等待审核通过后更新
            else:
                step.status = StepStatus.FAILED
                step.error = request_result.get("error", "Failed to enqueue ATA send request")
                step.completed_at = datetime.now().isoformat() + "Z"
        else:
            # 如果没有 tool_executor，标记为需要手动执行
            step.result = {
                "status": "manual_execution_required",
                "message": "ToolExecutor not available, manual execution required",
            }

        # 更新输出
        if step.result:
            for output_key in step.outputs:
                instance.outputs[output_key] = step.result.get(output_key, step.result)

        self._save_instance(instance)

    def _save_instance(self, instance: WorkflowInstance):
        """保存实例"""
        instance_file = self.instances_dir / f"{instance.instance_id}.json"
        instance_data = {
            "instance_id": instance.instance_id,
            "workflow_name": instance.workflow_name,
            "task_id": instance.task_id,
            "inputs": instance.inputs,
            "status": instance.status.value,
            "current_step": instance.current_step,
            "steps": [asdict(step) for step in instance.steps],
            "outputs": instance.outputs,
            "created_at": instance.created_at,
            "started_at": instance.started_at,
            "completed_at": instance.completed_at,
        }

        with open(instance_file, "w", encoding="utf-8") as f:
            json.dump(instance_data, f, ensure_ascii=False, indent=2)

    def _calculate_progress(self, instance_data: dict[str, Any]) -> dict[str, Any]:
        """计算进度"""
        steps = instance_data.get("steps", [])
        if not steps:
            return {"total": 0, "completed": 0, "percentage": 0}

        total = len(steps)
        completed = sum(1 for s in steps if s.get("status") == StepStatus.COMPLETED.value)
        percentage = int((completed / total) * 100) if total > 0 else 0

        return {
            "total": total,
            "completed": completed,
            "failed": sum(1 for s in steps if s.get("status") == StepStatus.FAILED.value),
            "percentage": percentage,
        }

    def get_all_instances(self) -> list[dict[str, Any]]:
        """获取所有工作流实例"""
        instances = []

        # 从文件系统加载所有实例
        if self.instances_dir.exists():
            for instance_file in self.instances_dir.glob("*.json"):
                try:
                    with open(instance_file, encoding="utf-8") as f:
                        instance_data = json.load(f)
                        # 计算进度
                        progress = self._calculate_progress(instance_data)

                        instance_info = {
                            "instance_id": instance_data.get("instance_id"),
                            "workflow_name": instance_data.get("workflow_name"),
                            "task_id": instance_data.get("task_id"),
                            "status": instance_data.get("status"),
                            "current_step": instance_data.get("current_step"),
                            "progress": progress,
                            "created_at": instance_data.get("created_at"),
                            "started_at": instance_data.get("started_at"),
                            "completed_at": instance_data.get("completed_at"),
                        }
                        instances.append(instance_info)
                except Exception:
                    continue

        # 按创建时间倒序排序
        instances.sort(key=lambda x: x.get("created_at", ""), reverse=True)
        return instances


class WorkflowEngine:
    """工作流引擎"""

    def __init__(self, repo_root: Path, coordinator=None, tool_executor=None):
        self.repo_root = repo_root
        self.coordinator = coordinator
        self.tool_executor = tool_executor
        self.template_manager = WorkflowTemplateManager(repo_root)
        self.executor = WorkflowExecutor(repo_root, coordinator, tool_executor)

    def get_all_workflows(self) -> list[dict[str, Any]]:
        """获取所有工作流实例"""
        return self.executor.get_all_instances()
