#!/usr/bin/env python3
"""
信念到仓位的完整流水线
将所有模块串联起来，实现从 Market Belief 到最终仓位的完整流程
"""

from typing import Any

from ..belief.market_belief import MarketBeliefRaw
from ..calibration.belief_calibration import create_belief_calibration_pipeline
from ..risk.budget import create_risk_budget_manager
from ..risk.per_unit_risk import create_per_unit_risk_estimator
from ..risk.position_sizing import create_position_sizer
from ..state.weight_estimator import compute_state_and_weight, create_weight_estimator


class BeliefToPositionPipeline:
    """
    信念到仓位的完整流水线
    整合所有模块，实现从 Market Belief 到最终仓位的转换
    """

    def __init__(self, config: dict[str, Any]):
        """
        初始化信念到仓位的流水线

        Args:
            config: 流水线配置
        """
        # 1. 初始化信念校准流水线
        self.calibration_pipeline = create_belief_calibration_pipeline()

        # 2. 初始化权重估计器
        self.weight_estimator = create_weight_estimator()

        # 3. 初始化风险预算管理器
        self.risk_budget_manager = create_risk_budget_manager(
            base_risk=config.get("base_risk", 1000.0),
            max_daily_loss=config.get("max_daily_loss", 5000.0),
            max_weekly_loss=config.get("max_weekly_loss", 20000.0),
            max_drawdown=config.get("max_drawdown", 50000.0),
        )

        # 4. 初始化单位风险估计器
        self.per_unit_risk_estimator = create_per_unit_risk_estimator(
            max_slippage=config.get("max_slippage", 0.005),
            tail_buffer_factor=config.get("tail_buffer_factor", 1.5),
        )

        # 5. 初始化仓位计算器
        self.position_sizer = create_position_sizer(
            max_position_size=config.get("max_position_size", 100.0)
        )

    def update_risk_state(
        self, daily_loss: float, weekly_loss: float, drawdown: float, is_loss: bool
    ) -> None:
        """
        更新风险状态

        Args:
            daily_loss: 当日累计损失
            weekly_loss: 当周累计损失
            drawdown: 当前回撤
            is_loss: 本次交易是否亏损
        """
        self.risk_budget_manager.update_risk_state(
            daily_loss=daily_loss, weekly_loss=weekly_loss, drawdown=drawdown, is_loss=is_loss
        )

    def run(
        self,
        raw_belief: MarketBeliefRaw,
        historical_performance: dict[str, Any],
        market_data: dict[str, Any],
    ) -> dict[str, Any]:
        """
        运行完整的信念到仓位流水线

        Args:
            raw_belief: 原始信念
            historical_performance: 历史表现数据
            market_data: 当前市场数据

        Returns:
            Dict[str, Any]: 完整的流水线结果
        """
        # 1. 校准信念并计算健康度评分
        calibrated_belief = self.calibration_pipeline.process(
            raw_belief=raw_belief, historical_performance=historical_performance
        )

        # 2. 计算风险强度 w 和状态标签
        w, state_label, should_participate = compute_state_and_weight(
            calibrated_belief=calibrated_belief, weight_estimator=self.weight_estimator
        )

        # 3. 如果不参与交易，返回空仓位
        if not should_participate:
            return {
                "raw_belief": raw_belief,
                "calibrated_belief": calibrated_belief,
                "w": w,
                "state_label": state_label,
                "should_participate": False,
                "effective_risk": 0.0,
                "per_unit_risk": 0.0,
                "position_size": 0.0,
                "risk_limit_exceeded": self.risk_budget_manager.is_risk_limit_exceeded(),
            }

        # 4. 计算 effective_risk
        effective_risk, risk_meta = self.risk_budget_manager.compute_effective_risk(
            w=w, health_score=calibrated_belief.health_score
        )

        # 5. 估计 per_unit_risk
        per_unit_risk, risk_components = self.per_unit_risk_estimator.estimate_per_unit_risk(
            calibrated_belief=calibrated_belief, market_data=market_data
        )

        # 6. 计算最终仓位
        position_size, sizing_meta = self.position_sizer.calculate_position_size(
            effective_risk=effective_risk, per_unit_risk=per_unit_risk
        )

        # 7. 生成完整结果
        result = {
            "raw_belief": raw_belief,
            "calibrated_belief": calibrated_belief,
            "w": w,
            "state_label": state_label,
            "should_participate": should_participate,
            "effective_risk": effective_risk,
            "risk_meta": risk_meta,
            "per_unit_risk": per_unit_risk,
            "risk_components": risk_components,
            "position_size": position_size,
            "sizing_meta": sizing_meta,
            "risk_limit_exceeded": self.risk_budget_manager.is_risk_limit_exceeded(),
        }

        return result


def create_belief_to_position_pipeline(config: dict[str, Any] = None) -> BeliefToPositionPipeline:
    """
    创建信念到仓位的流水线实例

    Args:
        config: 流水线配置

    Returns:
        BeliefToPositionPipeline: 信念到仓位的流水线实例
    """
    if config is None:
        config = {}

    return BeliefToPositionPipeline(config)
