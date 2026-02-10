#!/usr/bin/env python3
"""
投资组合快照模块
实现统一快照接口，一次性拉取并结构化输出账户余额、持仓、订单等信息
"""

import json
import logging
from datetime import datetime
from typing import Any

from .order_execution import OrderExecution

# 配置日志
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class PortfolioSnapshot:
    """
    投资组合快照类，用于生成和管理账户、持仓、订单的统一快照
    """

    def __init__(self, config: dict[str, Any]):
        """
        初始化投资组合快照模块

        Args:
            config: 配置信息，包含交易所API密钥等
        """
        self.config = config

        # 对于dry_run模式，使用模拟的OrderExecution对象
        if config.get("trading_mode") == "dry_run":
            self.order_execution = self._create_mock_order_execution()
        else:
            self.order_execution = OrderExecution(config)

    def get_portfolio_snapshot(self) -> dict[str, Any]:
        """
        获取投资组合快照，包括余额、持仓和未成交订单

        Returns:
            Dict[str, Any]: 结构化的投资组合快照
        """
        logger.info("开始生成投资组合快照")

        # 获取当前时间戳
        timestamp = datetime.utcnow().isoformat() + "Z"

        # 1. 获取账户余额
        balance_data = self._get_balance()

        # 2. 获取ETH永续持仓
        positions_data = self._get_positions()

        # 3. 获取未成交订单
        orders_data = self._get_open_orders()

        # 4. 构建统一快照
        snapshot = {
            "timestamp": timestamp,
            "source": "OKX REST",
            "balance": balance_data,
            "positions": positions_data,
            "open_orders": orders_data,
        }

        logger.info("投资组合快照生成完成")
        return snapshot

    def _get_balance(self) -> dict[str, Any]:
        """
        获取账户余额信息

        Returns:
            Dict[str, Any]: 结构化的余额信息
        """
        logger.info("获取账户余额")

        result = self.order_execution.get_balance()

        # 解析OKX API返回的余额数据
        usdt_balance = {"total": 0.0, "available": 0.0, "frozen": 0.0}

        if result.get("code") == "0" and result.get("data"):
            for balance_item in result["data"]:
                for asset in balance_item.get("details", []):
                    if asset.get("ccy") == "USDT":
                        usdt_balance = {
                            "total": float(asset.get("eq", "0")),
                            "available": float(asset.get("availEq", "0")),
                            "frozen": float(asset.get("frozenBal", "0")),
                        }
                        break

        return usdt_balance

    def _get_positions(self) -> list[dict[str, Any]]:
        """
        获取ETH永续持仓信息

        Returns:
            List[Dict[str, Any]]: 结构化的持仓列表
        """
        logger.info("获取ETH永续持仓")

        # 获取所有持仓
        result = self.order_execution.get_positions()

        positions = []

        if result.get("code") == "0" and result.get("data"):
            for position_item in result["data"]:
                # 只处理ETH永续合约
                if position_item.get("instId") == "ETH-USDT-SWAP":
                    position = {
                        "symbol": position_item.get("instId", ""),
                        "direction": position_item.get("posSide", "").lower(),
                        "size": float(position_item.get("pos", "0")),
                        "avg_entry_price": float(position_item.get("avgPx", "0")),
                        "unrealized_pnl": float(position_item.get("upl", "0")),
                        "margin_used": float(position_item.get("im", "0")),
                        "leverage": float(position_item.get("lever", "1")),
                        "liquidation_price": float(position_item.get("liqPx", "0")),
                    }
                    positions.append(position)

        return positions

    def _get_open_orders(self) -> list[dict[str, Any]]:
        """
        获取未成交订单信息

        Returns:
            List[Dict[str, Any]]: 结构化的未成交订单列表
        """
        logger.info("获取未成交订单")

        # 获取ETH永续合约的未成交订单
        result = self.order_execution.get_open_orders("ETH-USDT-SWAP")

        open_orders = []

        if result.get("code") == "0" and result.get("data"):
            for order_item in result["data"]:
                order = {
                    "order_id": order_item.get("ordId", ""),
                    "client_order_id": order_item.get("clOrdId", ""),
                    "symbol": order_item.get("instId", ""),
                    "side": order_item.get("side", "").lower(),
                    "direction": order_item.get("posSide", "").lower(),
                    "order_type": order_item.get("ordType", "").lower(),
                    "price": float(order_item.get("px", "0")),
                    "size": float(order_item.get("sz", "0")),
                    "filled_size": float(order_item.get("accFillSz", "0")),
                    "status": order_item.get("state", "").lower(),
                    "timestamp": order_item.get("cTime", ""),
                }
                open_orders.append(order)

        return open_orders

    def _create_mock_order_execution(self):
        """
        创建模拟的OrderExecution对象，用于dry_run模式

        Returns:
            MockOrderExecution: 模拟的OrderExecution对象
        """

        class MockOrderExecution:
            """
            模拟的OrderExecution类，用于dry_run模式下的测试
            """

            def get_balance(self):
                """
                模拟获取账户余额
                """
                return {
                    "code": "0",
                    "msg": "success",
                    "data": [
                        {
                            "details": [
                                {
                                    "ccy": "USDT",
                                    "eq": "100000.0000",
                                    "availEq": "85000.0000",
                                    "frozenBal": "15000.0000",
                                }
                            ]
                        }
                    ],
                }

            def get_positions(self):
                """
                模拟获取持仓信息
                """
                return {
                    "code": "0",
                    "msg": "success",
                    "data": [
                        {
                            "instId": "ETH-USDT-SWAP",
                            "posSide": "long",
                            "pos": "5.0000",
                            "avgPx": "2500.0000",
                            "upl": "1250.0000",
                            "im": "6250.0000",
                            "lever": "20.0000",
                            "liqPx": "2375.0000",
                        }
                    ],
                }

            def get_open_orders(self, symbol):
                """
                模拟获取未成交订单
                """
                return {
                    "code": "0",
                    "msg": "success",
                    "data": [
                        {
                            "ordId": "1234567890",
                            "clOrdId": "client_12345",
                            "instId": "ETH-USDT-SWAP",
                            "side": "buy",
                            "posSide": "long",
                            "ordType": "limit",
                            "px": "2450.0000",
                            "sz": "2.0000",
                            "accFillSz": "0.0000",
                            "state": "live",
                            "cTime": "2026-01-11T15:00:00.000Z",
                        },
                        {
                            "ordId": "1234567891",
                            "clOrdId": "client_12346",
                            "instId": "ETH-USDT-SWAP",
                            "side": "sell",
                            "posSide": "short",
                            "ordType": "limit",
                            "px": "2550.0000",
                            "sz": "3.0000",
                            "accFillSz": "0.0000",
                            "state": "live",
                            "cTime": "2026-01-11T15:30:00.000Z",
                        },
                    ],
                }

        return MockOrderExecution()

    def save_snapshot_to_file(
        self, snapshot: dict[str, Any], file_path: str = "portfolio_snapshot.json"
    ) -> None:
        """
        将快照保存到JSON文件

        Args:
            snapshot: 投资组合快照数据
            file_path: 保存文件路径
        """
        logger.info(f"保存快照到文件: {file_path}")

        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(snapshot, f, indent=2, ensure_ascii=False)

        logger.info(f"快照已成功保存到 {file_path}")


if __name__ == "__main__":
    # 测试代码
    import os
    import sys

    # 添加项目根目录到Python路径
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../..")))

    # 示例配置
    config = {"exchange": "okx", "trading_mode": "dry_run"}

    try:
        # 创建PortfolioSnapshot实例
        snapshot_generator = PortfolioSnapshot(config)

        # 获取快照
        snapshot = snapshot_generator.get_portfolio_snapshot()

        # 保存到文件
        snapshot_generator.save_snapshot_to_file(snapshot)

        logger.info("投资组合快照生成和保存成功")
    except Exception as e:
        logger.error(f"生成快照时出错: {e}")
        raise
