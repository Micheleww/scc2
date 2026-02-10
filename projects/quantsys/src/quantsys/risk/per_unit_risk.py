#!/usr/bin/env python3
"""
单位风险估计模块
保守估计每单位仓位的最坏风险
"""

from typing import Any

from ..belief.market_belief import MarketBeliefCalibrated


class PerUnitRiskEstimator:
    """
    单位风险估计器
    保守估计每单位仓位的最坏风险
    """

    def __init__(self, max_slippage: float, tail_buffer_factor: float = 1.5):
        """
        初始化单位风险估计器

        Args:
            max_slippage: 最大允许滑点
            tail_buffer_factor: 尾部风险缓冲因子
        """
        self.max_slippage = max_slippage
        self.tail_buffer_factor = tail_buffer_factor

    def estimate_per_unit_risk(
        self, calibrated_belief: MarketBeliefCalibrated, market_data: dict[str, Any]
    ) -> tuple[float, dict[str, float]]:
        """
        估计每单位仓位的最坏风险

        Args:
            calibrated_belief: 校准后的信念
            market_data: 当前市场数据

        Returns:
            Tuple[float, Dict[str, float]]: (per_unit_risk, 风险组成明细)
        """
        # 1. 计算止损损失
        # 基于幅度概率分布和时间概率分布保守估计
        stop_loss_risk = self._calculate_stop_loss_risk(calibrated_belief, market_data)

        # 2. 计算滑点缓冲
        slippage_buffer = self._calculate_slippage_buffer(market_data)

        # 3. 计算手续费
        fee_risk = self._calculate_fee_risk(market_data)

        # 4. 计算尾部/跳空缓冲
        # 基于幅度分布的极端情况和尾部缓冲因子
        tail_buffer = self._calculate_tail_buffer(calibrated_belief, stop_loss_risk)

        # 5. 总单位风险 = 止损损失 + 滑点缓冲 + 手续费 + 尾部缓冲
        per_unit_risk = stop_loss_risk + slippage_buffer + fee_risk + tail_buffer

        # 风险组成明细
        risk_components = {
            "stop_loss_risk": stop_loss_risk,
            "slippage_buffer": slippage_buffer,
            "fee_risk": fee_risk,
            "tail_buffer": tail_buffer,
        }

        return per_unit_risk, risk_components

    def _calculate_stop_loss_risk(
        self, calibrated_belief: MarketBeliefCalibrated, market_data: dict[str, Any]
    ) -> float:
        """
        计算止损损失

        Args:
            calibrated_belief: 校准后的信念
            market_data: 当前市场数据

        Returns:
            float: 止损损失
        """
        belief = calibrated_belief.belief

        # 基于幅度概率分布保守估计止损距离
        # 例如：使用大波动概率加权的平均止损距离
        magnitude_weights = {
            "small": 0.02,  # 小波动对应 2% 止损
            "medium": 0.05,  # 中波动对应 5% 止损
            "large": 0.10,  # 大波动对应 10% 止损
        }

        # 加权平均止损比例
        weighted_stop_loss = (
            belief.magnitude["small"] * magnitude_weights["small"]
            + belief.magnitude["medium"] * magnitude_weights["medium"]
            + belief.magnitude["large"] * magnitude_weights["large"]
        )

        # 应用时间因子：持有时间越长，止损距离可能越大
        time_factor = (
            belief.time["short"] * 1.0 + belief.time["medium"] * 1.2 + belief.time["long"] * 1.5
        )

        # 当前价格
        current_price = market_data.get("current_price", 1.0)

        # 止损损失 = 价格 * 加权止损比例 * 时间因子
        stop_loss_risk = current_price * weighted_stop_loss * time_factor

        return stop_loss_risk

    def _calculate_slippage_buffer(self, market_data: dict[str, Any]) -> float:
        """
        计算滑点缓冲

        Args:
            market_data: 当前市场数据

        Returns:
            float: 滑点缓冲
        """
        current_price = market_data.get("current_price", 1.0)

        # 基于最大允许滑点计算滑点缓冲
        # 保守估计：使用最大滑点
        slippage_buffer = current_price * self.max_slippage

        return slippage_buffer

    def _calculate_fee_risk(self, market_data: dict[str, Any]) -> float:
        """
        计算手续费风险

        Args:
            market_data: 当前市场数据

        Returns:
            float: 手续费风险
        """
        current_price = market_data.get("current_price", 1.0)
        fee_rate = market_data.get("fee_rate", 0.001)  # 默认千分之一手续费

        # 手续费 = 价格 * 手续费率 * 2（往返）
        fee_risk = current_price * fee_rate * 2

        return fee_risk

    def _calculate_tail_buffer(
        self, calibrated_belief: MarketBeliefCalibrated, stop_loss_risk: float
    ) -> float:
        """
        计算尾部/跳空缓冲

        Args:
            calibrated_belief: 校准后的信念
            stop_loss_risk: 止损损失

        Returns:
            float: 尾部/跳空缓冲
        """
        belief = calibrated_belief.belief

        # 基于大波动概率调整尾部缓冲
        # 大波动概率越高，尾部缓冲越大
        tail_factor = 1.0 + belief.magnitude["large"] * self.tail_buffer_factor

        # 尾部缓冲 = 止损损失 * 尾部因子
        tail_buffer = stop_loss_risk * tail_factor

        return tail_buffer


def create_per_unit_risk_estimator(
    max_slippage: float = 0.005, tail_buffer_factor: float = 1.5
) -> PerUnitRiskEstimator:
    """
    创建单位风险估计器实例

    Args:
        max_slippage: 最大允许滑点
        tail_buffer_factor: 尾部风险缓冲因子

    Returns:
        PerUnitRiskEstimator: 单位风险估计器实例
    """
    return PerUnitRiskEstimator(max_slippage=max_slippage, tail_buffer_factor=tail_buffer_factor)
