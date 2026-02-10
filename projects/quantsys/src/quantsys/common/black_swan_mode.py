#!/usr/bin/env python3
"""
黑天鹅模式管理模块
实现黑天鹅模式开关：触发条件（回撤/漂移/对账异常/断连频繁）；模式=只允许reduce-only或清仓；落盘原因与恢复条件
"""

import json
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    filename="logs/black_swan_mode.log",
)
logger = logging.getLogger(__name__)


class BlackSwanModeStatus(Enum):
    """
    黑天鹅模式状态枚举
    """

    NORMAL = "normal"  # 正常模式
    REDUCE_ONLY = "reduce_only"  # 只允许减仓模式
    LIQUIDATE = "liquidate"  # 清仓模式


class BlackSwanTriggerType(Enum):
    """
    黑天鹅模式触发类型枚举
    """

    DRAWdown = "drawdown"  # 回撤触发
    DRIFT = "drift"  # 漂移触发
    RECONCILIATION = "reconciliation"  # 对账异常触发
    DISCONNECTION = "disconnection"  # 断连频繁触发
    MANUAL = "manual"  # 手动触发


@dataclass
class BlackSwanEvent:
    """
    黑天鹅事件记录
    """

    event_id: str
    trigger_type: BlackSwanTriggerType
    status: BlackSwanModeStatus
    trigger_value: float
    threshold: float
    details: dict[str, Any]
    triggered_at: str = field(default_factory=lambda: datetime.now().isoformat())
    recovered_at: str | None = None
    recovery_reason: str | None = None


@dataclass
class BlackSwanConfig:
    """
    黑天鹅模式配置
    """

    # 回撤触发配置
    drawdown: dict[str, Any] = field(
        default_factory=lambda: {
            "enabled": True,
            "threshold": 0.15,  # 15%回撤触发
            "lookback_window": 24,  # 回溯窗口（小时）
            "action": "reduce_only",  # reduce_only或liquidate
        }
    )

    # 漂移触发配置
    drift: dict[str, Any] = field(
        default_factory=lambda: {
            "enabled": True,
            "action": "reduce_only",  # reduce_only或liquidate
        }
    )

    # 对账异常触发配置
    reconciliation: dict[str, Any] = field(
        default_factory=lambda: {
            "enabled": True,
            "threshold": 0.05,  # 5%资产差异触发
            "consecutive_failures": 3,  # 连续3次失败触发
            "action": "liquidate",  # reduce_only或liquidate
        }
    )

    # 断连频繁触发配置
    disconnection: dict[str, Any] = field(
        default_factory=lambda: {
            "enabled": True,
            "threshold": 10,  # 1小时内断连10次触发
            "time_window": 3600,  # 时间窗口（秒）
            "action": "reduce_only",  # reduce_only或liquidate
        }
    )

    # 恢复条件配置
    recovery: dict[str, Any] = field(
        default_factory=lambda: {
            "drawdown": {
                "required_return": 0.05,  # 需要5%的收益才能恢复
                "stable_period": 12,  # 稳定12小时
            },
            "drift": {
                "stable_period": 6  # 漂移恢复后稳定6小时
            },
            "reconciliation": {
                "consecutive_successes": 3  # 连续3次对账成功
            },
            "disconnection": {
                "stable_period": 1  # 断连恢复后稳定1小时
            },
        }
    )

    # 保存路径配置
    save_path: str = "data/black_swan_events.json"
    state_path: str = "data/black_swan_state.json"


class BlackSwanModeManager:
    """
    黑天鹅模式管理器
    """

    def __init__(self, config: dict[str, Any] | None = None):
        """
        初始化黑天鹅模式管理器

        Args:
            config: 配置信息
        """
        # 加载配置
        self.config = BlackSwanConfig(**(config or {}))

        # 状态管理
        self.current_status = BlackSwanModeStatus.NORMAL
        self.events: list[BlackSwanEvent] = []
        self.trigger_counts: dict[str, int] = {
            "reconciliation_failures": 0,
            "disconnection_count": 0,
        }
        self.disconnection_timestamps: list[float] = []

        # 恢复计时器
        self.recovery_timers: dict[str, float] = {}

        # 加载历史事件
        self._load_events()

        logger.info("黑天鹅模式管理器初始化完成，当前状态: %s", self.current_status.value)

    def _generate_event_id(self) -> str:
        """
        生成事件ID

        Returns:
            str: 事件ID
        """
        return f"black_swan_{datetime.now().strftime('%Y%m%d%H%M%S%f')}"

    def _load_events(self) -> None:
        """
        加载历史事件
        """
        try:
            if os.path.exists(self.config.save_path):
                with open(self.config.save_path, encoding="utf-8") as f:
                    events_data = json.load(f)
                    self.events = [
                        BlackSwanEvent(
                            event_id=event["event_id"],
                            trigger_type=BlackSwanTriggerType(event["trigger_type"]),
                            status=BlackSwanModeStatus(event["status"]),
                            trigger_value=event["trigger_value"],
                            threshold=event["threshold"],
                            details=event["details"],
                            triggered_at=event["triggered_at"],
                            recovered_at=event.get("recovered_at"),
                            recovery_reason=event.get("recovery_reason"),
                        )
                        for event in events_data.get("events", [])
                    ]

                # 恢复最后一个未恢复的事件状态
                active_events = [event for event in self.events if event.recovered_at is None]
                if active_events:
                    self.current_status = active_events[-1].status
                    logger.info("从历史事件恢复黑天鹅模式状态: %s", self.current_status.value)
        except Exception as e:
            logger.error("加载历史事件失败: %s", e)

    def _save_events(self) -> None:
        """
        保存事件到文件
        """
        try:
            # 创建目录
            os.makedirs(os.path.dirname(self.config.save_path), exist_ok=True)

            # 转换为可序列化格式
            events_data = {
                "timestamp": datetime.now().isoformat(),
                "events": [
                    {
                        "event_id": event.event_id,
                        "trigger_type": event.trigger_type.value,
                        "status": event.status.value,
                        "trigger_value": event.trigger_value,
                        "threshold": event.threshold,
                        "details": event.details,
                        "triggered_at": event.triggered_at,
                        "recovered_at": event.recovered_at,
                        "recovery_reason": event.recovery_reason,
                    }
                    for event in self.events
                ],
            }

            with open(self.config.save_path, "w", encoding="utf-8") as f:
                json.dump(events_data, f, indent=2, ensure_ascii=False)

            logger.info("黑天鹅事件已保存到 %s", self.config.save_path)
        except Exception as e:
            logger.error("保存事件失败: %s", e)

    def _save_state(self) -> None:
        """
        保存当前状态到文件
        """
        try:
            # 创建目录
            os.makedirs(os.path.dirname(self.config.state_path), exist_ok=True)

            # 转换为可序列化格式
            state_data = {
                "timestamp": datetime.now().isoformat(),
                "current_status": self.current_status.value,
                "trigger_counts": self.trigger_counts,
                "disconnection_timestamps": self.disconnection_timestamps,
                "recovery_timers": self.recovery_timers,
            }

            with open(self.config.state_path, "w", encoding="utf-8") as f:
                json.dump(state_data, f, indent=2, ensure_ascii=False)

            logger.info("黑天鹅状态已保存到 %s", self.config.state_path)
        except Exception as e:
            logger.error("保存状态失败: %s", e)

    def check_drawdown_trigger(self, current_drawdown: float) -> bool:
        """
        检查回撤触发条件

        Args:
            current_drawdown: 当前回撤率

        Returns:
            bool: 是否触发
        """
        if not self.config.drawdown["enabled"]:
            return False

        threshold = self.config.drawdown["threshold"]
        if current_drawdown >= threshold:
            # 创建触发事件
            event = BlackSwanEvent(
                event_id=self._generate_event_id(),
                trigger_type=BlackSwanTriggerType.DRAWdown,
                status=BlackSwanModeStatus(self.config.drawdown["action"]),
                trigger_value=current_drawdown,
                threshold=threshold,
                details={
                    "lookback_window": self.config.drawdown["lookback_window"],
                    "drawdown": current_drawdown,
                },
            )
            self.events.append(event)
            self.current_status = event.status
            self._save_events()
            self._save_state()

            logger.warning(
                "黑天鹅模式触发: 回撤 %.2f%% 超过阈值 %.2f%%",
                current_drawdown * 100,
                threshold * 100,
            )
            return True

        return False

    def check_drift_trigger(self, drift_status: str) -> bool:
        """
        检查漂移触发条件

        Args:
            drift_status: 漂移状态 (blocked/reduce_only/ok)

        Returns:
            bool: 是否触发
        """
        if not self.config.drift["enabled"]:
            return False

        if drift_status in ["blocked", "reduce_only"]:
            # 创建触发事件
            event = BlackSwanEvent(
                event_id=self._generate_event_id(),
                trigger_type=BlackSwanTriggerType.DRIFT,
                status=BlackSwanModeStatus(self.config.drift["action"]),
                trigger_value=1.0,
                threshold=1.0,
                details={"drift_status": drift_status},
            )
            self.events.append(event)
            self.current_status = event.status
            self._save_events()
            self._save_state()

            logger.warning("黑天鹅模式触发: 漂移状态 %s", drift_status)
            return True

        return False

    def check_reconciliation_trigger(self, asset_diff_ratio: float, is_success: bool) -> bool:
        """
        检查对账异常触发条件

        Args:
            asset_diff_ratio: 资产差异比率
            is_success: 是否对账成功

        Returns:
            bool: 是否触发
        """
        if not self.config.reconciliation["enabled"]:
            return False

        if not is_success:
            self.trigger_counts["reconciliation_failures"] += 1

            # 检查连续失败次数
            if (
                self.trigger_counts["reconciliation_failures"]
                >= self.config.reconciliation["consecutive_failures"]
            ):
                # 创建触发事件
                event = BlackSwanEvent(
                    event_id=self._generate_event_id(),
                    trigger_type=BlackSwanTriggerType.RECONCILIATION,
                    status=BlackSwanModeStatus(self.config.reconciliation["action"]),
                    trigger_value=asset_diff_ratio,
                    threshold=self.config.reconciliation["threshold"],
                    details={
                        "asset_diff_ratio": asset_diff_ratio,
                        "consecutive_failures": self.trigger_counts["reconciliation_failures"],
                        "required_failures": self.config.reconciliation["consecutive_failures"],
                    },
                )
                self.events.append(event)
                self.current_status = event.status
                self._save_events()
                self._save_state()

                logger.warning(
                    "黑天鹅模式触发: 连续 %d 次对账失败，资产差异 %.2f%%",
                    self.trigger_counts["reconciliation_failures"],
                    asset_diff_ratio * 100,
                )
                return True
        else:
            # 重置连续失败计数
            self.trigger_counts["reconciliation_failures"] = 0

        return False

    def check_disconnection_trigger(self) -> bool:
        """
        检查断连频繁触发条件

        Returns:
            bool: 是否触发
        """
        if not self.config.disconnection["enabled"]:
            return False

        # 添加当前时间戳
        current_time = datetime.now().timestamp()
        self.disconnection_timestamps.append(current_time)

        # 清理过期时间戳
        time_window = self.config.disconnection["time_window"]
        self.disconnection_timestamps = [
            ts for ts in self.disconnection_timestamps if current_time - ts <= time_window
        ]

        # 检查断连次数
        disconnect_count = len(self.disconnection_timestamps)
        threshold = self.config.disconnection["threshold"]

        if disconnect_count >= threshold:
            # 创建触发事件
            event = BlackSwanEvent(
                event_id=self._generate_event_id(),
                trigger_type=BlackSwanTriggerType.DISCONNECTION,
                status=BlackSwanModeStatus(self.config.disconnection["action"]),
                trigger_value=disconnect_count,
                threshold=threshold,
                details={
                    "disconnect_count": disconnect_count,
                    "time_window": time_window,
                    "timestamp": current_time,
                },
            )
            self.events.append(event)
            self.current_status = event.status
            self._save_events()
            self._save_state()

            logger.warning(
                "黑天鹅模式触发: %d秒内断连 %d 次，超过阈值 %d 次",
                time_window,
                disconnect_count,
                threshold,
            )
            return True

        return False

    def manual_trigger(self, action: str, reason: str) -> None:
        """
        手动触发黑天鹅模式

        Args:
            action: 操作类型 (reduce_only/liquidate)
            reason: 触发原因
        """
        # 创建触发事件
        event = BlackSwanEvent(
            event_id=self._generate_event_id(),
            trigger_type=BlackSwanTriggerType.MANUAL,
            status=BlackSwanModeStatus(action),
            trigger_value=1.0,
            threshold=1.0,
            details={"reason": reason},
        )
        self.events.append(event)
        self.current_status = event.status
        self._save_events()
        self._save_state()

        logger.warning("黑天鹅模式手动触发: %s，原因: %s", action, reason)

    def recover(self, reason: str) -> None:
        """
        恢复正常模式

        Args:
            reason: 恢复原因
        """
        # 找到未恢复的事件
        active_events = [event for event in self.events if event.recovered_at is None]
        if active_events:
            # 恢复最后一个事件
            last_event = active_events[-1]
            last_event.recovered_at = datetime.now().isoformat()
            last_event.recovery_reason = reason

            # 重置状态
            self.current_status = BlackSwanModeStatus.NORMAL
            self.trigger_counts = {"reconciliation_failures": 0, "disconnection_count": 0}
            self.disconnection_timestamps = []
            self.recovery_timers = {}

            self._save_events()
            self._save_state()

            logger.info("黑天鹅模式恢复正常，原因: %s", reason)

    def get_current_status(self) -> BlackSwanModeStatus:
        """
        获取当前状态

        Returns:
            BlackSwanModeStatus: 当前状态
        """
        return self.current_status

    def get_current_status_value(self) -> str:
        """
        获取当前状态值

        Returns:
            str: 当前状态值
        """
        return self.current_status.value

    def is_normal(self) -> bool:
        """
        是否正常模式

        Returns:
            bool: 是否正常
        """
        return self.current_status == BlackSwanModeStatus.NORMAL

    def is_reduce_only(self) -> bool:
        """
        是否只允许减仓模式

        Returns:
            bool: 是否只允许减仓
        """
        return self.current_status == BlackSwanModeStatus.REDUCE_ONLY

    def is_liquidate(self) -> bool:
        """
        是否清仓模式

        Returns:
            bool: 是否清仓
        """
        return self.current_status == BlackSwanModeStatus.LIQUIDATE

    def generate_self_test_evidence(self) -> dict[str, Any]:
        """
        生成自测证据

        Returns:
            Dict[str, Any]: 自测证据
        """
        # 生成测试数据

        # 模拟回撤触发
        self.check_drawdown_trigger(0.20)  # 20%回撤

        # 模拟恢复
        self.recover("测试恢复")

        # 模拟漂移触发
        self.check_drift_trigger("blocked")

        # 模拟恢复
        self.recover("测试恢复")

        # 生成证据
        evidence = {
            "test_name": "Black Swan Mode Self Test",
            "timestamp": datetime.now().isoformat(),
            "status": self.get_current_status_value(),
            "events_count": len(self.events),
            "trigger_counts": self.trigger_counts,
            "config": {
                "drawdown_threshold": self.config.drawdown["threshold"],
                "drift_enabled": self.config.drift["enabled"],
                "reconciliation_enabled": self.config.reconciliation["enabled"],
                "disconnection_threshold": self.config.disconnection["threshold"],
            },
        }

        # 保存证据
        evidence_path = (
            f"evidence/black_swan_mode_self_test_{datetime.now().strftime('%Y%m%d%H%M%S')}.json"
        )
        os.makedirs(os.path.dirname(evidence_path), exist_ok=True)

        with open(evidence_path, "w", encoding="utf-8") as f:
            json.dump(evidence, f, indent=2, ensure_ascii=False, default=str)

        logger.info("黑天鹅模式自测证据已保存到 %s", evidence_path)

        return evidence

    def get_events(self) -> list[BlackSwanEvent]:
        """
        获取所有事件

        Returns:
            List[BlackSwanEvent]: 事件列表
        """
        return self.events.copy()

    def get_latest_event(self) -> BlackSwanEvent | None:
        """
        获取最新事件

        Returns:
            Optional[BlackSwanEvent]: 最新事件
        """
        if self.events:
            return self.events[-1]
        return None
