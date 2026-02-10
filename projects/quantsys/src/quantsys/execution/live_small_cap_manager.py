#!/usr/bin/env python3
"""
Live小仓参数模板+硬限制管理器

实现单品种、最大仓位、最大下单频率、禁止开新仓开关等硬限制功能
配置化且写入审计事件，默认禁止live
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

# 配置日志
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


@dataclass
class LiveSmallCapConfig:
    """
    Live小仓参数模板配置类
    """

    # 基础配置
    enabled: bool = False

    # 单品种限制
    single_symbol_limit: dict[str, Any] = field(
        default_factory=lambda: {
            "enabled": False,
            "max_positions": 1,
            "max_order_amount": 1000,
            "max_daily_trades": 10,
        }
    )

    # 仓位限制
    position_limits: dict[str, Any] = field(
        default_factory=lambda: {
            "enabled": False,
            "max_total_position_ratio": 0.1,
            "max_single_position_ratio": 0.05,
            "max_leverage": 2,
        }
    )

    # 订单频率限制
    order_frequency_limit: dict[str, Any] = field(
        default_factory=lambda: {
            "enabled": False,
            "max_orders_per_minute": 1,
            "max_orders_per_hour": 10,
            "max_orders_per_day": 50,
        }
    )

    # 新仓限制
    new_positions_restriction: dict[str, Any] = field(
        default_factory=lambda: {
            "enabled": False,
            "allow_new_positions": False,
            "allow_reduce_only": True,
        }
    )


@dataclass
class OrderFrequencyStats:
    """
    订单频率统计类
    """

    orders_per_minute: list[float] = field(default_factory=list)
    orders_per_hour: list[float] = field(default_factory=list)
    orders_per_day: list[float] = field(default_factory=list)
    last_reset: dict[str, float] = field(
        default_factory=lambda: {"minute": time.time(), "hour": time.time(), "day": time.time()}
    )


class LiveSmallCapManager:
    """
    Live小仓参数模板和硬限制管理器
    """

    def __init__(self, config: dict[str, Any]):
        """
        初始化Live小仓参数模板管理器

        Args:
            config: 配置信息
        """
        self.config = config
        self.live_config: LiveSmallCapConfig | None = None
        self.order_frequency_stats = OrderFrequencyStats()

        # 初始化审计事件记录
        self.audit_events: list[dict[str, Any]] = []

        # 单品种交易统计
        self.symbol_trade_stats: dict[str, int] = {}

        # 确保证据目录存在
        self.evidence_dir = Path("data/evidence/live_small_cap")
        self.evidence_dir.mkdir(parents=True, exist_ok=True)

        # 加载配置
        self.load_config(config)

        logger.info("Live小仓参数模板管理器初始化完成")

    def load_config(self, config: dict[str, Any]) -> None:
        """
        加载live小仓参数模板配置

        Args:
            config: 配置信息
        """
        # 提取live配置
        live_config = config.get("live", {})
        small_cap_template = live_config.get("small_cap_template", {})

        # 创建LiveSmallCapConfig实例
        self.live_config = LiveSmallCapConfig(
            enabled=small_cap_template.get("enabled", False),
            single_symbol_limit=small_cap_template.get("single_symbol_limit", {}),
            position_limits=small_cap_template.get("position_limits", {}),
            order_frequency_limit=small_cap_template.get("order_frequency_limit", {}),
            new_positions_restriction=small_cap_template.get("new_positions_restriction", {}),
        )

        # 记录审计事件
        self._log_audit_event(
            "config_loaded", {"config": small_cap_template, "timestamp": time.time()}
        )

        logger.info(f"Live小仓参数模板配置已加载: enabled={self.live_config.enabled}")

    def _log_audit_event(self, event_type: str, event_data: dict[str, Any]) -> None:
        """
        记录审计事件

        Args:
            event_type: 事件类型
            event_data: 事件数据
        """
        event = {
            "event_id": f"audit_{int(time.time() * 1000)}",
            "event_type": event_type,
            "event_data": event_data,
            "timestamp": time.time(),
            "datetime": datetime.now().isoformat(),
        }

        self.audit_events.append(event)

        # 保存审计事件到文件
        self._save_audit_events()

    def _save_audit_events(self) -> None:
        """
        保存审计事件到文件
        """
        audit_file = self.evidence_dir / f"audit_events_{datetime.now().strftime('%Y%m%d')}.json"

        # 读取现有事件
        existing_events = []
        if audit_file.exists():
            with open(audit_file, encoding="utf-8") as f:
                existing_events = json.load(f)

        # 合并事件
        all_events = existing_events + self.audit_events

        # 保存到文件
        with open(audit_file, "w", encoding="utf-8") as f:
            json.dump(all_events, f, indent=2, ensure_ascii=False)

        # 清空内存中的事件
        self.audit_events = []

    def _update_order_frequency_stats(self) -> None:
        """
        更新订单频率统计
        """
        current_time = time.time()

        # 重置每分钟统计
        if current_time - self.order_frequency_stats.last_reset["minute"] >= 60:
            self.order_frequency_stats.orders_per_minute.clear()
            self.order_frequency_stats.last_reset["minute"] = current_time

        # 重置每小时统计
        if current_time - self.order_frequency_stats.last_reset["hour"] >= 3600:
            self.order_frequency_stats.orders_per_hour.clear()
            self.order_frequency_stats.last_reset["hour"] = current_time

        # 重置每天统计
        if current_time - self.order_frequency_stats.last_reset["day"] >= 86400:
            self.order_frequency_stats.orders_per_day.clear()
            self.order_frequency_stats.last_reset["day"] = current_time
            # 重置单品种交易统计
            self.symbol_trade_stats.clear()

    def check_single_symbol_limit(self, symbol: str, order_amount: float) -> dict[str, Any]:
        """
        检查单品种限制

        Args:
            symbol: 交易对
            order_amount: 订单金额

        Returns:
            Dict[str, Any]: 检查结果，包含是否通过、原因等
        """
        if not self.live_config or not self.live_config.single_symbol_limit.get("enabled", False):
            return {"passed": True, "reason": "单品种限制未启用"}

        # 获取单品种限制配置
        config = self.live_config.single_symbol_limit

        # 检查订单金额限制
        if order_amount > config.get("max_order_amount", 1000):
            reason = (
                f"订单金额 {order_amount} 超过单品种限制 {config.get('max_order_amount', 1000)}"
            )
            logger.warning(reason)
            return {"passed": False, "reason": reason}

        # 检查每日交易次数限制
        daily_trades = self.symbol_trade_stats.get(symbol, 0)
        if daily_trades >= config.get("max_daily_trades", 10):
            reason = f"{symbol} 每日交易次数 {daily_trades} 超过限制 {config.get('max_daily_trades', 10)}"
            logger.warning(reason)
            return {"passed": False, "reason": reason}

        return {"passed": True, "reason": "单品种限制检查通过"}

    def check_position_limits(
        self,
        symbol: str,
        order_amount: float,
        current_position: float,
        total_position: float,
        equity: float,
        leverage: float,
    ) -> dict[str, Any]:
        """
        检查仓位限制

        Args:
            symbol: 交易对
            order_amount: 订单金额
            current_position: 当前品种持仓金额
            total_position: 总持仓金额
            equity: 账户权益
            leverage: 使用杠杆

        Returns:
            Dict[str, Any]: 检查结果，包含是否通过、原因等
        """
        if not self.live_config or not self.live_config.position_limits.get("enabled", False):
            return {"passed": True, "reason": "仓位限制未启用"}

        # 获取仓位限制配置
        config = self.live_config.position_limits

        # 检查最大杠杆限制
        if leverage > config.get("max_leverage", 2):
            reason = f"杠杆 {leverage} 超过限制 {config.get('max_leverage', 2)}"
            logger.warning(reason)
            return {"passed": False, "reason": reason}

        # 检查单一品种仓位限制
        new_symbol_position = current_position + order_amount
        max_single_position = equity * config.get("max_single_position_ratio", 0.05)
        if new_symbol_position > max_single_position:
            reason = f"{symbol} 仓位 {new_symbol_position} 超过限制 {max_single_position}"
            logger.warning(reason)
            return {"passed": False, "reason": reason}

        # 检查总仓位限制
        new_total_position = total_position + order_amount
        max_total_position = equity * config.get("max_total_position_ratio", 0.1)
        if new_total_position > max_total_position:
            reason = f"总仓位 {new_total_position} 超过限制 {max_total_position}"
            logger.warning(reason)
            return {"passed": False, "reason": reason}

        return {"passed": True, "reason": "仓位限制检查通过"}

    def check_order_frequency_limit(self) -> dict[str, Any]:
        """
        检查订单频率限制

        Returns:
            Dict[str, Any]: 检查结果，包含是否通过、原因等
        """
        if not self.live_config or not self.live_config.order_frequency_limit.get("enabled", False):
            return {"passed": True, "reason": "订单频率限制未启用"}

        # 更新订单频率统计
        self._update_order_frequency_stats()

        # 获取订单频率限制配置
        config = self.live_config.order_frequency_limit

        # 检查每分钟订单数限制
        orders_per_minute = len(self.order_frequency_stats.orders_per_minute)
        if orders_per_minute >= config.get("max_orders_per_minute", 1):
            reason = f"每分钟订单数 {orders_per_minute} 超过限制 {config.get('max_orders_per_minute', 1)}"
            logger.warning(reason)
            return {"passed": False, "reason": reason}

        # 检查每小时订单数限制
        orders_per_hour = len(self.order_frequency_stats.orders_per_hour)
        if orders_per_hour >= config.get("max_orders_per_hour", 10):
            reason = (
                f"每小时订单数 {orders_per_hour} 超过限制 {config.get('max_orders_per_hour', 10)}"
            )
            logger.warning(reason)
            return {"passed": False, "reason": reason}

        # 检查每天订单数限制
        orders_per_day = len(self.order_frequency_stats.orders_per_day)
        if orders_per_day >= config.get("max_orders_per_day", 50):
            reason = f"每天订单数 {orders_per_day} 超过限制 {config.get('max_orders_per_day', 50)}"
            logger.warning(reason)
            return {"passed": False, "reason": reason}

        return {"passed": True, "reason": "订单频率限制检查通过"}

    def check_new_positions_restriction(
        self, side: str, current_position: float, order_amount: float
    ) -> dict[str, Any]:
        """
        检查新仓限制

        Args:
            side: 买卖方向
            current_position: 当前品种持仓金额
            order_amount: 订单金额

        Returns:
            Dict[str, Any]: 检查结果，包含是否通过、原因等
        """
        if not self.live_config or not self.live_config.new_positions_restriction.get(
            "enabled", False
        ):
            return {"passed": True, "reason": "新仓限制未启用"}

        # 获取新仓限制配置
        config = self.live_config.new_positions_restriction

        # 检查是否允许开新仓
        if not config.get("allow_new_positions", False):
            # 检查是否是开新仓操作
            if side == "buy" and current_position == 0:
                reason = "禁止开新仓"
                logger.warning(reason)
                return {"passed": False, "reason": reason}

            # 检查是否是加仓操作（增加现有仓位）
            if side == "buy" and current_position > 0:
                reason = "禁止加仓"
                logger.warning(reason)
                return {"passed": False, "reason": reason}

            # 检查是否允许减仓
            if side == "sell" and not config.get("allow_reduce_only", True):
                reason = "禁止减仓"
                logger.warning(reason)
                return {"passed": False, "reason": reason}

        return {"passed": True, "reason": "新仓限制检查通过"}

    def check_all_limits(
        self,
        symbol: str,
        side: str,
        order_amount: float,
        current_position: float,
        total_position: float,
        equity: float,
        leverage: float,
    ) -> dict[str, Any]:
        """
        检查所有限制

        Args:
            symbol: 交易对
            side: 买卖方向
            order_amount: 订单金额
            current_position: 当前品种持仓金额
            total_position: 总持仓金额
            equity: 账户权益
            leverage: 使用杠杆

        Returns:
            Dict[str, Any]: 综合检查结果
        """
        results = {
            "single_symbol_check": self.check_single_symbol_limit(symbol, order_amount),
            "position_check": self.check_position_limits(
                symbol, order_amount, current_position, total_position, equity, leverage
            ),
            "frequency_check": self.check_order_frequency_limit(),
            "new_positions_check": self.check_new_positions_restriction(
                side, current_position, order_amount
            ),
        }

        # 综合判断
        all_passed = all(result["passed"] for result in results.values())

        # 如果通过所有检查，更新统计
        if all_passed:
            self._update_order_frequency_stats()
            current_time = time.time()
            self.order_frequency_stats.orders_per_minute.append(current_time)
            self.order_frequency_stats.orders_per_hour.append(current_time)
            self.order_frequency_stats.orders_per_day.append(current_time)

            # 更新单品种交易统计
            self.symbol_trade_stats[symbol] = self.symbol_trade_stats.get(symbol, 0) + 1

            # 记录审计事件
            self._log_audit_event(
                "order_allowed",
                {
                    "symbol": symbol,
                    "side": side,
                    "order_amount": order_amount,
                    "timestamp": current_time,
                },
            )
        else:
            # 记录审计事件
            self._log_audit_event(
                "order_blocked",
                {
                    "symbol": symbol,
                    "side": side,
                    "order_amount": order_amount,
                    "reasons": [
                        result["reason"] for result in results.values() if not result["passed"]
                    ],
                    "timestamp": time.time(),
                },
            )

        return {"passed": all_passed, "results": results, "timestamp": time.time()}

    def update_config(self, new_config: dict[str, Any]) -> None:
        """
        更新配置

        Args:
            new_config: 新的配置信息
        """
        old_config = self.config.copy()
        self.config = new_config
        self.load_config(new_config)

        # 记录审计事件
        self._log_audit_event(
            "config_updated",
            {
                "old_config": old_config.get("live", {}).get("small_cap_template", {}),
                "new_config": new_config.get("live", {}).get("small_cap_template", {}),
                "timestamp": time.time(),
            },
        )

        logger.info("Live小仓参数模板配置已更新")

    def get_current_status(self) -> dict[str, Any]:
        """
        获取当前状态

        Returns:
            Dict[str, Any]: 当前状态信息
        """
        self._update_order_frequency_stats()

        return {
            "live_config": {
                "enabled": self.live_config.enabled if self.live_config else False,
                "single_symbol_limit": self.live_config.single_symbol_limit
                if self.live_config
                else {},
                "position_limits": self.live_config.position_limits if self.live_config else {},
                "order_frequency_limit": self.live_config.order_frequency_limit
                if self.live_config
                else {},
                "new_positions_restriction": self.live_config.new_positions_restriction
                if self.live_config
                else {},
            },
            "order_frequency": {
                "orders_per_minute": len(self.order_frequency_stats.orders_per_minute),
                "orders_per_hour": len(self.order_frequency_stats.orders_per_hour),
                "orders_per_day": len(self.order_frequency_stats.orders_per_day),
            },
            "symbol_trade_stats": self.symbol_trade_stats,
            "timestamp": time.time(),
            "datetime": datetime.now().isoformat(),
        }

    def run_self_test(self) -> dict[str, Any]:
        """
        运行自测

        Returns:
            Dict[str, Any]: 自测结果
        """
        test_result = {
            "test_name": "Live Small Cap Manager Self Test",
            "timestamp": time.time(),
            "tests": [],
            "overall_result": "PASS",
        }

        logger.info("开始运行Live小仓参数模板管理器自测...")

        # 测试1: 配置加载测试
        try:
            test_config = {
                "live": {
                    "small_cap_template": {
                        "enabled": True,
                        "single_symbol_limit": {
                            "enabled": True,
                            "max_positions": 1,
                            "max_order_amount": 1000,
                            "max_daily_trades": 10,
                        },
                        "position_limits": {
                            "enabled": True,
                            "max_total_position_ratio": 0.1,
                            "max_single_position_ratio": 0.05,
                            "max_leverage": 2,
                        },
                        "order_frequency_limit": {
                            "enabled": True,
                            "max_orders_per_minute": 1,
                            "max_orders_per_hour": 10,
                            "max_orders_per_day": 50,
                        },
                        "new_positions_restriction": {
                            "enabled": True,
                            "allow_new_positions": False,
                            "allow_reduce_only": True,
                        },
                    }
                }
            }

            manager = LiveSmallCapManager(test_config)
            assert manager.live_config is not None, "配置加载失败"
            test_result["tests"].append(
                {
                    "test_id": "config_loading",
                    "test_name": "配置加载测试",
                    "result": "PASS",
                    "message": "配置加载成功",
                }
            )
            logger.info("测试1通过: 配置加载测试")
        except Exception as e:
            test_result["tests"].append(
                {
                    "test_id": "config_loading",
                    "test_name": "配置加载测试",
                    "result": "FAIL",
                    "message": f"配置加载失败: {str(e)}",
                }
            )
            test_result["overall_result"] = "FAIL"
            logger.error(f"测试1失败: 配置加载测试 - {str(e)}")

        # 测试2: 新仓限制测试
        try:
            test_config = {
                "live": {
                    "small_cap_template": {
                        "enabled": True,
                        "new_positions_restriction": {
                            "enabled": True,
                            "allow_new_positions": False,
                            "allow_reduce_only": True,
                        },
                    }
                }
            }

            manager = LiveSmallCapManager(test_config)
            result = manager.check_new_positions_restriction("buy", 0, 100)
            assert not result["passed"], "新仓限制检查失败"
            test_result["tests"].append(
                {
                    "test_id": "new_positions_restriction",
                    "test_name": "新仓限制测试",
                    "result": "PASS",
                    "message": "新仓限制检查成功",
                }
            )
            logger.info("测试2通过: 新仓限制测试")
        except Exception as e:
            test_result["tests"].append(
                {
                    "test_id": "new_positions_restriction",
                    "test_name": "新仓限制测试",
                    "result": "FAIL",
                    "message": f"新仓限制检查失败: {str(e)}",
                }
            )
            test_result["overall_result"] = "FAIL"
            logger.error(f"测试2失败: 新仓限制测试 - {str(e)}")

        # 测试3: 单品种限制测试
        try:
            test_config = {
                "live": {
                    "small_cap_template": {
                        "enabled": True,
                        "single_symbol_limit": {"enabled": True, "max_order_amount": 1000},
                    }
                }
            }

            manager = LiveSmallCapManager(test_config)
            result = manager.check_single_symbol_limit("ETH-USDT", 2000)
            assert not result["passed"], "单品种限制检查失败"
            test_result["tests"].append(
                {
                    "test_id": "single_symbol_limit",
                    "test_name": "单品种限制测试",
                    "result": "PASS",
                    "message": "单品种限制检查成功",
                }
            )
            logger.info("测试3通过: 单品种限制测试")
        except Exception as e:
            test_result["tests"].append(
                {
                    "test_id": "single_symbol_limit",
                    "test_name": "单品种限制测试",
                    "result": "FAIL",
                    "message": f"单品种限制检查失败: {str(e)}",
                }
            )
            test_result["overall_result"] = "FAIL"
            logger.error(f"测试3失败: 单品种限制测试 - {str(e)}")

        # 保存自测证据
        self.save_self_test_evidence(test_result)

        logger.info("\n=== 自测完成 ===")
        logger.info(f"总体结果: {test_result['overall_result']}")
        logger.info(f"测试数量: {len(test_result['tests'])}")
        logger.info(
            f"通过数量: {sum(1 for test in test_result['tests'] if test['result'] == 'PASS')}"
        )

        return test_result

    def save_self_test_evidence(self, test_result: dict[str, Any]) -> None:
        """
        保存自测证据

        Args:
            test_result: 自测结果
        """
        evidence_path = self.evidence_dir / f"self_test_{int(time.time())}.json"

        with open(evidence_path, "w", encoding="utf-8") as f:
            json.dump(test_result, f, indent=2, ensure_ascii=False, default=str)

        logger.info(f"自测证据已保存到: {evidence_path}")

    def save_evidence(self) -> None:
        """
        保存当前证据
        """
        evidence = {
            "current_status": self.get_current_status(),
            "config": self.config,
            "timestamp": time.time(),
            "datetime": datetime.now().isoformat(),
        }

        evidence_path = self.evidence_dir / f"evidence_{int(time.time())}.json"

        with open(evidence_path, "w", encoding="utf-8") as f:
            json.dump(evidence, f, indent=2, ensure_ascii=False, default=str)

        logger.info(f"证据已保存到: {evidence_path}")


if __name__ == "__main__":
    # 测试代码
    test_config = {
        "live": {
            "small_cap_template": {
                "enabled": True,
                "single_symbol_limit": {
                    "enabled": True,
                    "max_positions": 1,
                    "max_order_amount": 1000,
                    "max_daily_trades": 10,
                },
                "position_limits": {
                    "enabled": True,
                    "max_total_position_ratio": 0.1,
                    "max_single_position_ratio": 0.05,
                    "max_leverage": 2,
                },
                "order_frequency_limit": {
                    "enabled": True,
                    "max_orders_per_minute": 1,
                    "max_orders_per_hour": 10,
                    "max_orders_per_day": 50,
                },
                "new_positions_restriction": {
                    "enabled": True,
                    "allow_new_positions": False,
                    "allow_reduce_only": True,
                },
            }
        }
    }

    manager = LiveSmallCapManager(test_config)
    test_result = manager.run_self_test()
    print(json.dumps(test_result, indent=2, ensure_ascii=False))
