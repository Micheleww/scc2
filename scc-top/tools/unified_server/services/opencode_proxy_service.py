"""
OpenCode proxy service.

This runs inside the unified server process and forwards requests to an
external OpenCode upstream (typically running on the Windows host).

Motivation:
- OpenCode (Windows exe) cannot run inside the linux-based SCC docker image.
- We still want a single-port experience: http://<unified>:18788/opencode/*
"""

from __future__ import annotations

import logging
from typing import Any

from tools.unified_server.core.service_registry import Service
from fastapi import Request

logger = logging.getLogger(__name__)


def _normalize_base(url: str) -> str:
    s = str(url or "").strip()
    if not s:
        return ""
    return s.rstrip("/")


class OpenCodeProxyService(Service):
    def __init__(
        self,
        name: str,
        enabled: bool,
        *,
        path: str = "/opencode",
        upstream: str,
    ) -> None:
        super().__init__(name, enabled, auto_allocate_port=False)
        self.path = path
        self.upstream = _normalize_base(upstream)
        self._app: Any = None

    async def initialize(self) -> None:
        from fastapi import FastAPI, WebSocket
        from fastapi.responses import HTMLResponse
        from fastapi.responses import JSONResponse, Response
        import httpx

        app = FastAPI(title="OpenCode Proxy", version="1.0.0")

        upstream = self.upstream
        if not upstream:
            upstream = ""

        @app.get("/health")
        async def health():
            if not upstream:
                return JSONResponse(status_code=503, content={"status": "degraded", "opencode": "unconfigured"})
            for path in ("/health", "/global/health", "/api/health"):
                try:
                    async with httpx.AsyncClient(timeout=3.0) as client:
                        r = await client.get(upstream + path)
                        if r.status_code < 500:
                            return {
                                "status": "healthy" if r.status_code == 200 else "degraded",
                                "opencode": "connected" if r.status_code == 200 else "reachable",
                                "upstream": upstream,
                                "probe": path,
                                "status_code": r.status_code,
                            }
                except Exception:
                    continue
            return JSONResponse(status_code=503, content={"status": "degraded", "opencode": "unavailable", "upstream": upstream})

        @app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS", "HEAD"])
        async def proxy_http(path: str, request: Request):
            if not upstream:
                return JSONResponse(status_code=503, content={"error": "opencode_upstream_unconfigured"})
            try:
                target_url = f"{upstream}/{path}"
                body = await request.body()
                headers = dict(request.headers)
                headers.pop("host", None)
                headers.pop("content-length", None)
                async with httpx.AsyncClient(timeout=30.0, follow_redirects=False) as client:
                    resp = await client.request(
                        method=request.method,
                        url=target_url,
                        headers=headers,
                        content=body if body else None,
                        params=dict(request.query_params),
                    )
                content_type = resp.headers.get("content-type", "")
                if "application/json" in content_type:
                    try:
                        return JSONResponse(content=resp.json(), status_code=resp.status_code, headers=dict(resp.headers))
                    except Exception:
                        return Response(content=resp.content, status_code=resp.status_code, headers=dict(resp.headers), media_type=content_type)
                return Response(content=resp.content, status_code=resp.status_code, headers=dict(resp.headers), media_type=content_type or None)
            except httpx.ConnectError:
                # In Workbench we usually embed OpenCode in an iframe. Provide an HTML landing page
                # so the UI isn't a blank error when the upstream isn't started yet.
                if request.method == "GET" and (path or "") == "" and "text/html" in (request.headers.get("accept") or ""):
                    hint = (
                        "<h2>OpenCode 未连接</h2>"
                        "<p>统一服务器会把 Windows 主机上的 OpenCode 服务代理到这里。</p>"
                        f"<p><b>Upstream</b>: <code>{upstream}</code></p>"
                        "<p>请在 Windows 主机启动 OpenCode（默认端口 18790），然后刷新。</p>"
                        "<p><a href=\"/opencode/health\">/opencode/health</a></p>"
                    )
                    return HTMLResponse(content=f"<!doctype html><html><body style='font-family:Segoe UI, sans-serif'>{hint}</body></html>", status_code=503)
                return JSONResponse(status_code=503, content={"error": "opencode_upstream_unreachable", "upstream": upstream})
            except Exception as e:  # noqa: BLE001
                logger.error("OpenCode proxy error: %s", e, exc_info=True)
                return JSONResponse(status_code=502, content={"error": f"opencode_proxy_error: {e}"})

        try:
            import websockets

            @app.websocket("/ws/{path:path}")
            async def proxy_ws(path: str, websocket: WebSocket):
                if not upstream:
                    await websocket.accept()
                    await websocket.close(code=1011, reason="opencode_upstream_unconfigured")
                    return
                try:
                    up = upstream
                    if up.startswith("https://"):
                        ws_base = "wss://" + up[len("https://") :]
                    elif up.startswith("http://"):
                        ws_base = "ws://" + up[len("http://") :]
                    else:
                        ws_base = up
                    ws_url = f"{ws_base}/ws/{path}"
                    qs = str(websocket.url.query or "").strip()
                    if qs:
                        ws_url += "?" + qs
                    await websocket.accept()
                    async with websockets.connect(ws_url) as target:
                        async def _to_up():
                            try:
                                while True:
                                    msg = await websocket.receive_text()
                                    await target.send(msg)
                            except Exception:
                                pass

                        async def _to_down():
                            try:
                                async for msg in target:
                                    await websocket.send_text(msg)
                            except Exception:
                                pass

                        import asyncio

                        await asyncio.gather(_to_up(), _to_down())
                except Exception as e:  # noqa: BLE001
                    logger.error("OpenCode WS proxy error: %s", e, exc_info=True)
                    try:
                        await websocket.close(code=1011, reason=str(e))
                    except Exception:
                        pass

        except Exception:
            pass

        self._app = app
        logger.info("OpenCode proxy initialized: path=%s upstream=%s", self.path, self.upstream)

    async def shutdown(self) -> None:
        logger.info("OpenCode proxy shutting down")

    def get_app(self) -> Any:
        return self._app
