#!/usr/bin/env python3
"""
安全性增强中间件
- CSRF保护
- 安全头设置
- 输入验证
"""

import logging
import secrets

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger(__name__)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """安全头中间件 - 同时设置安全头和HTTP缓存头"""

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)

        # 设置安全头
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "SAMEORIGIN"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

        # CSP (Content Security Policy)
        csp = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' 'unsafe-eval'; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data: https:; "
            "font-src 'self' data:; "
            "connect-src 'self' ws: wss:; "
            "frame-src 'self'; "
            "frame-ancestors 'self';"
        )
        response.headers["Content-Security-Policy"] = csp

        # HSTS (如果使用HTTPS)
        if request.url.scheme == "https":
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"

        # HTTP缓存头设置（性能优化）
        path = request.url.path

        # 静态资源 - 长期缓存
        if any(
            path.startswith(prefix)
            for prefix in ["/_dash-", "/_dash-component-suites/", "/static/", "/assets/"]
        ):
            response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
            response.headers["ETag"] = f'"{hash(str(path))}"'
        # API端点 - 根据路径设置不同的缓存策略
        elif path.startswith("/api/monitoring/"):
            # 监控API - 短缓存（5秒）
            response.headers["Cache-Control"] = "public, max-age=5"
        elif path.startswith("/api/viewer/statistics") or path.startswith(
            "/api/collaboration/statistics"
        ):
            # 统计API - 中等缓存（30秒）
            response.headers["Cache-Control"] = "public, max-age=30"
        elif path.startswith("/api/viewer/") or path.startswith("/api/collaboration/agents"):
            # 其他viewer和协作API - 中等缓存（30秒）
            response.headers["Cache-Control"] = "public, max-age=30"
        elif path.startswith("/api/"):
            # 其他API - 不缓存或短缓存
            response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        else:
            # HTML页面 - 不缓存
            if path.endswith(".html") or path == "/" or path == "/login":
                response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"

        return response


class CSRFProtectionMiddleware(BaseHTTPMiddleware):
    """CSRF保护中间件"""

    def __init__(self, app, secret_key: str = None):
        super().__init__(app)
        self.secret_key = secret_key or secrets.token_urlsafe(32)

    async def dispatch(self, request: Request, call_next):
        # 跳过GET、HEAD、OPTIONS请求
        if request.method in ["GET", "HEAD", "OPTIONS"]:
            return await call_next(request)

        # 检查CSRF token
        csrf_token = request.headers.get("X-CSRF-Token")
        cookie_token = request.cookies.get("csrf_token")

        if not csrf_token or csrf_token != cookie_token:
            from fastapi.responses import JSONResponse

            return JSONResponse({"error": "CSRF token mismatch"}, status_code=403)

        response = await call_next(request)

        # 设置CSRF token cookie（如果不存在）
        if "csrf_token" not in request.cookies:
            csrf_token = secrets.token_urlsafe(32)
            response.set_cookie(
                "csrf_token",
                csrf_token,
                httponly=False,  # 需要JavaScript访问
                secure=False,  # 开发环境
                samesite="lax",
            )

        return response


def sanitize_input(value: str) -> str:
    """输入清理"""
    if not isinstance(value, str):
        return value

    # 移除潜在的XSS字符
    dangerous_chars = ["<", ">", '"', "'", "&", "\x00"]
    for char in dangerous_chars:
        value = value.replace(char, "")

    return value.strip()
