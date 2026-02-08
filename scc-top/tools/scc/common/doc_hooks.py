"""
SCC文档维护Hook模块

基于统一时间模块(QPC)的文档维护任务Hook，支持：
- 文档过期检测
- 文档链接检查
- 文档元数据维护
- 与SCC任务系统集成
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

from tools.scc.common.time_utils import (
    QPCTimer,
    TaskHook,
    UnifiedScheduler,
    get_scheduler,
    utc_now_iso,
    utc_now_timestamp_ms,
)


# =============================================================================
# 数据模型
# =============================================================================

@dataclass
class DocInfo:
    """文档信息"""

    path: Path
    title: str = ""
    modified: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    size_bytes: int = 0
    word_count: int = 0
    links: List[str] = field(default_factory=list)
    headings: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "path": str(self.path),
            "title": self.title,
            "modified": self.modified.isoformat(),
            "size_bytes": self.size_bytes,
            "word_count": self.word_count,
            "links": self.links,
            "headings": self.headings,
            "metadata": self.metadata,
        }


@dataclass
class DocHealthReport:
    """文档健康报告"""

    doc_path: Path
    status: str  # "ok", "warning", "error"
    issues: List[Dict[str, Any]] = field(default_factory=list)
    last_check: str = field(default_factory=utc_now_iso)
    age_days: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "doc_path": str(self.doc_path),
            "status": self.status,
            "issues": self.issues,
            "last_check": self.last_check,
            "age_days": self.age_days,
        }


# =============================================================================
# 文档分析器
# =============================================================================

class DocumentAnalyzer:
    """文档分析器 - 解析文档内容提取信息"""

    # Markdown frontmatter 正则
    FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)
    # 标题正则
    HEADING_RE = re.compile(r"^#{1,6}\s+(.+)$", re.MULTILINE)
    # 链接正则
    LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
    # 图片正则
    IMAGE_RE = re.compile(r"!\[([^\]]*)\]\(([^)]+)\)")

    def __init__(self, repo_root: Path):
        self.repo_root = Path(repo_root)

    def analyze(self, doc_path: Path) -> DocInfo:
        """分析单个文档"""
        content = doc_path.read_text(encoding="utf-8", errors="replace")
        stat = doc_path.stat()

        info = DocInfo(
            path=doc_path,
            modified=datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc),
            size_bytes=stat.st_size,
        )

        # 解析frontmatter
        metadata = self._extract_frontmatter(content)
        info.metadata = metadata
        info.title = metadata.get("title", self._extract_title(content, doc_path))

        # 统计字数
        info.word_count = len(content.split())

        # 提取链接
        info.links = self._extract_links(content)

        # 提取标题
        info.headings = self._extract_headings(content)

        return info

    def _extract_frontmatter(self, content: str) -> Dict[str, Any]:
        """提取YAML frontmatter"""
        match = self.FRONTMATTER_RE.match(content)
        if not match:
            return {}

        # 简单解析YAML（只支持key: value格式）
        fm_text = match.group(1)
        metadata: Dict[str, Any] = {}
        for line in fm_text.split("\n"):
            line = line.strip()
            if ":" in line:
                key, value = line.split(":", 1)
                key = key.strip()
                value = value.strip().strip('"').strip("'")
                metadata[key] = value
        return metadata

    def _extract_title(self, content: str, doc_path: Path) -> str:
        """提取文档标题"""
        # 尝试从第一个heading提取
        match = self.HEADING_RE.search(content)
        if match:
            return match.group(1).strip()
        # 使用文件名
        return doc_path.stem

    def _extract_links(self, content: str) -> List[str]:
        """提取文档中的链接"""
        links = []
        for match in self.LINK_RE.finditer(content):
            url = match.group(2)
            links.append(url)
        return links

    def _extract_headings(self, content: str) -> List[str]:
        """提取文档标题结构"""
        return [m.group(1).strip() for m in self.HEADING_RE.finditer(content)]


# =============================================================================
# 文档健康检查器
# =============================================================================

class DocHealthChecker:
    """文档健康检查器"""

    def __init__(self, repo_root: Path, docs_path: Optional[Path] = None):
        self.repo_root = Path(repo_root)
        self.docs_path = docs_path or (self.repo_root / "docs")
        self.analyzer = DocumentAnalyzer(repo_root)

        # 配置
        self.config = {
            "max_age_days": 30,  # 文档最大年龄（天）
            "min_word_count": 50,  # 最小字数
            "required_sections": [],  # 必需章节
            "broken_link_check": True,  # 检查死链
        }

    def check(self, doc_path: Path) -> DocHealthReport:
        """检查单个文档健康状态"""
        issues: List[Dict[str, Any]] = []

        # 基本信息
        stat = doc_path.stat()
        modified = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc)
        now = datetime.now(timezone.utc)
        age_days = (now - modified).days

        # 检查文档年龄
        if age_days > self.config["max_age_days"]:
            issues.append({
                "type": "age",
                "severity": "warning",
                "message": f"Document is {age_days} days old (max: {self.config['max_age_days']})",
            })

        # 分析内容
        try:
            info = self.analyzer.analyze(doc_path)

            # 检查字数
            if info.word_count < self.config["min_word_count"]:
                issues.append({
                    "type": "content",
                    "severity": "warning",
                    "message": f"Word count too low: {info.word_count} (min: {self.config['min_word_count']})",
                })

            # 检查必需章节
            for section in self.config["required_sections"]:
                if section not in info.headings:
                    issues.append({
                        "type": "structure",
                        "severity": "error",
                        "message": f"Missing required section: {section}",
                    })

            # 检查死链
            if self.config["broken_link_check"]:
                broken = self._check_links(doc_path, info.links)
                for link in broken:
                    issues.append({
                        "type": "link",
                        "severity": "error",
                        "message": f"Broken link: {link}",
                    })

        except Exception as e:
            issues.append({
                "type": "parse",
                "severity": "error",
                "message": f"Failed to analyze: {e}",
            })

        # 确定状态
        status = "ok"
        if any(i["severity"] == "error" for i in issues):
            status = "error"
        elif any(i["severity"] == "warning" for i in issues):
            status = "warning"

        return DocHealthReport(
            doc_path=doc_path,
            status=status,
            issues=issues,
            age_days=age_days,
        )

    def _check_links(self, doc_path: Path, links: List[str]) -> List[str]:
        """检查链接是否有效"""
        broken: List[str] = []
        for link in links:
            # 只检查本地相对链接
            if link.startswith("http://") or link.startswith("https://"):
                continue
            if link.startswith("#"):
                continue  # 锚点链接

            # 解析相对路径
            if link.startswith("/"):
                target = self.repo_root / link.lstrip("/")
            else:
                target = doc_path.parent / link

            if not target.exists():
                broken.append(link)

        return broken


# =============================================================================
# 文档维护Hook实现
# =============================================================================

class DocMaintenanceHook:
    """
    文档维护任务Hook

    功能：
    - 定期扫描文档
    - 健康检查
    - 生成报告
    - 触发更新任务
    """

    def __init__(
        self,
        repo_root: Path,
        docs_path: Optional[Path] = None,
        output_path: Optional[Path] = None,
    ):
        self.repo_root = Path(repo_root)
        self.docs_path = docs_path or (self.repo_root / "docs")
        self.output_path = output_path or (self.repo_root / "artifacts" / "doc_maintenance")
        self.checker = DocHealthChecker(repo_root, docs_path)

        # 运行时数据
        self.reports: List[DocHealthReport] = []
        self.check_count = 0
        self.last_run: Optional[str] = None

    def __call__(self, *, task_id: str, context: Dict[str, Any]) -> None:
        """执行文档维护检查"""
        with QPCTimer("doc_maintenance") as timer:
            self._run_check(task_id, context)

        self.last_run = utc_now_iso()
        self.check_count += 1

        # 记录性能
        print(f"[DocMaintenance] Check #{self.check_count} completed in {timer.elapsed_ms:.2f}ms")

    def _run_check(self, task_id: str, context: Dict[str, Any]) -> None:
        """执行检查流程"""
        # 1. 确保输出目录
        self.output_path.mkdir(parents=True, exist_ok=True)

        # 2. 扫描文档
        docs = self._scan_documents()

        # 3. 健康检查
        reports: List[DocHealthReport] = []
        for doc_path in docs:
            report = self.checker.check(doc_path)
            reports.append(report)

        self.reports = reports

        # 4. 生成报告
        self._save_report(reports)

        # 5. 触发更新任务（如果有问题文档）
        error_docs = [r for r in reports if r.status == "error"]
        warning_docs = [r for r in reports if r.status == "warning"]

        if error_docs:
            self._trigger_repair(error_docs, "error")

        if warning_docs:
            self._trigger_repair(warning_docs, "warning")

    def _scan_documents(self) -> List[Path]:
        """扫描文档目录"""
        if not self.docs_path.exists():
            return []

        docs: List[Path] = []
        for pattern in ["**/*.md"]:
            docs.extend(self.docs_path.glob(pattern))
        return sorted(docs)

    def _save_report(self, reports: List[DocHealthReport]) -> None:
        """保存检查报告"""
        timestamp = utc_now_timestamp_ms()
        report_file = self.output_path / f"report_{timestamp}.json"

        data = {
            "timestamp": utc_now_iso(),
            "total_docs": len(reports),
            "ok_count": len([r for r in reports if r.status == "ok"]),
            "warning_count": len([r for r in reports if r.status == "warning"]),
            "error_count": len([r for r in reports if r.status == "error"]),
            "reports": [r.to_dict() for r in reports],
        }

        report_file.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

        # 同时保存最新报告
        latest_file = self.output_path / "latest_report.json"
        latest_file.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    def _trigger_repair(self, reports: List[DocHealthReport], severity: str) -> None:
        """触发修复任务"""
        # 可以集成到SCC的任务队列
        print(f"[DocMaintenance] Triggering repair for {len(reports)} docs with {severity} issues")

        for report in reports:
            for issue in report.issues:
                print(f"  - {report.doc_path}: {issue['message']}")


# =============================================================================
# 文档索引维护Hook
# =============================================================================

class DocIndexHook:
    """
    文档索引维护Hook

    功能：
    - 维护文档索引
    - 更新搜索索引
    - 维护文档关系图
    """

    def __init__(
        self,
        repo_root: Path,
        docs_path: Optional[Path] = None,
    ):
        self.repo_root = Path(repo_root)
        self.docs_path = docs_path or (self.repo_root / "docs")
        self.analyzer = DocumentAnalyzer(repo_root)
        self.index_file = self.repo_root / "artifacts" / "doc_index.json"

    def __call__(self, *, task_id: str, context: Dict[str, Any]) -> None:
        """执行索引更新"""
        with QPCTimer("doc_index") as timer:
            self._update_index()

        print(f"[DocIndex] Index updated in {timer.elapsed_ms:.2f}ms")

    def _update_index(self) -> None:
        """更新文档索引"""
        if not self.docs_path.exists():
            return

        index: Dict[str, Any] = {
            "updated": utc_now_iso(),
            "docs": {},
        }

        for doc_path in self.docs_path.glob("**/*.md"):
            try:
                info = self.analyzer.analyze(doc_path)
                rel_path = doc_path.relative_to(self.docs_path)
                index["docs"][str(rel_path)] = info.to_dict()
            except Exception as e:
                print(f"[DocIndex] Failed to index {doc_path}: {e}")

        # 保存索引
        self.index_file.parent.mkdir(parents=True, exist_ok=True)
        self.index_file.write_text(json.dumps(index, indent=2, ensure_ascii=False), encoding="utf-8")


# =============================================================================
# 便捷函数
# =============================================================================

def register_doc_maintenance(
    repo_root: Path,
    interval_ms: int = 3600000,  # 默认每小时
    docs_path: Optional[Path] = None,
    task_id: str = "doc_maintenance",
) -> str:
    """
    注册文档维护任务

    Args:
        repo_root: 仓库根目录
        interval_ms: 检查间隔（毫秒）
        docs_path: 文档目录路径
        task_id: 任务ID

    Returns:
        str: 任务ID
    """
    scheduler = get_scheduler()
    hook = DocMaintenanceHook(repo_root, docs_path)

    task = scheduler.register(
        task_id=task_id,
        name="文档维护检查",
        interval_ms=interval_ms,
        hook=hook,
        context={"repo_root": str(repo_root)},
    )

    return task.task_id


def register_doc_index(
    repo_root: Path,
    interval_ms: int = 1800000,  # 默认每30分钟
    docs_path: Optional[Path] = None,
    task_id: str = "doc_index",
) -> str:
    """
    注册文档索引任务

    Args:
        repo_root: 仓库根目录
        interval_ms: 更新间隔（毫秒）
        docs_path: 文档目录路径
        task_id: 任务ID

    Returns:
        str: 任务ID
    """
    scheduler = get_scheduler()
    hook = DocIndexHook(repo_root, docs_path)

    task = scheduler.register(
        task_id=task_id,
        name="文档索引更新",
        interval_ms=interval_ms,
        hook=hook,
        context={"repo_root": str(repo_root)},
    )

    return task.task_id


def setup_doc_hooks(
    repo_root: Path,
    maintenance_interval_ms: int = 3600000,
    index_interval_ms: int = 1800000,
    autostart: bool = True,
) -> List[str]:
    """
    一键设置所有文档维护Hook

    Args:
        repo_root: 仓库根目录
        maintenance_interval_ms: 维护检查间隔
        index_interval_ms: 索引更新间隔
        autostart: 是否自动启动调度器

    Returns:
        List[str]: 注册的任务ID列表
    """
    task_ids: List[str] = []

    # 注册维护任务
    task_ids.append(register_doc_maintenance(repo_root, maintenance_interval_ms))

    # 注册索引任务
    task_ids.append(register_doc_index(repo_root, index_interval_ms))

    # 启动调度器
    if autostart:
        scheduler = get_scheduler()
        if not scheduler.is_running:
            scheduler.start()

    return task_ids


# =============================================================================
# 命令行接口
# =============================================================================

if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python doc_hooks.py <repo_root> [check|index|watch]")
        sys.exit(1)

    repo_root = Path(sys.argv[1])
    command = sys.argv[2] if len(sys.argv) > 2 else "check"

    if command == "check":
        # 单次检查
        hook = DocMaintenanceHook(repo_root)
        hook(task_id="manual_check", context={})

    elif command == "index":
        # 单次索引
        hook = DocIndexHook(repo_root)
        hook(task_id="manual_index", context={})

    elif command == "watch":
        # 启动持续监控
        print(f"Starting doc hooks watch mode for {repo_root}")
        task_ids = setup_doc_hooks(repo_root, autostart=True)
        print(f"Registered tasks: {task_ids}")

        scheduler = get_scheduler()
        print("Scheduler running. Press Ctrl+C to stop.")

        try:
            while scheduler.is_running:
                import time

                time.sleep(1)
        except KeyboardInterrupt:
            print("\nStopping scheduler...")
            scheduler.stop()

    else:
        print(f"Unknown command: {command}")
        sys.exit(1)
