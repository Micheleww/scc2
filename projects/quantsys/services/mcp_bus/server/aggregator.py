"""
结果聚合器 (Result Aggregator)
收集多个 Agent 的输出，合并和整合结果，验证结果完整性
"""

import json
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any


class MergeStrategy(str, Enum):
    """合并策略"""

    CONCATENATE = "concatenate"  # 简单拼接
    INTELLIGENT = "intelligent"  # 智能合并
    VOTING = "voting"  # 投票合并
    WEIGHTED = "weighted"  # 加权合并


@dataclass
class Result:
    """结果定义"""

    result_id: str
    task_id: str
    subtask_id: str
    agent_id: str
    content: dict[str, Any]
    timestamp: str
    confidence: float = 1.0  # 置信度 0-1
    validated: bool = False


class ResultCollector:
    """结果收集器"""

    def __init__(self, repo_root: Path):
        self.repo_root = repo_root
        self.results_dir = self.repo_root / "docs" / "REPORT" / "ata" / "results"
        self.results_dir.mkdir(parents=True, exist_ok=True)
        self.messages_dir = self.repo_root / "docs" / "REPORT" / "ata" / "messages"

    def collect_results(
        self, task_id: str, subtask_ids: list[str] | None = None, include_intermediate: bool = False
    ) -> dict[str, Any]:
        """收集结果"""
        results = {}

        # 从任务文件中获取子任务结果
        task_file = self.repo_root / "docs" / "REPORT" / "ata" / "tasks" / f"{task_id}.json"
        if task_file.exists():
            with open(task_file, encoding="utf-8") as f:
                task_data = json.load(f)

            subtasks = task_data.get("plan", {}).get("subtasks", [])
            for subtask in subtasks:
                subtask_id = subtask.get("subtask_id")

                # 如果指定了子任务列表，只收集指定的子任务
                if subtask_ids and subtask_id not in subtask_ids:
                    continue

                # 收集结果
                result = subtask.get("result")
                if result or include_intermediate:
                    results[subtask_id] = {
                        "subtask_id": subtask_id,
                        "agent_id": subtask.get("assigned_agent"),
                        "status": subtask.get("status"),
                        "result": result,
                        "error": subtask.get("error"),
                        "started_at": subtask.get("started_at"),
                        "completed_at": subtask.get("completed_at"),
                    }
        else:
            # 如果任务文件不存在，从消息系统中收集
            # 查找任务相关的消息
            task_messages_dir = self.messages_dir / task_id
            if task_messages_dir.exists():
                for msg_file in task_messages_dir.glob("*.json"):
                    try:
                        with open(msg_file, encoding="utf-8") as f:
                            msg_data = json.load(f)

                        # 只收集响应消息
                        if msg_data.get("kind") == "response":
                            subtask_id = msg_data.get("payload", {}).get("subtask_id")
                            if subtask_id and (not subtask_ids or subtask_id in subtask_ids):
                                results[subtask_id] = {
                                    "subtask_id": subtask_id,
                                    "agent_id": msg_data.get("from_agent"),
                                    "result": msg_data.get("payload"),
                                    "timestamp": msg_data.get("created_at"),
                                }
                    except Exception:
                        continue

        return {"success": True, "task_id": task_id, "results": results, "count": len(results)}

    def validate_results(
        self, results: dict[str, Any], required_subtasks: list[str]
    ) -> dict[str, Any]:
        """验证结果完整性"""
        collected = set(results.keys())
        required = set(required_subtasks)

        missing = required - collected
        extra = collected - required

        all_complete = len(missing) == 0

        return {
            "valid": all_complete,
            "missing": list(missing),
            "extra": list(extra),
            "completeness": len(collected) / len(required) if required else 1.0,
        }


class ResultMerger:
    """结果合并器"""

    def merge_results(
        self,
        results: dict[str, Any],
        merge_strategy: str = "concatenate",
        weights: dict[str, float] | None = None,
    ) -> dict[str, Any]:
        """合并结果"""
        if not results:
            return {"success": False, "error": "No results to merge"}

        strategy = MergeStrategy(merge_strategy)

        if strategy == MergeStrategy.CONCATENATE:
            return self._concatenate(results)
        elif strategy == MergeStrategy.INTELLIGENT:
            return self._intelligent_merge(results)
        elif strategy == MergeStrategy.VOTING:
            return self._voting_merge(results)
        elif strategy == MergeStrategy.WEIGHTED:
            return self._weighted_merge(results, weights or {})
        else:
            return self._concatenate(results)

    def _concatenate(self, results: dict[str, Any]) -> dict[str, Any]:
        """简单拼接"""
        merged = {
            "merged_at": datetime.now().isoformat() + "Z",
            "strategy": "concatenate",
            "subtasks": [],
        }

        # 按时间戳排序
        sorted_results = sorted(
            results.items(), key=lambda x: x[1].get("completed_at") or x[1].get("timestamp") or ""
        )

        for subtask_id, result_data in sorted_results:
            merged["subtasks"].append(
                {
                    "subtask_id": subtask_id,
                    "agent_id": result_data.get("agent_id"),
                    "content": result_data.get("result"),
                    "status": result_data.get("status"),
                }
            )

            # 合并内容
            if result_data.get("result"):
                if "content" not in merged:
                    merged["content"] = {}
                merged["content"][subtask_id] = result_data.get("result")

        return {"success": True, "merged": merged}

    def _intelligent_merge(self, results: dict[str, Any]) -> dict[str, Any]:
        """智能合并"""
        merged = {
            "merged_at": datetime.now().isoformat() + "Z",
            "strategy": "intelligent",
            "subtasks": [],
        }

        # 分类结果
        code_results = {}
        doc_results = {}
        data_results = {}

        for subtask_id, result_data in results.items():
            content = result_data.get("result", {})

            # 根据内容类型分类
            if isinstance(content, dict):
                if "code" in content or "files" in content:
                    code_results[subtask_id] = result_data
                elif "documentation" in content or "report" in content:
                    doc_results[subtask_id] = result_data
                else:
                    data_results[subtask_id] = result_data

        # 合并代码结果
        if code_results:
            merged["code"] = {}
            for subtask_id, result_data in code_results.items():
                content = result_data.get("result", {})
                merged["code"][subtask_id] = content
                merged["subtasks"].append(
                    {"subtask_id": subtask_id, "type": "code", "content": content}
                )

        # 合并文档结果
        if doc_results:
            merged["documentation"] = []
            for subtask_id, result_data in doc_results.items():
                content = result_data.get("result", {})
                merged["documentation"].append(content)
                merged["subtasks"].append(
                    {"subtask_id": subtask_id, "type": "documentation", "content": content}
                )

        # 合并数据结果
        if data_results:
            merged["data"] = {}
            for subtask_id, result_data in data_results.items():
                content = result_data.get("result", {})
                merged["data"][subtask_id] = content
                merged["subtasks"].append(
                    {"subtask_id": subtask_id, "type": "data", "content": content}
                )

        return {"success": True, "merged": merged}

    def _voting_merge(self, results: dict[str, Any]) -> dict[str, Any]:
        """投票合并（用于有多个相同类型结果的情况）"""
        merged = {
            "merged_at": datetime.now().isoformat() + "Z",
            "strategy": "voting",
            "subtasks": [],
        }

        # 按内容分组
        content_groups = {}
        for subtask_id, result_data in results.items():
            content = result_data.get("result", {})
            # 简单的哈希作为内容标识
            content_key = str(hash(str(content)))

            if content_key not in content_groups:
                content_groups[content_key] = []

            content_groups[content_key].append(
                {
                    "subtask_id": subtask_id,
                    "agent_id": result_data.get("agent_id"),
                    "content": content,
                }
            )

        # 选择最常见的结果
        if content_groups:
            most_common = max(content_groups.items(), key=lambda x: len(x[1]))
            merged["selected"] = most_common[1][0]["content"]
            merged["votes"] = len(most_common[1])
            merged["alternatives"] = len(content_groups) - 1

        return {"success": True, "merged": merged}

    def _weighted_merge(self, results: dict[str, Any], weights: dict[str, float]) -> dict[str, Any]:
        """加权合并"""
        merged = {
            "merged_at": datetime.now().isoformat() + "Z",
            "strategy": "weighted",
            "subtasks": [],
        }

        # 计算总权重
        total_weight = sum(weights.get(subtask_id, 1.0) for subtask_id in results)

        if total_weight == 0:
            return {"success": False, "error": "Total weight is zero"}

        # 加权合并
        weighted_content = {}
        for subtask_id, result_data in results.items():
            weight = weights.get(subtask_id, 1.0) / total_weight
            content = result_data.get("result", {})

            # 简单的加权合并（如果是数值）
            if isinstance(content, dict):
                for key, value in content.items():
                    if isinstance(value, (int, float)):
                        if key not in weighted_content:
                            weighted_content[key] = 0
                        weighted_content[key] += value * weight
                    else:
                        weighted_content[key] = value  # 非数值直接使用
            else:
                weighted_content[subtask_id] = content

        merged["content"] = weighted_content

        return {"success": True, "merged": merged}


class ConflictResolver:
    """冲突解决器"""

    def resolve_conflicts(self, results: list[dict[str, Any]]) -> dict[str, Any]:
        """处理冲突"""
        if len(results) < 2:
            return {"success": True, "resolved": results[0] if results else None, "conflicts": []}

        conflicts = []

        # 简单冲突检测：比较结果的关键字段
        keys_to_check = ["code", "files", "decision", "status"]

        for key in keys_to_check:
            values = [r.get("result", {}).get(key) for r in results if r.get("result", {}).get(key)]
            if len(set(str(v) for v in values)) > 1:
                conflicts.append(
                    {"field": key, "values": values, "count": len(set(str(v) for v in values))}
                )

        # 如果没有冲突，返回第一个结果
        if not conflicts:
            return {"success": True, "resolved": results[0].get("result"), "conflicts": []}

        # 解决冲突：选择置信度最高的结果
        sorted_results = sorted(results, key=lambda x: x.get("confidence", 0.0), reverse=True)

        resolved = sorted_results[0].get("result")

        return {
            "success": True,
            "resolved": resolved,
            "conflicts": conflicts,
            "selected_from": sorted_results[0].get("agent_id"),
            "confidence": sorted_results[0].get("confidence", 0.0),
        }


class ResultAggregator:
    """结果聚合器"""

    def __init__(self, repo_root: Path):
        self.repo_root = repo_root
        self.collector = ResultCollector(repo_root)
        self.merger = ResultMerger()
        self.resolver = ConflictResolver()

    def get_result(self, task_id: str, include_intermediate: bool = False) -> dict[str, Any]:
        """获取任务结果"""
        # 收集结果
        collection_result = self.collector.collect_results(
            task_id, include_intermediate=include_intermediate
        )

        if not collection_result.get("success"):
            return collection_result

        results = collection_result.get("results", {})

        # 如果没有结果
        if not results:
            return {"success": False, "error": "No results found", "task_id": task_id}

        # 合并结果
        merged = self.merger.merge_results(results, merge_strategy="intelligent")

        return {
            "success": True,
            "task_id": task_id,
            "results_count": len(results),
            "merged": merged.get("merged") if merged.get("success") else None,
            "raw_results": results if include_intermediate else None,
        }
