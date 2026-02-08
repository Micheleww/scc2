"""
Clawdbot/OpenClaw gateway proxy service.

This service exists so SCC's unified server (often running in Docker) can
provide a single-port access pattern:
  http://127.0.0.1:18788/clawdbot/*

The upstream gateway typically runs on the Windows host (or on another device),
so the proxy supports:
- CLAWDBOT_UPSTREAM=http://host.docker.internal:19001
- CLAWDBOT_GATEWAY_PORT=19001 (fallback when upstream not set)
"""

from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path
from typing import Any, Optional

from tools.unified_server.core.service_registry import Service
from fastapi import Request

logger = logging.getLogger(__name__)


def _normalize_base(url: str) -> str:
    s = str(url or "").strip()
    return s.rstrip("/") if s else ""


def _http_to_ws(base: str) -> str:
    if base.startswith("https://"):
        return "wss://" + base[len("https://") :]
    if base.startswith("http://"):
        return "ws://" + base[len("http://") :]
    return base


class ClawdbotService(Service):
    def __init__(
        self,
        name: str,
        enabled: bool,
        repo_root: Optional[Path] = None,
        path: str = "/clawdbot",
        secret_key: Optional[str] = None,
        gateway_port: Optional[int] = None,
        auto_allocate_port: bool = False,  # kept for API compatibility; not used here
        upstream: str = "",
        **_ignored: Any,  # compatibility with older call sites
    ) -> None:
        super().__init__(name, enabled, auto_allocate_port=False)
        self.path = path
        self.repo_root = repo_root or Path(__file__).resolve().parents[4]
        self.secret_key = (secret_key or os.getenv("CLAWDBOT_SECRET_KEY", "") or "").strip()
        # OpenClaw Gateway uses X-OpenClaw-Token auth for non-loopback binds.
        # We keep this separate from CLAWDBOT_SECRET_KEY (which is SCC-side).
        self.gateway_token = (os.getenv("CLAWDBOT_GATEWAY_TOKEN", "") or "").strip()
        self.gateway_port = int(gateway_port or int(os.getenv("CLAWDBOT_GATEWAY_PORT", "19001")))
        self.upstream = _normalize_base(upstream or os.getenv("CLAWDBOT_UPSTREAM", ""))
        self._app: Any = None

    def _default_upstream(self) -> str:
        return f"http://127.0.0.1:{self.gateway_port}"

    async def initialize(self) -> None:
        from fastapi import FastAPI, WebSocket
        from fastapi.responses import HTMLResponse
        from fastapi.responses import JSONResponse, Response
        import httpx

        app = FastAPI(title="Clawdbot/OpenClaw Proxy", version="1.0.0")

        upstream = self.upstream or self._default_upstream()

        def _maybe_auth_headers(headers: dict[str, str]) -> dict[str, str]:
            # Gateway auth token (preferred).
            if self.gateway_token:
                headers.setdefault("x-openclaw-token", self.gateway_token)
            # SCC-side secret (optional; used by some installations).
            if self.secret_key:
                headers.setdefault("X-Clawdbot-Secret", self.secret_key)
            return headers

        @app.get("/health")
        async def health():
            try:
                async with httpx.AsyncClient(timeout=3.0) as client:
                    # OpenClaw Gateway uses /healthz (not /health) in recent builds.
                    # Keep /health as fallback for older gateways.
                    headers: dict[str, str] = _maybe_auth_headers({})
                    r = await client.get(upstream + "/healthz", headers=headers)
                    if r.status_code == 404:
                        r = await client.get(upstream + "/health", headers=headers)
                return {
                    "status": "healthy" if r.status_code == 200 else "degraded",
                    "gateway": "connected" if r.status_code == 200 else "reachable",
                    "upstream": upstream,
                    "status_code": r.status_code,
                }
            except Exception as e:  # noqa: BLE001
                return JSONResponse(status_code=503, content={"status": "degraded", "gateway": "unavailable", "upstream": upstream, "error": str(e)})

        @app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS", "HEAD"])
        async def proxy_http(path: str, request: Request):
            try:
                target_url = f"{upstream}/{path}"
                body = await request.body()
                headers = dict(request.headers)
                headers.pop("host", None)
                headers.pop("content-length", None)
                headers = _maybe_auth_headers(headers)

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
                if request.method == "GET" and (path or "") == "" and "text/html" in (request.headers.get("accept") or ""):
                    hint = (
                        "<h2>OpenClaw 未连接</h2>"
                        "<p>统一服务器会把 Windows 主机上的 OpenClaw Gateway 代理到这里。</p>"
                        f"<p><b>Upstream</b>: <code>{upstream}</code></p>"
                        "<p>请在 Windows 主机启动 OpenClaw Gateway（默认端口 19001），然后刷新。</p>"
                        "<p><a href=\"/clawdbot/health\">/clawdbot/health</a></p>"
                    )
                    return HTMLResponse(content=f"<!doctype html><html><body style='font-family:Segoe UI, sans-serif'>{hint}</body></html>", status_code=503)
                return JSONResponse(status_code=503, content={"error": "clawdbot_upstream_unreachable", "upstream": upstream})
            except Exception as e:  # noqa: BLE001
                logger.error("Clawdbot proxy error: %s", e, exc_info=True)
                return JSONResponse(status_code=502, content={"error": f"clawdbot_proxy_error: {e}"})

        try:
            import websockets

            # The OpenClaw gateway is primarily WebSocket-driven and uses a fixed WS path,
            # currently `/__openclaw__/ws`. We proxy any WS upgrade path 1:1 to upstream.
            @app.websocket("/{path:path}")
            async def proxy_ws(path: str, websocket: WebSocket):
                ws_url = f"{_http_to_ws(upstream)}/{path}"
                qs = str(websocket.url.query or "").strip()
                if qs:
                    ws_url += "?" + qs
                await websocket.accept()
                try:
                    extra_headers: list[tuple[str, str]] = []
                    if self.gateway_token:
                        extra_headers.append(("x-openclaw-token", self.gateway_token))
                    if self.secret_key:
                        extra_headers.append(("X-Clawdbot-Secret", self.secret_key))

                    async with websockets.connect(ws_url, extra_headers=extra_headers or None) as target:
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

                        await asyncio.gather(_to_up(), _to_down())
                except Exception as e:  # noqa: BLE001
                    logger.error("Clawdbot WS proxy error: %s", e, exc_info=True)
                    try:
                        await websocket.close(code=1011, reason=str(e))
                    except Exception:
                        pass

        except Exception:
            pass

        self._app = app
        logger.info("Clawdbot proxy initialized: path=%s upstream=%s", self.path, upstream)

    async def shutdown(self) -> None:
        logger.info("Clawdbot proxy shutting down")

    def get_app(self) -> Any:
        return self._app
