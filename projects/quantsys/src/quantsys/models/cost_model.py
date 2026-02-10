"""
统一成本模型
支持fee/maker-taker、滑点（按波动/深度简化）、冲击成本（可选）
回测/纸交易/实盘同口径引用
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class CostBreakdown:
    """
    成本分解结构
    """

    fee: float = 0.0  # 手续费成本
    slippage_cost: float = 0.0  # 滑点成本
    impact_cost: float = 0.0  # 冲击成本
    funding_cost: float = 0.0  # 资金费率成本
    total_cost: float = 0.0  # 总成本
    fee_rate: float = 0.0  # 实际使用的费率
    is_taker: bool = False  # 是否为taker单
    cost_details: dict[str, Any] = field(default_factory=dict)  # 成本计算详情


class UnifiedCostModel:
    """
    统一成本模型
    支持fee/maker-taker、滑点（按波动/深度简化）、冲击成本（可选）
    回测/纸交易/实盘同口径引用
    """

    def __init__(
        self,
        maker_fee: float = 0.0002,  # maker手续费率
        taker_fee: float = 0.0005,  # taker手续费率
        slippage_type: str = "volatility",  # 滑点类型: volatility/depth/simple
        slippage_param: float = 0.001,  # 滑点参数，根据类型不同含义不同
        enable_impact_cost: bool = False,  # 是否启用冲击成本
        impact_cost_factor: float = 0.0001,  # 冲击成本因子
        funding_rate: float = 0.0,  # 资金费率
        funding_interval_hours: float = 8.0,  # 资金费率结算间隔（小时）
        environment: str = "backtest",  # 运行环境: backtest/paper/live
    ) -> None:
        """
        初始化统一成本模型

        Args:
            maker_fee: maker手续费率
            taker_fee: taker手续费率
            slippage_type: 滑点类型，可选值: volatility/depth/simple
            slippage_param: 滑点参数
                - volatility: 基于波动的滑点系数（如0.001表示0.1%）
                - depth: 基于深度的滑点系数
                - simple: 固定滑点百分比
            enable_impact_cost: 是否启用冲击成本
            impact_cost_factor: 冲击成本因子
            funding_rate: 资金费率
            funding_interval_hours: 资金费率结算间隔（小时）
            environment: 运行环境，用于区分回测/纸交易/实盘
        """
        self.maker_fee = maker_fee
        self.taker_fee = taker_fee
        self.slippage_type = slippage_type
        self.slippage_param = slippage_param
        self.enable_impact_cost = enable_impact_cost
        self.impact_cost_factor = impact_cost_factor
        self.funding_rate = funding_rate
        self.funding_interval_hours = funding_interval_hours
        self.environment = environment

        # 验证滑点类型
        if self.slippage_type not in ["volatility", "depth", "simple"]:
            raise ValueError(f"不支持的滑点类型: {self.slippage_type}")

    def calculate_fee(
        self,
        notional: float,  # 名义价值
        is_taker: bool,  # 是否为taker单
    ) -> float:
        """
        计算手续费成本

        Args:
            notional: 名义价值
            is_taker: 是否为taker单

        Returns:
            float: 手续费成本
        """
        fee_rate = self.taker_fee if is_taker else self.maker_fee
        return abs(notional) * fee_rate if notional != 0 else 0.0

    def calculate_slippage(
        self,
        base_price: float,  # 基准价格
        qty: float,  # 数量
        volatility: float = 0.001,  # 波动率（如0.001表示0.1%）
        order_book_depth: float = 10000.0,  # 订单簿深度（名义价值）
        fill_price: float | None = None,  # 实际成交价（用于simple模式）
    ) -> float:
        """
        计算滑点成本

        Args:
            base_price: 基准价格
            qty: 数量
            volatility: 波动率，用于volatility模式
            order_book_depth: 订单簿深度，用于depth模式
            fill_price: 实际成交价，用于simple模式

        Returns:
            float: 滑点成本
        """
        if base_price <= 0 or qty == 0:
            return 0.0

        notional = abs(qty) * base_price
        slippage = 0.0

        if self.slippage_type == "simple":
            # 简单模式：使用固定滑点百分比或实际成交价差
            if fill_price is not None:
                # 有实际成交价时，使用实际价差
                slippage = abs(fill_price - base_price) * abs(qty)
            else:
                # 无实际成交价时，使用固定滑点百分比
                slippage = base_price * abs(qty) * self.slippage_param

        elif self.slippage_type == "volatility":
            # 基于波动率的滑点
            # 滑点 = 基准价格 * 数量 * 波动率 * 滑点系数
            slippage = base_price * abs(qty) * volatility * self.slippage_param

        elif self.slippage_type == "depth":
            # 基于深度的滑点
            # 滑点 = (成交名义价值 / 订单簿深度) * 基准价格 * 数量 * 滑点系数
            depth_ratio = min(1.0, notional / order_book_depth) if order_book_depth > 0 else 0.0
            slippage = depth_ratio * base_price * abs(qty) * self.slippage_param

        return slippage

    def calculate_impact_cost(
        self,
        notional: float,  # 名义价值
        order_book_depth: float = 10000.0,  # 订单簿深度（名义价值）
        volatility: float = 0.001,  # 波动率
    ) -> float:
        """
        计算冲击成本

        Args:
            notional: 名义价值
            order_book_depth: 订单簿深度
            volatility: 波动率

        Returns:
            float: 冲击成本
        """
        if not self.enable_impact_cost or notional == 0:
            return 0.0

        # 冲击成本 = (成交名义价值 / 订单簿深度) * 波动率 * 冲击成本因子 * 名义价值
        depth_ratio = min(1.0, abs(notional) / order_book_depth) if order_book_depth > 0 else 0.0
        impact_cost = depth_ratio * volatility * self.impact_cost_factor * abs(notional)

        return impact_cost

    def calculate_funding_cost(
        self,
        notional: float,  # 名义价值
        hours_held: float,  # 持有时间（小时）
        position_side: int,  # 仓位方向: 1=多头, -1=空头
    ) -> float:
        """
        计算资金费率成本

        Args:
            notional: 名义价值
            hours_held: 持有时间（小时）
            position_side: 仓位方向

        Returns:
            float: 资金费率成本
        """
        if self.funding_interval_hours <= 0 or hours_held <= 0:
            return 0.0

        # 计算资金费率结算次数
        intervals = int(hours_held // self.funding_interval_hours)
        if intervals <= 0:
            return 0.0

        # 资金费率成本 = 名义价值 * 资金费率 * 结算次数 * 仓位方向
        funding_cost = notional * self.funding_rate * intervals * position_side

        return funding_cost

    def calculate(
        self,
        base_price: float,  # 基准价格
        qty: float,  # 数量
        is_taker: bool,  # 是否为taker单
        hours_held: float = 0.0,  # 持有时间（小时）
        position_side: int = 1,  # 仓位方向
        volatility: float = 0.001,  # 波动率
        order_book_depth: float = 10000.0,  # 订单簿深度
        fill_price: float | None = None,  # 实际成交价
        **kwargs,
    ) -> CostBreakdown:
        """
        计算总成本

        Args:
            base_price: 基准价格
            qty: 数量
            is_taker: 是否为taker单
            hours_held: 持有时间（小时）
            position_side: 仓位方向
            volatility: 波动率
            order_book_depth: 订单簿深度
            fill_price: 实际成交价

        Returns:
            CostBreakdown: 成本分解
        """
        if base_price <= 0:
            return CostBreakdown()

        notional = abs(qty) * base_price
        fee_rate = self.taker_fee if is_taker else self.maker_fee

        # 计算各项成本
        fee = self.calculate_fee(notional, is_taker)
        slippage = self.calculate_slippage(
            base_price, qty, volatility, order_book_depth, fill_price
        )
        impact_cost = self.calculate_impact_cost(notional, order_book_depth, volatility)
        funding_cost = self.calculate_funding_cost(notional, hours_held, position_side)

        # 计算总成本
        total_cost = fee + slippage + impact_cost + funding_cost

        # 生成成本详情
        cost_details = {
            "environment": self.environment,
            "base_price": base_price,
            "qty": qty,
            "notional": notional,
            "slippage_type": self.slippage_type,
            "slippage_param": self.slippage_param,
            "volatility": volatility,
            "order_book_depth": order_book_depth,
            "enable_impact_cost": self.enable_impact_cost,
            "impact_cost_factor": self.impact_cost_factor,
            "funding_rate": self.funding_rate,
            "funding_hours_held": hours_held,
            "position_side": position_side,
        }

        return CostBreakdown(
            fee=fee,
            slippage_cost=slippage,
            impact_cost=impact_cost,
            funding_cost=funding_cost,
            total_cost=total_cost,
            fee_rate=fee_rate,
            is_taker=is_taker,
            cost_details=cost_details,
        )

    def get_config(self) -> dict[str, Any]:
        """
        获取成本模型配置

        Returns:
            Dict[str, Any]: 配置字典
        """
        return {
            "maker_fee": self.maker_fee,
            "taker_fee": self.taker_fee,
            "slippage_type": self.slippage_type,
            "slippage_param": self.slippage_param,
            "enable_impact_cost": self.enable_impact_cost,
            "impact_cost_factor": self.impact_cost_factor,
            "funding_rate": self.funding_rate,
            "funding_interval_hours": self.funding_interval_hours,
            "environment": self.environment,
        }

    def __repr__(self) -> str:
        """
        字符串表示

        Returns:
            str: 字符串表示
        """
        return (
            f"UnifiedCostModel(environment={self.environment}, "
            f"maker_fee={self.maker_fee}, taker_fee={self.taker_fee}, "
            f"slippage={self.slippage_type}:{self.slippage_param}, "
            f"impact_cost={'enabled' if self.enable_impact_cost else 'disabled'})"
        )


# 为了向后兼容，保留原有的TradeCostModel类
class TradeCostModel(UnifiedCostModel):
    """
    向后兼容类
    """

    def __init__(
        self,
        maker_fee: float = 0.0002,
        taker_fee: float = 0.0005,
        funding_rate: float = 0.0,
        funding_interval_hours: float = 8.0,
    ) -> None:
        super().__init__(
            maker_fee=maker_fee,
            taker_fee=taker_fee,
            slippage_type="simple",
            slippage_param=0.0,
            enable_impact_cost=False,
            funding_rate=funding_rate,
            funding_interval_hours=funding_interval_hours,
        )

    def calculate(
        self,
        notional: float,
        is_taker: bool,
        slippage_cost: float,
        hours_held: float,
        position_side: int,
    ) -> CostBreakdown:
        """
        兼容原有calculate方法
        """
        result = super().calculate(
            base_price=notional / abs(notional) if notional != 0 else 1.0,
            qty=abs(notional),
            is_taker=is_taker,
            hours_held=hours_held,
            position_side=position_side,
        )
        # 使用传入的滑点成本覆盖计算结果
        result.slippage_cost = slippage_cost
        result.total_cost = result.fee + slippage_cost + result.funding_cost
        return result

    def slippage_cost(self, base_price: float, fill_price: float, qty: float) -> float:
        """
        兼容原有slippage_cost方法
        """
        return super().calculate_slippage(base_price=base_price, qty=qty, fill_price=fill_price)
