#!/usr/bin/env python3
"""
SignalAdapter: Quantsys→Freqtrade Strategy 输入桥接

负责将Quantsys生成的signal_intent.json转换为Freqtrade策略可消费的格式
"""

import json
import logging
import os
from typing import Any

# 导入通知服务
from quantsys.notifications.notification_service import NotificationService

# 配置日志
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class SignalAdapter:
    """
    信号适配器类
    负责将Quantsys的signal_intent.json转换为Freqtrade策略可消费的格式
    """

    def __init__(self, config: dict[str, Any] = None):
        """
        初始化信号适配器

        Args:
            config: 配置信息
        """
        self.config = config or {}
        self.signal_intent_path = self.config.get(
            "signal_intent_path", "d:/quantsys/signal_intent.json"
        )
        self.freqtrade_signal_path = self.config.get(
            "freqtrade_signal_path", "d:/quantsys/freqtrade_signal.json"
        )

        # 记录已处理的信号ID，防止重复处理
        self.processed_signal_ids = set()

        # 初始化通知服务
        self.notification_service = NotificationService(self.config.get("notifications", {}))

        logger.info("SignalAdapter初始化完成")

    def _generate_intent_id(self, signal: dict[str, Any]) -> str:
        """
        生成唯一的信号意图ID，用于防止重复处理

        Args:
            signal: 信号数据

        Returns:
            str: 唯一的意图ID
        """
        timestamp = signal.get("timestamp", "")
        direction = signal.get("direction", "")
        strategy = signal.get("strategy", "")
        # 基于时间戳、方向和策略生成唯一ID
        intent_id = f"{timestamp}_{direction}_{strategy}"
        return intent_id

    def _convert_to_freqtrade_format(self, intent: dict[str, Any]) -> dict[str, Any] | None:
        """
        将Quantsys信号意图转换为Freqtrade兼容格式

        Args:
            intent: Quantsys信号意图

        Returns:
            Optional[Dict[str, Any]]: Freqtrade兼容的信号格式，None表示不应该处理
        """
        # 检查状态是否为OK
        if intent.get("status") != "OK":
            logger.warning(f"信号状态不是OK，跳过处理: {intent.get('status')}")
            return None

        # 生成唯一意图ID
        intent_id = self._generate_intent_id(intent)

        # 检查是否已处理过该信号
        if intent_id in self.processed_signal_ids:
            logger.info(f"信号已处理过，跳过: {intent_id}")
            return None

        # 记录已处理的信号
        self.processed_signal_ids.add(intent_id)

        # 转换方向为Freqtrade格式
        direction = intent.get("direction", "")
        if direction == "OPEN_LONG":
            side = "buy"
            action = "enter"
        elif direction == "OPEN_SHORT":
            side = "sell"
            action = "enter"
        elif direction == "CLOSE_LONG":
            side = "buy"
            action = "exit"
        elif direction == "CLOSE_SHORT":
            side = "sell"
            action = "exit"
        elif direction == "HOLD":
            # HOLD状态不需要处理
            logger.info(f"信号为HOLD状态，跳过: {intent_id}")
            return None
        else:
            logger.warning(f"未知的信号方向，跳过: {direction}")
            return None

        # 构建Freqtrade信号格式
        freqtrade_signal = {
            "intent_id": intent_id,
            "timestamp": intent.get("timestamp"),
            "pair": "ETH/USDT:USDT",  # 只支持ETH永续
            "side": side,
            "action": action,
            "strategy": intent.get("strategy", ""),
            "entry_price": intent.get("entry_price", 0.0),
            "stop_loss": intent.get("stop_loss", 0.0),
            "reason": intent.get("reason", ""),
            "signal_timestamp": intent.get("signal", {}).get("timestamp", ""),
        }

        return freqtrade_signal

    def convert_signal(self) -> dict[str, Any] | None:
        """
        转换信号意图为Freqtrade兼容格式

        Returns:
            Optional[Dict[str, Any]]: 转换后的信号，None表示没有需要处理的信号
        """
        try:
            # 读取signal_intent.json
            if not os.path.exists(self.signal_intent_path):
                logger.warning(f"signal_intent.json文件不存在: {self.signal_intent_path}")
                return None

            with open(self.signal_intent_path, encoding="utf-8") as f:
                intent = json.load(f)

            # 发送信号生成通知
            self.notification_service.notify_signal_generated(intent)

            # 转换为Freqtrade格式
            freqtrade_signal = self._convert_to_freqtrade_format(intent)

            if freqtrade_signal:
                # 保存转换后的信号
                self._save_freqtrade_signal(freqtrade_signal)
                logger.info(f"信号已转换并保存: {freqtrade_signal['intent_id']}")

                # 发送信号转换完成通知
                self.notification_service.notify_signal_converted(freqtrade_signal)

                return freqtrade_signal
            else:
                logger.info("没有需要处理的信号")
                return None

        except json.JSONDecodeError as e:
            logger.error(f"解析signal_intent.json失败: {e}")
            return None
        except Exception as e:
            logger.error(f"转换信号失败: {e}")
            return None

    def _save_freqtrade_signal(self, signal: dict[str, Any]):
        """
        保存Freqtrade信号到文件

        Args:
            signal: Freqtrade信号
        """
        try:
            # 确保输出目录存在
            output_dir = os.path.dirname(self.freqtrade_signal_path)
            if output_dir and not os.path.exists(output_dir):
                os.makedirs(output_dir, exist_ok=True)

            # 保存信号
            with open(self.freqtrade_signal_path, "w", encoding="utf-8") as f:
                json.dump(signal, f, ensure_ascii=False, indent=2)

            logger.info(f"Freqtrade信号已保存到: {self.freqtrade_signal_path}")
        except Exception as e:
            logger.error(f"保存Freqtrade信号失败: {e}")

    def run(self) -> bool:
        """
        运行信号转换

        Returns:
            bool: 转换是否成功
        """
        try:
            signal = self.convert_signal()
            return signal is not None
        except Exception as e:
            logger.error(f"运行信号转换失败: {e}")
            return False


# 示例使用
if __name__ == "__main__":
    # 创建适配器实例
    adapter = SignalAdapter()

    # 运行信号转换
    result = adapter.run()
    print(f"信号转换结果: {'成功' if result else '失败'}")
