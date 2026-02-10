#!/usr/bin/env python3
"""
Browser-Tools-MCP 集成模块
桥接browser-tools-server的HTTP API到MCP Bus
"""

import logging
import os
from typing import Any

import httpx

logger = logging.getLogger(__name__)

# Browser-Tools-Server配置
BROWSER_TOOLS_HOST = os.getenv("BROWSER_TOOLS_HOST", "127.0.0.1")
BROWSER_TOOLS_PORT = int(os.getenv("BROWSER_TOOLS_PORT", "3025"))
BROWSER_TOOLS_BASE_URL = f"http://{BROWSER_TOOLS_HOST}:{BROWSER_TOOLS_PORT}"


class BrowserToolsIntegration:
    """Browser-Tools-MCP集成类"""

    def __init__(self):
        """初始化集成"""
        self.base_url = BROWSER_TOOLS_BASE_URL
        self.client = httpx.AsyncClient(timeout=30.0)
        self._server_available = None

    async def check_server_available(self) -> bool:
        """检查browser-tools-server是否可用"""
        if self._server_available is not None:
            return self._server_available

        try:
            response = await self.client.get(f"{self.base_url}/.identity")
            if response.status_code == 200:
                data = response.json()
                if data.get("signature") == "mcp-browser-connector-24x7":
                    self._server_available = True
                    logger.info(f"Browser-Tools-Server可用: {self.base_url}")
                    return True
        except Exception as e:
            logger.warning(f"Browser-Tools-Server不可用: {e}")

        self._server_available = False
        return False

    async def run_accessibility_audit(self, url: str) -> dict[str, Any]:
        """运行可访问性审计"""
        if not await self.check_server_available():
            return {"success": False, "error": "Browser-Tools-Server不可用"}

        try:
            response = await self.client.post(
                f"{self.base_url}/audit/accessibility", json={"url": url}
            )
            if response.status_code == 200:
                return {"success": True, "data": response.json()}
            else:
                return {"success": False, "error": f"HTTP {response.status_code}"}
        except Exception as e:
            logger.error(f"可访问性审计失败: {e}")
            return {"success": False, "error": str(e)}

    async def run_performance_audit(self, url: str) -> dict[str, Any]:
        """运行性能审计"""
        if not await self.check_server_available():
            return {"success": False, "error": "Browser-Tools-Server不可用"}

        try:
            response = await self.client.post(
                f"{self.base_url}/audit/performance", json={"url": url}
            )
            if response.status_code == 200:
                return {"success": True, "data": response.json()}
            else:
                return {"success": False, "error": f"HTTP {response.status_code}"}
        except Exception as e:
            logger.error(f"性能审计失败: {e}")
            return {"success": False, "error": str(e)}

    async def run_seo_audit(self, url: str) -> dict[str, Any]:
        """运行SEO审计"""
        if not await self.check_server_available():
            return {"success": False, "error": "Browser-Tools-Server不可用"}

        try:
            response = await self.client.post(f"{self.base_url}/audit/seo", json={"url": url})
            if response.status_code == 200:
                return {"success": True, "data": response.json()}
            else:
                return {"success": False, "error": f"HTTP {response.status_code}"}
        except Exception as e:
            logger.error(f"SEO审计失败: {e}")
            return {"success": False, "error": str(e)}

    async def run_best_practices_audit(self, url: str) -> dict[str, Any]:
        """运行最佳实践审计"""
        if not await self.check_server_available():
            return {"success": False, "error": "Browser-Tools-Server不可用"}

        try:
            response = await self.client.post(
                f"{self.base_url}/audit/best-practices", json={"url": url}
            )
            if response.status_code == 200:
                return {"success": True, "data": response.json()}
            else:
                return {"success": False, "error": f"HTTP {response.status_code}"}
        except Exception as e:
            logger.error(f"最佳实践审计失败: {e}")
            return {"success": False, "error": str(e)}

    async def run_audit_mode(self, url: str) -> dict[str, Any]:
        """运行完整审计模式（所有审计）"""
        if not await self.check_server_available():
            return {"success": False, "error": "Browser-Tools-Server不可用"}

        try:
            response = await self.client.post(f"{self.base_url}/audit/all", json={"url": url})
            if response.status_code == 200:
                return {"success": True, "data": response.json()}
            else:
                return {"success": False, "error": f"HTTP {response.status_code}"}
        except Exception as e:
            logger.error(f"完整审计失败: {e}")
            return {"success": False, "error": str(e)}

    async def capture_screenshot(self, url: str | None = None) -> dict[str, Any]:
        """捕获截图"""
        if not await self.check_server_available():
            return {"success": False, "error": "Browser-Tools-Server不可用"}

        try:
            payload = {}
            if url:
                payload["url"] = url

            response = await self.client.post(f"{self.base_url}/screenshot", json=payload)
            if response.status_code == 200:
                return {"success": True, "data": response.json()}
            else:
                return {"success": False, "error": f"HTTP {response.status_code}"}
        except Exception as e:
            logger.error(f"截图捕获失败: {e}")
            return {"success": False, "error": str(e)}

    async def get_console_logs(self) -> dict[str, Any]:
        """获取控制台日志"""
        if not await self.check_server_available():
            return {"success": False, "error": "Browser-Tools-Server不可用"}

        try:
            response = await self.client.get(f"{self.base_url}/logs/console")
            if response.status_code == 200:
                return {"success": True, "data": response.json()}
            else:
                return {"success": False, "error": f"HTTP {response.status_code}"}
        except Exception as e:
            logger.error(f"获取控制台日志失败: {e}")
            return {"success": False, "error": str(e)}

    async def get_network_logs(self) -> dict[str, Any]:
        """获取网络日志"""
        if not await self.check_server_available():
            return {"success": False, "error": "Browser-Tools-Server不可用"}

        try:
            response = await self.client.get(f"{self.base_url}/logs/network")
            if response.status_code == 200:
                return {"success": True, "data": response.json()}
            else:
                return {"success": False, "error": f"HTTP {response.status_code}"}
        except Exception as e:
            logger.error(f"获取网络日志失败: {e}")
            return {"success": False, "error": str(e)}

    async def close(self):
        """关闭HTTP客户端"""
        await self.client.aclose()


# 全局实例
_browser_tools_integration: BrowserToolsIntegration | None = None


def get_browser_tools_integration() -> BrowserToolsIntegration:
    """获取Browser-Tools集成实例"""
    global _browser_tools_integration
    if _browser_tools_integration is None:
        _browser_tools_integration = BrowserToolsIntegration()
    return _browser_tools_integration
