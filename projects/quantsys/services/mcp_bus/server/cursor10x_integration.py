#!/usr/bin/env python3
"""
Cursor10x (DevContext) 集成模块
桥接Cursor10x的MCP工具到MCP Bus
通过subprocess调用cursor10x-mcp的MCP工具
"""

import asyncio
import json
import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

# Cursor10x配置
CURSOR10X_ENABLED = os.getenv("CURSOR10X_ENABLED", "false").lower() == "true"
TURSO_DATABASE_URL = os.getenv("TURSO_DATABASE_URL", "")
TURSO_AUTH_TOKEN = os.getenv("TURSO_AUTH_TOKEN", "")


class Cursor10xMCPClient:
    """Cursor10x MCP客户端（通过subprocess调用）"""

    def __init__(self):
        """初始化MCP客户端"""
        self.env = os.environ.copy()
        if TURSO_DATABASE_URL:
            self.env["TURSO_DATABASE_URL"] = TURSO_DATABASE_URL
        if TURSO_AUTH_TOKEN:
            self.env["TURSO_AUTH_TOKEN"] = TURSO_AUTH_TOKEN

    async def call_tool(self, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        """调用MCP工具"""
        try:
            # 构建MCP JSON-RPC请求
            request = {
                "jsonrpc": "2.0",
                "method": "tools/call",
                "params": {"name": tool_name, "arguments": arguments},
                "id": f"cursor10x-{tool_name}-{hash(str(arguments))}",
            }

            # 通过subprocess调用cursor10x-mcp
            # 注意：这需要cursor10x-mcp已经安装并可用
            process = await asyncio.create_subprocess_exec(
                "npx",
                "cursor10x-mcp",
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=self.env,
            )

            # 发送请求
            request_json = json.dumps(request) + "\n"
            stdout, stderr = await process.communicate(request_json.encode())

            if process.returncode != 0:
                error_msg = stderr.decode() if stderr else "Unknown error"
                logger.error(f"Cursor10x MCP调用失败: {error_msg}")
                return {"success": False, "error": error_msg}

            # 解析响应
            response_text = stdout.decode()
            try:
                response = json.loads(response_text)
                if "error" in response:
                    return {"success": False, "error": response["error"]}
                return {"success": True, "data": response.get("result", {})}
            except json.JSONDecodeError as e:
                logger.error(f"Cursor10x响应解析失败: {e}")
                return {"success": False, "error": f"响应解析失败: {e}"}

        except FileNotFoundError:
            logger.error("cursor10x-mcp未找到，请确保已安装: npm install -g cursor10x-mcp")
            return {"success": False, "error": "cursor10x-mcp未安装"}
        except Exception as e:
            logger.error(f"Cursor10x MCP调用异常: {e}")
            return {"success": False, "error": str(e)}


class Cursor10xIntegration:
    """Cursor10x集成类"""

    def __init__(self):
        """初始化集成"""
        self.enabled = CURSOR10X_ENABLED and bool(TURSO_DATABASE_URL) and bool(TURSO_AUTH_TOKEN)
        self.client = None
        if self.enabled:
            try:
                self.client = Cursor10xMCPClient()
                logger.info("Cursor10x MCP客户端已初始化")
            except Exception as e:
                logger.warning(f"Cursor10x MCP客户端初始化失败: {e}")
                self.enabled = False
        else:
            logger.warning("Cursor10x未启用或配置不完整")

    def is_available(self) -> bool:
        """检查是否可用"""
        return self.enabled and self.client is not None

    async def store_memory(
        self, content: str, memory_type: str = "short_term", importance: int = 5
    ) -> dict[str, Any]:
        """存储记忆"""
        if not self.is_available():
            return {"success": False, "error": "Cursor10x未启用或不可用"}

        try:
            # 调用Cursor10x的存储记忆工具
            # 注意：实际的工具名称可能不同，需要根据cursor10x-mcp的文档调整
            result = await self.client.call_tool(
                "mcp_cursor10x_storeMemory",
                {"content": content, "memory_type": memory_type, "importance": importance},
            )
            return result
        except Exception as e:
            logger.error(f"存储记忆失败: {e}")
            return {"success": False, "error": str(e)}

    async def retrieve_memory(self, query: str, limit: int = 10) -> dict[str, Any]:
        """检索记忆"""
        if not self.is_available():
            return {"success": False, "error": "Cursor10x未启用或不可用"}

        try:
            # 调用Cursor10x的检索记忆工具
            result = await self.client.call_tool(
                "mcp_cursor10x_retrieveMemory", {"query": query, "limit": limit}
            )
            return result
        except Exception as e:
            logger.error(f"检索记忆失败: {e}")
            return {"success": False, "error": str(e)}

    async def get_memory_stats(self) -> dict[str, Any]:
        """获取记忆统计"""
        if not self.is_available():
            return {"success": False, "error": "Cursor10x未启用或不可用"}

        try:
            # 调用Cursor10x的获取统计工具
            result = await self.client.call_tool("mcp_cursor10x_getMemoryStats", {})
            return result
        except Exception as e:
            logger.error(f"获取记忆统计失败: {e}")
            return {"success": False, "error": str(e)}

    async def check_health(self) -> dict[str, Any]:
        """检查健康状态"""
        if not self.is_available():
            return {"success": False, "error": "Cursor10x未启用或不可用"}

        try:
            # 调用健康检查工具
            result = await self.client.call_tool("mcp_cursor10x_checkHealth", {})
            return result
        except Exception as e:
            logger.error(f"健康检查失败: {e}")
            return {"success": False, "error": str(e)}


# 全局实例
_cursor10x_integration: Cursor10xIntegration | None = None


def get_cursor10x_integration() -> Cursor10xIntegration:
    """获取Cursor10x集成实例"""
    global _cursor10x_integration
    if _cursor10x_integration is None:
        _cursor10x_integration = Cursor10xIntegration()
    return _cursor10x_integration
