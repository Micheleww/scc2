#!/usr/bin/env python3
"""
风险预算管理模块
负责计算从 w 到 effective_risk 的转换

!!! 核心红线资产：仅允许经主控批准修改 !!!
任何对本文件的修改必须经过严格的审查和批准流程
详见 docs/core_assets.md
"""

from typing import Any

from ..belief.market_belief import HealthScore


class RiskBudgetManager:
    """
    风险预算管理器
    计算并管理风险预算
    """

    def __init__(
        self, base_risk: float, max_daily_loss: float, max_weekly_loss: float, max_drawdown: float
    ):
        """
        初始化风险预算管理器

        Args:
            base_risk: 账户层面可承受的单笔最大损失上限
            max_daily_loss: 每日最大允许损失
            max_weekly_loss: 每周最大允许损失
            max_drawdown: 最大允许回撤
        """
        # 只读参数，只能通过配置修改
        self._base_risk = base_risk
        self.max_daily_loss = max_daily_loss
        self.max_weekly_loss = max_weekly_loss
        self.max_drawdown = max_drawdown

        # 运行时状态
        self.daily_loss = 0.0
        self.weekly_loss = 0.0
        self.current_drawdown = 0.0
        self.consecutive_losses = 0
        self.w_cap = 1.0  # w 的上限，可动态调整

    @property
    def base_risk(self) -> float:
        """
        base_risk 只读属性
        """
        return self._base_risk

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
        self.daily_loss = daily_loss
        self.weekly_loss = weekly_loss
        self.current_drawdown = drawdown

        # 更新连续亏损计数
        if is_loss:
            self.consecutive_losses += 1
        else:
            self.consecutive_losses = 0

        # 根据连续亏损调整 w_cap
        # 连续亏损越多，w_cap 越低
        if self.consecutive_losses >= 3:
            self.w_cap = max(0.5, 1.0 - (self.consecutive_losses - 2) * 0.1)
        else:
            self.w_cap = 1.0

    def compute_effective_risk(
        self, w: float, health_score: HealthScore
    ) -> tuple[float, dict[str, Any]]:
        """
        计算 effective_risk

        Args:
            w: 风险强度
            health_score: 信念健康度评分

        Returns:
            Tuple[float, Dict[str, Any]]: (effective_risk, 风险预算元数据)
        """
        # 1. 应用 w_cap 限制
        adjusted_w = min(w, self.w_cap)

        # 2. 计算基础 effective_risk: base_risk × w²
        effective_risk = self.base_risk * (adjusted_w**2)

        # 3. 应用信念健康度调整
        # 健康度只能降低风险，不能放大
        effective_risk = effective_risk * health_score.overall_health

        # 4. 应用亏损限制
        # 确保不超过日/周/回撤限制
        remaining_daily_risk = max(0.0, self.max_daily_loss - self.daily_loss)
        remaining_weekly_risk = max(0.0, self.max_weekly_loss - self.weekly_loss)
        remaining_drawdown_risk = max(0.0, self.max_drawdown - self.current_drawdown)

        # 取最小值作为最终 effective_risk
        effective_risk = min(
            effective_risk, remaining_daily_risk, remaining_weekly_risk, remaining_drawdown_risk
        )

        # 5. 确保 effective_risk 非负
        effective_risk = max(0.0, effective_risk)

        # 生成风险预算元数据
        risk_meta = {
            "base_risk": self.base_risk,
            "raw_w": w,
            "adjusted_w": adjusted_w,
            "health_score": health_score.overall_health,
            "w_cap": self.w_cap,
            "remaining_daily_risk": remaining_daily_risk,
            "remaining_weekly_risk": remaining_weekly_risk,
            "remaining_drawdown_risk": remaining_drawdown_risk,
            "consecutive_losses": self.consecutive_losses,
        }

        return effective_risk, risk_meta

    def is_risk_limit_exceeded(self) -> bool:
        """
        检查是否超过风险限制

        Returns:
            bool: 是否超过风险限制
        """
        return (
            self.daily_loss >= self.max_daily_loss
            or self.weekly_loss >= self.max_weekly_loss
            or self.current_drawdown >= self.max_drawdown
        )


def create_risk_budget_manager(
    base_risk: float, max_daily_loss: float, max_weekly_loss: float, max_drawdown: float
) -> RiskBudgetManager:
    """
    创建风险预算管理器实例

    Args:
        base_risk: 账户层面可承受的单笔最大损失上限
        max_daily_loss: 每日最大允许损失
        max_weekly_loss: 每周最大允许损失
        max_drawdown: 最大允许回撤

    Returns:
        RiskBudgetManager: 风险预算管理器实例
    """
    return RiskBudgetManager(
        base_risk=base_risk,
        max_daily_loss=max_daily_loss,
        max_weekly_loss=max_weekly_loss,
        max_drawdown=max_drawdown,
    )
