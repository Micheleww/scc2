#!/usr/bin/env python3

"""
告警引擎模块
实现量化交易系统的告警功能
"""

import json
import logging
import os
from datetime import datetime
from typing import Any

# 配置日志
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class AlertEngine:
    """
    告警引擎类
    实现量化交易系统的告警功能
    """

    def __init__(self):
        """
        初始化告警引擎
        """
        # 告警配置
        self.alert_config = {
            "alert_events": [
                "SAFE_STOP",
                "RECONCILIATION_FAILED",
                "ORDER_FAILED",
                "DRAWDOWN_TRIGGERED",
                "GATE_BLOCKED",
            ],
            "alert_channels": ["LOG_HIGHLIGHT", "WINDOWS_NOTIFICATION"],
            "log_file": "alerts_log.jsonl",
            "snapshot_file": "alerts_snapshot.md",
        }

        # 告警状态
        self.alert_state = {
            "total_alerts": 0,
            "alerts_by_event": {
                "SAFE_STOP": 0,
                "RECONCILIATION_FAILED": 0,
                "ORDER_FAILED": 0,
                "DRAWDOWN_TRIGGERED": 0,
                "GATE_BLOCKED": 0,
            },
            "last_alert_time": None,
            "current_alerts": [],
        }

        # 初始化日志文件
        self._initialize_log_file()

        logger.info("告警引擎初始化完成，告警配置: %s", self.alert_config)

    def _initialize_log_file(self):
        """
        初始化告警日志文件
        """
        # 如果文件不存在，创建空文件
        if not os.path.exists(self.alert_config["log_file"]):
            with open(self.alert_config["log_file"], "w", encoding="utf-8") as f:
                pass

    def _send_windows_notification(self, title: str, message: str):
        """
        发送Windows本地通知

        Args:
            title: 通知标题
            message: 通知内容
        """
        try:
            from win10toast import ToastNotifier

            toaster = ToastNotifier()
            toaster.show_toast(title=title, msg=message, duration=10, threaded=True)
            logger.info("Windows通知发送成功: %s - %s", title, message)
        except ImportError:
            logger.warning("win10toast库未安装，无法发送Windows通知")
        except Exception as e:
            logger.error("发送Windows通知失败: %s", str(e))

    def _log_highlight(self, level: str, message: str):
        """
        日志高亮显示

        Args:
            level: 日志级别
            message: 日志消息
        """
        # 使用不同颜色的日志格式
        color_map = {
            "ERROR": "[ERROR] 33[91m{}33[0m",  # 红色
            "WARNING": "[WARNING] 33[93m{}33[0m",  # 黄色
            "INFO": "[INFO] 33[92m{}33[0m",  # 绿色
        }

        color_format = color_map.get(level, "[{}] {}")
        logger.info(color_format.format(message))

    def _write_to_log(self, alert: dict[str, Any]):
        """
        写入告警到日志文件

        Args:
            alert: 告警信息
        """
        with open(self.alert_config["log_file"], "a", encoding="utf-8") as f:
            f.write(json.dumps(alert, ensure_ascii=False) + "\n")

    def _update_alert_state(self, alert: dict[str, Any]):
        """
        更新告警状态

        Args:
            alert: 告警信息
        """
        # 更新总告警数
        self.alert_state["total_alerts"] += 1

        # 更新按事件分类的告警数
        event_type = alert["event_type"]
        if event_type in self.alert_state["alerts_by_event"]:
            self.alert_state["alerts_by_event"][event_type] += 1

        # 更新最后告警时间
        self.alert_state["last_alert_time"] = alert["timestamp"]

        # 添加到当前告警列表（最多保存最近10个）
        self.alert_state["current_alerts"].append(alert)
        if len(self.alert_state["current_alerts"]) > 10:
            self.alert_state["current_alerts"].pop(0)

    def create_alert_snapshot(self):
        """
        创建告警快照
        """
        with open(self.alert_config["snapshot_file"], "w", encoding="utf-8") as f:
            f.write("# 告警快照\n\n")
            f.write(f"## 生成时间: {datetime.now().isoformat()}\n\n")
            f.write("## 告警统计\n\n")
            f.write(f"- 总告警数: {self.alert_state['total_alerts']}\n")
            f.write(f"- 最后告警时间: {self.alert_state['last_alert_time']}\n\n")
            f.write("### 按事件分类\n\n")
            for event, count in self.alert_state["alerts_by_event"].items():
                f.write(f"- {event}: {count}\n")
            f.write("\n## 最近告警\n\n")
            if self.alert_state["current_alerts"]:
                for i, alert in enumerate(reversed(self.alert_state["current_alerts"])):
                    f.write(f"### 告警 {i + 1}\n")
                    f.write(f"- 事件类型: {alert['event_type']}\n")
                    f.write(f"- 时间: {alert['timestamp']}\n")
                    f.write(f"- 级别: {alert['level']}\n")
                    f.write(f"- 消息: {alert['message']}\n")
                    f.write(f"- 详情: {json.dumps(alert['details'], indent=2)}\n\n")
            else:
                f.write("暂无告警\n")

        logger.info("告警快照已生成: %s", self.alert_config["snapshot_file"])

    def trigger_alert(
        self, event_type: str, message: str, details: dict[str, Any] = None, level: str = "WARNING"
    ):
        """
        触发告警

        Args:
            event_type: 事件类型
            message: 告警消息
            details: 告警详情
            level: 告警级别
        """
        # 检查事件类型是否在配置中
        if event_type not in self.alert_config["alert_events"]:
            logger.warning("未知的告警事件类型: %s", event_type)
            return

        # 构造告警信息
        alert = {
            "event_type": event_type,
            "message": message,
            "details": details or {},
            "level": level,
            "timestamp": datetime.now().isoformat(),
            "alert_id": f"alert_{self.alert_state['total_alerts'] + 1}",
        }

        # 发送告警到各个渠道
        if "LOG_HIGHLIGHT" in self.alert_config["alert_channels"]:
            self._log_highlight(level, f"{event_type}: {message}")

        if "WINDOWS_NOTIFICATION" in self.alert_config["alert_channels"]:
            self._send_windows_notification(event_type, message)

        # 写入告警日志
        self._write_to_log(alert)

        # 更新告警状态
        self._update_alert_state(alert)

        # 更新告警快照
        self.create_alert_snapshot()

        logger.info("告警已触发: %s, 消息: %s", event_type, message)

    def trigger_safe_stop_alert(self, reason: str, details: dict[str, Any] = None):
        """
        触发安全停止告警

        Args:
            reason: 安全停止原因
            details: 详情
        """
        self.trigger_alert(
            event_type="SAFE_STOP",
            message=f"安全停止已触发: {reason}",
            details=details or {},
            level="ERROR",
        )

    def trigger_reconciliation_failed_alert(self, reason: str, details: dict[str, Any] = None):
        """
        触发对账失败告警

        Args:
            reason: 对账失败原因
            details: 详情
        """
        self.trigger_alert(
            event_type="RECONCILIATION_FAILED",
            message=f"对账失败: {reason}",
            details=details or {},
            level="ERROR",
        )

    def trigger_order_failed_alert(
        self, order_id: str, reason: str, details: dict[str, Any] = None
    ):
        """
        触发下单失败告警

        Args:
            order_id: 订单ID
            reason: 下单失败原因
            details: 详情
        """
        self.trigger_alert(
            event_type="ORDER_FAILED",
            message=f"下单失败 - 订单 {order_id}: {reason}",
            details=details or {},
            level="ERROR",
        )

    def trigger_drawdown_alert(
        self, drawdown: float, threshold: float, details: dict[str, Any] = None
    ):
        """
        触发回撤触发告警

        Args:
            drawdown: 当前回撤
            threshold: 回撤阈值
            details: 详情
        """
        self.trigger_alert(
            event_type="DRAWDOWN_TRIGGERED",
            message=f"回撤已触发: 当前回撤 {drawdown:.4f}, 阈值 {threshold:.4f}",
            details=details or {},
            level="WARNING",
        )

    def trigger_gate_blocked_alert(self, reason: str, details: dict[str, Any] = None):
        """
        触发门禁BLOCKED告警

        Args:
            reason: 门禁BLOCKED原因
            details: 详情
        """
        self.trigger_alert(
            event_type="GATE_BLOCKED",
            message=f"门禁已BLOCKED: {reason}",
            details=details or {},
            level="ERROR",
        )

    def get_alert_state(self) -> dict[str, Any]:
        """
        获取当前告警状态

        Returns:
            Dict[str, Any]: 告警状态
        """
        return self.alert_state.copy()

    def get_alerts_count(self) -> int:
        """
        获取总告警数

        Returns:
            int: 总告警数
        """
        return self.alert_state["total_alerts"]

    def clear_alerts(self):
        """
        清空告警状态
        """
        self.alert_state = {
            "total_alerts": 0,
            "alerts_by_event": {
                "SAFE_STOP": 0,
                "RECONCILIATION_FAILED": 0,
                "ORDER_FAILED": 0,
                "DRAWDOWN_TRIGGERED": 0,
                "GATE_BLOCKED": 0,
            },
            "last_alert_time": None,
            "current_alerts": [],
        }

        logger.info("告警状态已清空")
        self.create_alert_snapshot()
