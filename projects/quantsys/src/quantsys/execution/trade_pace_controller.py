#!/usr/bin/env python3
"""
实盘交易节奏控制器
实现周频1-3次的交易节奏控制，避免过度交易
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


class TradePaceController:
    """
    实盘交易节奏控制器
    统计过去7天真实开仓次数，超过3次进入COOLDOWN状态
    """

    def __init__(self, config: dict[str, Any] = None):
        """
        初始化交易节奏控制器

        Args:
            config: 配置信息
        """
        self.config = config or {}

        # 配置参数
        self.lookback_days = self.config.get("lookback_days", 7)  # 统计窗口，默认7天
        self.max_trades = self.config.get("max_trades", 3)  # 最大交易次数，默认3次
        self.min_trades = self.config.get("min_trades", 1)  # 最小交易次数，默认1次

        # 交易记录文件路径
        self.trade_record_path = self.config.get(
            "trade_record_path", os.path.join("data", "trade_records.json")
        )

        # 状态文件路径
        self.state_file_path = self.config.get(
            "state_file_path", os.path.join("reports", "pace_state.json")
        )

        # 确保目录存在
        os.makedirs(os.path.dirname(self.trade_record_path), exist_ok=True)
        os.makedirs(os.path.dirname(self.state_file_path), exist_ok=True)

        # 初始化交易记录
        self.trade_records = self._load_trade_records()

        logger.info("交易节奏控制器初始化完成")

    def _load_trade_records(self) -> list:
        """
        加载交易记录

        Returns:
            list: 交易记录列表
        """
        try:
            if os.path.exists(self.trade_record_path):
                with open(self.trade_record_path, encoding="utf-8") as f:
                    return json.load(f)
        except (OSError, json.JSONDecodeError) as e:
            logger.error(f"加载交易记录失败: {e}")

        # 返回空列表作为默认值
        return []

    def _save_trade_records(self) -> None:
        """
        保存交易记录
        """
        try:
            with open(self.trade_record_path, "w", encoding="utf-8") as f:
                json.dump(self.trade_records, f, indent=2, ensure_ascii=False)
        except OSError as e:
            logger.error(f"保存交易记录失败: {e}")

    def add_trade_record(self, trade_info: dict[str, Any]) -> None:
        """
        添加交易记录

        Args:
            trade_info: 交易信息，包含开仓时间等
        """
        # 确保包含时间戳
        if "timestamp" not in trade_info:
            trade_info["timestamp"] = datetime.utcnow().isoformat() + "Z"

        # 确保包含开仓时间
        if "open_time" not in trade_info:
            trade_info["open_time"] = datetime.utcnow().isoformat() + "Z"

        # 添加到交易记录
        self.trade_records.append(trade_info)

        # 保存到文件
        self._save_trade_records()

        logger.info(f"添加交易记录: {trade_info}")

    def _get_recent_trades_count(self) -> int:
        """
        获取过去lookback_days天的开仓次数

        Returns:
            int: 开仓次数
        """
        # 计算时间窗口
        now = datetime.utcnow()
        window_start = now - timedelta(days=self.lookback_days)

        # 统计开仓次数
        count = 0
        for trade in self.trade_records:
            try:
                # 解析开仓时间
                open_time_str = trade.get("open_time", trade.get("timestamp", ""))
                if open_time_str:
                    open_time = datetime.fromisoformat(open_time_str.replace("Z", ""))
                    if open_time >= window_start:
                        count += 1
            except ValueError as e:
                logger.error(f"解析交易时间失败: {e}")
                continue

        return count

    def check_pace(self) -> dict[str, Any]:
        """
        检查交易节奏，生成状态报告

        Returns:
            Dict[str, Any]: 节奏状态报告
        """
        # 获取最近交易次数
        recent_count = self._get_recent_trades_count()

        # 计算时间窗口
        now = datetime.utcnow()
        window_start = now - timedelta(days=self.lookback_days)

        # 初始化状态
        state = {
            "count": recent_count,
            "window": {
                "start": window_start.isoformat() + "Z",
                "end": now.isoformat() + "Z",
                "days": self.lookback_days,
            },
            "cooldown_until": None,
            "reason": None,
            "timestamp": now.isoformat() + "Z",
            "action": "ALLOW",  # 默认允许
            "message": "交易节奏正常",
        }

        # 检查是否超过最大交易次数
        if recent_count >= self.max_trades:
            # 计算冷却结束时间（窗口结束时间）
            state["cooldown_until"] = window_start.isoformat() + "Z"
            state["reason"] = (
                f"过去{self.lookback_days}天开仓次数({recent_count})已达上限({self.max_trades})"
            )
            state["action"] = "COOLDOWN"
            state["message"] = (
                f"已进入冷却期，只允许平仓，不允许新开仓。冷却结束时间: {state['cooldown_until']}"
            )
        elif recent_count < self.min_trades:
            # 低于最小交易次数，仅提示
            state["reason"] = (
                f"过去{self.lookback_days}天开仓次数({recent_count})低于建议值({self.min_trades})"
            )
            state["action"] = "ALLOW"
            state["message"] = "交易次数偏少，建议增加交易频率"

        # 保存状态到文件
        self._save_pace_state(state)

        return state

    def _save_pace_state(self, state: dict[str, Any]) -> None:
        """
        保存节奏状态到文件

        Args:
            state: 节奏状态
        """
        try:
            with open(self.state_file_path, "w", encoding="utf-8") as f:
                json.dump(state, f, indent=2, ensure_ascii=False)
            logger.info(f"节奏状态已保存到 {self.state_file_path}")
        except OSError as e:
            logger.error(f"保存节奏状态失败: {e}")

    def is_new_position_allowed(self) -> bool:
        """
        检查是否允许新开仓

        Returns:
            bool: 是否允许新开仓
        """
        state = self.check_pace()
        return state["action"] != "COOLDOWN"

    def get_pace_state(self) -> dict[str, Any]:
        """
        获取当前节奏状态

        Returns:
            Dict[str, Any]: 节奏状态
        """
        # 先检查状态文件是否存在
        if os.path.exists(self.state_file_path):
            try:
                with open(self.state_file_path, encoding="utf-8") as f:
                    return json.load(f)
            except (OSError, json.JSONDecodeError) as e:
                logger.error(f"加载节奏状态失败: {e}")

        # 如果文件不存在或加载失败，重新计算
        return self.check_pace()

    def reset_trade_records(self) -> None:
        """
        重置交易记录
        """
        self.trade_records = []
        self._save_trade_records()
        logger.info("交易记录已重置")


# 主函数，用于测试
def main():
    """
    主函数，用于测试
    """
    # 初始化控制器
    controller = TradePaceController()

    # 测试添加交易记录
    controller.add_trade_record(
        {"symbol": "ETH-USDT", "side": "buy", "amount": 0.01, "price": 2000, "type": "limit"}
    )

    # 测试检查节奏
    state = controller.check_pace()
    print(f"节奏状态: {json.dumps(state, indent=2, ensure_ascii=False)}")

    # 测试是否允许新开仓
    allowed = controller.is_new_position_allowed()
    print(f"是否允许新开仓: {allowed}")

    # 测试获取节奏状态
    saved_state = controller.get_pace_state()
    print(f"保存的节奏状态: {json.dumps(saved_state, indent=2, ensure_ascii=False)}")


if __name__ == "__main__":
    main()
