"""
SCC统一调度器与现有系统集成模块

将基于QPC的统一调度器集成到SCC现有系统中：
- 与task_queue集成
- 与automation/daemon_inbox集成
- 与orchestrators集成
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

# 添加repo_root到路径
REPO_ROOT = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))

from tools.scc.common.time_utils import (
    QPCTimer,
    TaskHook,
    UnifiedScheduler,
    get_scheduler,
    qpc_now,
    utc_now_iso,
)


# =============================================================================
# SCC任务队列集成
# =============================================================================

class TaskQueueAdapter:
    """
    SCC任务队列适配器

    将统一调度器与SCC的task_queue集成
    """

    def __init__(self, repo_root: Path):
        self.repo_root = Path(repo_root)
        self.scheduler = get_scheduler()

    def register_hook_as_task(
        self,
        task_id: str,
        name: str,
        interval_ms: int,
        hook: TaskHook,
        context: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        注册Hook作为定时任务

        同时注册到统一调度器和SCC任务系统
        """
        # 注册到统一调度器
        task = self.scheduler.register(
            task_id=task_id,
            name=name,
            interval_ms=interval_ms,
            hook=hook,
            context=context,
        )

        # 同时写入SCC任务目录（可选）
        self._write_scc_task(task_id, name, context)

        return task.task_id

    def _write_scc_task(self, task_id: str, name: str, context: Optional[Dict[str, Any]]) -> None:
        """将任务写入SCC任务目录"""
        import json

        tasks_root = self.repo_root / "artifacts" / "scc_tasks" / task_id
        tasks_root.mkdir(parents=True, exist_ok=True)

        task_file = tasks_root / "task.json"
        task_data = {
            "task_id": task_id,
            "name": name,
            "created_at": utc_now_iso(),
            "status": "pending",
            "context": context or {},
            "source": "unified_scheduler",
        }

        task_file.write_text(json.dumps(task_data, indent=2), encoding="utf-8")


# =============================================================================
# 自动化守护进程集成
# =============================================================================

class AutomationAdapter:
    """
    SCC自动化适配器

    将统一调度器与daemon_inbox集成
    """

    def __init__(self, repo_root: Path):
        self.repo_root = Path(repo_root)
        self.scheduler = get_scheduler()
        self.inbox_path = repo_root / "artifacts" / "scc_inbox" / "parents.jsonl"

    def submit_to_inbox(self, parent_task: Dict[str, Any]) -> bool:
        """
        提交任务到SCC收件箱

        Args:
            parent_task: 父任务定义

        Returns:
            bool: 是否成功
        """
        import json

        try:
            self.inbox_path.parent.mkdir(parents=True, exist_ok=True)

            with open(self.inbox_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(parent_task, ensure_ascii=False) + "\n")

            return True
        except Exception as e:
            print(f"[AutomationAdapter] Failed to submit to inbox: {e}")
            return False

    def create_hook_with_inbox_submit(
        self,
        base_hook: TaskHook,
        parent_template: Optional[Dict[str, Any]] = None,
    ) -> TaskHook:
        """
        创建一个Hook，执行后自动提交到inbox

        Args:
            base_hook: 基础Hook
            parent_template: 提交到inbox的模板

        Returns:
            TaskHook: 包装后的Hook
        """

        def wrapped_hook(*, task_id: str, context: Dict[str, Any]) -> None:
            # 执行原始Hook
            base_hook(task_id=task_id, context=context)

            # 提交到inbox
            parent = parent_template or {
                "goal": f"Scheduled task: {task_id}",
                "context": context,
                "submitted_at": utc_now_iso(),
            }
            parent["task_id"] = task_id
            parent["triggered_at"] = utc_now_iso()

            self.submit_to_inbox(parent)

        return wrapped_hook


# =============================================================================
# 编排器集成
# =============================================================================

class OrchestratorAdapter:
    """
    SCC编排器适配器

    将统一调度器与orchestrators集成
    """

    def __init__(self, repo_root: Path):
        self.repo_root = Path(repo_root)
        self.scheduler = get_scheduler()

    def create_orchestrator_hook(
        self,
        orchestrator_id: str,
        phase: str = "monitoring",
    ) -> TaskHook:
        """
        创建与编排器集成的Hook

        Args:
            orchestrator_id: 编排器ID
            phase: 阶段

        Returns:
            TaskHook: 编排器Hook
        """

        def hook(*, task_id: str, context: Dict[str, Any]) -> None:
            """编排器Hook实现"""
            # 更新编排器状态
            self._update_orchestrator_state(orchestrator_id, phase, context)

            # 执行编排器逻辑
            print(f"[OrchestratorAdapter] {orchestrator_id} running phase: {phase}")

        return hook

    def _update_orchestrator_state(
        self,
        orchestrator_id: str,
        phase: str,
        context: Dict[str, Any],
    ) -> None:
        """更新编排器状态"""
        import json

        state_file = (
            self.repo_root
            / "artifacts"
            / "scc_tasks"
            / orchestrator_id
            / "orchestrator_state.json"
        )
        state_file.parent.mkdir(parents=True, exist_ok=True)

        state = {
            "orchestrator_id": orchestrator_id,
            "phase": phase,
            "updated_at": utc_now_iso(),
            "context": context,
        }

        state_file.write_text(json.dumps(state, indent=2), encoding="utf-8")


# =============================================================================
# 统一集成入口
# =============================================================================

class SCCSchedulerIntegration:
    """
    SCC统一调度器集成入口

    提供与SCC所有组件的集成能力
    """

    def __init__(self, repo_root: Optional[Path] = None):
        self.repo_root = Path(repo_root) if repo_root else self._find_repo_root()
        self.scheduler = get_scheduler()

        # 适配器
        self.task_queue = TaskQueueAdapter(self.repo_root)
        self.automation = AutomationAdapter(self.repo_root)
        self.orchestrator = OrchestratorAdapter(self.repo_root)

    def _find_repo_root(self) -> Path:
        """自动查找repo_root"""
        current = Path(__file__).resolve()
        # 向上查找直到找到artifacts目录
        for parent in current.parents:
            if (parent / "artifacts").exists():
                return parent
        # 默认返回scc-top目录
        return current.parent.parent.parent.parent

    def start_with_defaults(self) -> List[str]:
        """
        启动调度器并注册默认任务

        Returns:
            List[str]: 注册的任务ID列表
        """
        task_ids: List[str] = []

        # 1. 注册文档维护任务
        from tools.scc.common.doc_hooks import DocMaintenanceHook, DocIndexHook

        doc_maintenance = DocMaintenanceHook(self.repo_root)
        task_ids.append(
            self.scheduler.register(
                task_id="scc.doc_maintenance",
                name="SCC文档维护",
                interval_ms=3600000,  # 每小时
                hook=doc_maintenance,
                context={"repo_root": str(self.repo_root)},
            ).task_id
        )

        # 2. 注册文档索引任务
        doc_index = DocIndexHook(self.repo_root)
        task_ids.append(
            self.scheduler.register(
                task_id="scc.doc_index",
                name="SCC文档索引",
                interval_ms=1800000,  # 每30分钟
                hook=doc_index,
                context={"repo_root": str(self.repo_root)},
            ).task_id
        )

        # 3. 启动调度器
        if not self.scheduler.is_running:
            self.scheduler.start()

        return task_ids

    def register_custom_hook(
        self,
        task_id: str,
        name: str,
        interval_ms: int,
        hook: TaskHook,
        context: Optional[Dict[str, Any]] = None,
        submit_to_inbox: bool = False,
    ) -> str:
        """
        注册自定义Hook

        Args:
            task_id: 任务ID
            name: 任务名称
            interval_ms: 间隔（毫秒）
            hook: Hook函数
            context: 上下文
            submit_to_inbox: 是否同时提交到inbox

        Returns:
            str: 任务ID
        """
        final_hook = hook

        if submit_to_inbox:
            final_hook = self.automation.create_hook_with_inbox_submit(hook)

        task = self.scheduler.register(
            task_id=task_id,
            name=name,
            interval_ms=interval_ms,
            hook=final_hook,
            context=context,
        )

        return task.task_id

    def get_status(self) -> Dict[str, Any]:
        """获取集成状态"""
        return {
            "scheduler_running": self.scheduler.is_running,
            "repo_root": str(self.repo_root),
            "registered_tasks": [t.task_id for t in self.scheduler.list_tasks()],
            "task_count": len(self.scheduler.list_tasks()),
        }

    def stop(self) -> None:
        """停止调度器"""
        self.scheduler.stop()


# =============================================================================
# 便捷函数
# =============================================================================

_integration_instance: Optional[SCCSchedulerIntegration] = None


def get_integration(repo_root: Optional[Path] = None) -> SCCSchedulerIntegration:
    """获取集成实例（单例）"""
    global _integration_instance
    if _integration_instance is None:
        _integration_instance = SCCSchedulerIntegration(repo_root)
    return _integration_instance


def start_scc_scheduler(repo_root: Optional[Path] = None) -> List[str]:
    """
    一键启动SCC统一调度器

    Args:
        repo_root: 仓库根目录

    Returns:
        List[str]: 注册的任务ID列表
    """
    integration = get_integration(repo_root)
    return integration.start_with_defaults()


def register_task(
    task_id: str,
    name: str,
    interval_ms: int,
    hook: TaskHook,
    context: Optional[Dict[str, Any]] = None,
    repo_root: Optional[Path] = None,
) -> str:
    """
    注册定时任务

    Args:
        task_id: 任务ID
        name: 任务名称
        interval_ms: 间隔（毫秒）
        hook: Hook函数
        context: 上下文
        repo_root: 仓库根目录

    Returns:
        str: 任务ID
    """
    integration = get_integration(repo_root)
    return integration.register_custom_hook(task_id, name, interval_ms, hook, context)


# =============================================================================
# 命令行接口
# =============================================================================

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="SCC统一调度器集成")
    parser.add_argument("--repo-root", type=Path, help="仓库根目录")
    parser.add_argument("--start", action="store_true", help="启动调度器")
    parser.add_argument("--status", action="store_true", help="查看状态")
    parser.add_argument("--stop", action="store_true", help="停止调度器")

    args = parser.parse_args()

    if args.start:
        print("Starting SCC unified scheduler...")
        task_ids = start_scc_scheduler(args.repo_root)
        print(f"Registered tasks: {task_ids}")

        integration = get_integration(args.repo_root)
        print("Scheduler is running. Press Ctrl+C to stop.")

        try:
            while integration.scheduler.is_running:
                import time

                time.sleep(1)
        except KeyboardInterrupt:
            print("\nStopping...")
            integration.stop()

    elif args.status:
        integration = get_integration(args.repo_root)
        status = integration.get_status()
        print(json.dumps(status, indent=2))

    elif args.stop:
        integration = get_integration(args.repo_root)
        integration.stop()
        print("Scheduler stopped.")

    else:
        parser.print_help()
