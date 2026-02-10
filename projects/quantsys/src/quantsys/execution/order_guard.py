#!/usr/bin/env python3
"""
异常订单护栏模块
检测重复下单/价格偏离/超量/频繁撤单/连续失败，触发时设置为reduce-only或BLOCKED

!!! 核心红线资产：仅允许经主控批准修改 !!!
任何对本文件的修改必须经过严格的审查和批准流程
详见 docs/core_assets.md
"""

import logging
import time
from datetime import datetime
from typing import Any

# 配置日志
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class OrderGuard:
    """
    异常订单护栏类，用于检测和处理异常订单情况
    """

    def __init__(self, config: dict[str, Any]):
        """
        初始化订单护栏

        Args:
            config: 配置信息
        """
        self.config = config

        # 护栏规则配置
        self.rules_config = config.get(
            "rules",
            {
                # 重复下单检测：同一策略同一品种同一方向短时间内重复下单
                "duplicate_order": {
                    "enabled": True,
                    "time_window": 10,  # 时间窗口（秒）
                    "max_orders": 2,  # 最大允许订单数
                    "action": "block",  # 触发动作：block/reduce-only
                },
                # 价格偏离检测：订单价格与市场价格偏离过大
                "price_deviation": {
                    "enabled": True,
                    "max_deviation": 0.05,  # 最大允许偏离比例（5%）
                    "action": "block",  # 触发动作：block/reduce-only
                },
                # 超量检测：订单数量超过账户权益的一定比例
                "excessive_amount": {
                    "enabled": True,
                    "max_amount_ratio": 0.1,  # 最大允许比例（10%）
                    "action": "block",  # 触发动作：block/reduce-only
                },
                # 频繁撤单检测：短时间内频繁撤单
                "frequent_cancel": {
                    "enabled": True,
                    "time_window": 60,  # 时间窗口（秒）
                    "max_cancels": 5,  # 最大允许撤单数
                    "action": "reduce-only",  # 触发动作：block/reduce-only
                },
                # 连续失败检测：连续下单失败
                "consecutive_failures": {
                    "enabled": True,
                    "max_failures": 3,  # 最大允许连续失败次数
                    "action": "block",  # 触发动作：block/reduce-only
                },
            },
        )

        # 状态追踪
        self.order_history: list[dict[str, Any]] = []  # 订单历史记录
        self.cancel_history: list[float] = []  # 撤单时间记录
        self.failure_count: dict[str, int] = {}  # 策略连续失败计数
        self.guard_status: dict[str, str] = {}  # 护栏状态：正常/blocked/reduce-only

        # 事件流
        self.event_log: list[dict[str, Any]] = []

        # 报告
        self.reports: list[dict[str, Any]] = []

        logger.info("异常订单护栏初始化完成")

    def check_order(
        self, order_data: dict[str, Any], market_data: dict[str, Any], account_data: dict[str, Any]
    ) -> dict[str, Any]:
        """
        检查订单是否符合护栏规则

        Args:
            order_data: 订单数据
            market_data: 市场数据
            account_data: 账户数据

        Returns:
            检查结果，包含是否通过、原因、建议动作
        """
        # 当前时间
        current_time = time.time()

        # 检查策略是否已被blocked
        strategy_id = order_data.get("strategy_id", "default")
        if self.guard_status.get(strategy_id) == "blocked":
            return {
                "passed": False,
                "reason": f"策略 {strategy_id} 已被护栏blocked",
                "action": "block",
                "status": self.guard_status[strategy_id],
            }

        # 检查策略是否为reduce-only
        is_reduce_only = self.guard_status.get(strategy_id) == "reduce-only"
        if is_reduce_only and order_data["side"] != "sell":
            return {
                "passed": False,
                "reason": f"策略 {strategy_id} 处于reduce-only状态，只允许卖出",
                "action": "reduce-only",
                "status": self.guard_status[strategy_id],
            }

        # 执行各项规则检查
        violations = []

        # 1. 重复下单检测
        if self.rules_config["duplicate_order"]["enabled"]:
            duplicate_result = self._check_duplicate_order(order_data, current_time)
            if not duplicate_result["passed"]:
                violations.append(duplicate_result)

        # 2. 价格偏离检测
        if self.rules_config["price_deviation"]["enabled"]:
            price_result = self._check_price_deviation(order_data, market_data)
            if not price_result["passed"]:
                violations.append(price_result)

        # 3. 超量检测
        if self.rules_config["excessive_amount"]["enabled"]:
            excessive_result = self._check_excessive_amount(order_data, market_data, account_data)
            if not excessive_result["passed"]:
                violations.append(excessive_result)

        # 4. 频繁撤单检测
        if self.rules_config["frequent_cancel"]["enabled"]:
            cancel_result = self._check_frequent_cancel(current_time)
            if not cancel_result["passed"]:
                violations.append(cancel_result)

        # 5. 连续失败检测
        if self.rules_config["consecutive_failures"]["enabled"]:
            failure_result = self._check_consecutive_failures(strategy_id)
            if not failure_result["passed"]:
                violations.append(failure_result)

        # 处理检查结果
        if violations:
            # 合并违规结果，取最严格的动作
            actions = [violation["action"] for violation in violations]
            final_action = "block" if "block" in actions else "reduce-only"

            # 更新护栏状态
            self.guard_status[strategy_id] = final_action

            # 记录事件
            event = {
                "timestamp": datetime.utcnow().isoformat() + "Z",
                "event_type": "guard_violation",
                "strategy_id": strategy_id,
                "order_data": order_data,
                "violations": violations,
                "action": final_action,
            }
            self.event_log.append(event)

            return {
                "passed": False,
                "reason": "; ".join([v["reason"] for v in violations]),
                "action": final_action,
                "status": final_action,
            }

        # 检查通过，记录订单
        self._record_order(order_data, current_time)

        return {
            "passed": True,
            "reason": "订单符合所有护栏规则",
            "action": "normal",
            "status": "normal",
        }

    def _check_duplicate_order(
        self, order_data: dict[str, Any], current_time: float
    ) -> dict[str, Any]:
        """
        检查重复下单
        """
        strategy_id = order_data.get("strategy_id", "default")
        symbol = order_data["symbol"]
        side = order_data["side"]

        # 获取规则配置
        rule_config = self.rules_config["duplicate_order"]
        time_window = rule_config["time_window"]
        max_orders = rule_config["max_orders"]

        # 筛选指定时间窗口内的同一策略、同一品种、同一方向的订单
        recent_orders = [
            order
            for order in self.order_history
            if order["strategy_id"] == strategy_id
            and order["symbol"] == symbol
            and order["side"] == side
            and (current_time - order["timestamp"]) <= time_window
        ]

        if len(recent_orders) >= max_orders:
            return {
                "passed": False,
                "reason": f"短时间内同一策略同一品种同一方向订单数量超过限制（{max_orders}）",
                "rule": "duplicate_order",
                "action": rule_config["action"],
            }

        return {
            "passed": True,
            "reason": "未触发重复下单规则",
            "rule": "duplicate_order",
            "action": "normal",
        }

    def _check_price_deviation(
        self, order_data: dict[str, Any], market_data: dict[str, Any]
    ) -> dict[str, Any]:
        """
        检查价格偏离
        """
        if order_data["order_type"] == "market":
            return {
                "passed": True,
                "reason": "市价单不检查价格偏离",
                "rule": "price_deviation",
                "action": "normal",
            }

        # 获取规则配置
        rule_config = self.rules_config["price_deviation"]
        max_deviation = rule_config["max_deviation"]

        # 获取市场价格
        symbol = order_data["symbol"]
        order_price = order_data["price"]

        if symbol not in market_data:
            return {
                "passed": True,
                "reason": "无市场数据，跳过价格偏离检查",
                "rule": "price_deviation",
                "action": "normal",
            }

        market_price = market_data[symbol].get("price", 0)
        if market_price == 0:
            return {
                "passed": True,
                "reason": "市场价格为0，跳过价格偏离检查",
                "rule": "price_deviation",
                "action": "normal",
            }

        # 计算偏离比例
        deviation = abs(order_price - market_price) / market_price

        if deviation > max_deviation:
            return {
                "passed": False,
                "reason": f"订单价格与市场价格偏离过大（偏离比例：{deviation:.2%}，最大允许：{max_deviation:.2%}）",
                "rule": "price_deviation",
                "action": rule_config["action"],
            }

        return {
            "passed": True,
            "reason": "未触发价格偏离规则",
            "rule": "price_deviation",
            "action": "normal",
        }

    def _check_excessive_amount(
        self, order_data: dict[str, Any], market_data: dict[str, Any], account_data: dict[str, Any]
    ) -> dict[str, Any]:
        """
        检查超量
        """
        # 获取规则配置
        rule_config = self.rules_config["excessive_amount"]
        max_amount_ratio = rule_config["max_amount_ratio"]

        # 计算订单金额
        symbol = order_data["symbol"]
        amount = order_data["amount"]

        # 获取市场价格
        market_price = market_data.get(symbol, {}).get("price", 0)
        if market_price == 0:
            # 如果没有市场价格，使用订单价格
            market_price = order_data.get("price", 0)

        if market_price == 0:
            return {
                "passed": True,
                "reason": "无法计算订单金额，跳过超量检查",
                "rule": "excessive_amount",
                "action": "normal",
            }

        order_value = amount * market_price
        equity = account_data.get("equity", 0)

        if equity == 0:
            return {
                "passed": True,
                "reason": "账户权益为0，跳过超量检查",
                "rule": "excessive_amount",
                "action": "normal",
            }

        # 计算订单金额占账户权益的比例
        amount_ratio = order_value / equity

        if amount_ratio > max_amount_ratio:
            return {
                "passed": False,
                "reason": f"订单金额占账户权益比例过大（{amount_ratio:.2%}，最大允许：{max_amount_ratio:.2%}）",
                "rule": "excessive_amount",
                "action": rule_config["action"],
            }

        return {
            "passed": True,
            "reason": "未触发超量规则",
            "rule": "excessive_amount",
            "action": "normal",
        }

    def _check_frequent_cancel(self, current_time: float) -> dict[str, Any]:
        """
        检查频繁撤单
        """
        # 获取规则配置
        rule_config = self.rules_config["frequent_cancel"]
        time_window = rule_config["time_window"]
        max_cancels = rule_config["max_cancels"]

        # 筛选指定时间窗口内的撤单
        recent_cancels = [
            cancel_time
            for cancel_time in self.cancel_history
            if (current_time - cancel_time) <= time_window
        ]

        if len(recent_cancels) > max_cancels:
            return {
                "passed": False,
                "reason": f"短时间内撤单次数超过限制（{max_cancels}）",
                "rule": "frequent_cancel",
                "action": rule_config["action"],
            }

        return {
            "passed": True,
            "reason": "未触发频繁撤单规则",
            "rule": "frequent_cancel",
            "action": "normal",
        }

    def _check_consecutive_failures(self, strategy_id: str) -> dict[str, Any]:
        """
        检查连续失败
        """
        # 获取规则配置
        rule_config = self.rules_config["consecutive_failures"]
        max_failures = rule_config["max_failures"]

        # 获取当前策略的连续失败次数
        failure_count = self.failure_count.get(strategy_id, 0)

        if failure_count >= max_failures:
            return {
                "passed": False,
                "reason": f"策略连续下单失败次数超过限制（{max_failures}）",
                "rule": "consecutive_failures",
                "action": rule_config["action"],
            }

        return {
            "passed": True,
            "reason": "未触发连续失败规则",
            "rule": "consecutive_failures",
            "action": "normal",
        }

    def _record_order(self, order_data: dict[str, Any], timestamp: float) -> None:
        """
        记录订单
        """
        order_record = {
            "strategy_id": order_data.get("strategy_id", "default"),
            "symbol": order_data["symbol"],
            "side": order_data["side"],
            "order_type": order_data["order_type"],
            "amount": order_data["amount"],
            "price": order_data.get("price"),
            "timestamp": timestamp,
        }

        self.order_history.append(order_record)

        # 清理过期订单历史（保留最近1小时）
        one_hour_ago = timestamp - 3600
        self.order_history = [
            order for order in self.order_history if order["timestamp"] >= one_hour_ago
        ]

    def record_cancel(self) -> None:
        """
        记录撤单
        """
        current_time = time.time()
        self.cancel_history.append(current_time)

        # 清理过期撤单历史（保留最近1小时）
        one_hour_ago = current_time - 3600
        self.cancel_history = [
            cancel_time for cancel_time in self.cancel_history if cancel_time >= one_hour_ago
        ]

    def record_order_result(self, strategy_id: str, success: bool) -> None:
        """
        记录订单结果

        Args:
            strategy_id: 策略ID
            success: 是否成功
        """
        if success:
            # 重置连续失败计数
            if strategy_id in self.failure_count:
                del self.failure_count[strategy_id]

            # 如果策略处于blocked或reduce-only状态，恢复正常
            if strategy_id in self.guard_status:
                del self.guard_status[strategy_id]
                logger.info(f"策略 {strategy_id} 已恢复正常状态")
        else:
            # 增加连续失败计数
            self.failure_count[strategy_id] = self.failure_count.get(strategy_id, 0) + 1
            logger.warning(f"策略 {strategy_id} 连续失败次数: {self.failure_count[strategy_id]}")

    def generate_report(self) -> dict[str, Any]:
        """
        生成订单护栏报告

        Returns:
            报告数据
        """
        report = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "guard_status": self.guard_status.copy(),
            "order_history_count": len(self.order_history),
            "cancel_history_count": len(self.cancel_history),
            "failure_count": self.failure_count.copy(),
            "event_log_count": len(self.event_log),
            "recent_events": self.event_log[-10:],  # 最近10个事件
        }

        self.reports.append(report)

        # 清理旧报告（保留最近10个）
        if len(self.reports) > 10:
            self.reports = self.reports[-10:]

        return report

    def get_event_log(self) -> list[dict[str, Any]]:
        """
        获取事件日志

        Returns:
            事件日志列表
        """
        return self.event_log

    def clear_event_log(self) -> None:
        """
        清空事件日志
        """
        self.event_log = []

    def get_status(self) -> dict[str, str]:
        """
        获取护栏状态

        Returns:
            护栏状态字典
        """
        return self.guard_status.copy()

    def reset_status(self, strategy_id: str | None = None) -> None:
        """
        重置护栏状态

        Args:
            strategy_id: 可选，指定策略ID，不指定则重置所有
        """
        if strategy_id:
            if strategy_id in self.guard_status:
                del self.guard_status[strategy_id]
            if strategy_id in self.failure_count:
                del self.failure_count[strategy_id]
        else:
            self.guard_status.clear()
            self.failure_count.clear()

        logger.info(f"已重置{strategy_id if strategy_id else '所有'}策略的护栏状态")
