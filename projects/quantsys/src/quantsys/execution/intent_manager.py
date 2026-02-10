#!/usr/bin/env python3
"""
Intent管理器模块
实现Intent的幂等性检查和去重功能，确保同一intent_id只允许一次entry，已有持仓时禁止新intent entry
"""

import json
import logging
import os
from dataclasses import dataclass
from datetime import datetime
from typing import Any

# 配置日志
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


@dataclass
class IntentConsumeRecord:
    """
    Intent消费记录数据结构
    """

    # Intent基本信息
    intent_id: str  # 统一的intent_id
    strategy_id: str  # 策略ID
    symbol: str  # 交易对
    side: str  # 买卖方向
    bar_time: str  # K线时间

    # 消费状态
    consumed_at: str = datetime.now().isoformat()
    status: str = "CONSUMED"  # 状态：CONSUMED, REJECTED, PENDING
    reason: str | None = None  # 消费结果原因

    def to_dict(self) -> dict[str, Any]:
        """
        转换为字典格式
        """
        return {
            "intent_id": self.intent_id,
            "strategy_id": self.strategy_id,
            "symbol": self.symbol,
            "side": self.side,
            "bar_time": self.bar_time,
            "consumed_at": self.consumed_at,
            "status": self.status,
            "reason": self.reason,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "IntentConsumeRecord":
        """
        从字典创建IntentConsumeRecord实例
        """
        return cls(
            intent_id=data["intent_id"],
            strategy_id=data["strategy_id"],
            symbol=data["symbol"],
            side=data["side"],
            bar_time=data["bar_time"],
            consumed_at=data.get("consumed_at", datetime.now().isoformat()),
            status=data.get("status", "CONSUMED"),
            reason=data.get("reason"),
        )


class IntentManager:
    """
    Intent管理器
    负责intent_id的生成、管理和消费记录的跟踪
    """

    def __init__(
        self,
        intent_journal_file: str = "data/intent_journal.jsonl",
        ledger_file: str = "data/order_ledger.json",
    ):
        """
        初始化Intent管理器

        Args:
            intent_journal_file: Intent消费记录文件路径
            ledger_file: 订单账本文件路径，用于重启后识别已消费的intent
        """
        self.intent_journal_file = intent_journal_file
        self.ledger_file = ledger_file

        # 已消费的intent_id集合
        self.consumed_intent_ids: set[str] = set()

        # 当前持仓状态 {symbol: bool}
        self.current_positions: dict[str, bool] = {}

        # 确保目录存在（如果有路径的话）
        journal_dir = os.path.dirname(intent_journal_file)
        if journal_dir:
            os.makedirs(journal_dir, exist_ok=True)

        # 确保账本目录存在（如果有路径的话）
        ledger_dir = os.path.dirname(ledger_file)
        if ledger_dir:
            os.makedirs(ledger_dir, exist_ok=True)

        # 加载已消费的intent记录
        self._load_consumed_intents()

        # 从账本加载已消费的intent
        self._load_consumed_intents_from_ledger()

        logger.info(
            f"Intent管理器初始化完成，已加载 {len(self.consumed_intent_ids)} 条已消费intent记录"
        )

    def _load_consumed_intents(self) -> None:
        """
        从intent_journal.jsonl加载已消费的intent记录
        """
        if os.path.exists(self.intent_journal_file):
            try:
                with open(self.intent_journal_file, encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line:
                            record_dict = json.loads(line)
                            record = IntentConsumeRecord.from_dict(record_dict)
                            self.consumed_intent_ids.add(record.intent_id)
            except json.JSONDecodeError:
                logger.error(f"无法解析Intent消费记录文件 {self.intent_journal_file}，将重新创建")
            except Exception as e:
                logger.error(f"加载Intent消费记录失败: {str(e)}")

    def _load_consumed_intents_from_ledger(self) -> None:
        """
        从订单账本加载已消费的intent
        """
        if os.path.exists(self.ledger_file):
            try:
                with open(self.ledger_file, encoding="utf-8") as f:
                    ledger_data = json.load(f)

                # 遍历账本中的订单，提取intent_id
                for order in ledger_data:
                    # 检查订单中是否包含intent_id
                    if isinstance(order, dict):
                        # 从clientOrderId中提取intent相关信息
                        client_order_id = order.get("clientOrderId", "")
                        if client_order_id:
                            # 从clientOrderId中提取intent_id（如果包含）
                            # 或者从order的meta信息中提取
                            if "meta" in order and isinstance(order["meta"], dict):
                                intent_id = order["meta"].get("intent_id")
                                if intent_id:
                                    self.consumed_intent_ids.add(intent_id)
            except json.JSONDecodeError:
                logger.error(f"无法解析订单账本文件 {self.ledger_file}")
            except Exception as e:
                logger.error(f"从订单账本加载已消费intent失败: {str(e)}")

    def _append_to_journal(self, record: IntentConsumeRecord) -> None:
        """
        将消费记录追加到intent_journal.jsonl
        """
        try:
            with open(self.intent_journal_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(record.to_dict(), ensure_ascii=False) + "\n")
            logger.info(f"Intent消费记录已写入: {record.intent_id}")
        except Exception as e:
            logger.error(f"写入Intent消费记录失败: {str(e)}")

    def generate_intent_id(self, strategy_id: str, bar_time: str, symbol: str) -> str:
        """
        生成统一的intent_id

        Args:
            strategy_id: 策略ID
            bar_time: K线时间
            symbol: 交易对

        Returns:
            str: 生成的intent_id，格式为 {strategy_id}_{bar_time}_{symbol}_{timestamp}
        """
        timestamp = int(datetime.now().timestamp() * 1000)
        return f"{strategy_id}_{bar_time}_{symbol}_{timestamp}"

    def check_intent_allowed(
        self, intent_id: str, strategy_id: str, symbol: str, side: str, has_position: bool = False
    ) -> tuple[bool, str]:
        """
        检查intent是否允许entry

        Args:
            intent_id: 统一的intent_id
            strategy_id: 策略ID
            symbol: 交易对
            side: 买卖方向
            has_position: 是否已有持仓

        Returns:
            tuple[bool, str]: (是否允许entry, 原因)
        """
        # 检查1：intent_id是否已被消费
        if intent_id in self.consumed_intent_ids:
            logger.warning(f"Intent已被消费，禁止重复entry: {intent_id}")
            return False, f"Intent已被消费: {intent_id}"

        # 检查2：是否已有持仓
        if has_position:
            logger.warning(f"已有持仓，禁止新intent entry: {symbol}")
            return False, f"已有持仓: {symbol}"

        # 检查3：当前是否有该品种的持仓
        if self.current_positions.get(symbol, False):
            logger.warning(f"当前已有持仓，禁止新intent entry: {symbol}")
            return False, f"当前已有持仓: {symbol}"

        logger.info(f"Intent检查通过，允许entry: {intent_id}")
        return True, "Intent检查通过"

    def consume_intent(
        self,
        intent_id: str,
        strategy_id: str,
        symbol: str,
        side: str,
        bar_time: str,
        status: str = "CONSUMED",
        reason: str | None = None,
    ) -> bool:
        """
        消费intent，记录到journal并更新状态

        Args:
            intent_id: 统一的intent_id
            strategy_id: 策略ID
            symbol: 交易对
            side: 买卖方向
            bar_time: K线时间
            status: 消费状态
            reason: 消费原因

        Returns:
            bool: 消费是否成功
        """
        # 如果intent_id已被消费，直接返回失败
        if intent_id in self.consumed_intent_ids:
            logger.warning(f"Intent已被消费，无法重复消费: {intent_id}")
            return False

        # 创建消费记录
        record = IntentConsumeRecord(
            intent_id=intent_id,
            strategy_id=strategy_id,
            symbol=symbol,
            side=side,
            bar_time=bar_time,
            status=status,
            reason=reason,
        )

        # 写入journal
        self._append_to_journal(record)

        # 添加到已消费集合
        self.consumed_intent_ids.add(intent_id)

        # 如果是买入或卖出建仓，更新持仓状态
        if status == "CONSUMED" and side in ["buy", "sell"]:
            # 这里假设买入是开多，卖出是开空
            # 在实际应用中，需要根据具体的交易逻辑更新持仓状态
            self.current_positions[symbol] = True

        logger.info(f"Intent已消费: {intent_id}, 状态: {status}")
        return True

    def update_position_status(self, symbol: str, has_position: bool) -> None:
        """
        更新持仓状态

        Args:
            symbol: 交易对
            has_position: 是否有持仓
        """
        self.current_positions[symbol] = has_position
        logger.info(f"持仓状态已更新: {symbol} -> {has_position}")

    def get_consumed_intent_count(self) -> int:
        """
        获取已消费的intent数量

        Returns:
            int: 已消费的intent数量
        """
        return len(self.consumed_intent_ids)

    def is_intent_consumed(self, intent_id: str) -> bool:
        """
        检查intent_id是否已被消费

        Args:
            intent_id: 统一的intent_id

        Returns:
            bool: 是否已被消费
        """
        return intent_id in self.consumed_intent_ids


# 单例模式
_intent_manager = None


def get_intent_manager(
    intent_journal_file: str = "data/intent_journal.jsonl",
    ledger_file: str = "data/order_ledger.json",
) -> IntentManager:
    """
    获取Intent管理器实例（单例模式）

    Args:
        intent_journal_file: Intent消费记录文件路径
        ledger_file: 订单账本文件路径

    Returns:
        IntentManager: Intent管理器实例
    """
    global _intent_manager

    if _intent_manager is None:
        _intent_manager = IntentManager(intent_journal_file, ledger_file)

    return _intent_manager


# 测试代码
if __name__ == "__main__":
    # 初始化Intent管理器
    intent_manager = get_intent_manager("test_intent_journal.jsonl", "test_order_ledger.json")

    # 测试生成intent_id
    intent_id = intent_manager.generate_intent_id(
        "strategy_001", "2026-01-12T14:00:00Z", "ETH-USDT"
    )
    print(f"生成的intent_id: {intent_id}")

    # 测试检查intent
    allowed, reason = intent_manager.check_intent_allowed(
        intent_id, "strategy_001", "ETH-USDT", "buy", False
    )
    print(f"Intent检查结果: {allowed}, 原因: {reason}")

    # 测试消费intent
    consumed = intent_manager.consume_intent(
        intent_id, "strategy_001", "ETH-USDT", "buy", "2026-01-12T14:00:00Z"
    )
    print(f"Intent消费结果: {consumed}")

    # 测试重复消费intent
    allowed, reason = intent_manager.check_intent_allowed(
        intent_id, "strategy_001", "ETH-USDT", "buy", False
    )
    print(f"重复Intent检查结果: {allowed}, 原因: {reason}")

    # 测试已有持仓时的intent检查
    intent_id2 = intent_manager.generate_intent_id(
        "strategy_001", "2026-01-12T15:00:00Z", "ETH-USDT"
    )
    intent_manager.update_position_status("ETH-USDT", True)
    allowed, reason = intent_manager.check_intent_allowed(
        intent_id2, "strategy_001", "ETH-USDT", "buy", True
    )
    print(f"已有持仓Intent检查结果: {allowed}, 原因: {reason}")

    # 清理测试文件
    import os

    for file in ["test_intent_journal.jsonl", "test_order_ledger.json"]:
        if os.path.exists(file):
            os.remove(file)
            print(f"已清理测试文件: {file}")
