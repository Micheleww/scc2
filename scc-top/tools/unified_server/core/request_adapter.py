"""
请求适配器模块

处理应用与统一服务器之间的请求适配：
1. 路径前缀适配（向后兼容）
2. 请求头适配
3. 响应格式适配
"""

import logging
from typing import Optional
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

logger = logging.getLogger(__name__)


class PathAdapterMiddleware(BaseHTTPMiddleware):
    """
    路径适配中间件
    
    提供向后兼容的路径映射：
    - /mcp (原MCP总线) -> /mcp (保持不变)
    - /api (原A2A Hub) -> /api (保持不变)
    - /exchange (原Exchange Server) -> /exchange (保持不变)
    
    同时支持旧路径的直接访问（如果应用仍使用旧端口）
    """
    
    # NOTE:
    # Unified server mounts each service under a path prefix (e.g. /mcp).
    # Some embedded services (e.g. MCP Bus) are implemented with their own
    # "/mcp" route at the app root. When mounted at "/mcp", the effective path
    # becomes "/mcp/mcp". This middleware provides a small compatibility shim:
    # - External POST/GET /mcp -> internal /mcp/mcp
    
    async def dispatch(self, request: Request, call_next: ASGIApp) -> Response:
        """处理请求路径适配"""
        original_path = request.url.path

        # Control-plane compatibility shim:
        # /api is reserved for legacy A2A Hub (mounted under /api). Historically we used /api/*
        # for unified-server endpoints too; once A2A Hub is mounted, those paths become unreachable.
        # Rewrite a small allowlist of /api/* control-plane endpoints to /cp/*.
        if original_path.startswith("/api/"):
            # Keep A2A Hub endpoints intact (do not rewrite /api/health or /api/task/* etc).
            rewrites = (
                ("/api/executor", "/cp/executor"),
                ("/api/files", "/cp/files"),
                ("/api/executors", "/cp/executors"),
                ("/api/jobs", "/cp/jobs"),
                ("/api/system/info", "/cp/system/info"),
                ("/api/memory", "/cp/memory"),
            )
            for src, dst in rewrites:
                if original_path == src or original_path.startswith(src + "/"):
                    new_path = dst + original_path[len(src) :]
                    request.scope["path"] = new_path
                    request.scope["raw_path"] = new_path.encode("utf-8", errors="ignore")
                    break

        # MCP Bus compatibility: mounted app expects "/mcp" internally.
        if original_path == "/mcp":
            request.scope["path"] = "/mcp/mcp"
            request.scope["raw_path"] = b"/mcp/mcp"
        # Expose MCP Bus web viewer on the unified root for convenience.
        # The viewer HTML uses absolute /api/viewer/* endpoints, so we also
        # forward those to the MCP Bus mount.
        elif original_path == "/viewer" or original_path.startswith("/viewer/"):
            new_path = f"/mcp{original_path}"
            request.scope["path"] = new_path
            request.scope["raw_path"] = new_path.encode("utf-8", errors="ignore")
        elif original_path == "/login" or original_path.startswith("/login/"):
            new_path = f"/mcp{original_path}"
            request.scope["path"] = new_path
            request.scope["raw_path"] = new_path.encode("utf-8", errors="ignore")
        elif original_path.startswith("/api/viewer/"):
            new_path = f"/mcp{original_path}"
            request.scope["path"] = new_path
            request.scope["raw_path"] = new_path.encode("utf-8", errors="ignore")
        
        # 检查是否需要路径适配
        # 如果路径已经在映射表中，直接使用
        # 如果路径不在映射表中，检查是否是旧路径
        
        # 获取请求头中的信息，判断是否来自旧客户端
        user_agent = request.headers.get("User-Agent", "")
        referer = request.headers.get("Referer", "")
        
        # 检查是否是旧端口的请求（通过Host头判断）
        host = request.headers.get("Host", "")
        
        # 如果请求来自旧端口（通过Host判断），进行路径适配
        # 但统一服务器已经挂载到正确路径，所以这里主要是记录日志
        
        # 记录请求信息（用于调试）
        if logger.level <= logging.DEBUG:
            logger.debug(
                f"Request: {request.method} {original_path} "
                f"from {request.client.host if request.client else 'unknown'}"
            )
        
        # 继续处理请求（路径已经在应用工厂中正确挂载）
        response = await call_next(request)
        
        # 添加适配信息到响应头
        response.headers["X-Path-Adapter"] = "unified-server"
        response.headers["X-Original-Path"] = original_path
        
        return response


class RequestIDPropagationMiddleware(BaseHTTPMiddleware):
    """
    请求ID传播中间件
    
    确保请求ID在所有服务间传播
    """
    
    async def dispatch(self, request: Request, call_next: ASGIApp) -> Response:
        """传播请求ID"""
        # 获取或生成请求ID
        request_id = request.headers.get("X-Request-ID") or request.headers.get("X-Trace-ID")
        
        if request_id:
            # 将请求ID添加到请求状态
            request.state.request_id = request_id
            # 确保请求ID传播到子服务
            # 这会在子服务的请求中自动包含
        
        response = await call_next(request)
        
        # 确保响应包含请求ID
        if hasattr(request.state, "request_id"):
            response.headers["X-Request-ID"] = request.state.request_id
        
        return response


class CORSAdapterMiddleware(BaseHTTPMiddleware):
    """
    CORS适配中间件
    
    处理跨域请求，确保所有服务都能正确响应CORS请求
    """
    
    async def dispatch(self, request: Request, call_next: ASGIApp) -> Response:
        """处理CORS请求"""
        # 处理预检请求
        if request.method == "OPTIONS":
            response = Response()
            response.headers["Access-Control-Allow-Origin"] = "*"
            response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS"
            response.headers["Access-Control-Allow-Headers"] = "*"
            response.headers["Access-Control-Allow-Credentials"] = "true"
            return response
        
        response = await call_next(request)
        
        # 添加CORS头
        origin = request.headers.get("Origin")
        if origin:
            response.headers["Access-Control-Allow-Origin"] = origin
            response.headers["Access-Control-Allow-Credentials"] = "true"
        else:
            response.headers["Access-Control-Allow-Origin"] = "*"
        
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS"
        response.headers["Access-Control-Allow-Headers"] = "*"
        
        return response
