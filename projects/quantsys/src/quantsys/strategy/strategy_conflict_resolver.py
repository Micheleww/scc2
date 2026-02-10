#!/usr/bin/env python3
"""
多策略冲突解算器
实现同品种多策略目标仓位合并、净额化、优先级规则
输出最终target_position与解释字段
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    filename="logs/strategy_conflict_resolver.log",
)
logger = logging.getLogger(__name__)


@dataclass
class StrategyPositionRequest:
    """
    策略仓位请求
    """

    strategy_id: str
    symbol: str
    target_position: float
    priority: int = 100  # 优先级，值越小优先级越高
    confidence: float = 1.0  # 置信度，0-1之间
    reason: str | None = None  # 仓位调整原因
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class ResolvedPosition:
    """
    解算后的最终仓位
    """

    symbol: str
    target_position: float
    resolved_at: str = field(default_factory=lambda: datetime.now().isoformat())
    explanation: dict[str, Any] = field(default_factory=dict)


@dataclass
class PositionResolutionResult:
    """
    仓位解算结果
    """

    resolved_positions: list[ResolvedPosition]
    conflicts_resolved: int = 0
    total_requests: int = 0
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())


class StrategyConflictResolver:
    """
    多策略冲突解算器
    """

    def __init__(self, config: dict[str, Any] | None = None):
        """
        初始化冲突解算器

        Args:
            config: 配置信息
        """
        self.config = config or {}
        self.strategy_priorities = self.config.get("strategy_priorities", {})
        self.default_priority = self.config.get("default_priority", 100)
        self.enable_netting = self.config.get("enable_netting", True)
        self.max_conflicts_per_symbol = self.config.get("max_conflicts_per_symbol", 10)

        logger.info("多策略冲突解算器初始化完成")

    def resolve_conflicts(
        self, position_requests: list[StrategyPositionRequest]
    ) -> PositionResolutionResult:
        """
        解算多策略仓位冲突

        Args:
            position_requests: 策略仓位请求列表

        Returns:
            PositionResolutionResult: 仓位解算结果
        """
        logger.info(f"开始解算策略仓位冲突，共 {len(position_requests)} 个请求")

        # 按品种分组
        symbol_requests: dict[str, list[StrategyPositionRequest]] = {}
        for request in position_requests:
            if request.symbol not in symbol_requests:
                symbol_requests[request.symbol] = []
            symbol_requests[request.symbol].append(request)

        resolved_positions = []
        conflicts_resolved = 0

        # 处理每个品种的仓位请求
        for symbol, requests in symbol_requests.items():
            # 计算该品种的冲突数量
            conflict_count = len(requests) - 1
            conflicts_resolved += conflict_count if conflict_count > 0 else 0

            # 解算该品种的最终仓位
            resolved_position = self._resolve_symbol_positions(symbol, requests)
            resolved_positions.append(resolved_position)

        result = PositionResolutionResult(
            resolved_positions=resolved_positions,
            conflicts_resolved=conflicts_resolved,
            total_requests=len(position_requests),
        )

        logger.info(f"策略仓位冲突解算完成，解决了 {conflicts_resolved} 个冲突")
        return result

    def _resolve_symbol_positions(
        self, symbol: str, requests: list[StrategyPositionRequest]
    ) -> ResolvedPosition:
        """
        解算单个品种的仓位请求

        Args:
            symbol: 品种符号
            requests: 该品种的仓位请求列表

        Returns:
            ResolvedPosition: 解算后的仓位
        """
        # 按优先级排序，优先级值越小优先级越高
        sorted_requests = sorted(requests, key=lambda x: (x.priority, -x.confidence))

        # 生成解释信息
        explanation = {
            "symbol": symbol,
            "original_requests": [
                {
                    "strategy_id": req.strategy_id,
                    "target_position": req.target_position,
                    "priority": req.priority,
                    "confidence": req.confidence,
                    "reason": req.reason,
                    "timestamp": req.timestamp,
                }
                for req in requests
            ],
            "sorted_requests": [req.strategy_id for req in sorted_requests],
            "resolution_method": "priority-based" if len(requests) > 1 else "single_strategy",
            "conflict_count": len(requests) - 1 if len(requests) > 1 else 0,
        }

        if len(requests) == 1:
            # 只有一个策略请求，直接使用其目标仓位
            req = requests[0]
            target_position = req.target_position
            explanation["final_strategy"] = req.strategy_id
            explanation["merge_details"] = "single_strategy_no_conflict"
        else:
            # 多个策略请求，使用优先级规则合并
            target_position = self._merge_positions(sorted_requests, explanation)

        # 生成最终的解算仓位
        resolved_position = ResolvedPosition(
            symbol=symbol, target_position=target_position, explanation=explanation
        )

        logger.info(f"品种 {symbol} 的仓位解算完成，最终目标仓位: {target_position}")
        return resolved_position

    def _merge_positions(
        self, sorted_requests: list[StrategyPositionRequest], explanation: dict[str, Any]
    ) -> float:
        """
        合并多个策略的仓位请求

        Args:
            sorted_requests: 按优先级排序的仓位请求列表
            explanation: 解释信息字典，会被更新

        Returns:
            float: 合并后的目标仓位
        """
        # 计算优先级权重
        weights = self._calculate_priority_weights(sorted_requests)
        explanation["priority_weights"] = weights

        # 计算加权平均仓位
        weighted_sum = 0.0
        total_weight = 0.0

        weight_details = []
        for i, (req, weight) in enumerate(zip(sorted_requests, weights)):
            weighted_position = req.target_position * weight
            weighted_sum += weighted_position
            total_weight += weight

            weight_details.append(
                {
                    "strategy_id": req.strategy_id,
                    "weight": weight,
                    "target_position": req.target_position,
                    "weighted_contribution": weighted_position,
                }
            )

        explanation["weight_details"] = weight_details

        # 计算最终目标仓位
        if total_weight > 0:
            target_position = weighted_sum / total_weight
        else:
            target_position = 0.0

        # 应用净额化处理
        if self.enable_netting:
            original_position = target_position
            target_position = self._apply_netting(target_position)
            explanation["netting_applied"] = True
            explanation["netting_original"] = original_position
            explanation["netting_result"] = target_position
        else:
            explanation["netting_applied"] = False

        explanation["merge_details"] = "weighted_average_by_priority"
        explanation["final_strategy"] = "merged_by_priority"

        return target_position

    def _calculate_priority_weights(
        self, sorted_requests: list[StrategyPositionRequest]
    ) -> list[float]:
        """
        计算优先级权重

        Args:
            sorted_requests: 按优先级排序的仓位请求列表

        Returns:
            List[float]: 每个请求的权重列表
        """
        # 基于优先级计算权重，优先级越高权重越大
        weights = []

        for i, req in enumerate(sorted_requests):
            # 优先级权重：1/(i+1)，i从0开始
            priority_weight = 1.0 / (i + 1)
            # 置信度权重：req.confidence
            confidence_weight = req.confidence
            # 综合权重
            total_weight = priority_weight * confidence_weight
            weights.append(total_weight)

        # 归一化权重
        total = sum(weights)
        if total > 0:
            weights = [w / total for w in weights]

        return weights

    def _apply_netting(self, position: float) -> float:
        """
        应用净额化处理

        Args:
            position: 原始仓位

        Returns:
            float: 净额化后的仓位
        """
        # 这里实现简单的净额化，实际可以根据需求调整
        # 例如：去除微小仓位，或者根据交易所规则调整
        return round(position, 8)  # 保留8位小数

    def generate_evidence(self, result: PositionResolutionResult) -> dict[str, Any]:
        """
        生成解算证据

        Args:
            result: 仓位解算结果

        Returns:
            Dict[str, Any]: 解算证据
        """
        evidence = {
            "resolver_name": "StrategyConflictResolver",
            "result": {
                "resolved_positions_count": len(result.resolved_positions),
                "conflicts_resolved": result.conflicts_resolved,
                "total_requests": result.total_requests,
                "timestamp": result.timestamp,
            },
            "resolved_positions": [
                {
                    "symbol": pos.symbol,
                    "target_position": pos.target_position,
                    "resolved_at": pos.resolved_at,
                    "explanation": pos.explanation,
                }
                for pos in result.resolved_positions
            ],
            "generated_at": datetime.now().isoformat(),
        }

        return evidence

    def save_evidence(self, result: PositionResolutionResult, output_dir: str = "evidence") -> str:
        """
        保存解算证据到文件

        Args:
            result: 仓位解算结果
            output_dir: 输出目录

        Returns:
            str: 证据文件路径
        """
        import json
        import os

        os.makedirs(output_dir, exist_ok=True)
        evidence = self.generate_evidence(result)
        evidence_file = os.path.join(
            output_dir,
            f"strategy_conflict_resolution_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
        )

        try:
            with open(evidence_file, "w", encoding="utf-8") as f:
                json.dump(evidence, f, indent=2, ensure_ascii=False)
            logger.info(f"策略冲突解算证据已保存到: {evidence_file}")
            return evidence_file
        except Exception as e:
            logger.error(f"保存策略冲突解算证据失败: {e}")
            raise
