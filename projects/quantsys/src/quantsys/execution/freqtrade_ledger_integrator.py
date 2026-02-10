#!/usr/bin/env python3
"""
Freqtrade订单/成交回流到Quantsys交易账本模块
将Freqtrade的订单事件、成交和持仓状态转换为quantsys可读的交易账本
"""

import json
import logging
import os
import time
from typing import Any

import pandas as pd

from .trade_ledger import EventType, LedgerEvent, TradeLedger

# 配置日志
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class FreqtradeLedgerIntegrator:
    """
    Freqtrade订单/成交回流到Quantsys交易账本的集成器
    """

    def __init__(
        self,
        output_path: str = "freqtrade_trade_ledger.jsonl",
        format: str = "jsonl",
        ledger_path: str = "test_ledger.json",
    ):
        """
        初始化集成器

        Args:
            output_path: 输出文件路径
            format: 输出格式，支持jsonl和parquet
            ledger_path: 交易账本路径，用于隔离测试环境
        """
        self.output_path = output_path
        self.format = format.lower()

        # 验证格式
        if self.format not in ["jsonl", "parquet"]:
            raise ValueError(f"不支持的输出格式: {self.format}，仅支持jsonl和parquet")

        # 交易账本实例 - 使用测试专用路径，避免加载现有数据
        self.trade_ledger = TradeLedger(ledger_path=ledger_path)

        # 已处理的事件ID集合，用于去重
        self.processed_event_ids = set()

        logger.info(
            f"Freqtrade订单/成交集成器初始化完成，输出路径: {self.output_path}，格式: {self.format}"
        )

    def convert_freqtrade_order_to_ledger(
        self, freqtrade_order: dict[str, Any]
    ) -> LedgerEvent | None:
        """
        将Freqtrade订单转换为交易账本事件

        Args:
            freqtrade_order: Freqtrade订单数据

        Returns:
            Optional[LedgerEvent]: 交易账本事件，转换失败返回None
        """
        try:
            # 提取必要字段
            order_id = freqtrade_order.get("id") or freqtrade_order.get("order_id")
            if not order_id:
                logger.error("Freqtrade订单缺少id字段")
                return None

            # 生成事件ID
            event_id = f"freqtrade_order_{order_id}"

            # 去重检查
            if event_id in self.processed_event_ids:
                return None

            # 转换为quantsys订单数据格式
            quantsys_order = {
                "clientOrderId": order_id,
                "symbol": freqtrade_order.get("pair", ""),
                "side": freqtrade_order.get("side", "").lower(),
                "order_type": freqtrade_order.get("type", "").lower(),
                "amount": freqtrade_order.get("amount", 0.0),
                "price": freqtrade_order.get("price", 0.0),
                "status": freqtrade_order.get("status", "").upper(),
                "create_ts": freqtrade_order.get("timestamp")
                or freqtrade_order.get("create_timestamp")
                or time.time(),
                "update_ts": freqtrade_order.get("update_timestamp") or time.time(),
                "intent_id": freqtrade_order.get("intent_id", f"intent_{order_id}"),
                "fee": freqtrade_order.get("fee", {"currency": "USDT", "cost": 0.0}),
            }

            # 确定事件类型
            status = quantsys_order["status"]
            if status == "CREATED":
                event_type = EventType.ORDER_CREATED
            else:
                event_type = EventType.ORDER_UPDATED

            # 创建账本事件
            event = LedgerEvent(
                event_type=event_type,
                event_data=quantsys_order,
                event_id=event_id,
                timestamp=quantsys_order["create_ts"],
            )

            # 标记为已处理
            self.processed_event_ids.add(event_id)

            return event
        except Exception as e:
            logger.error(f"转换Freqtrade订单失败: {e}")
            return None

    def convert_freqtrade_fill_to_ledger(
        self, freqtrade_fill: dict[str, Any]
    ) -> LedgerEvent | None:
        """
        将Freqtrade成交数据转换为交易账本事件

        Args:
            freqtrade_fill: Freqtrade成交数据

        Returns:
            Optional[LedgerEvent]: 交易账本事件，转换失败返回None
        """
        try:
            # 提取必要字段
            order_id = freqtrade_fill.get("order_id")
            if not order_id:
                logger.error("Freqtrade成交数据缺少order_id字段")
                return None

            # 生成事件ID
            event_id = f"freqtrade_fill_{order_id}_{time.time()}"

            # 去重检查 - 成交数据可能有唯一ID
            fill_id = freqtrade_fill.get("id") or freqtrade_fill.get("fill_id")
            if fill_id:
                event_id = f"freqtrade_fill_{fill_id}"
                if event_id in self.processed_event_ids:
                    return None
            else:
                # 如果没有唯一fill_id，使用order_id和时间戳
                if event_id in self.processed_event_ids:
                    return None

            # 转换为quantsys成交数据格式
            quantsys_fill = {
                "symbol": freqtrade_fill.get("pair", ""),
                "side": freqtrade_fill.get("side", "").lower(),
                "fillAmount": freqtrade_fill.get("amount", 0.0),
                "fillPrice": freqtrade_fill.get("price", 0.0),
                "clientOrderId": order_id,
                "timestamp": freqtrade_fill.get("timestamp")
                or freqtrade_fill.get("fill_timestamp")
                or time.time(),
                "fee": freqtrade_fill.get("fee", 0.0)
                if isinstance(freqtrade_fill.get("fee"), float)
                else freqtrade_fill.get("fee", {}).get("cost", 0.0),
                "intent_id": freqtrade_fill.get("intent_id", f"intent_{order_id}"),
            }

            # 创建账本事件
            event = LedgerEvent(
                event_type=EventType.FILL_CREATED,
                event_data=quantsys_fill,
                event_id=event_id,
                timestamp=quantsys_fill["timestamp"],
            )

            # 标记为已处理
            self.processed_event_ids.add(event_id)

            return event
        except Exception as e:
            logger.error(f"转换Freqtrade成交数据失败: {e}")
            return None

    def process_freqtrade_event(
        self, event_data: dict[str, Any], event_type: str
    ) -> LedgerEvent | None:
        """
        处理Freqtrade事件

        Args:
            event_data: Freqtrade事件数据
            event_type: 事件类型，支持order, fill, position

        Returns:
            Optional[LedgerEvent]: 交易账本事件，转换失败返回None
        """
        if event_type == "order":
            return self.convert_freqtrade_order_to_ledger(event_data)
        elif event_type == "fill":
            return self.convert_freqtrade_fill_to_ledger(event_data)
        elif event_type == "position":
            # 目前不直接处理持仓事件，持仓会通过成交事件自动更新
            logger.debug("持仓事件暂不处理，将通过成交事件自动更新")
            return None
        else:
            logger.error(f"不支持的事件类型: {event_type}")
            return None

    def process_events_batch(
        self, events: list[dict[str, Any]], event_type: str
    ) -> list[LedgerEvent]:
        """
        批量处理Freqtrade事件

        Args:
            events: Freqtrade事件列表
            event_type: 事件类型，支持order, fill, position

        Returns:
            List[LedgerEvent]: 转换后的交易账本事件列表
        """
        converted_events = []

        for event_data in events:
            event = self.process_freqtrade_event(event_data, event_type)
            if event:
                converted_events.append(event)
                # 记录到交易账本
                self.trade_ledger.record_event(event.event_type, event.event_data)

        logger.info(
            f"批量处理完成，共处理 {len(events)} 个事件，成功转换 {len(converted_events)} 个"
        )
        return converted_events

    def save_ledger_to_file(self, output_path: str | None = None) -> bool:
        """
        将交易账本保存到文件

        Args:
            output_path: 输出文件路径，不指定则使用初始化时的路径

        Returns:
            bool: 保存成功返回True，失败返回False
        """
        try:
            save_path = output_path or self.output_path

            # 确保目录存在
            dir_name = os.path.dirname(save_path)
            if dir_name:
                os.makedirs(dir_name, exist_ok=True)

            if self.format == "jsonl":
                # 保存为JSONL格式
                with open(save_path, "w") as f:
                    for event in self.trade_ledger.events:
                        json.dump(event.to_dict(), f)
                        f.write("\n")
            elif self.format == "parquet":
                # 转换为DataFrame并保存为Parquet
                events_data = []
                for event in self.trade_ledger.events:
                    event_dict = event.to_dict()
                    # 处理event_data为JSON字符串，避免struct类型不一致问题
                    event_dict["event_data"] = json.dumps(event_dict["event_data"])
                    events_data.append(event_dict)
                df = pd.DataFrame(events_data)
                df.to_parquet(save_path, index=False)

            logger.info(f"交易账本已保存到 {save_path}，格式: {self.format}")
            return True
        except Exception as e:
            logger.error(f"保存交易账本失败: {e}")
            return False

    def load_freqtrade_orders(self, orders_path: str) -> list[dict[str, Any]]:
        """
        从文件加载Freqtrade订单数据

        Args:
            orders_path: Freqtrade订单文件路径

        Returns:
            List[Dict[str, Any]]: 订单数据列表
        """
        try:
            with open(orders_path) as f:
                orders = json.load(f)

            if not isinstance(orders, list):
                orders = [orders]

            logger.info(f"已加载 {len(orders)} 个Freqtrade订单")
            return orders
        except Exception as e:
            logger.error(f"加载Freqtrade订单失败: {e}")
            return []

    def load_freqtrade_fills(self, fills_path: str) -> list[dict[str, Any]]:
        """
        从文件加载Freqtrade成交数据

        Args:
            fills_path: Freqtrade成交文件路径

        Returns:
            List[Dict[str, Any]]: 成交数据列表
        """
        try:
            with open(fills_path) as f:
                fills = json.load(f)

            if not isinstance(fills, list):
                fills = [fills]

            logger.info(f"已加载 {len(fills)} 个Freqtrade成交")
            return fills
        except Exception as e:
            logger.error(f"加载Freqtrade成交失败: {e}")
            return []

    def integrate_from_files(
        self, orders_path: str | None = None, fills_path: str | None = None
    ) -> bool:
        """
        从文件集成Freqtrade订单和成交数据到交易账本

        Args:
            orders_path: Freqtrade订单文件路径
            fills_path: Freqtrade成交文件路径

        Returns:
            bool: 集成成功返回True，失败返回False
        """
        try:
            # 加载并处理订单数据
            if orders_path:
                orders = self.load_freqtrade_orders(orders_path)
                self.process_events_batch(orders, "order")

            # 加载并处理成交数据
            if fills_path:
                fills = self.load_freqtrade_fills(fills_path)
                self.process_events_batch(fills, "fill")

            # 保存到文件
            return self.save_ledger_to_file()
        except Exception as e:
            logger.error(f"从文件集成失败: {e}")
            return False

    def integrate_from_data(
        self, orders: list[dict[str, Any]] | None = None, fills: list[dict[str, Any]] | None = None
    ) -> bool:
        """
        从内存数据集成Freqtrade订单和成交数据到交易账本

        Args:
            orders: Freqtrade订单数据列表
            fills: Freqtrade成交数据列表

        Returns:
            bool: 集成成功返回True，失败返回False
        """
        try:
            # 处理订单数据
            if orders:
                self.process_events_batch(orders, "order")

            # 处理成交数据
            if fills:
                self.process_events_batch(fills, "fill")

            # 保存到文件
            return self.save_ledger_to_file()
        except Exception as e:
            logger.error(f"从内存数据集成失败: {e}")
            return False

    def get_ledger_summary(self) -> dict[str, Any]:
        """
        获取交易账本摘要

        Returns:
            Dict[str, Any]: 交易账本摘要
        """
        return {
            "total_events": len(self.trade_ledger.events),
            "orders": len(self.trade_ledger.current_state["orders"]),
            "fills": len(self.trade_ledger.current_state["fills"]),
            "positions": len(self.trade_ledger.current_state["positions"]),
            "last_event_time": self.trade_ledger.current_state["last_event_time"],
        }


# 示例使用
if __name__ == "__main__":
    # 创建集成器实例
    integrator = FreqtradeLedgerIntegrator(
        output_path="freqtrade_trade_ledger.jsonl", format="jsonl"
    )

    # 模拟Freqtrade订单数据
    sample_orders = [
        {
            "id": "order_123",
            "pair": "BTC/USDT",
            "side": "BUY",
            "type": "LIMIT",
            "amount": 0.001,
            "price": 35000.0,
            "status": "CREATED",
            "timestamp": time.time() - 3600,
        },
        {
            "id": "order_456",
            "pair": "ETH/USDT",
            "side": "SELL",
            "type": "MARKET",
            "amount": 0.1,
            "price": 2200.0,
            "status": "FILLED",
            "timestamp": time.time() - 1800,
        },
    ]

    # 模拟Freqtrade成交数据
    sample_fills = [
        {
            "id": "fill_789",
            "order_id": "order_123",
            "pair": "BTC/USDT",
            "side": "BUY",
            "amount": 0.001,
            "price": 35000.0,
            "fee": {"currency": "USDT", "cost": 0.0175},
            "timestamp": time.time() - 3590,
        },
        {
            "id": "fill_101",
            "order_id": "order_456",
            "pair": "ETH/USDT",
            "side": "SELL",
            "amount": 0.1,
            "price": 2200.0,
            "fee": 0.11,
            "timestamp": time.time() - 1790,
        },
    ]

    # 从内存数据集成
    success = integrator.integrate_from_data(orders=sample_orders, fills=sample_fills)

    if success:
        print("集成成功！")
        summary = integrator.get_ledger_summary()
        print(f"账本摘要: {summary}")
    else:
        print("集成失败！")
