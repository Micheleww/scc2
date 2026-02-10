#!/usr/bin/env python3
"""
持仓管理器
功能：
- 持仓最长3天：到期强制退出
- 触发止损/止盈/反向信号时退出
- 退出后必须对账确认“仓位归零/订单清空”，否则SAFE_STOP
- 输出position_lifecycle_report.json
"""

import json
import logging
import os
from datetime import datetime, timedelta
from typing import Any

# 配置日志
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class PositionManager:
    """
    持仓管理器类
    负责管理持仓的整个生命周期：开仓→持有→退出→对账
    """

    def __init__(self, config: dict[str, Any] = None):
        """
        初始化持仓管理器

        Args:
            config: 配置信息
        """
        self.config = config or {}

        # 持仓最长时间（默认3天）
        self.max_hold_time = timedelta(days=self.config.get("max_hold_days", 3))

        # 持仓记录
        self.positions = {}

        # 持仓生命周期报告
        self.lifecycle_report = {
            "version": "1.0",
            "generated_at": datetime.now().isoformat(),
            "position_events": [],
        }

        logger.info("PositionManager初始化完成")

    def open_position(
        self,
        symbol: str,
        side: str,
        price: float,
        quantity: float,
        stop_loss: float,
        take_profit: float,
        reason: str,
    ) -> str:
        """
        开仓

        Args:
            symbol: 交易对
            side: 方向（long/short）
            price: 开仓价格
            quantity: 开仓数量
            stop_loss: 止损价
            take_profit: 止盈价
            reason: 开仓理由

        Returns:
            str: 持仓ID
        """
        # 生成持仓ID
        position_id = f"pos_{datetime.now().strftime('%Y%m%d%H%M%S')}_{symbol}_{side[:3]}"

        # 记录开仓信息
        position = {
            "position_id": position_id,
            "symbol": symbol,
            "side": side,
            "quantity": quantity,
            "entry_price": price,
            "stop_loss": stop_loss,
            "take_profit": take_profit,
            "entry_time": datetime.now(),
            "status": "open",
            "reason": reason,
            "exit_info": None,
        }

        self.positions[position_id] = position

        # 记录到生命周期报告
        self._add_position_event(
            position_id,
            "opened",
            reason,
            {
                "symbol": symbol,
                "side": side,
                "price": price,
                "quantity": quantity,
                "stop_loss": stop_loss,
                "take_profit": take_profit,
            },
        )

        logger.info(f"开仓成功: {position_id}, {symbol}, {side}, {price}, {quantity}")
        return position_id

    def check_positions(self, market_data: dict[str, Any]) -> list[str]:
        """
        检查所有持仓，判断是否需要退出

        Args:
            market_data: 市场数据，包含各交易对的最新价格

        Returns:
            List[str]: 需要退出的持仓ID列表
        """
        positions_to_exit = []

        for position_id, position in self.positions.items():
            if position["status"] != "open":
                continue

            symbol = position["symbol"]
            side = position["side"]
            current_price = market_data.get(symbol, {}).get("price", 0)

            if current_price == 0:
                logger.warning(f"无法获取{symbol}的最新价格，跳过持仓检查")
                continue

            # 1. 检查持仓时间是否超过最长限制
            if datetime.now() - position["entry_time"] > self.max_hold_time:
                positions_to_exit.append(position_id)
                logger.info(f"持仓到期: {position_id}, 持有时间超过{self.max_hold_time.days}天")
                continue

            # 2. 检查是否触发止损
            if side == "long":
                if current_price <= position["stop_loss"]:
                    positions_to_exit.append(position_id)
                    logger.info(
                        f"触发止损: {position_id}, 当前价格: {current_price} <= 止损价: {position['stop_loss']}"
                    )
                    continue
            else:  # short
                if current_price >= position["stop_loss"]:
                    positions_to_exit.append(position_id)
                    logger.info(
                        f"触发止损: {position_id}, 当前价格: {current_price} >= 止损价: {position['stop_loss']}"
                    )
                    continue

            # 3. 检查是否触发止盈
            if side == "long":
                if current_price >= position["take_profit"]:
                    positions_to_exit.append(position_id)
                    logger.info(
                        f"触发止盈: {position_id}, 当前价格: {current_price} >= 止盈价: {position['take_profit']}"
                    )
                    continue
            else:  # short
                if current_price <= position["take_profit"]:
                    positions_to_exit.append(position_id)
                    logger.info(
                        f"触发止盈: {position_id}, 当前价格: {current_price} <= 止盈价: {position['take_profit']}"
                    )
                    continue

        return positions_to_exit

    def exit_position(self, position_id: str, exit_price: float, reason: str) -> bool:
        """
        退出持仓

        Args:
            position_id: 持仓ID
            exit_price: 平仓价格
            reason: 平仓理由

        Returns:
            bool: 是否成功退出
        """
        if position_id not in self.positions:
            logger.error(f"持仓不存在: {position_id}")
            return False

        position = self.positions[position_id]
        if position["status"] != "open":
            logger.error(f"持仓已关闭: {position_id}")
            return False

        # 更新持仓状态
        position["status"] = "closed"
        position["exit_info"] = {
            "exit_price": exit_price,
            "exit_time": datetime.now(),
            "exit_reason": reason,
            "duration": (datetime.now() - position["entry_time"]).total_seconds()
            / 3600,  # 持仓时长（小时）
            "pnl": self._calculate_pnl(position, exit_price),
        }

        # 记录到生命周期报告
        self._add_position_event(
            position_id,
            "closed",
            reason,
            {
                "exit_price": exit_price,
                "duration_hours": position["exit_info"]["duration"],
                "pnl": position["exit_info"]["pnl"],
            },
        )

        logger.info(f"平仓成功: {position_id}, 价格: {exit_price}, 理由: {reason}")
        return True

    def reconcile_position(self, position_id: str, order_manager: Any) -> bool:
        """
        对账，确认仓位归零/订单清空

        Args:
            position_id: 持仓ID
            order_manager: 订单管理器实例，用于查询当前仓位和订单状态

        Returns:
            bool: 对账是否成功
        """
        if position_id not in self.positions:
            logger.error(f"持仓不存在: {position_id}")
            return False

        position = self.positions[position_id]
        symbol = position["symbol"]

        # 查询当前仓位
        current_position = order_manager.get_position(symbol)

        # 查询当前订单
        current_orders = order_manager.get_orders(symbol)

        # 检查仓位是否归零
        position_zero = abs(current_position) < 0.0001  # 允许微小误差

        # 检查订单是否清空
        orders_empty = len(current_orders) == 0

        if position_zero and orders_empty:
            # 对账成功
            self._add_position_event(
                position_id,
                "reconciled",
                "仓位归零且订单清空",
                {"current_position": current_position, "current_orders": len(current_orders)},
            )
            logger.info(f"对账成功: {position_id}, 仓位归零，订单清空")
            return True
        else:
            # 对账失败，执行SAFE_STOP
            self._add_position_event(
                position_id,
                "safe_stop",
                "对账失败，执行安全停止",
                {
                    "current_position": current_position,
                    "current_orders": len(current_orders),
                    "position_zero": position_zero,
                    "orders_empty": orders_empty,
                },
            )
            logger.error(
                f"对账失败: {position_id}, 当前仓位: {current_position}, 当前订单数: {len(current_orders)}"
            )

            # 执行安全停止操作
            self._safe_stop_position(position_id, order_manager)
            return False

    def _safe_stop_position(self, position_id: str, order_manager: Any):
        """
        执行安全停止操作

        Args:
            position_id: 持仓ID
            order_manager: 订单管理器实例
        """
        position = self.positions[position_id]
        symbol = position["symbol"]

        # 取消所有未成交订单
        order_manager.cancel_all_orders(symbol)
        logger.info(f"已取消{symbol}的所有未成交订单")

        # 平掉剩余仓位
        current_position = order_manager.get_position(symbol)
        if abs(current_position) > 0.0001:  # 还有仓位
            exit_side = "sell" if current_position > 0 else "buy"
            order_manager.place_market_order(symbol, exit_side, abs(current_position))
            logger.info(f"已平掉{symbol}的剩余仓位: {current_position}")

    def _calculate_pnl(self, position: dict[str, Any], exit_price: float) -> float:
        """
        计算盈亏

        Args:
            position: 持仓信息
            exit_price: 平仓价格

        Returns:
            float: 盈亏金额
        """
        if position["side"] == "long":
            return (exit_price - position["entry_price"]) * position["quantity"]
        else:  # short
            return (position["entry_price"] - exit_price) * position["quantity"]

    def _add_position_event(
        self, position_id: str, event_type: str, reason: str, details: dict[str, Any]
    ):
        """
        添加持仓事件到生命周期报告

        Args:
            position_id: 持仓ID
            event_type: 事件类型（opened/closed/reconciled/safe_stop）
            reason: 事件理由
            details: 事件详情
        """
        event = {
            "position_id": position_id,
            "event_type": event_type,
            "event_time": datetime.now().isoformat(),
            "reason": reason,
            "details": details,
        }

        self.lifecycle_report["position_events"].append(event)

    def generate_report(self, output_path: str = None) -> dict[str, Any]:
        """
        生成持仓生命周期报告

        Args:
            output_path: 报告输出路径，默认输出到data/position_lifecycle_report.json

        Returns:
            Dict[str, Any]: 持仓生命周期报告
        """
        # 更新报告生成时间
        self.lifecycle_report["generated_at"] = datetime.now().isoformat()

        # 输出报告到文件
        if not output_path:
            output_path = os.path.join("d:/quantsys", "data", "position_lifecycle_report.json")

        # 确保输出目录存在
        os.makedirs(os.path.dirname(output_path), exist_ok=True)

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(self.lifecycle_report, f, indent=2, ensure_ascii=False)

        logger.info(f"持仓生命周期报告已生成: {output_path}")
        return self.lifecycle_report

    def get_open_positions(self) -> list[dict[str, Any]]:
        """
        获取所有开仓状态的持仓

        Returns:
            List[Dict[str, Any]]: 开仓状态的持仓列表
        """
        return [pos for pos in self.positions.values() if pos["status"] == "open"]

    def get_position(self, position_id: str) -> dict[str, Any] | None:
        """
        获取指定持仓信息

        Args:
            position_id: 持仓ID

        Returns:
            Optional[Dict[str, Any]]: 持仓信息，不存在则返回None
        """
        return self.positions.get(position_id)

    def get_positions_by_symbol(self, symbol: str) -> list[dict[str, Any]]:
        """
        获取指定交易对的所有持仓

        Args:
            symbol: 交易对

        Returns:
            List[Dict[str, Any]]: 持仓列表
        """
        return [pos for pos in self.positions.values() if pos["symbol"] == symbol]


# 示例用法
if __name__ == "__main__":
    # 测试PositionManager功能
    pm = PositionManager()

    # 开仓测试
    pos_id = pm.open_position(
        symbol="ETH-USDT",
        side="long",
        price=2500,
        quantity=1,
        stop_loss=2450,
        take_profit=2600,
        reason="突破信号",
    )

    # 模拟市场数据
    market_data = {"ETH-USDT": {"price": 2550}}

    # 检查持仓
    positions_to_exit = pm.check_positions(market_data)
    print(f"需要退出的持仓: {positions_to_exit}")

    # 平仓测试
    pm.exit_position(pos_id, 2550, "达到止盈")

    # 生成报告
    report = pm.generate_report()
    print(f"报告生成完成，共{len(report['position_events'])}个事件")
