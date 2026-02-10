#!/usr/bin/env python3
"""
监控和日志模块
实现策略运行的实时监控和日志记录
"""

import json
import logging
from datetime import datetime, timedelta
from typing import Any

import pandas as pd

# 配置日志
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class StrategyMonitor:
    """
    策略监控器，实现实时监控和日志记录
    """

    def __init__(self, config: dict[str, Any]):
        """
        初始化监控器

        Args:
            config: 监控配置
        """
        self.config = config

        # 监控数据
        self.strategy_stats = {
            "start_time": datetime.now(),
            "total_trades": 0,
            "winning_trades": 0,
            "losing_trades": 0,
            "total_pnl": 0.0,
            "max_drawdown": 0.0,
            "current_position": 0.0,
            "current_balance": 0.0,
            "last_signal_time": None,
            "last_order_time": None,
            "last_pnl_update_time": None,
        }

        # 交易历史记录
        self.trade_history = []

        # 信号历史记录
        self.signal_history = []

        # 订单历史记录
        self.order_history = []

        # 风险指标历史记录
        self.risk_history = []

        logger.info("策略监控模块初始化完成")

    def log_signal(
        self,
        timestamp: datetime,
        symbol: str,
        signal: float,
        signal_type: str,
        factor_values: dict[str, float] = None,
    ):
        """
        记录交易信号

        Args:
            timestamp: 信号时间
            symbol: 交易对
            signal: 信号值
            signal_type: 信号类型
            factor_values: 因子值
        """
        signal_record = {
            "timestamp": timestamp,
            "symbol": symbol,
            "signal": signal,
            "signal_type": signal_type,
            "factor_values": factor_values or {},
        }

        self.signal_history.append(signal_record)
        self.strategy_stats["last_signal_time"] = timestamp

        logger.info(f"信号记录: {symbol} {signal_type} 信号值={signal:.4f}")

    def log_order(
        self,
        order_id: str,
        timestamp: datetime,
        symbol: str,
        side: str,
        order_type: str,
        amount: float,
        price: float,
        status: str,
    ):
        """
        记录订单信息

        Args:
            order_id: 订单ID
            timestamp: 订单时间
            symbol: 交易对
            side: 买卖方向
            order_type: 订单类型
            amount: 交易数量
            price: 交易价格
            status: 订单状态
        """
        order_record = {
            "order_id": order_id,
            "timestamp": timestamp,
            "symbol": symbol,
            "side": side,
            "order_type": order_type,
            "amount": amount,
            "price": price,
            "status": status,
            "filled_amount": 0.0,
            "filled_price": 0.0,
            "pnl": 0.0,
            "closed": False,
        }

        self.order_history.append(order_record)
        self.strategy_stats["last_order_time"] = timestamp

        logger.info(
            f"订单记录: {order_id} {symbol} {side} {order_type} {amount}@{price} 状态={status}"
        )

    def update_order_status(
        self,
        order_id: str,
        status: str,
        filled_amount: float = 0.0,
        filled_price: float = 0.0,
        pnl: float = 0.0,
    ):
        """
        更新订单状态

        Args:
            order_id: 订单ID
            status: 新状态
            filled_amount: 已成交数量
            filled_price: 成交价格
            pnl: 盈亏
        """
        for order in self.order_history:
            if order["order_id"] == order_id:
                order["status"] = status
                order["filled_amount"] = filled_amount
                order["filled_price"] = filled_price
                order["pnl"] = pnl
                order["closed"] = status in ["filled", "cancelled", "rejected"]

                if order["closed"] and filled_amount > 0:
                    # 更新策略统计
                    self.strategy_stats["total_trades"] += 1
                    self.strategy_stats["total_pnl"] += pnl
                    self.strategy_stats["last_pnl_update_time"] = datetime.now()

                    if pnl > 0:
                        self.strategy_stats["winning_trades"] += 1
                    elif pnl < 0:
                        self.strategy_stats["losing_trades"] += 1

                    # 记录交易历史
                    trade_record = {
                        "trade_id": order_id,
                        "timestamp": order["timestamp"],
                        "symbol": order["symbol"],
                        "side": order["side"],
                        "order_type": order["order_type"],
                        "amount": order["amount"],
                        "price": order["price"],
                        "filled_amount": filled_amount,
                        "filled_price": filled_price,
                        "pnl": pnl,
                        "status": status,
                    }
                    self.trade_history.append(trade_record)

                logger.info(
                    f"订单状态更新: {order_id} 状态={status} 已成交={filled_amount:.6f}@{filled_price:.4f} PnL={pnl:.4f}"
                )
                break

    def update_risk_metrics(self, risk_metrics: dict[str, Any]):
        """
        更新风险指标

        Args:
            risk_metrics: 风险指标
        """
        risk_record = {"timestamp": datetime.now(), **risk_metrics}

        self.risk_history.append(risk_record)

        logger.info(f"风险指标更新: {json.dumps(risk_metrics, default=str)}")

    def update_position(self, balance: float, position: float):
        """
        更新账户余额和持仓信息

        Args:
            balance: 账户余额
            position: 持仓金额
        """
        self.strategy_stats["current_balance"] = balance
        self.strategy_stats["current_position"] = position

        logger.info(f"账户更新: 余额={balance:.2f} 持仓={position:.2f}")

    def get_strategy_status(self) -> dict[str, Any]:
        """
        获取策略当前状态

        Returns:
            dict: 策略状态信息
        """
        # 计算策略运行时间
        runtime = datetime.now() - self.strategy_stats["start_time"]

        # 计算胜率
        win_rate = 0.0
        if self.strategy_stats["total_trades"] > 0:
            win_rate = self.strategy_stats["winning_trades"] / self.strategy_stats["total_trades"]

        status = {
            "runtime": str(runtime),
            "total_trades": self.strategy_stats["total_trades"],
            "winning_trades": self.strategy_stats["winning_trades"],
            "losing_trades": self.strategy_stats["losing_trades"],
            "win_rate": win_rate,
            "total_pnl": self.strategy_stats["total_pnl"],
            "avg_trade_pnl": self.strategy_stats["total_pnl"] / self.strategy_stats["total_trades"]
            if self.strategy_stats["total_trades"] > 0
            else 0.0,
            "current_balance": self.strategy_stats["current_balance"],
            "current_position": self.strategy_stats["current_position"],
            "last_signal_time": self.strategy_stats["last_signal_time"],
            "last_order_time": self.strategy_stats["last_order_time"],
            "last_pnl_update_time": self.strategy_stats["last_pnl_update_time"],
        }

        return status

    def generate_trade_report(
        self, start_time: datetime | None = None, end_time: datetime | None = None
    ) -> pd.DataFrame:
        """
        生成交易报告

        Args:
            start_time: 开始时间
            end_time: 结束时间

        Returns:
            pd.DataFrame: 交易报告
        """
        # 筛选时间范围内的交易
        filtered_trades = self.trade_history
        if start_time:
            filtered_trades = [t for t in filtered_trades if t["timestamp"] >= start_time]
        if end_time:
            filtered_trades = [t for t in filtered_trades if t["timestamp"] <= end_time]

        # 转换为DataFrame
        df = pd.DataFrame(filtered_trades)

        if not df.empty:
            df["timestamp"] = pd.to_datetime(df["timestamp"])
            df = df.set_index("timestamp")

        return df

    def generate_signal_report(
        self, start_time: datetime | None = None, end_time: datetime | None = None
    ) -> pd.DataFrame:
        """
        生成信号报告

        Args:
            start_time: 开始时间
            end_time: 结束时间

        Returns:
            pd.DataFrame: 信号报告
        """
        # 筛选时间范围内的信号
        filtered_signals = self.signal_history
        if start_time:
            filtered_signals = [s for s in filtered_signals if s["timestamp"] >= start_time]
        if end_time:
            filtered_signals = [s for s in filtered_signals if s["timestamp"] <= end_time]

        # 转换为DataFrame
        df = pd.DataFrame(filtered_signals)

        if not df.empty:
            df["timestamp"] = pd.to_datetime(df["timestamp"])
            df = df.set_index("timestamp")

        return df

    def generate_risk_report(
        self, start_time: datetime | None = None, end_time: datetime | None = None
    ) -> pd.DataFrame:
        """
        生成风险报告

        Args:
            start_time: 开始时间
            end_time: 结束时间

        Returns:
            pd.DataFrame: 风险报告
        """
        # 筛选时间范围内的风险指标
        filtered_risk = self.risk_history
        if start_time:
            filtered_risk = [r for r in filtered_risk if r["timestamp"] >= start_time]
        if end_time:
            filtered_risk = [r for r in filtered_risk if r["timestamp"] <= end_time]

        # 转换为DataFrame
        df = pd.DataFrame(filtered_risk)

        if not df.empty:
            df["timestamp"] = pd.to_datetime(df["timestamp"])
            df = df.set_index("timestamp")

        return df

    def save_trade_history(self, file_path: str):
        """
        保存交易历史记录

        Args:
            file_path: 文件路径
        """
        with open(file_path, "w") as f:
            json.dump(self.trade_history, f, default=str, indent=2)

        logger.info(f"交易历史记录已保存到 {file_path}")

    def save_signal_history(self, file_path: str):
        """
        保存信号历史记录

        Args:
            file_path: 文件路径
        """
        with open(file_path, "w") as f:
            json.dump(self.signal_history, f, default=str, indent=2)

        logger.info(f"信号历史记录已保存到 {file_path}")

    def save_order_history(self, file_path: str):
        """
        保存订单历史记录

        Args:
            file_path: 文件路径
        """
        with open(file_path, "w") as f:
            json.dump(self.order_history, f, default=str, indent=2)

        logger.info(f"订单历史记录已保存到 {file_path}")

    def print_strategy_summary(self):
        """
        打印策略运行摘要
        """
        status = self.get_strategy_status()

        logger.info("=" * 50)
        logger.info("策略运行摘要")
        logger.info("=" * 50)
        logger.info(f"运行时间: {status['runtime']}")
        logger.info(f"总交易次数: {status['total_trades']}")
        logger.info(f"盈利交易: {status['winning_trades']}")
        logger.info(f"亏损交易: {status['losing_trades']}")
        logger.info(f"胜率: {status['win_rate']:.2%}")
        logger.info(f"总盈亏: {status['total_pnl']:.4f}")
        logger.info(f"平均每笔盈亏: {status['avg_trade_pnl']:.4f}")
        logger.info(f"当前余额: {status['current_balance']:.2f}")
        logger.info(f"当前持仓: {status['current_position']:.2f}")
        logger.info(f"最后信号时间: {status['last_signal_time']}")
        logger.info(f"最后订单时间: {status['last_order_time']}")
        logger.info(f"最后盈亏更新时间: {status['last_pnl_update_time']}")
        logger.info("=" * 50)

    def check_alert_conditions(self) -> list[str]:
        """
        检查告警条件

        Returns:
            list: 告警信息列表
        """
        alerts = []
        status = self.get_strategy_status()

        # 检查长时间无信号
        if status["last_signal_time"]:
            time_since_last_signal = datetime.now() - status["last_signal_time"]
            if time_since_last_signal > timedelta(hours=1):
                alerts.append(f"长时间无信号: {time_since_last_signal}")

        # 检查长时间无订单
        if status["last_order_time"]:
            time_since_last_order = datetime.now() - status["last_order_time"]
            if time_since_last_order > timedelta(days=1):
                alerts.append(f"长时间无订单: {time_since_last_order}")

        # 检查亏损过大
        if status["total_pnl"] < -1000:  # 示例阈值
            alerts.append(f"总亏损过大: {status['total_pnl']:.2f}")

        # 检查胜率过低
        if status["total_trades"] > 10 and status["win_rate"] < 0.3:
            alerts.append(f"胜率过低: {status['win_rate']:.2%}")

        return alerts
