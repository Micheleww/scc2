#!/usr/bin/env python3
"""
仓位计算模块
基于 effective_risk / per_unit_risk 计算最终仓位
"""

from typing import Any


class PositionSizer:
    """
    仓位计算器
    基于 effective_risk / per_unit_risk 计算最终仓位
    """

    def __init__(self, max_position_size: float):
        """
        初始化仓位计算器

        Args:
            max_position_size: 最大允许仓位大小
        """
        self.max_position_size = max_position_size

    def calculate_position_size(
        self, effective_risk: float, per_unit_risk: float
    ) -> tuple[float, dict[str, Any]]:
        """
        计算最终仓位大小

        Args:
            effective_risk: 本次交易允许消耗的最大现金损失
            per_unit_risk: 每单位仓位的最坏风险

        Returns:
            Tuple[float, Dict[str, Any]]: (position_size, 仓位计算元数据)
        """
        # 1. 检查参数合法性
        if per_unit_risk <= 0:
            raise ValueError("per_unit_risk must be positive")

        if effective_risk < 0:
            raise ValueError("effective_risk must be non-negative")

        # 2. 核心公式：仓位大小 = 可承受最大损失 ÷ 单位最坏风险
        position_size = effective_risk / per_unit_risk

        # 3. 应用最大仓位限制
        position_size = min(position_size, self.max_position_size)

        # 4. 确保仓位大小非负
        position_size = max(0.0, position_size)

        # 生成仓位计算元数据
        sizing_meta = {
            "effective_risk": effective_risk,
            "per_unit_risk": per_unit_risk,
            "calculated_position": effective_risk / per_unit_risk,
            "applied_max_position": self.max_position_size,
            "final_position": position_size,
        }

        return position_size, sizing_meta

    def validate_position_size(self, position_size: float) -> bool:
        """
        验证仓位大小是否合法

        Args:
            position_size: 仓位大小

        Returns:
            bool: 是否合法
        """
        return 0.0 <= position_size <= self.max_position_size


def create_position_sizer(max_position_size: float = 1.0) -> PositionSizer:
    """
    创建仓位计算器实例

    Args:
        max_position_size: 最大允许仓位大小

    Returns:
        PositionSizer: 仓位计算器实例
    """
    return PositionSizer(max_position_size=max_position_size)
