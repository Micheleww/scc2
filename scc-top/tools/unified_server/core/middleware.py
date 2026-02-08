
"""
中间件模块

提供可重用的中间件类
"""

import time
import uuid
import logging
import os
from typing import Callable
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

logger = logging.getLogger(__name__)


class RequestIDMiddleware(BaseHTTPMiddleware):
    """请求ID中间件 - 为每个请求生成唯一ID"""
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # 生成或获取请求ID
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        
        # 添加到请求状态
        request.state.request_id = request_id
        
        # 处理请求
        response = await call_next(request)
        
        # 添加请求ID到响应头
        response.headers["X-Request-ID"] = request_id
        
        return response


class LoggingMiddleware(BaseHTTPMiddleware):
    """日志中间件 - 记录请求和响应"""
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        start_time = time.time()
        request_id = getattr(request.state, "request_id", "unknown")
        
        # 记录请求
        logger.info(
            f"Request: {request.method} {request.url.path}",
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "client": request.client.host if request.client else "unknown"
            }
        )
        
        try:
            # 处理请求
            response = await call_next(request)
            
            # 计算处理时间
            process_time = time.time() - start_time
            
            # 记录响应
            logger.info(
                f"Response: {response.status_code}",
                extra={
                    "request_id": request_id,
                    "status_code": response.status_code,
                    "process_time": process_time
                }
            )
            
            # 添加处理时间到响应头
            response.headers["X-Process-Time"] = str(process_time)
            
            return response
            
        except Exception as e:
            # 记录错误
            process_time = time.time() - start_time
            logger.error(
                f"Request failed: {str(e)}",
                extra={
                    "request_id": request_id,
                    "error": str(e),
                    "process_time": process_time
                },
                exc_info=True
            )
            raise


class ErrorHandlingMiddleware(BaseHTTPMiddleware):
    """错误处理中间件 - 统一错误响应格式"""
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        try:
            response = await call_next(request)
            return response
        except Exception as e:
            request_id = getattr(request.state, "request_id", "unknown")
            
            # 记录错误
            logger.error(
                f"Unhandled exception: {str(e)}",
                extra={"request_id": request_id},
                exc_info=True
            )
            
            # 返回统一错误响应
            from fastapi.responses import JSONResponse
            return JSONResponse(
                status_code=500,
                content={
                    "error": "Internal Server Error",
                    "message": str(e) if logger.level <= logging.DEBUG else "An error occurred",
                    "request_id": request_id
                }
            )


class AccessControlMiddleware(BaseHTTPMiddleware):
    """
    Optional enterprise access control:
    - When UNIFIED_SERVER_ADMIN_TOKEN is set, require header X-Admin-Token for non-health endpoints.
    - When UNIFIED_SERVER_ALLOWED_IPS is set, restrict client IPs (comma-separated).

    Defaults are permissive (disabled) unless env vars are set.
    """

    def __init__(self, app: ASGIApp):
        super().__init__(app)
        self.admin_token = (os.environ.get("UNIFIED_SERVER_ADMIN_TOKEN") or "").strip()
        self.allowed_ips = [
            s.strip()
            for s in (os.environ.get("UNIFIED_SERVER_ALLOWED_IPS") or "").split(",")
            if s.strip()
        ]
        self.allow_health_without_token = (
            (os.environ.get("UNIFIED_SERVER_ALLOW_HEALTH_NO_AUTH") or "true").strip().lower()
            != "false"
        )

    def _is_health_path(self, path: str) -> bool:
        return (
            path == "/"
            or path.startswith("/health")
            or path.startswith("/dashboard")
            or path.startswith("/assets")
            or path.startswith("/app")
            # /api is reserved for the legacy A2A Hub WSGI app.
            or path.startswith("/api/health")
            # Unified-server control plane endpoints live under /cp.
            or path.startswith("/cp/system")
            or path.startswith("/cp/health")
        )

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        path = request.url.path
        ip = request.client.host if request.client else ""

        if self.allowed_ips and ip and ip not in self.allowed_ips:
            from fastapi.responses import JSONResponse

            return JSONResponse(status_code=403, content={"error": "forbidden", "detail": f"ip_not_allowed: {ip}"})

        if self.admin_token:
            if self.allow_health_without_token and self._is_health_path(path):
                return await call_next(request)

            token = (request.headers.get("x-admin-token") or "").strip()
            if not token:
                token = (request.cookies.get("admin_token") or "").strip()
            if not token:
                token = (request.query_params.get("token") or "").strip()
            if token != self.admin_token:
                from fastapi.responses import JSONResponse

                return JSONResponse(status_code=401, content={"error": "unauthorized", "detail": "invalid_admin_token"})

        return await call_next(request)
