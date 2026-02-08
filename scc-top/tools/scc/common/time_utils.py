"""
SCC统一时间模块 - 基于Windows QueryPerformanceCounter (QPC) 的高精度时间服务

提供功能：
1. 高精度计时 (QPC)
2. 统一UTC时间获取
3. 定时器管理
4. 任务Hook调度
"""

from __future__ import annotations

import ctypes
import threading
import time
from ctypes import wintypes
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Protocol, Set


# =============================================================================
# Windows QPC API 封装
# =============================================================================

class _QPCTime:
    """Windows QueryPerformanceCounter 封装类"""

    _instance: Optional["_QPCTime"] = None
    _lock = threading.Lock()

    def __new__(cls) -> "_QPCTime":
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._init_qpc()
        return cls._instance

    def _init_qpc(self) -> None:
        """初始化QPC"""
        self._kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

        # QueryPerformanceCounter
        self._qpc = self._kernel32.QueryPerformanceCounter
        self._qpc.argtypes = [ctypes.POINTER(wintypes.LARGE_INTEGER)]
        self._qpc.restype = wintypes.BOOL

        # QueryPerformanceFrequency
        self._qpf = self._kernel32.QueryPerformanceFrequency
        self._qpf.argtypes = [ctypes.POINTER(wintypes.LARGE_INTEGER)]
        self._qpf.restype = wintypes.BOOL

        # 获取频率
        freq = wintypes.LARGE_INTEGER()
        if not self._qpf(ctypes.byref(freq)):
            raise OSError("Failed to initialize QPC frequency")
        self._frequency = freq.value
        self._frequency_f = float(freq.value)

    @property
    def frequency(self) -> int:
        """QPC频率 (ticks per second)"""
        return self._frequency

    def now(self) -> int:
        """获取当前QPC计数值"""
        counter = wintypes.LARGE_INTEGER()
        if not self._qpc(ctypes.byref(counter)):
            raise OSError("QueryPerformanceCounter failed")
        return counter.value

    def to_seconds(self, ticks: int) -> float:
        """将tick数转换为秒"""
        return ticks / self._frequency_f

    def to_milliseconds(self, ticks: int) -> float:
        """将tick数转换为毫秒"""
        return (ticks * 1000.0) / self._frequency_f

    def elapsed_seconds(self, start_ticks: int, end_ticks: Optional[int] = None) -> float:
        """计算经过的秒数"""
        if end_ticks is None:
            end_ticks = self.now()
        return self.to_seconds(end_ticks - start_ticks)


# 全局QPC实例
_qpc_time = _QPCTime()


# =============================================================================
# 公共API
# =============================================================================

def qpc_now() -> int:
    """
    获取当前QPC计数值

    Returns:
        int: QPC计数器当前值 (ticks)
    """
    return _qpc_time.now()


def qpc_frequency() -> int:
    """
    获取QPC频率

    Returns:
        int: ticks per second
    """
    return _qpc_time.frequency


def qpc_to_seconds(ticks: int) -> float:
    """将QPC tick数转换为秒"""
    return _qpc_time.to_seconds(ticks)


def qpc_to_milliseconds(ticks: int) -> float:
    """将QPC tick数转换为毫秒"""
    return _qpc_time.to_milliseconds(ticks)


def qpc_elapsed(start_ticks: int, end_ticks: Optional[int] = None) -> float:
    """
    计算QPC经过的时间（秒）

    Args:
        start_ticks: 起始tick值
        end_ticks: 结束tick值（默认为当前）

    Returns:
        float: 经过的秒数
    """
    return _qpc_time.elapsed_seconds(start_ticks, end_ticks)


def utc_now_iso() -> str:
    """
    获取当前UTC时间的ISO格式字符串

    Returns:
        str: ISO 8601格式时间字符串
    """
    return datetime.now(timezone.utc).isoformat()


def utc_now_timestamp_ms() -> int:
    """
    获取当前UTC时间戳（毫秒）

    Returns:
        int: 毫秒级时间戳
    """
    return int(time.time() * 1000)


# =============================================================================
# 高精度计时器上下文管理器
# =============================================================================

class QPCTimer:
    """
    基于QPC的高精度计时器上下文管理器

    Example:
        with QPCTimer() as timer:
            # 执行需要计时的操作
            do_something()
        print(f"耗时: {timer.elapsed_ms:.3f} ms")
    """

    def __init__(self, name: str = ""):
        self.name = name
        self._start_ticks: int = 0
        self._end_ticks: int = 0
        self._elapsed_ticks: int = 0

    def __enter__(self) -> "QPCTimer":
        self._start_ticks = _qpc_time.now()
        return self

    def __exit__(self, *args: Any) -> None:
        self._end_ticks = _qpc_time.now()
        self._elapsed_ticks = self._end_ticks - self._start_ticks

    @property
    def elapsed_ticks(self) -> int:
        """经过的tick数"""
        if self._elapsed_ticks == 0 and self._start_ticks != 0:
            return _qpc_time.now() - self._start_ticks
        return self._elapsed_ticks

    @property
    def elapsed_s(self) -> float:
        """经过的秒数"""
        return _qpc_time.to_seconds(self.elapsed_ticks)

    @property
    def elapsed_ms(self) -> float:
        """经过的毫秒数"""
        return _qpc_time.to_milliseconds(self.elapsed_ticks)

    def __repr__(self) -> str:
        name = f"[{self.name}] " if self.name else ""
        return f"<QPCTimer {name}elapsed={self.elapsed_ms:.3f}ms>"


# =============================================================================
# 定时器Hook协议与类型定义
# =============================================================================

class TaskHook(Protocol):
    """任务Hook协议"""

    def __call__(self, *, task_id: str, context: Dict[str, Any]) -> None:
        """执行Hook"""
        ...


@dataclass
class ScheduledTask:
    """定时任务定义"""

    task_id: str
    name: str
    interval_ms: int  # 执行间隔（毫秒）
    hook: TaskHook
    context: Dict[str, Any] = field(default_factory=dict)
    last_run_ticks: int = field(default=0)
    enabled: bool = True
    run_count: int = 0

    def should_run(self, current_ticks: int) -> bool:
        """检查是否应该执行"""
        if not self.enabled:
            return False
        elapsed_ms = _qpc_time.to_milliseconds(current_ticks - self.last_run_ticks)
        return elapsed_ms >= self.interval_ms


# =============================================================================
# 统一调度器
# =============================================================================

class UnifiedScheduler:
    """
    基于QPC的统一任务调度器

    特性：
    - 使用QPC高精度计时
    - 支持多任务调度
    - 线程安全
    - 支持任务Hook

    Example:
        scheduler = UnifiedScheduler()

        # 注册文档维护任务
        scheduler.register(
            task_id="doc_maintenance",
            name="文档维护检查",
            interval_ms=60000,  # 每分钟
            hook=my_doc_hook
        )

        # 启动调度器
        scheduler.start()
    """

    _instance: Optional["UnifiedScheduler"] = None
    _lock = threading.Lock()

    def __new__(cls) -> "UnifiedScheduler":
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True

        self._tasks: Dict[str, ScheduledTask] = {}
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._task_lock = threading.RLock()
        self._poll_interval_ms = 100  # 默认轮询间隔100ms

    def register(
        self,
        task_id: str,
        name: str,
        interval_ms: int,
        hook: TaskHook,
        context: Optional[Dict[str, Any]] = None,
        enabled: bool = True,
    ) -> ScheduledTask:
        """
        注册定时任务

        Args:
            task_id: 任务唯一标识
            name: 任务名称
            interval_ms: 执行间隔（毫秒）
            hook: 任务执行函数
            context: 任务上下文数据
            enabled: 是否启用

        Returns:
            ScheduledTask: 创建的任务对象
        """
        with self._task_lock:
            task = ScheduledTask(
                task_id=task_id,
                name=name,
                interval_ms=interval_ms,
                hook=hook,
                context=context or {},
                enabled=enabled,
            )
            self._tasks[task_id] = task
            return task

    def unregister(self, task_id: str) -> bool:
        """注销任务"""
        with self._task_lock:
            if task_id in self._tasks:
                del self._tasks[task_id]
                return True
            return False

    def enable(self, task_id: str) -> bool:
        """启用任务"""
        with self._task_lock:
            if task_id in self._tasks:
                self._tasks[task_id].enabled = True
                return True
            return False

    def disable(self, task_id: str) -> bool:
        """禁用任务"""
        with self._task_lock:
            if task_id in self._tasks:
                self._tasks[task_id].enabled = False
                return True
            return False

    def get_task(self, task_id: str) -> Optional[ScheduledTask]:
        """获取任务"""
        with self._task_lock:
            return self._tasks.get(task_id)

    def list_tasks(self) -> List[ScheduledTask]:
        """列出所有任务"""
        with self._task_lock:
            return list(self._tasks.values())

    def start(self, poll_interval_ms: int = 100) -> None:
        """
        启动调度器

        Args:
            poll_interval_ms: 轮询间隔（毫秒）
        """
        if self._running:
            return

        self._poll_interval_ms = poll_interval_ms
        self._running = True
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run_loop, name="UnifiedScheduler", daemon=True)
        self._thread.start()

    def stop(self, timeout_s: float = 5.0) -> None:
        """停止调度器"""
        if not self._running:
            return

        self._running = False
        self._stop_event.set()

        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=timeout_s)

    def _run_loop(self) -> None:
        """调度器主循环"""
        while self._running and not self._stop_event.is_set():
            current_ticks = _qpc_time.now()

            with self._task_lock:
                tasks_to_run: List[ScheduledTask] = []
                for task in self._tasks.values():
                    if task.should_run(current_ticks):
                        tasks_to_run.append(task)

            # 执行任务（在锁外执行避免阻塞）
            for task in tasks_to_run:
                try:
                    with QPCTimer(task.name) as timer:
                        task.hook(task_id=task.task_id, context=task.context)

                    task.last_run_ticks = _qpc_time.now()
                    task.run_count += 1

                except Exception as e:
                    # 记录错误但不中断调度器
                    print(f"Task {task.task_id} failed: {e}")

            # 等待下一次轮询
            self._stop_event.wait(self._poll_interval_ms / 1000.0)

    @property
    def is_running(self) -> bool:
        """调度器是否正在运行"""
        return self._running


# =============================================================================
# 文档维护任务Hook示例
# =============================================================================

class DocumentMaintenanceHook:
    """
    文档维护任务Hook

    功能：
    - 检查文档过期
    - 触发文档更新
    - 记录维护日志
    """

    def __init__(self, repo_root: Path, docs_path: Optional[Path] = None):
        self.repo_root = Path(repo_root)
        self.docs_path = docs_path or (self.repo_root / "docs")
        self.maintenance_log: List[Dict[str, Any]] = []

    def __call__(self, *, task_id: str, context: Dict[str, Any]) -> None:
        """执行文档维护检查"""
        check_time = utc_now_iso()

        # 1. 扫描文档目录
        docs_to_check = self._scan_documents()

        # 2. 检查每个文档的状态
        for doc_path in docs_to_check:
            status = self._check_document(doc_path)
            if status["needs_update"]:
                self._trigger_update(doc_path, status)

        # 3. 记录维护日志
        self.maintenance_log.append({
            "timestamp": check_time,
            "task_id": task_id,
            "docs_checked": len(docs_to_check),
            "context": context,
        })

    def _scan_documents(self) -> List[Path]:
        """扫描文档目录"""
        if not self.docs_path.exists():
            return []

        docs: List[Path] = []
        for pattern in ["**/*.md", "**/*.rst", "**/*.txt"]:
            docs.extend(self.docs_path.glob(pattern))
        return docs

    def _check_document(self, doc_path: Path) -> Dict[str, Any]:
        """检查单个文档状态"""
        stat = doc_path.stat()
        modified_time = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc)
        now = datetime.now(timezone.utc)
        age_days = (now - modified_time).days

        return {
            "path": str(doc_path),
            "modified": modified_time.isoformat(),
            "age_days": age_days,
            "needs_update": age_days > 30,  # 30天未更新
        }

    def _trigger_update(self, doc_path: Path, status: Dict[str, Any]) -> None:
        """触发文档更新"""
        # 这里可以集成到SCC的任务系统中
        print(f"[DocMaintenance] Document needs update: {doc_path} (age: {status['age_days']} days)")


# =============================================================================
# 便捷函数
# =============================================================================

def get_scheduler() -> UnifiedScheduler:
    """获取统一调度器单例"""
    return UnifiedScheduler()


def register_doc_maintenance_hook(
    repo_root: Path,
    interval_ms: int = 3600000,  # 默认每小时检查一次
) -> str:
    """
    注册文档维护任务Hook

    Args:
        repo_root: 仓库根目录
        interval_ms: 检查间隔（毫秒）

    Returns:
        str: 任务ID
    """
    scheduler = get_scheduler()
    hook = DocumentMaintenanceHook(repo_root)

    task = scheduler.register(
        task_id="doc_maintenance",
        name="文档维护检查",
        interval_ms=interval_ms,
        hook=hook,
        context={"repo_root": str(repo_root)},
    )

    return task.task_id


# =============================================================================
# 模块测试
# =============================================================================

if __name__ == "__main__":
    # 测试QPC功能
    print("=== QPC Time Test ===")
    print(f"QPC Frequency: {qpc_frequency():,} ticks/second")

    # 测试计时器
    with QPCTimer("test_operation") as timer:
        time.sleep(0.1)  # 模拟100ms操作
    print(f"Timer result: {timer}")

    # 测试UTC时间
    print(f"\nUTC Now: {utc_now_iso()}")
    print(f"Timestamp (ms): {utc_now_timestamp_ms()}")

    # 测试调度器
    print("\n=== Scheduler Test ===")
    scheduler = get_scheduler()

    def sample_hook(*, task_id: str, context: Dict[str, Any]) -> None:
        print(f"Hook executed: {task_id} at {utc_now_iso()}")

    scheduler.register(
        task_id="test_task",
        name="测试任务",
        interval_ms=1000,  # 每秒执行
        hook=sample_hook,
    )

    scheduler.start()
    time.sleep(3.5)  # 运行3.5秒，应该执行3-4次
    scheduler.stop()

    task = scheduler.get_task("test_task")
    if task:
        print(f"Task ran {task.run_count} times")

    print("\n=== Test Complete ===")
