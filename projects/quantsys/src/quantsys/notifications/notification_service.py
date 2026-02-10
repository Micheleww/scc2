#!/usr/bin/env python3
"""
NotificationService: 交易信号通知服务

负责在交易信号产生和处理的关键节点发送通知到电脑和手机
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

# 动态导入所需库，避免依赖问题
try:
    from plyer import notification

    DESKTOP_NOTIFICATION_AVAILABLE = True
except ImportError:
    logger.warning("plyer库未安装，将无法发送桌面通知")
    DESKTOP_NOTIFICATION_AVAILABLE = False

try:
    import requests

    REQUESTS_AVAILABLE = True
except ImportError:
    logger.warning("requests库未安装，将无法发送网络通知")
    REQUESTS_AVAILABLE = False


class NotificationService:
    """
    通知服务类，支持多种通知方式
    实现：Windows桌面通知 + 企业微信 + Telegram + 本地日志
    """

    def __init__(self, config: dict[str, Any] = None):
        """
        初始化通知服务

        Args:
            config: 配置信息
        """
        self.config = config or {}

        # 本地日志配置
        self.local_log_enabled = self.config.get("local_log_enabled", True)
        self.alerts_log_path = self.config.get("alerts_log_path", "d:/quantsys/alerts_log.jsonl")

        # 桌面通知配置
        self.desktop_notification_enabled = self.config.get("desktop_notification_enabled", True)

        # 企业微信配置
        self.wecom_enabled = self.config.get("wecom_enabled", False)
        self.wecom_webhook = self.config.get("wecom_webhook", "")

        # Telegram配置
        self.telegram_enabled = self.config.get("telegram_enabled", False)
        self.telegram_bot_token = self.config.get("telegram_bot_token", "")
        self.telegram_chat_id = self.config.get("telegram_chat_id", "")

        # 通知模板 - 扩展关键事件模板
        self.templates = {
            "signal_generated": {
                "title": "新交易信号生成",
                "message": "信号: {direction} | 策略: {strategy} | 时间: {timestamp}",
            },
            "signal_converted": {
                "title": "交易信号已转换",
                "message": "信号: {side} {action} | 策略: {strategy} | 时间: {timestamp}",
            },
            "trade_opened": {
                "title": "交易已开仓",
                "message": "对: {pair} | 方向: {direction} | 价格: {price} | 数量: {amount}",
            },
            "trade_closed": {
                "title": "交易已平仓",
                "message": "对: {pair} | 方向: {direction} | 盈利: {profit} | 利润: {profit_amount}",
            },
            "order_complete": {
                "title": "订单已完成",
                "message": "订单: {order_id} | 状态: {status} | 对: {pair} | 类型: {type}",
            },
            "safe_stop": {
                "title": "⚠️ SAFE_STOP触发",
                "message": "原因: {reason} | 时间: {timestamp}",
            },
            "reconciliation_failed": {
                "title": "⚠️ 对账失败",
                "message": "原因: {reason} | 时间: {timestamp}",
            },
            "order_failed": {
                "title": "⚠️ 下单失败",
                "message": "订单类型: {order_type} | 原因: {reason} | 时间: {timestamp}",
            },
            "vpn_disconnected": {"title": "⚠️ VPN断连", "message": "时间: {timestamp}"},
        }

        logger.info("NotificationService初始化完成")

    def _send_desktop_notification(self, title: str, message: str) -> bool:
        """
        发送桌面通知，---bot---作为标题前缀，内容前添加4个空格对齐

        Args:
            title: 通知标题
            message: 通知内容

        Returns:
            bool: 发送是否成功
        """
        if not self.desktop_notification_enabled or not DESKTOP_NOTIFICATION_AVAILABLE:
            return False

        # 格式化标题和内容
        modified_title = f"---bot--- {title}"
        indented_message = f"    {message}"  # 添加4个空格对齐

        try:
            # 直接使用plyer库发送通知
            from plyer import notification

            notification.notify(
                title=modified_title,
                message=indented_message,
                timeout=30,  # 30秒显示时长
                app_name="---bot---",
            )
            logger.info(f"桌面通知发送成功: {modified_title}")
            return True
        except Exception as e:
            logger.error(f"发送桌面通知失败: {e}")
            return False

    def _write_local_log(self, template_key: str, title: str, message: str) -> bool:
        """
        写入本地日志到alerts_log.jsonl

        Args:
            template_key: 通知模板键
            title: 通知标题
            message: 通知内容

        Returns:
            bool: 写入是否成功
        """
        if not self.local_log_enabled:
            return False

        try:
            # 确保日志目录存在
            log_dir = os.path.dirname(self.alerts_log_path)
            if log_dir and not os.path.exists(log_dir):
                os.makedirs(log_dir, exist_ok=True)

            # 构建日志条目
            log_entry = {
                "timestamp": datetime.now().isoformat(),
                "type": template_key,
                "title": title,
                "message": message,
                "level": "warning" if "⚠️" in title else "info",
            }

            # 追加写入到日志文件
            with open(self.alerts_log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")

            logger.info(f"本地日志写入成功: {self.alerts_log_path}")
            return True
        except Exception as e:
            logger.error(f"写入本地日志失败: {e}")
            return False

    def _send_wecom_notification(self, title: str, message: str) -> bool:
        """
        发送企业微信通知

        Args:
            title: 通知标题
            message: 通知内容

        Returns:
            bool: 发送是否成功
        """
        if not self.wecom_enabled or not self.wecom_webhook or not REQUESTS_AVAILABLE:
            return False

        try:
            # 构建企业微信消息格式
            wecom_message = {
                "msgtype": "markdown",
                "markdown": {"content": f"## {title}\n{message}"},
            }

            response = requests.post(
                self.wecom_webhook, json=wecom_message, headers={"Content-Type": "application/json"}
            )
            response.raise_for_status()

            # 检查企业微信返回结果
            result = response.json()
            if result.get("errcode") != 0:
                logger.error(f"企业微信通知发送失败: {result.get('errmsg')}")
                return False

            logger.info(f"企业微信通知发送成功: {title}")
            return True
        except Exception as e:
            logger.error(f"发送企业微信通知失败: {e}")
            return False

    def _send_telegram_notification(self, title: str, message: str) -> bool:
        """
        发送Telegram通知

        Args:
            title: 通知标题
            message: 通知内容

        Returns:
            bool: 发送是否成功
        """
        if (
            not self.telegram_enabled
            or not self.telegram_bot_token
            or not self.telegram_chat_id
            or not REQUESTS_AVAILABLE
        ):
            return False

        try:
            url = f"https://api.telegram.org/bot{self.telegram_bot_token}/sendMessage"
            data = {
                "chat_id": self.telegram_chat_id,
                "text": f"*{title}*\n{message}",
                "parse_mode": "Markdown",
            }
            response = requests.post(url, data=data)
            response.raise_for_status()
            logger.info(f"Telegram通知发送成功: {title}")
            return True
        except Exception as e:
            logger.error(f"发送Telegram通知失败: {e}")
            return False

    def send_notification(self, template_key: str, data: dict[str, Any]) -> dict[str, bool]:
        """
        发送通知，支持Windows桌面通知 + 企业微信 + Telegram + 本地日志

        Args:
            template_key: 通知模板键
            data: 通知数据，用于填充模板

        Returns:
            Dict[str, bool]: 各通知方式的发送结果
        """
        # 获取通知模板
        template = self.templates.get(template_key)
        if not template:
            logger.error(f"未知的通知模板: {template_key}")
            return {}

        # 填充模板
        title = template["title"]
        message = template["message"].format(**data)

        # 写入本地日志
        self._write_local_log(template_key, title, message)

        # 发送通知（Windows桌面 + 企业微信 + Telegram）
        results = {
            "desktop": self._send_desktop_notification(title, message),
            "wecom": self._send_wecom_notification(title, message),
            "telegram": self._send_telegram_notification(title, message),
        }

        return results

    def notify_signal_generated(self, signal: dict[str, Any]) -> dict[str, bool]:
        """
        通知新信号生成

        Args:
            signal: 信号数据

        Returns:
            Dict[str, bool]: 各通知方式的发送结果
        """
        data = {
            "direction": signal.get("direction", "未知"),
            "strategy": signal.get("strategy", "未知"),
            "timestamp": signal.get("timestamp", datetime.now().isoformat()),
        }
        return self.send_notification("signal_generated", data)

    def notify_signal_converted(self, signal: dict[str, Any]) -> dict[str, bool]:
        """
        通知信号已转换

        Args:
            signal: 转换后的信号数据

        Returns:
            Dict[str, bool]: 各通知方式的发送结果
        """
        data = {
            "side": signal.get("side", "未知"),
            "action": signal.get("action", "未知"),
            "strategy": signal.get("strategy", "未知"),
            "timestamp": signal.get("timestamp", datetime.now().isoformat()),
        }
        return self.send_notification("signal_converted", data)

    def notify_trade_opened(self, trade: Any) -> dict[str, bool]:
        """
        通知交易已开仓

        Args:
            trade: 交易对象

        Returns:
            Dict[str, bool]: 各通知方式的发送结果
        """
        data = {
            "pair": getattr(trade, "pair", "未知"),
            "direction": "多" if getattr(trade, "is_long", True) else "空",
            "price": getattr(trade, "open_rate", 0.0),
            "amount": getattr(trade, "stake_amount", 0.0),
        }
        return self.send_notification("trade_opened", data)

    def notify_trade_closed(self, trade: Any) -> dict[str, bool]:
        """
        通知交易已平仓

        Args:
            trade: 交易对象

        Returns:
            Dict[str, bool]: 各通知方式的发送结果
        """
        data = {
            "pair": getattr(trade, "pair", "未知"),
            "direction": "多" if getattr(trade, "is_long", True) else "空",
            "profit": f"{getattr(trade, 'close_profit_percent', 0.0):.2f}%",
            "profit_amount": getattr(trade, "close_profit_abs", 0.0),
        }
        return self.send_notification("trade_closed", data)

    def notify_order_complete(self, order: Any, trade: Any) -> dict[str, bool]:
        """
        通知订单已完成

        Args:
            order: 订单对象
            trade: 交易对象

        Returns:
            Dict[str, bool]: 各通知方式的发送结果
        """
        data = {
            "order_id": getattr(order, "id", "未知"),
            "status": getattr(order, "status", "未知"),
            "pair": getattr(order, "pair", "未知"),
            "type": getattr(order, "ordertype", "未知"),
        }
        return self.send_notification("order_complete", data)

    def notify_safe_stop(self, reason: str) -> dict[str, bool]:
        """
        通知SAFE_STOP触发

        Args:
            reason: SAFE_STOP触发原因

        Returns:
            Dict[str, bool]: 各通知方式的发送结果
        """
        data = {"reason": reason, "timestamp": datetime.now().isoformat()}
        return self.send_notification("safe_stop", data)

    def notify_reconciliation_failed(self, reason: str) -> dict[str, bool]:
        """
        通知对账失败

        Args:
            reason: 对账失败原因

        Returns:
            Dict[str, bool]: 各通知方式的发送结果
        """
        data = {"reason": reason, "timestamp": datetime.now().isoformat()}
        return self.send_notification("reconciliation_failed", data)

    def notify_order_failed(self, order_type: str, reason: str) -> dict[str, bool]:
        """
        通知下单失败

        Args:
            order_type: 订单类型
            reason: 下单失败原因

        Returns:
            Dict[str, bool]: 各通知方式的发送结果
        """
        data = {"order_type": order_type, "reason": reason, "timestamp": datetime.now().isoformat()}
        return self.send_notification("order_failed", data)

    def notify_vpn_disconnected(self) -> dict[str, bool]:
        """
        通知VPN断连

        Returns:
            Dict[str, bool]: 各通知方式的发送结果
        """
        data = {"timestamp": datetime.now().isoformat()}
        return self.send_notification("vpn_disconnected", data)

    def notify(self, title: str, message: str, template_key: str = "custom") -> dict[str, bool]:
        """
        通用通知方法，用于发送自定义通知

        Args:
            title: 通知标题
            message: 通知内容
            template_key: 模板键（默认自定义）

        Returns:
            Dict[str, bool]: 各通知方式的发送结果
        """
        # 如果是自定义通知，创建临时模板
        if template_key == "custom":
            self.templates["custom"] = {"title": title, "message": message}
            data = {}
        else:
            # 确保模板存在
            if template_key not in self.templates:
                logger.error(f"未知的通知模板: {template_key}")
                return {}
            data = {"timestamp": datetime.now().isoformat()}

        return self.send_notification(template_key, data)


# 示例使用
if __name__ == "__main__":
    # 创建通知服务实例 - 配置Windows桌面通知 + 企业微信双通道
    config = {
        "local_log_enabled": True,
        "desktop_notification_enabled": True,
        # 企业微信配置
        "wecom_enabled": True,  # 已启用企业微信
        "wecom_webhook": "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=72cc0f5e-3935-429e-a5b9-9c81f9be6c22",  # 用户提供的Webhook
        # Telegram配置（可选）
        "telegram_enabled": False,  # 设置为True启用Telegram
        # 'telegram_bot_token': 'your_bot_token',  # 替换为实际的bot token
        # 'telegram_chat_id': 'your_chat_id'  # 替换为实际的chat id
    }

    notification_service = NotificationService(config)

    print("=== 测试通知系统 ===")

    # 测试1: 信号生成通知
    print("\n1. 测试信号生成通知...")
    test_signal = {
        "direction": "OPEN_LONG",
        "strategy": "trend_following",
        "timestamp": datetime.now().isoformat(),
    }
    notification_service.notify_signal_generated(test_signal)

    # 测试2: SAFE_STOP触发通知
    print("\n2. 测试SAFE_STOP触发通知...")
    notification_service.notify_safe_stop("交易系统触发安全停止")

    # 测试3: 对账失败通知
    print("\n3. 测试对账失败通知...")
    notification_service.notify_reconciliation_failed("账户余额与交易所不一致")

    # 测试4: 下单失败通知
    print("\n4. 测试下单失败通知...")
    notification_service.notify_order_failed("限价单", "价格超出范围")

    # 测试5: VPN断连通知
    print("\n5. 测试VPN断连通知...")
    notification_service.notify_vpn_disconnected()

    # 测试6: 通用通知
    print("\n6. 测试通用通知...")
    notification_service.notify("自定义通知", "这是一条测试通知")

    print("\n=== 所有测试已完成 ===")
    print(f"本地日志已写入: {notification_service.alerts_log_path}")
    print("\n=== 企业微信配置说明 ===")
    print("1. 登录企业微信，进入群聊")
    print("2. 点击群设置 -> 智能群助手 -> 添加机器人")
    print("3. 创建自定义机器人，获取webhook URL")
    print("4. 将webhook URL填入配置中的wecom_webhook字段")
    print("5. 设置wecom_enabled为True")
