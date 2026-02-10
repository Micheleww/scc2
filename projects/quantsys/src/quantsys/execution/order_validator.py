#!/usr/bin/env python3
"""
订单验证器
验证订单的合法性，包括参数验证、格式验证等
"""

import logging
from dataclasses import dataclass
from typing import Any

# 配置日志
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


@dataclass
class ValidationResult:
    """验证结果数据类"""

    valid: bool
    errors: list
    warnings: list = None

    def __post_init__(self):
        if self.warnings is None:
            self.warnings = []


class OrderValidator:
    """
    订单验证器
    验证订单的合法性
    """

    def __init__(self, config: dict[str, Any] = None):
        """
        初始化订单验证器

        Args:
            config: 配置信息
        """
        self.config = config or {}
        self.min_amount = self.config.get("min_amount", 0.01)
        self.max_amount = self.config.get("max_amount", 1000000.0)
        self.min_price = self.config.get("min_price", 0.0001)
        self.max_price = self.config.get("max_price", 1000000.0)
        logger.info("OrderValidator initialized")

    def validate_order(
        self, symbol: str, side: str, order_type: str, amount: float, price: float | None = None
    ) -> ValidationResult:
        """
        验证订单

        Args:
            symbol: 交易对
            side: 买卖方向
            order_type: 订单类型
            amount: 交易数量
            price: 交易价格（限价单需要）

        Returns:
            ValidationResult: 验证结果
        """
        errors = []
        warnings = []

        # 1. 验证交易对格式
        if not symbol or not isinstance(symbol, str):
            errors.append("交易对不能为空且必须是字符串")
        elif len(symbol) < 3:
            errors.append("交易对格式无效")

        # 2. 验证买卖方向
        if side not in ["buy", "sell"]:
            errors.append(f"买卖方向无效: {side}，必须是 'buy' 或 'sell'")

        # 3. 验证订单类型
        if order_type not in ["market", "limit", "stop", "stop_limit"]:
            errors.append(f"订单类型无效: {order_type}")

        # 4. 验证数量
        if not isinstance(amount, (int, float)) or amount <= 0:
            errors.append(f"交易数量无效: {amount}，必须大于0")
        elif amount < self.min_amount:
            errors.append(f"交易数量 {amount} 小于最小限制 {self.min_amount}")
        elif amount > self.max_amount:
            errors.append(f"交易数量 {amount} 超过最大限制 {self.max_amount}")

        # 5. 验证价格（限价单必须提供价格）
        if order_type in ["limit", "stop_limit"]:
            if price is None:
                errors.append("限价单必须提供价格")
            elif not isinstance(price, (int, float)) or price <= 0:
                errors.append(f"价格无效: {price}，必须大于0")
            elif price < self.min_price:
                errors.append(f"价格 {price} 小于最小限制 {self.min_price}")
            elif price > self.max_price:
                errors.append(f"价格 {price} 超过最大限制 {self.max_price}")

        # 6. 验证交易对格式（简化验证）
        if symbol and "-" not in symbol and "/" not in symbol:
            warnings.append(f"交易对格式可能不正确: {symbol}")

        # 记录验证结果
        if errors:
            logger.warning(f"订单验证失败: {errors}")
        elif warnings:
            logger.info(f"订单验证通过，但有警告: {warnings}")
        else:
            logger.debug(f"订单验证通过: {symbol} {side} {amount} @ {price}")

        return ValidationResult(valid=len(errors) == 0, errors=errors, warnings=warnings)

    def validate_cancel_order(self, symbol: str, order_id: str) -> ValidationResult:
        """
        验证撤单请求

        Args:
            symbol: 交易对
            order_id: 订单ID

        Returns:
            ValidationResult: 验证结果
        """
        errors = []
        warnings = []

        # 验证交易对
        if not symbol or not isinstance(symbol, str):
            errors.append("交易对不能为空且必须是字符串")

        # 验证订单ID
        if not order_id or not isinstance(order_id, str):
            errors.append("订单ID不能为空且必须是字符串")

        return ValidationResult(valid=len(errors) == 0, errors=errors, warnings=warnings)
