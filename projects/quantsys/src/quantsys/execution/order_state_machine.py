#!/usr/bin/env python3
"""
订单状态机模块
管理订单状态转换和状态验证
"""

from enum import Enum
from typing import Any


class OrderStatus(Enum):
    """
    订单状态枚举
    """

    CREATED = "CREATED"  # 订单已创建
    SENT = "SENT"  # 订单已发送到交易所
    ACK = "ACK"  # 交易所已确认订单
    OPEN = "OPEN"  # 订单已挂单
    PARTIAL = "PARTIAL"  # 部分成交
    FILLED = "FILLED"  # 完全成交
    CANCELED = "CANCELED"  # 已取消
    REJECTED = "REJECTED"  # 已拒绝


class OrderStateMachine:
    """
    订单状态机
    管理订单状态转换和验证
    """

    # 状态转换规则：{当前状态: {允许的下一个状态}}
    _TRANSITION_RULES = {
        OrderStatus.CREATED: {"SENT", "REJECTED"},
        OrderStatus.SENT: {"ACK", "REJECTED"},
        OrderStatus.ACK: {"OPEN", "CANCELED", "REJECTED"},
        OrderStatus.OPEN: {"PARTIAL", "FILLED", "CANCELED"},
        OrderStatus.PARTIAL: {"FILLED", "CANCELED"},
        OrderStatus.FILLED: set(),  # 最终状态
        OrderStatus.CANCELED: set(),  # 最终状态
        OrderStatus.REJECTED: set(),  # 最终状态
    }

    @staticmethod
    def is_valid_transition(current_status: str, new_status: str) -> bool:
        """
        检查状态转换是否有效

        Args:
            current_status: 当前状态
            new_status: 新状态

        Returns:
            valid: 是否有效
        """
        try:
            current = OrderStatus(current_status)

            # 检查是否允许从current转换到new
            return new_status in OrderStateMachine._TRANSITION_RULES[current]
        except ValueError:
            # 无效的状态值
            return False

    @staticmethod
    def get_valid_transitions(current_status: str) -> list:
        """
        获取当前状态允许的所有转换

        Args:
            current_status: 当前状态

        Returns:
            valid_transitions: 有效转换列表
        """
        try:
            current = OrderStatus(current_status)
            return [status.value for status in OrderStateMachine._TRANSITION_RULES[current]]
        except ValueError:
            return []

    @staticmethod
    def is_final_status(status: str) -> bool:
        """
        检查状态是否为最终状态

        Args:
            status: 状态

        Returns:
            is_final: 是否为最终状态
        """
        return len(OrderStateMachine.get_valid_transitions(status)) == 0

    @staticmethod
    def is_active_status(status: str) -> bool:
        """
        检查状态是否为活跃状态（pending/open/partial/filled）

        Args:
            status: 状态

        Returns:
            is_active: 是否为活跃状态
        """
        active_statuses = [
            OrderStatus.CREATED.value,
            OrderStatus.SENT.value,
            OrderStatus.ACK.value,
            OrderStatus.OPEN.value,
            OrderStatus.PARTIAL.value,
            OrderStatus.FILLED.value,
        ]
        return status in active_statuses

    @staticmethod
    def validate_order(order: dict[str, Any]) -> bool:
        """
        验证订单数据完整性

        Args:
            order: 订单数据

        Returns:
            valid: 是否有效
        """
        required_fields = [
            "clientOrderId",
            "symbol",
            "side",
            "order_type",
            "amount",
            "status",
            "create_ts",
            "update_ts",
        ]

        # 检查必填字段
        for field in required_fields:
            if field not in order:
                return False

        # 检查状态是否有效
        try:
            OrderStatus(order["status"])
        except ValueError:
            return False

        return True
