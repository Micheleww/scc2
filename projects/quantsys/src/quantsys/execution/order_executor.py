#!/usr/bin/env python3
"""
订单执行器
订单执行的核心逻辑，负责执行单个订单
"""

import logging
from typing import Any

from .exceptions import (
    ExchangeException,
    ExecutionException,
    ValidationException,
    handle_execution_errors,
)
from .exchange_adapter import ExchangeAdapter
from .order_ids import OrderIdManager
from .order_validator import OrderValidator

# 配置日志
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class OrderExecutor:
    """
    订单执行器
    负责执行单个订单的核心逻辑
    """

    def __init__(
        self,
        exchange_adapter: ExchangeAdapter,
        order_id_manager: OrderIdManager,
        order_validator: OrderValidator | None = None,
    ):
        """
        初始化订单执行器

        Args:
            exchange_adapter: 交易所适配器
            order_id_manager: 订单ID管理器
            order_validator: 订单验证器（可选）
        """
        self.exchange_adapter = exchange_adapter
        self.order_id_manager = order_id_manager
        self.order_validator = order_validator or OrderValidator()
        logger.info("OrderExecutor initialized")

    @handle_execution_errors
    def execute_order(
        self,
        symbol: str,
        side: str,
        order_type: str,
        amount: float,
        price: float | None = None,
        params: dict[str, Any] = None,
    ) -> dict[str, Any]:
        """
        执行订单

        Args:
            symbol: 交易对
            side: 买卖方向
            order_type: 订单类型
            amount: 交易数量
            price: 交易价格（限价单需要）
            params: 其他参数

        Returns:
            result: 订单创建结果
        """
        params = params or {}

        # 1. 验证订单
        validation = self.order_validator.validate_order(symbol, side, order_type, amount, price)
        if not validation.valid:
            raise ValidationException(
                errors=validation.errors,
                order={"symbol": symbol, "side": side, "amount": amount, "price": price},
            )

        # 2. 生成clientOrderId
        strategy_id = params.get("strategy_id", "default")
        client_order_id = self.order_id_manager.generate_client_order_id(
            strategy_id=strategy_id, symbol=symbol, side=side, price=price or 0.0, amount=amount
        )

        logger.info(
            f"执行订单: {side} {order_type} {symbol} {amount} {price}, clientOrderId: {client_order_id}"
        )

        # 3. 幂等性检查
        if self.order_id_manager.check_order_exists(client_order_id):
            existing_order = self.order_id_manager.get_order_by_client_id(client_order_id)
            logger.info(f"订单已存在，返回既有结果: {existing_order}")
            return {
                "code": "0",
                "msg": "Order already exists",
                "data": [
                    {
                        "ordId": existing_order.get("exchange_order_id"),
                        "clOrdId": client_order_id,
                        "state": existing_order.get("status", "unknown").lower(),
                    }
                ],
            }

        # 4. 初始化订单到账本
        self.order_id_manager.add_order(
            client_order_id=client_order_id,
            symbol=symbol,
            side=side,
            order_type=order_type,
            amount=amount,
            price=price,
            strategy_version=params.get("strategy_version"),
            factor_version=params.get("factor_version"),
            run_id=params.get("run_id"),
            feature_snapshot_hash=params.get("feature_snapshot_hash"),
        )

        # 5. 添加clientOrderId到参数
        params["clOrdId"] = client_order_id

        # 6. 调用交易所适配器下单
        self.order_id_manager.update_order_status(client_order_id, "SENT")

        try:
            result = self.exchange_adapter.place_order(
                symbol=symbol,
                side=side,
                order_type=order_type,
                amount=amount,
                price=price,
                params=params,
            )

            # 7. 更新订单状态
            if result.get("code") == "0" and result.get("data"):
                order_data = result["data"][0]
                exchange_order_id = order_data.get("ordId")

                # 更新订单状态为ACK并保存交易所订单ID
                self.order_id_manager.update_order_status(
                    client_order_id=client_order_id,
                    status="ACK",
                    exchange_order_id=exchange_order_id,
                )
            else:
                # 订单发送失败，更新状态为REJECTED
                self.order_id_manager.update_order_status(client_order_id, "REJECTED")
                error_msg = result.get("msg", "Unknown error")
                exchange_name = getattr(self.exchange_adapter, "exchange", "unknown")
                raise ExchangeException(
                    message=f"Exchange rejected order: {error_msg}",
                    exchange=exchange_name,
                    api_response=result,
                )

            return result

        except Exception as e:
            # 更新订单状态为REJECTED
            self.order_id_manager.update_order_status(client_order_id, "REJECTED")
            raise ExecutionException(
                message=f"Order execution failed: {str(e)}",
                order={
                    "symbol": symbol,
                    "side": side,
                    "amount": amount,
                    "price": price,
                    "client_order_id": client_order_id,
                },
                cause=e,
            )

    @handle_execution_errors
    def cancel_order(self, symbol: str, order_id: str) -> dict[str, Any]:
        """
        取消订单

        Args:
            symbol: 交易对
            order_id: 订单ID

        Returns:
            result: 撤单结果
        """
        # 验证撤单请求
        validation = self.order_validator.validate_cancel_order(symbol, order_id)
        if not validation.valid:
            raise ValidationException(
                errors=validation.errors, order={"symbol": symbol, "order_id": order_id}
            )

        try:
            # 调用交易所适配器撤单
            result = self.exchange_adapter.cancel_order(symbol, order_id)

            # 更新本地订单状态
            if result.get("code") == "0" and result.get("data"):
                for data_item in result["data"]:
                    client_order_id = data_item.get("clOrdId", "")
                    if client_order_id:
                        self.order_id_manager.update_order_status(
                            client_order_id, "CANCELED", order_id
                        )
            else:
                error_msg = result.get("msg", "Unknown error")
                exchange_name = getattr(self.exchange_adapter, "exchange", "unknown")
                raise ExchangeException(
                    message=f"Exchange rejected cancel: {error_msg}",
                    exchange=exchange_name,
                    api_response=result,
                )

            return result

        except Exception as e:
            raise ExecutionException(
                message=f"Cancel order failed: {str(e)}",
                order={"symbol": symbol, "order_id": order_id},
                cause=e,
            )

    def get_order_status(self, symbol: str, order_id: str) -> dict[str, Any]:
        """
        查询订单状态

        Args:
            symbol: 交易对
            order_id: 订单ID

        Returns:
            result: 订单状态
        """
        # 调用交易所适配器查询订单
        result = self.exchange_adapter.get_order(symbol, order_id)

        # 更新本地订单状态
        if result.get("code") == "0" and result.get("data"):
            order_data = result["data"][0]
            client_order_id = order_data.get("clOrdId", "")

            if client_order_id:
                # 映射交易所状态到本地状态
                status_map = {
                    "pending": "SENT",
                    "live": "OPEN",
                    "partially_filled": "PARTIAL",
                    "filled": "FILLED",
                    "canceled": "CANCELED",
                    "rejected": "REJECTED",
                }

                exchange_status = order_data.get("state", "pending")
                local_status = status_map.get(exchange_status, "SENT")

                # 更新订单状态
                self.order_id_manager.update_order_status(client_order_id, local_status, order_id)

                # 更新成交信息
                acc_fill_sz = float(order_data.get("accFillSz", "0"))
                fill_px = float(order_data.get("fillPx", "0"))
                if acc_fill_sz > 0:
                    self.order_id_manager.update_order_fill(client_order_id, acc_fill_sz, fill_px)

        return result

    def place_order(
        self,
        symbol: str,
        side: str,
        order_type: str,
        amount: float,
        price: float | None = None,
        params: dict[str, Any] = None,
    ) -> dict[str, Any]:
        """
        下单（兼容接口，供order_splitter使用）

        Args:
            symbol: 交易对
            side: 买卖方向
            order_type: 订单类型
            amount: 交易数量
            price: 交易价格（限价单需要）
            params: 其他参数

        Returns:
            result: 订单创建结果
        """
        return self.execute_order(symbol, side, order_type, amount, price, params)
