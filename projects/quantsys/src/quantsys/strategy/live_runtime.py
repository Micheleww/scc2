#!/usr/bin/env python3
"""
实盘策略运行时
负责将现有策略接入Live环境，处理bar_close触发、信号生成和交易意图输出
"""

import json
import logging
import os
from datetime import datetime
from typing import Any

import pandas as pd

# 配置日志
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class LiveRuntime:
    """
    实盘策略运行时类
    负责：
    1. bar_close触发：计算因子→生成信号→输出交易意图
    2. 确保交易意图包含：方向、入场价/保护价、止损价、理由字段
    3. 无止损/不满足0.8%风险计算 → BLOCKED
    """

    def __init__(self, config: dict[str, Any]):
        """
        初始化实盘运行时

        Args:
            config: 配置信息
        """
        self.config = config
        self.strategy = None
        self.strategy_name = None

        # 加载策略
        self._load_strategy()

        logger.info("LiveRuntime初始化完成")

    def _load_strategy(self):
        """
        加载指定的策略
        """
        strategy_class_name = self.config.get("strategy_class")
        if not strategy_class_name:
            raise ValueError("策略类名未指定")

        # 根据策略类名动态导入策略
        try:
            # 先尝试从user_data/strategies目录加载
            import sys

            sys.path.insert(0, "d:/quantsys")

            # 为策略创建基本的config对象
            base_config = {
                "dry_run": True,
                "dry_run_wallet": 10000,
                "stake_currency": "USDT",
                "leverage": 1,
                "fee": 0.001,
                "exchange": {"name": "okx", "type": "okx", "key": "", "secret": "", "password": ""},
            }

            if strategy_class_name == "EthPerpTrendStrategy":
                from user_data.strategies.eth_perp_trend_strategy import (
                    EthPerpTrendStrategy,
                )

                self.strategy = EthPerpTrendStrategy(base_config)
            elif strategy_class_name == "EthPerpRangeStrategy":
                from user_data.strategies.eth_perp_range_strategy import (
                    EthPerpRangeStrategy,
                )

                self.strategy = EthPerpRangeStrategy(base_config)
            else:
                # 尝试从其他位置加载
                module_path, class_name = strategy_class_name.rsplit(".", 1)
                module = __import__(module_path, fromlist=[class_name])
                strategy_class = getattr(module, class_name)
                self.strategy = strategy_class(base_config)

            self.strategy_name = strategy_class_name
            logger.info(f"成功加载策略: {self.strategy_name}")
        except Exception as e:
            logger.error(f"加载策略失败: {e}")
            raise

    def on_bar_close(self, bar_data: pd.DataFrame) -> dict[str, Any]:
        """
        bar_close触发时执行

        Args:
            bar_data: K线数据

        Returns:
            Dict[str, Any]: 交易意图或BLOCKED状态
        """
        try:
            logger.info(f"{self.strategy_name} - 处理bar_close事件")

            # 1. 计算因子（策略内部已实现）
            analyzed_data = self._analyze_data(bar_data)

            # 2. 生成信号
            signal = self._generate_signal(analyzed_data)

            # 3. 生成交易意图
            intent = self._generate_trade_intent(signal, analyzed_data)

            # 4. 风险检查
            validated_intent = self._validate_risk(intent, analyzed_data)

            # 5. 输出signal_intent.json
            self._save_signal_intent(validated_intent)

            return validated_intent
        except Exception as e:
            logger.error(f"处理bar_close事件失败: {e}")
            # 出错时返回BLOCKED状态
            return {
                "status": "BLOCKED",
                "reason": f"处理bar_close事件失败: {str(e)}",
                "timestamp": datetime.now().isoformat(),
            }

    def _analyze_data(self, bar_data: pd.DataFrame) -> pd.DataFrame:
        """
        分析K线数据，计算因子

        Args:
            bar_data: K线数据

        Returns:
            pd.DataFrame: 分析后的数据
        """
        # 调用策略的populate_indicators方法
        analyzed_data = self.strategy.populate_indicators(bar_data.copy(), {})
        return analyzed_data

    def _generate_signal(self, analyzed_data: pd.DataFrame) -> dict[str, Any]:
        """
        生成交易信号

        Args:
            analyzed_data: 分析后的数据

        Returns:
            Dict[str, Any]: 交易信号
        """
        # 调用策略的populate_entry_trend和populate_exit_trend方法
        entry_signal = self.strategy.populate_entry_trend(analyzed_data.copy(), {})
        exit_signal = self.strategy.populate_exit_trend(analyzed_data.copy(), {})

        # 提取最新的信号
        latest_entry = entry_signal.iloc[-1]
        latest_exit = exit_signal.iloc[-1]
        latest_data = analyzed_data.iloc[-1]

        signal = {
            "timestamp": latest_data.name.isoformat()
            if hasattr(latest_data.name, "isoformat")
            else datetime.now().isoformat(),
            "close": float(latest_data["close"]),
            "enter_long": bool(latest_entry.get("enter_long", 0)),
            "enter_short": bool(latest_entry.get("enter_short", 0)),
            "exit_long": bool(latest_exit.get("exit_long", 0)),
            "exit_short": bool(latest_exit.get("exit_short", 0)),
            "indicators": {
                "ema_fast": float(latest_data.get("ema_fast", 0)),
                "ema_slow": float(latest_data.get("ema_slow", 0)),
                "adx": float(latest_data.get("adx", 0)),
                "atr": float(latest_data.get("atr", 0)),
                "bb_upper": float(latest_data.get("bb_upper", 0)),
                "bb_mid": float(latest_data.get("bb_mid", 0)),
                "bb_lower": float(latest_data.get("bb_lower", 0)),
                "rsi": float(latest_data.get("rsi", 0)),
            },
        }

        return signal

    def _generate_trade_intent(
        self, signal: dict[str, Any], analyzed_data: pd.DataFrame
    ) -> dict[str, Any]:
        """
        生成交易意图

        Args:
            signal: 交易信号
            analyzed_data: 分析后的数据

        Returns:
            Dict[str, Any]: 交易意图
        """
        latest_data = analyzed_data.iloc[-1]
        close_price = signal["close"]
        atr = latest_data.get("atr", 0)

        # 确定交易方向
        direction = "HOLD"
        if signal["enter_long"]:
            direction = "OPEN_LONG"
        elif signal["enter_short"]:
            direction = "OPEN_SHORT"
        elif signal["exit_long"]:
            direction = "CLOSE_LONG"
        elif signal["exit_short"]:
            direction = "CLOSE_SHORT"

        # 计算止损价
        stop_loss = 0.0
        reason = ""

        if direction in ["OPEN_LONG", "OPEN_SHORT"]:
            # 计算入场价/保护价
            if direction == "OPEN_LONG":
                entry_price = close_price
                # 计算止损价（ATR止损）
                stop_loss = entry_price - (atr * getattr(self.strategy, "atr_stop_mult", 2.0))
                reason = f"多头信号: EMA多头排列，ADX={signal['indicators']['adx']:.2f}"
            else:  # OPEN_SHORT
                entry_price = close_price
                # 计算止损价（ATR止损）
                stop_loss = entry_price + (atr * getattr(self.strategy, "atr_stop_mult", 2.0))
                reason = f"空头信号: EMA空头排列，ADX={signal['indicators']['adx']:.2f}"

        # 构建交易意图
        intent = {
            "status": "OK",
            "timestamp": datetime.now().isoformat(),
            "strategy": self.strategy_name,
            "direction": direction,
            "entry_price": close_price if direction in ["OPEN_LONG", "OPEN_SHORT"] else 0.0,
            "stop_loss": stop_loss,
            "reason": reason,
            "signal": signal,
        }

        return intent

    def _validate_risk(self, intent: dict[str, Any], analyzed_data: pd.DataFrame) -> dict[str, Any]:
        """
        风险验证
        无止损/不满足0.8%风险计算 → BLOCKED

        Args:
            intent: 交易意图
            analyzed_data: 分析后的数据

        Returns:
            Dict[str, Any]: 验证后的交易意图或BLOCKED状态
        """
        # 如果是HOLD状态，直接返回
        if intent["direction"] == "HOLD":
            return intent

        # 检查是否有止损价
        if intent["stop_loss"] <= 0:
            logger.warning(f"{self.strategy_name} - 无止损价，交易被BLOCKED")
            return {
                "status": "BLOCKED",
                "reason": "无止损价",
                "timestamp": datetime.now().isoformat(),
                "strategy": self.strategy_name,
                "direction": intent["direction"],
                "original_intent": intent,
            }

        # 计算风险比例
        latest_data = analyzed_data.iloc[-1]
        close_price = intent["entry_price"]
        stop_loss = intent["stop_loss"]

        # 计算风险百分比
        if intent["direction"] == "OPEN_LONG":
            risk_percent = abs((close_price - stop_loss) / close_price) * 100
        else:  # OPEN_SHORT
            risk_percent = abs((stop_loss - close_price) / close_price) * 100

        # 检查是否满足0.8%风险计算
        min_risk_percent = 0.8
        if risk_percent < min_risk_percent:
            logger.warning(
                f"{self.strategy_name} - 风险比例{risk_percent:.2f}% < {min_risk_percent}%，交易被BLOCKED"
            )
            return {
                "status": "BLOCKED",
                "reason": f"风险比例{risk_percent:.2f}% < {min_risk_percent}%",
                "timestamp": datetime.now().isoformat(),
                "strategy": self.strategy_name,
                "direction": intent["direction"],
                "original_intent": intent,
            }

        logger.info(f"{self.strategy_name} - 风险验证通过，风险比例: {risk_percent:.2f}%")
        return intent

    def _save_signal_intent(self, intent: dict[str, Any]):
        """
        保存交易意图到signal_intent.json

        Args:
            intent: 交易意图
        """
        output_path = os.path.join("d:/quantsys", "signal_intent.json")

        try:
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(intent, f, ensure_ascii=False, indent=2)
            logger.info(f"交易意图已保存到: {output_path}")
        except Exception as e:
            logger.error(f"保存交易意图失败: {e}")
            raise


# 示例使用
if __name__ == "__main__":
    # 测试配置
    config = {"strategy_class": "EthPerpRangeStrategy"}

    try:
        # 创建LiveRuntime实例
        live_runtime = LiveRuntime(config)

        # 生成测试数据
        from datetime import datetime, timedelta

        import numpy as np

        # 生成200根1小时K线数据（符合策略的startup_candle_count要求）
        now = datetime.now()
        dates = [now - timedelta(hours=i) for i in range(200)][::-1]

        # 生成模拟的ETH价格数据
        np.random.seed(42)
        base_price = 2500
        prices = []
        current_price = base_price
        for _ in dates:
            change = np.random.normal(0, 10, 1)[0]
            current_price += change
            prices.append(max(current_price, 1000))  # 确保价格为正

        # 创建DataFrame
        data = {
            "open": [p * 0.999 for p in prices],
            "high": [p * 1.001 for p in prices],
            "low": [p * 0.998 for p in prices],
            "close": prices,
            "volume": [np.random.randint(1000, 10000) for _ in dates],
        }

        df = pd.DataFrame(data, index=dates)
        df.index.name = "datetime"

        # 测试bar_close处理
        result = live_runtime.on_bar_close(df)
        logger.info(f"测试结果: {result['status']}")
        if result["status"] == "OK":
            logger.info(f"交易方向: {result['direction']}")
            logger.info(f"入场价: {result['entry_price']:.2f}")
            logger.info(f"止损价: {result['stop_loss']:.2f}")
            logger.info(f"理由: {result['reason']}")
    except Exception as e:
        logger.error(f"测试失败: {e}")
        import traceback

        traceback.print_exc()
