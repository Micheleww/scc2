"""
Desktop/user-facing entrypoints for local-only Unified Server.

- `/desktop`: a simple landing page for human users
- `/client-config/*`: canonical client configuration snippets (Trae, etc.)
"""

from __future__ import annotations

import json
from typing import Any, Dict, Tuple

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response

from .client_config import CLIENT_CONFIG_EXAMPLES

router = APIRouter(tags=["desktop"])


def _base_url(request: Request) -> str:
    base = str(request.base_url).rstrip("/")
    return base


def _make_client_config(client_type: str, base: str) -> Dict[str, Any]:
    src = CLIENT_CONFIG_EXAMPLES.get(client_type)
    if not src:
        return {}

    out: Dict[str, Any] = {
        "client_type": client_type,
        "description": src.get("description", ""),
    }
    if "file_path" in src:
        out["file_path"] = src["file_path"]

    if "config" in src:
        cfg = json.loads(json.dumps(src["config"]))
        try:
            cfg["mcpServers"]["qcc-bus-local"]["transport"]["url"] = f"{base}/mcp"
        except Exception:
            pass
        out["config"] = cfg

    if "code" in src:
        code = str(src["code"])
        # Keep examples canonical and aligned with the current server origin.
        code = code.replace('UNIFIED_SERVER_URL = "http://localhost:18788"', f'UNIFIED_SERVER_URL = "{base}"')
        code = code.replace("const UNIFIED_SERVER_URL = 'http://localhost:18788';", f"const UNIFIED_SERVER_URL = '{base}';")
        out["code"] = code

    return out


def _download_payload(client_type: str, base: str) -> Tuple[str, str, bytes]:
    cfg = _make_client_config(client_type, base)
    if not cfg:
        return ("text/plain; charset=utf-8", f"{client_type}.txt", b"unknown client_type\n")

    if "config" in cfg:
        content = json.dumps(cfg["config"], ensure_ascii=False, indent=2).encode("utf-8")
        filename = f"{client_type}.json"
        return ("application/json; charset=utf-8", filename, content)

    if "code" in cfg:
        content = str(cfg["code"]).encode("utf-8")
        filename = f"{client_type}.txt"
        return ("text/plain; charset=utf-8", filename, content)

    content = json.dumps(cfg, ensure_ascii=False, indent=2).encode("utf-8")
    return ("application/json; charset=utf-8", f"{client_type}.json", content)


@router.get("/client-config")
async def list_client_configs(request: Request):
    base = _base_url(request)
    items = []
    for k in sorted(CLIENT_CONFIG_EXAMPLES.keys()):
        cfg = _make_client_config(k, base)
        if cfg:
            items.append(cfg)
    return {"ok": True, "base_url": base, "items": items}


@router.get("/client-config/{client_type}")
async def get_client_config(client_type: str, request: Request):
    base = _base_url(request)
    cfg = _make_client_config(client_type, base)
    if not cfg:
        return JSONResponse(status_code=404, content={"ok": False, "error": "unknown_client_type"})
    return {"ok": True, "base_url": base, "config": cfg}


@router.get("/client-config/{client_type}/download")
async def download_client_config(client_type: str, request: Request):
    base = _base_url(request)
    mime, filename, content = _download_payload(client_type, base)
    return Response(
        content=content,
        media_type=mime,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/desktop", response_class=HTMLResponse)
async def desktop_home(request: Request):
    base = _base_url(request)
    return HTMLResponse(
        f"""
<!doctype html>
<html lang="zh">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width,initial-scale=1" />
    <title>SCC Desktop</title>
    <style>
      body {{ font-family: ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Helvetica, Arial, "Apple Color Emoji","Segoe UI Emoji"; padding: 24px; }}
      code {{ background: #f3f4f6; padding: 2px 6px; border-radius: 6px; }}
      .grid {{ display: grid; grid-template-columns: 1fr; gap: 12px; max-width: 900px; }}
      a {{ text-decoration: none; }}
      .card {{ border: 1px solid #e5e7eb; border-radius: 12px; padding: 14px 16px; }}
      .muted {{ color: #6b7280; }}
    </style>
  </head>
  <body>
    <h1>SCC Desktop（本机）</h1>
    <p class="muted">统一入口：<code>{base}</code>（单端口 18788）。</p>
    <div class="grid">
      <div class="card">
        <div><a href="/" target="_blank" rel="noreferrer">Workbench UI</a></div>
        <div class="muted"><code>/</code></div>
      </div>
      <div class="card">
        <div><a href="/health/ready" target="_blank" rel="noreferrer">健康检查</a></div>
        <div class="muted"><code>/health/ready</code></div>
      </div>
      <div class="card">
        <div><a href="/scc" target="_blank" rel="noreferrer">SCC Console</a></div>
        <div class="muted"><code>/scc</code></div>
      </div>


      <div class="card">
        <div><a href="/clawdbot/health" target="_blank" rel="noreferrer">OpenClaw (Gateway Proxy)</a></div>
        <div class="muted"><code>/clawdbot</code></div>
      </div>
      <div class="card">
        <div><a href="/opencode/health" target="_blank" rel="noreferrer">OpenCode (UI/API Proxy)</a></div>
        <div class="muted"><code>/opencode</code></div>
      </div>
      <div class="card">
        <div><a href="/viewer" target="_blank" rel="noreferrer">Viewer</a></div>
        <div class="muted"><code>/viewer</code></div>
      </div>
      <div class="card">
        <div><a href="/client-config" target="_blank" rel="noreferrer">客户端配置（归一化）</a></div>
        <div class="muted">Trae / Python / JS 示例（可下载）。</div>
      </div>
    </div>
  </body>
</html>
""".strip()
    )
