#!/usr/bin/env python3
"""
通知集成模块 - 集成已有的通知应用
支持：Windows桌面通知、企业微信、Telegram
"""

import logging
import os
import sys
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# 添加项目路径
REPO_ROOT = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))

# 动态导入通知服务
NOTIFICATION_SERVICE_AVAILABLE = False
NOTIFICATION_SERVICE = None

try:
    from src.quantsys.notifications.notification_service import NotificationService

    NOTIFICATION_SERVICE_AVAILABLE = True
    logger.info("✅ NotificationService 导入成功")
except ImportError as e:
    logger.warning(f"⚠️  NotificationService 导入失败: {e}")

# 企业微信通知
WECHAT_NOTIFIER_AVAILABLE = False
WECHAT_NOTIFIER = None

try:
    # 尝试导入企业微信通知
    wechat_config_path = REPO_ROOT / "corefiles" / "config_wechat_notifications.py"
    if wechat_config_path.exists():
        # 动态加载企业微信配置
        import importlib.util

        spec = importlib.util.spec_from_file_location("wechat_notifier", wechat_config_path)
        wechat_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(wechat_module)
        if hasattr(wechat_module, "WeChatNotifier"):
            WECHAT_NOTIFIER_AVAILABLE = True
            logger.info("✅ WeChatNotifier 导入成功")
except Exception as e:
    logger.warning(f"⚠️  WeChatNotifier 导入失败: {e}")


class NotificationIntegration:
    """通知集成类 - 统一调用已有的通知应用"""

    def __init__(self):
        """初始化通知集成"""
        self.notification_service = None
        self.wechat_notifier = None

        # 初始化NotificationService
        if NOTIFICATION_SERVICE_AVAILABLE:
            try:
                config = {
                    "desktop_notification_enabled": True,
                    "local_log_enabled": False,  # 网页通知不需要本地日志
                    "wecom_enabled": os.getenv("WECOM_ENABLED", "false").lower() == "true",
                    "wecom_webhook": os.getenv("WECOM_WEBHOOK", ""),
                    "telegram_enabled": os.getenv("TELEGRAM_ENABLED", "false").lower() == "true",
                    "telegram_bot_token": os.getenv("TELEGRAM_BOT_TOKEN", ""),
                    "telegram_chat_id": os.getenv("TELEGRAM_CHAT_ID", ""),
                }
                self.notification_service = NotificationService(config)
                logger.info("✅ NotificationService 初始化成功")
            except Exception as e:
                logger.warning(f"⚠️  NotificationService 初始化失败: {e}")
                # 尝试直接使用plyer作为备用方案
                try:
                    from plyer import notification

                    self._plyer_available = True
                    logger.info("✅ 使用plyer作为备用桌面通知方案")
                except ImportError:
                    self._plyer_available = False
                    logger.warning("⚠️  plyer也未安装，桌面通知不可用")

        # 初始化企业微信通知（通过动态导入）
        if WECHAT_NOTIFIER_AVAILABLE:
            try:
                import importlib.util

                wechat_config_path = REPO_ROOT / "corefiles" / "config_wechat_notifications.py"
                if wechat_config_path.exists():
                    spec = importlib.util.spec_from_file_location(
                        "wechat_notifier", wechat_config_path
                    )
                    wechat_module = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(wechat_module)
                    if hasattr(wechat_module, "WeChatNotifier"):
                        self.wechat_notifier = wechat_module.WeChatNotifier()
                        logger.info("✅ WeChatNotifier 初始化成功")
            except Exception as e:
                logger.warning(f"⚠️  WeChatNotifier 初始化失败: {e}")

    def send_desktop_notification(self, title: str, message: str) -> dict[str, Any]:
        """发送桌面通知"""
        # 优先使用NotificationService
        if self.notification_service:
            try:
                result = self.notification_service._send_desktop_notification(title, message)
                return {"success": result, "mode": "desktop"}
            except Exception as e:
                logger.warning(f"NotificationService发送失败，尝试备用方案: {e}")

        # 备用方案：直接使用plyer
        try:
            from plyer import notification

            notification.notify(
                title=f"ATA系统 - {title}", message=message, timeout=10, app_name="ATA系统"
            )
            return {"success": True, "mode": "desktop", "fallback": True}
        except ImportError:
            return {"success": False, "error": "plyer未安装，桌面通知不可用", "mode": "desktop"}
        except Exception as e:
            logger.error(f"桌面通知发送失败: {e}")
            return {"success": False, "error": str(e), "mode": "desktop"}

    def send_wecom_notification(self, title: str, message: str) -> dict[str, Any]:
        """发送企业微信通知"""
        if not self.wechat_notifier:
            # 尝试从NotificationService发送
            if self.notification_service:
                try:
                    result = self.notification_service._send_wecom_notification(title, message)
                    return {"success": result, "mode": "wecom"}
                except Exception as e:
                    logger.warning(f"通过NotificationService发送企业微信通知失败: {e}")
            return {"success": False, "error": "WeChatNotifier not available"}

        try:
            result = self.wechat_notifier.send_notification(title, message)
            return {"success": result, "mode": "wecom"}
        except Exception as e:
            logger.error(f"企业微信通知发送失败: {e}")
            return {"success": False, "error": str(e), "mode": "wecom"}

    def send_telegram_notification(self, title: str, message: str) -> dict[str, Any]:
        """发送Telegram通知"""
        if not self.notification_service:
            return {"success": False, "error": "NotificationService not available"}

        try:
            result = self.notification_service._send_telegram_notification(title, message)
            return {"success": result, "mode": "telegram"}
        except Exception as e:
            logger.error(f"Telegram通知发送失败: {e}")
            return {"success": False, "error": str(e), "mode": "telegram"}

    def send_notification(self, title: str, message: str, mode: str = "all") -> dict[str, Any]:
        """
        发送通知（统一接口）

        Args:
            title: 通知标题
            message: 通知内容
            mode: 通知模式 (ata/desktop/wecom/telegram/all)

        Returns:
            发送结果
        """
        results = {}

        if mode == "ata":
            # ATA消息模式，不发送额外通知
            return {"success": True, "mode": "ata", "message": "ATA消息模式，跳过通知"}

        if mode == "desktop" or mode == "all":
            results["desktop"] = self.send_desktop_notification(title, message)

        if mode == "wecom" or mode == "all":
            results["wecom"] = self.send_wecom_notification(title, message)

        if mode == "telegram" or mode == "all":
            results["telegram"] = self.send_telegram_notification(title, message)

        # 判断整体成功状态
        success_count = sum(1 for r in results.values() if r.get("success"))
        total_count = len(results)

        return {
            "success": success_count > 0,
            "mode": mode,
            "results": results,
            "success_count": success_count,
            "total_count": total_count,
        }


# 全局单例
_notification_integration: NotificationIntegration | None = None


def get_notification_integration() -> NotificationIntegration:
    """获取通知集成单例"""
    global _notification_integration
    if _notification_integration is None:
        _notification_integration = NotificationIntegration()
    return _notification_integration
