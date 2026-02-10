#!/usr/bin/env python3
"""
信号冻结模块
实现策略信号到下单参数的冻结功能，防止策略参数漂移
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
class SignalFreezeRecord:
    """
    信号冻结记录数据结构
    """

    # 订单幂等键，用于绑定冻结记录和订单
    idempotency_key: str

    # 策略相关信息
    strategy_id: str
    strategy_name: str
    strategy_params: dict[str, Any]
    factor_version: str
    bar_time: str
    trigger_reason: str

    # 交易参数
    symbol: str
    side: str
    order_type: str
    planned_entry_price: float | None
    planned_stop_loss: float
    planned_take_profit: float | None

    # 风险预算
    single_trade_budget: float  # 单笔交易预算 (3.3u)
    total_budget: float  # 总预算 (10u)
    risk_per_trade: float  # 单笔交易风险 (0.8%)

    # 冻结时间
    frozen_at: str = datetime.now().isoformat()

    # 状态
    status: str = "ACTIVE"

    def to_dict(self) -> dict[str, Any]:
        """
        转换为字典格式
        """
        return {
            "idempotency_key": self.idempotency_key,
            "strategy_id": self.strategy_id,
            "strategy_name": self.strategy_name,
            "strategy_params": self.strategy_params,
            "factor_version": self.factor_version,
            "bar_time": self.bar_time,
            "trigger_reason": self.trigger_reason,
            "symbol": self.symbol,
            "side": self.side,
            "order_type": self.order_type,
            "planned_entry_price": self.planned_entry_price,
            "planned_stop_loss": self.planned_stop_loss,
            "planned_take_profit": self.planned_take_profit,
            "single_trade_budget": self.single_trade_budget,
            "total_budget": self.total_budget,
            "risk_per_trade": self.risk_per_trade,
            "frozen_at": self.frozen_at,
            "status": self.status,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SignalFreezeRecord":
        """
        从字典创建SignalFreezeRecord实例
        """
        return cls(
            idempotency_key=data["idempotency_key"],
            strategy_id=data["strategy_id"],
            strategy_name=data["strategy_name"],
            strategy_params=data["strategy_params"],
            factor_version=data["factor_version"],
            bar_time=data["bar_time"],
            trigger_reason=data["trigger_reason"],
            symbol=data["symbol"],
            side=data["side"],
            order_type=data["order_type"],
            planned_entry_price=data["planned_entry_price"],
            planned_stop_loss=data["planned_stop_loss"],
            planned_take_profit=data["planned_take_profit"],
            single_trade_budget=data["single_trade_budget"],
            total_budget=data["total_budget"],
            risk_per_trade=data["risk_per_trade"],
            frozen_at=data.get("frozen_at", datetime.now().isoformat()),
            status=data.get("status", "ACTIVE"),
        )


class SignalFreezeManager:
    """
    信号冻结管理器
    负责生成、存储和管理信号冻结记录
    """

    def __init__(self, freeze_file: str = "intent_freeze.json"):
        """
        初始化信号冻结管理器

        Args:
            freeze_file: 冻结记录文件路径
        """
        self.freeze_file = freeze_file
        self.freeze_records: dict[str, SignalFreezeRecord] = {}

        # 加载已有的冻结记录
        self._load_freeze_records()

        logger.info(f"信号冻结管理器初始化完成，加载了 {len(self.freeze_records)} 条冻结记录")

    def _load_freeze_records(self) -> None:
        """
        加载已有的冻结记录
        """
        if os.path.exists(self.freeze_file):
            try:
                with open(self.freeze_file, encoding="utf-8") as f:
                    data = json.load(f)

                # 转换为SignalFreezeRecord实例
                for record_dict in data:
                    record = SignalFreezeRecord.from_dict(record_dict)
                    self.freeze_records[record.idempotency_key] = record

            except json.JSONDecodeError:
                logger.error(f"无法解析冻结记录文件 {self.freeze_file}，将重新创建")
            except Exception as e:
                logger.error(f"加载冻结记录失败: {str(e)}")

    def _save_freeze_records(self) -> None:
        """
        保存冻结记录到文件
        """
        try:
            # 转换为字典列表
            records_list = [record.to_dict() for record in self.freeze_records.values()]

            with open(self.freeze_file, "w", encoding="utf-8") as f:
                json.dump(records_list, f, ensure_ascii=False, indent=2)

            logger.info(f"冻结记录已保存到 {self.freeze_file}")

        except Exception as e:
            logger.error(f"保存冻结记录失败: {str(e)}")

    def generate_idempotency_key(self, strategy_id: str, bar_time: str, symbol: str) -> str:
        """
        生成订单幂等键

        Args:
            strategy_id: 策略ID
            bar_time: K线时间
            symbol: 交易对

        Returns:
            str: 订单幂等键
        """
        return f"{strategy_id}_{bar_time}_{symbol}_{int(datetime.now().timestamp() * 1000)}"

    def freeze_signal(
        self,
        strategy_id: str,
        strategy_name: str,
        strategy_params: dict[str, Any],
        factor_version: str,
        bar_time: str,
        trigger_reason: str,
        symbol: str,
        side: str,
        order_type: str,
        planned_entry_price: float | None,
        planned_stop_loss: float,
        planned_take_profit: float | None,
        single_trade_budget: float = 3.3,  # 3.3u
        total_budget: float = 10.0,  # 10u
        risk_per_trade: float = 0.008,  # 0.8%
        idempotency_key: str | None = None,
    ) -> SignalFreezeRecord:
        """
        冻结策略信号

        Args:
            strategy_id: 策略ID
            strategy_name: 策略名称
            strategy_params: 策略参数
            factor_version: 因子版本
            bar_time: K线时间
            trigger_reason: 触发理由
            symbol: 交易对
            side: 买卖方向
            order_type: 订单类型
            planned_entry_price: 计划入场价格
            planned_stop_loss: 计划止损价格
            planned_take_profit: 计划止盈价格
            single_trade_budget: 单笔交易预算
            total_budget: 总预算
            risk_per_trade: 单笔交易风险
            idempotency_key: 订单幂等键（可选，如不提供则自动生成）

        Returns:
            SignalFreezeRecord: 冻结记录
        """
        # 生成或使用提供的幂等键
        if idempotency_key is None:
            idempotency_key = self.generate_idempotency_key(strategy_id, bar_time, symbol)

        # 创建冻结记录
        freeze_record = SignalFreezeRecord(
            idempotency_key=idempotency_key,
            strategy_id=strategy_id,
            strategy_name=strategy_name,
            strategy_params=strategy_params,
            factor_version=factor_version,
            bar_time=bar_time,
            trigger_reason=trigger_reason,
            symbol=symbol,
            side=side,
            order_type=order_type,
            planned_entry_price=planned_entry_price,
            planned_stop_loss=planned_stop_loss,
            planned_take_profit=planned_take_profit,
            single_trade_budget=single_trade_budget,
            total_budget=total_budget,
            risk_per_trade=risk_per_trade,
        )

        # 保存冻结记录
        self.freeze_records[idempotency_key] = freeze_record
        self._save_freeze_records()

        logger.info(
            f"信号已冻结，幂等键: {idempotency_key}, 策略: {strategy_name}, 交易对: {symbol}"
        )

        return freeze_record

    def get_freeze_record(self, idempotency_key: str) -> SignalFreezeRecord | None:
        """
        获取冻结记录

        Args:
            idempotency_key: 订单幂等键

        Returns:
            Optional[SignalFreezeRecord]: 冻结记录，如果不存在则返回None
        """
        return self.freeze_records.get(idempotency_key)

    def update_record_status(self, idempotency_key: str, status: str) -> bool:
        """
        更新冻结记录状态

        Args:
            idempotency_key: 订单幂等键
            status: 新状态

        Returns:
            bool: 更新是否成功
        """
        if idempotency_key in self.freeze_records:
            self.freeze_records[idempotency_key].status = status
            self._save_freeze_records()
            logger.info(f"冻结记录状态已更新，幂等键: {idempotency_key}, 新状态: {status}")
            return True
        else:
            logger.error(f"找不到冻结记录，幂等键: {idempotency_key}")
            return False

    def get_active_records(self) -> list[SignalFreezeRecord]:
        """
        获取所有活跃的冻结记录

        Returns:
            List[SignalFreezeRecord]: 活跃的冻结记录列表
        """
        return [record for record in self.freeze_records.values() if record.status == "ACTIVE"]

    def get_records_by_strategy(self, strategy_id: str) -> list[SignalFreezeRecord]:
        """
        根据策略ID获取冻结记录

        Args:
            strategy_id: 策略ID

        Returns:
            List[SignalFreezeRecord]: 冻结记录列表
        """
        return [
            record for record in self.freeze_records.values() if record.strategy_id == strategy_id
        ]

    def clear_expired_records(self, days: int = 7) -> int:
        """
        清理过期的冻结记录

        Args:
            days: 保留天数

        Returns:
            int: 清理的记录数量
        """
        from datetime import timedelta

        cutoff_time = datetime.now() - timedelta(days=days)
        expired_keys = []

        for key, record in self.freeze_records.items():
            record_time = datetime.fromisoformat(record.frozen_at)
            if record_time < cutoff_time:
                expired_keys.append(key)

        # 删除过期记录
        for key in expired_keys:
            del self.freeze_records[key]

        # 保存更新后的记录
        if expired_keys:
            self._save_freeze_records()
            logger.info(f"已清理 {len(expired_keys)} 条过期冻结记录")

        return len(expired_keys)


# 单例模式
_signal_freeze_manager = None


def get_signal_freeze_manager(freeze_file: str = "intent_freeze.json") -> SignalFreezeManager:
    """
    获取信号冻结管理器实例（单例模式）

    Args:
        freeze_file: 冻结记录文件路径

    Returns:
        SignalFreezeManager: 信号冻结管理器实例
    """
    global _signal_freeze_manager

    if _signal_freeze_manager is None:
        _signal_freeze_manager = SignalFreezeManager(freeze_file)

    return _signal_freeze_manager


# 测试代码
if __name__ == "__main__":
    # 初始化管理器
    manager = get_signal_freeze_manager("test_intent_freeze.json")

    # 测试冻结信号
    freeze_record = manager.freeze_signal(
        strategy_id="strategy_001",
        strategy_name="ETH趋势跟踪策略",
        strategy_params={"fast_ma": 10, "slow_ma": 30, "rsi_period": 14, "rsi_threshold": 70},
        factor_version="v1.0.0",
        bar_time="2026-01-11T14:00:00Z",
        trigger_reason="突破20日均线",
        symbol="ETH-USDT",
        side="buy",
        order_type="market",
        planned_entry_price=2500.0,
        planned_stop_loss=2450.0,
        planned_take_profit=2600.0,
    )

    print("冻结记录:")
    print(json.dumps(freeze_record.to_dict(), ensure_ascii=False, indent=2))

    # 测试获取冻结记录
    retrieved = manager.get_freeze_record(freeze_record.idempotency_key)
    print("\n获取的冻结记录:")
    print(json.dumps(retrieved.to_dict(), ensure_ascii=False, indent=2))

    # 测试更新状态
    manager.update_record_status(freeze_record.idempotency_key, "COMPLETED")
    updated = manager.get_freeze_record(freeze_record.idempotency_key)
    print("\n更新状态后的记录:")
    print(json.dumps(updated.to_dict(), ensure_ascii=False, indent=2))

    # 测试获取活跃记录
    active_records = manager.get_active_records()
    print(f"\n活跃记录数量: {len(active_records)}")

    # 清理测试文件
    import os

    if os.path.exists("test_intent_freeze.json"):
        os.remove("test_intent_freeze.json")
        print("\n测试文件已清理")
