#!/usr/bin/env python3
"""
交易成本计算模块
实现实盘版手续费/滑点/资金费率统一成本核算
"""

import json
import logging
import os
import time
from dataclasses import dataclass
from typing import Any

from ..models.cost_model import UnifiedCostModel

# 配置日志
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


@dataclass
class TradeCostBreakdown:
    """
    交易成本分解结构
    """

    trade_id: str
    symbol: str
    timestamp: float
    side: str
    amount: float
    trigger_price: float
    protection_price: float
    filled_price: float
    is_taker: bool

    # 成本明细
    fee: float
    fee_rate: float
    slippage_cost: float
    slippage_pct: float
    funding_cost: float
    funding_rate: float
    total_cost: float

    # 关联信息
    order_id: str
    fill_id: str
    position_side: int = 1  # 1=多头, -1=空头

    def to_dict(self) -> dict[str, Any]:
        """转换为字典格式"""
        return {
            "trade_id": self.trade_id,
            "symbol": self.symbol,
            "timestamp": self.timestamp,
            "side": self.side,
            "amount": self.amount,
            "trigger_price": self.trigger_price,
            "protection_price": self.protection_price,
            "filled_price": self.filled_price,
            "is_taker": self.is_taker,
            "fee": self.fee,
            "fee_rate": self.fee_rate,
            "slippage_cost": self.slippage_cost,
            "slippage_pct": self.slippage_pct,
            "funding_cost": self.funding_cost,
            "funding_rate": self.funding_rate,
            "total_cost": self.total_cost,
            "order_id": self.order_id,
            "fill_id": self.fill_id,
            "position_side": self.position_side,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TradeCostBreakdown":
        """从字典创建实例"""
        return cls(
            trade_id=data["trade_id"],
            symbol=data["symbol"],
            timestamp=data["timestamp"],
            side=data["side"],
            amount=data["amount"],
            trigger_price=data["trigger_price"],
            protection_price=data["protection_price"],
            filled_price=data["filled_price"],
            is_taker=data["is_taker"],
            fee=data["fee"],
            fee_rate=data["fee_rate"],
            slippage_cost=data["slippage_cost"],
            slippage_pct=data["slippage_pct"],
            funding_cost=data["funding_cost"],
            funding_rate=data["funding_rate"],
            total_cost=data["total_cost"],
            order_id=data["order_id"],
            fill_id=data["fill_id"],
            position_side=data.get("position_side", 1),
        )


class TradeCostCalculator:
    """
    交易成本计算器
    实现实盘手续费/滑点/资金费率统一核算
    """

    def __init__(self, config: dict[str, Any] | None = None):
        """
        初始化交易成本计算器

        Args:
            config: 配置字典，包含手续费率、资金费率等
        """
        self.config = config or {}

        # 手续费率配置
        self.maker_fee = self.config.get("maker_fee", 0.0002)
        self.taker_fee = self.config.get("taker_fee", 0.0005)

        # 资金费率配置
        self.funding_rate = self.config.get("funding_rate", 0.0)
        self.funding_interval_hours = self.config.get("funding_interval_hours", 8.0)

        # 成本模型
        self.cost_model = UnifiedCostModel(
            maker_fee=self.maker_fee,
            taker_fee=self.taker_fee,
            slippage_type="simple",
            slippage_param=0.0,
            enable_impact_cost=False,
            funding_rate=self.funding_rate,
            funding_interval_hours=self.funding_interval_hours,
            environment="live",
        )

        # 成本分解记录
        self.cost_breakdowns: list[TradeCostBreakdown] = []

        # 输出文件路径
        self.output_path = self.config.get("output_path", "trade_cost_breakdown.json")

    def calculate_trade_cost(
        self, fill_data: dict[str, Any], order_data: dict[str, Any]
    ) -> TradeCostBreakdown:
        """
        计算单笔交易成本

        Args:
            fill_data: 成交数据
            order_data: 订单数据

        Returns:
            TradeCostBreakdown: 交易成本分解
        """
        # 提取关键数据
        symbol = fill_data["symbol"]
        side = fill_data["side"]
        amount = fill_data["fillAmount"]
        filled_price = fill_data["fillPrice"]
        order_id = fill_data["clientOrderId"]
        fill_id = fill_data.get("fillId", f"fill_{int(time.time())}_{order_id}")

        # 从订单数据获取触发价和保护价
        trigger_price = order_data.get("price", filled_price)
        protection_price = order_data.get("protection_price", trigger_price)

        # 判断是否为taker单
        is_taker = order_data.get("is_taker", True)  # 默认taker

        # 计算名义价值
        notional = amount * filled_price

        # 计算手续费
        fee = self.cost_model.calculate_fee(notional, is_taker)
        fee_rate = self.taker_fee if is_taker else self.maker_fee

        # 计算滑点成本（基于触发价）
        if side == "buy":
            # 买入滑点：成交价超过触发价的部分
            slippage_cost = (filled_price - trigger_price) * amount
        else:
            # 卖出滑点：触发价超过成交价的部分
            slippage_cost = (trigger_price - filled_price) * amount

        # 计算滑点百分比
        if trigger_price > 0:
            slippage_pct = abs(slippage_cost / (trigger_price * amount))
        else:
            slippage_pct = 0.0

        # 计算资金费率成本（默认当前资金费率，实际应从API获取）
        # 这里简化处理，实际应从交易所API获取当前资金费率
        funding_cost = 0.0  # 首次成交时资金费率成本为0，后续持仓期间计算
        funding_rate = self.funding_rate

        # 总成本
        total_cost = fee + max(slippage_cost, 0)  # 只计算不利滑点

        # 确定仓位方向
        position_side = 1 if side == "buy" else -1

        # 生成交易ID
        trade_id = f"trade_{int(time.time())}_{order_id}"

        # 创建成本分解
        cost_breakdown = TradeCostBreakdown(
            trade_id=trade_id,
            symbol=symbol,
            timestamp=fill_data.get("timestamp", time.time()),
            side=side,
            amount=amount,
            trigger_price=trigger_price,
            protection_price=protection_price,
            filled_price=filled_price,
            is_taker=is_taker,
            fee=fee,
            fee_rate=fee_rate,
            slippage_cost=slippage_cost,
            slippage_pct=slippage_pct,
            funding_cost=funding_cost,
            funding_rate=funding_rate,
            total_cost=total_cost,
            order_id=order_id,
            fill_id=fill_id,
            position_side=position_side,
        )

        # 保存成本分解
        self.cost_breakdowns.append(cost_breakdown)

        return cost_breakdown

    def calculate_funding_cost(self, position_data: dict[str, Any], hours_held: float) -> float:
        """
        计算资金费率成本

        Args:
            position_data: 持仓数据
            hours_held: 持有时间（小时）

        Returns:
            float: 资金费率成本
        """
        symbol = position_data["symbol"]
        amount = position_data["total_amount"]
        avg_price = position_data["avg_price"]
        position_side = 1 if amount > 0 else -1

        # 计算名义价值
        notional = abs(amount) * avg_price

        # 使用统一成本模型计算资金费率
        funding_cost = self.cost_model.calculate_funding_cost(
            notional=notional, hours_held=hours_held, position_side=position_side
        )

        return funding_cost

    def save_cost_breakdowns(self, output_path: str | None = None) -> None:
        """
        保存成本分解到文件

        Args:
            output_path: 输出文件路径，默认使用初始化时的路径
        """
        save_path = output_path or self.output_path

        # 确保目录存在
        dir_name = os.path.dirname(save_path)
        if dir_name:
            os.makedirs(dir_name, exist_ok=True)

        # 转换为字典格式
        cost_data = {
            "generated_at": time.time(),
            "total_trades": len(self.cost_breakdowns),
            "total_cost": sum(cb.total_cost for cb in self.cost_breakdowns),
            "total_fee": sum(cb.fee for cb in self.cost_breakdowns),
            "total_slippage": sum(cb.slippage_cost for cb in self.cost_breakdowns),
            "total_funding": sum(cb.funding_cost for cb in self.cost_breakdowns),
            "cost_breakdowns": [cb.to_dict() for cb in self.cost_breakdowns],
        }

        try:
            with open(save_path, "w") as f:
                json.dump(cost_data, f, indent=2, ensure_ascii=False)
            logger.info(f"交易成本分解已保存到: {save_path}")
        except Exception as e:
            logger.error(f"保存交易成本分解失败: {e}")

    def load_cost_breakdowns(self, input_path: str | None = None) -> None:
        """
        从文件加载成本分解

        Args:
            input_path: 输入文件路径，默认使用初始化时的路径
        """
        load_path = input_path or self.output_path

        try:
            with open(load_path) as f:
                cost_data = json.load(f)

            # 加载成本分解
            self.cost_breakdowns = [
                TradeCostBreakdown.from_dict(cb) for cb in cost_data.get("cost_breakdowns", [])
            ]

            logger.info(f"成功加载 {len(self.cost_breakdowns)} 笔交易成本分解")
        except Exception as e:
            logger.error(f"加载交易成本分解失败: {e}")

    def get_cost_summary(self, symbol: str | None = None) -> dict[str, Any]:
        """
        获取成本汇总

        Args:
            symbol: 可选，指定交易对，默认所有交易对

        Returns:
            Dict[str, Any]: 成本汇总
        """
        # 过滤指定交易对
        filtered_breakdowns = self.cost_breakdowns
        if symbol:
            filtered_breakdowns = [cb for cb in self.cost_breakdowns if cb.symbol == symbol]

        total_trades = len(filtered_breakdowns)
        total_cost = sum(cb.total_cost for cb in filtered_breakdowns)
        total_fee = sum(cb.fee for cb in filtered_breakdowns)
        total_slippage = sum(cb.slippage_cost for cb in filtered_breakdowns)
        total_funding = sum(cb.funding_cost for cb in filtered_breakdowns)

        # 计算平均滑点率
        avg_slippage_pct = (
            sum(cb.slippage_pct for cb in filtered_breakdowns) / total_trades
            if total_trades > 0
            else 0.0
        )

        return {
            "symbol": symbol or "all",
            "total_trades": total_trades,
            "total_cost": total_cost,
            "total_fee": total_fee,
            "total_slippage": total_slippage,
            "total_funding": total_funding,
            "avg_slippage_pct": avg_slippage_pct,
            "generated_at": time.time(),
        }

    def update_trade_records(self, trade_ledger: Any) -> None:
        """
        更新交易记录，添加成本分解字段

        Args:
            trade_ledger: 交易账本实例
        """
        # 遍历所有成本分解
        for cost_breakdown in self.cost_breakdowns:
            # 查找对应的成交记录
            fill_data = trade_ledger.current_state["fills"].get(cost_breakdown.fill_id)
            if fill_data:
                # 添加成本分解到成交记录
                fill_data["cost_breakdown"] = cost_breakdown.to_dict()

                # 更新订单数据
                order_data = trade_ledger.current_state["orders"].get(cost_breakdown.order_id)
                if order_data:
                    if "cost_breakdowns" not in order_data:
                        order_data["cost_breakdowns"] = []
                    order_data["cost_breakdowns"].append(cost_breakdown.to_dict())

        logger.info(f"已更新 {len(self.cost_breakdowns)} 笔交易记录的成本分解")


# 示例使用
if __name__ == "__main__":
    # 配置
    config = {
        "maker_fee": 0.0002,
        "taker_fee": 0.0005,
        "funding_rate": 0.0001,
        "output_path": "trade_cost_breakdown.json",
    }

    # 创建成本计算器实例
    cost_calculator = TradeCostCalculator(config)

    # 模拟订单数据
    test_order = {
        "clientOrderId": "test_order_123",
        "symbol": "ETH-USDT",
        "side": "buy",
        "price": 2000.0,
        "amount": 1.0,
        "is_taker": True,
        "status": "FILLED",
    }

    # 模拟成交数据
    test_fill = {
        "symbol": "ETH-USDT",
        "side": "buy",
        "fillAmount": 1.0,
        "fillPrice": 2001.0,
        "clientOrderId": "test_order_123",
    }

    # 计算成本
    cost_breakdown = cost_calculator.calculate_trade_cost(test_fill, test_order)
    print("成本分解:")
    print(json.dumps(cost_breakdown.to_dict(), indent=2, ensure_ascii=False))

    # 保存成本分解
    cost_calculator.save_cost_breakdowns()

    # 获取成本汇总
    summary = cost_calculator.get_cost_summary()
    print("\n成本汇总:")
    print(json.dumps(summary, indent=2, ensure_ascii=False))

    # 加载成本分解（测试持久化）
    cost_calculator.load_cost_breakdowns()
    print(f"\n加载后成本分解数量: {len(cost_calculator.cost_breakdowns)}")
