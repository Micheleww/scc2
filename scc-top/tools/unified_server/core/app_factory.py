
"""
搴旂敤宸ュ巶妯″潡

瀹炵幇搴旂敤宸ュ巶妯″紡锛屾敮鎸侀厤缃鐞嗗拰鐢熷懡鍛ㄦ湡绠＄悊
"""

import logging
import os
import sys
import json
import shutil
import subprocess
import time
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from starlette.responses import FileResponse, PlainTextResponse

from .config import ServerConfig, ServiceConfig, get_config, get_service_config
from .lifecycle import get_lifecycle_manager
from .service_registry import get_service_registry, Service
from .service_registry_config import load_service_registry_config
from .middleware import RequestIDMiddleware, LoggingMiddleware, ErrorHandlingMiddleware, AccessControlMiddleware
from .health import router as health_router
from .desktop_router import router as desktop_router
from .executor_hub import register_executor_hub
import asyncio

logger = logging.getLogger(__name__)


def create_app(config: Optional[ServerConfig] = None) -> FastAPI:
    """
    鍒涘缓FastAPI搴旂敤瀹炰緥
    
    Args:
        config: 鏈嶅姟鍣ㄩ厤缃紝濡傛灉涓篘one鍒欎粠鐜鍙橀噺鍔犺浇
        
    Returns:
        FastAPI搴旂敤瀹炰緥
    """
    # 鑾峰彇閰嶇疆
    if config is None:
        config = get_config()
    
    service_config = get_service_config()
    
    # 璁剧疆椤圭洰鏍硅矾寰?
    if config.repo_root:
        repo_root = Path(config.repo_root)
    else:
        # 鑷姩妫€娴嬮」鐩牴璺緞
        current_file = Path(__file__).resolve()
        repo_root = current_file.parent.parent.parent.parent
    
    # 娣诲姞璺緞鍒皊ys.path
    repo_root_str = str(repo_root)
    if repo_root_str not in sys.path:
        sys.path.insert(0, repo_root_str)
    
    src_path = repo_root / "src"
    if str(src_path) not in sys.path:
        sys.path.insert(0, str(src_path))
    
    # 鑾峰彇鐢熷懡鍛ㄦ湡绠＄悊鍣ㄥ拰鏈嶅姟娉ㄥ唽琛?
    lifecycle = get_lifecycle_manager()
    registry = get_service_registry()
    
    # 鍒涘缓FastAPI搴旂敤
    logger.info("Creating FastAPI application with lifespan")
    logger.info(f"Lifecycle manager: {lifecycle}")
    logger.info(f"Lifespan function: {lifecycle.lifespan}")
    
    app = FastAPI(
        title=config.app_name,
        description="缁熶竴鏈嶅姟鍣?- 鏁村悎MCP鎬荤嚎銆丄2A Hub鍜孍xchange Server",
        version=config.app_version,
        debug=config.debug,
        lifespan=lifecycle.lifespan
    )
    
    logger.info("FastAPI application created successfully")
    
    # 娉ㄥ唽涓棿浠讹紙椤哄簭寰堥噸瑕侊級
    # 璇锋眰閫傞厤涓棿浠讹紙鏈€鍏堟墽琛岋紝纭繚璇锋眰ID浼犳挱鍜岃矾寰勯€傞厤锛?
    try:
        from .request_adapter import (
            PathAdapterMiddleware,
            RequestIDPropagationMiddleware,
        )
        app.add_middleware(RequestIDPropagationMiddleware)
        app.add_middleware(PathAdapterMiddleware)
        logger.info("Request adapter middleware loaded")
    except ImportError as e:
        logger.warning(f"Request adapter middleware not available: {e}")
    
    # 鏍稿績涓棿浠?
    app.add_middleware(AccessControlMiddleware)
    app.add_middleware(RequestIDMiddleware)
    app.add_middleware(LoggingMiddleware)
    app.add_middleware(ErrorHandlingMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=config.cors_origins,
        allow_credentials=config.cors_allow_credentials,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(GZipMiddleware, minimum_size=1000)
    
    # Health endpoints
    app.include_router(health_router)
    # Desktop/user-facing entrypoints
    app.include_router(desktop_router)

    # Remote executor hub (OpenClaw/Windows agents)
    # NOTE: control-plane endpoints live under /cp; /api is reserved for legacy A2A Hub.
    register_executor_hub(app, repo_root=repo_root, base_path="/cp")

    # Unified-server control plane APIs (Tasks/Routing/Logs/Flow/Status)
    try:
        from .control_plane import register_control_plane_routes

        register_control_plane_routes(app, repo_root=repo_root, config=config)
    except Exception as e:
        logger.warning(f"Failed to register control-plane routes: {e}")
    
    # 娉ㄥ唽鏍硅矾寰?
    @app.get("/")
    async def root():
        ui_dist = (repo_root / "tools" / "scc_ui" / "dist").resolve()
        if not ui_dist.exists():
            ui_dist = (repo_root / "scc-top" / "tools" / "scc_ui" / "dist").resolve()
        index = (ui_dist / "index.html").resolve()
        if index.is_file() and str(index).startswith(str(ui_dist)):
            return FileResponse(index)
        msg = (
            "scc_ui is not built.\n"
            "Build it on host:\n"
            "  cd tools/scc_ui\n"
            "  npm install\n"
            "  npm run build\n"
        )
        return PlainTextResponse(msg, status_code=503)

    @app.get("/assets/{asset_path:path}")
    async def ui_assets(asset_path: str):
        ui_dist = (repo_root / "tools" / "scc_ui" / "dist").resolve()
        if not ui_dist.exists():
            ui_dist = (repo_root / "scc-top" / "tools" / "scc_ui" / "dist").resolve()
        assets_dir = (ui_dist / "assets").resolve()
        p = (assets_dir / str(asset_path or "")).resolve()
        if str(p).startswith(str(assets_dir)) and p.is_file():
            return FileResponse(p)
        return JSONResponse(status_code=404, content={"ok": False, "error": "asset_not_found"})

    # Previous JSON root moved here.
    @app.get("/api/system/info")
    async def api_system_info():
        from .service_registry import get_service_registry

        registry = get_service_registry()
        port_allocations = registry.get_port_allocations()

        services_info = {}
        for name, service in registry.get_all().items():
            if service.enabled:
                service_info = {"path": getattr(service, "path", f"/{name}")}
                if service.allocated_port:
                    service_info["allocated_port"] = service.allocated_port
                services_info[name] = service_info

        return {
            "status": "running",
            "service": config.app_name,
            "version": config.app_version,
            "server_port": config.port,
            "endpoints": {
                "health": "/health",
                "ready": "/health/ready",
                "live": "/health/live",
                "ports": "/health/ports",
                "mcp": "/mcp",
                "opencode": "/opencode",
                "clawdbot": "/clawdbot",
                "console": "/scc",
                **{name: info["path"] for name, info in services_info.items()},
            },
            "services": services_info,
            "port_allocations": port_allocations,
        }

    @app.get("/api/health")
    async def api_health():
        # Canonical readiness probe for clients (same semantics as `/health/ready`).
        from .health import readiness_check

        return await readiness_check()

    # --- Memory ledger + secretary/task intake (minimal, server-first) ---
    _memory_lock = threading.Lock()
    _proposals_lock = threading.Lock()

    def _memory_ledger_path() -> Path:
        p = (repo_root / "artifacts" / "scc_state" / "memory_ledger.jsonl").resolve()
        try:
            p.parent.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass
        return p

    def _task_proposals_dir() -> Path:
        p = (repo_root / "artifacts" / "scc_state" / "task_proposals").resolve()
        try:
            p.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass
        return p

    def _tail_jsonl(path: Path, n: int = 100) -> list[dict]:
        n = max(1, min(int(n or 100), 2000))
        if not path.exists():
            return []
        out_lines: list[bytes] = []
        # Read from the end in chunks until we have enough newlines.
        with path.open("rb") as f:
            f.seek(0, os.SEEK_END)
            size = f.tell()
            block = 64 * 1024
            buf = b""
            pos = size
            while pos > 0 and len(out_lines) <= n:
                step = block if pos >= block else pos
                pos -= step
                f.seek(pos, os.SEEK_SET)
                chunk = f.read(step)
                buf = chunk + buf
                parts = buf.split(b"\n")
                # keep the first partial line in buf
                buf = parts[0]
                for b in parts[1:]:
                    if b:
                        out_lines.append(b)
                if pos == 0 and buf:
                    out_lines.append(buf)
            out_lines = out_lines[:n]
        out: list[dict] = []
        for b in reversed(out_lines):
            try:
                out.append(json.loads(b.decode("utf-8", errors="replace")))
            except Exception:
                out.append({"_raw": b.decode("utf-8", errors="replace")})
        return out

    def _slug(s: str) -> str:
        s = (s or "").strip().lower()
        if not s:
            return "proposal"
        out = []
        last_dash = False
        for ch in s:
            ok = ("a" <= ch <= "z") or ("0" <= ch <= "9")
            if ok:
                out.append(ch)
                last_dash = False
            else:
                if not last_dash:
                    out.append("-")
                    last_dash = True
        slug = "".join(out).strip("-")
        if not slug:
            slug = "proposal"
        return slug[:60]

    def _targets_path() -> Path:
        p = (repo_root / "artifacts" / "scc_state" / "secretary_targets.json").resolve()
        try:
            p.parent.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass
        return p

    @app.post("/api/memory/append")
    async def api_memory_append(request: Request):
        body = await request.json()
        if not isinstance(body, dict):
            return JSONResponse(status_code=400, content={"ok": False, "error": "invalid_body"})

        content = str(body.get("content") or "").strip()
        if not content:
            return JSONResponse(status_code=400, content={"ok": False, "error": "missing_content"})

        item = {
            "ts_utc": str(body.get("ts_utc") or "").strip() or datetime.now(timezone.utc).isoformat(),
            "source": str(body.get("source") or "").strip() or "unknown",
            "role": str(body.get("role") or "").strip() or "user",
            "kind": str(body.get("kind") or "").strip() or "message",
            "content": content,
            "meta": body.get("meta") if isinstance(body.get("meta"), dict) else {},
        }

        path = _memory_ledger_path()
        line = (json.dumps(item, ensure_ascii=False) + "\n").encode("utf-8", errors="replace")
        with _memory_lock:
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("ab") as f:
                f.write(line)

        return {"ok": True, "path": str(path), "item": item}

    @app.get("/api/memory/tail")
    async def api_memory_tail(n: int = 100):
        path = _memory_ledger_path()
        items = _tail_jsonl(path, n=n)
        return {"ok": True, "path": str(path), "n": int(n or 100), "items": items}

    @app.get("/api/memory/stats")
    async def api_memory_stats():
        path = _memory_ledger_path()
        try:
            st = path.stat() if path.exists() else None
        except Exception:
            st = None
        return {
            "ok": True,
            "path": str(path),
            "exists": bool(path.exists()),
            "size": int(st.st_size) if st else 0,
            "mtime_utc": datetime.fromtimestamp(st.st_mtime, tz=timezone.utc).isoformat() if st else None,
        }

    @app.post("/api/tasks/propose")
    async def api_tasks_propose(request: Request):
        body = await request.json()
        if not isinstance(body, dict):
            return JSONResponse(status_code=400, content={"ok": False, "error": "invalid_body"})

        title = str(body.get("title") or "").strip()
        if not title:
            title = "Task Proposal"

        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        slug = _slug(title)
        out_dir = _task_proposals_dir()
        out_path = (out_dir / f"{ts}__{slug}.json").resolve()

        payload = {
            "ts_utc": datetime.now(timezone.utc).isoformat(),
            "title": title,
            "proposal": body,
        }

        with _proposals_lock:
            out_dir.mkdir(parents=True, exist_ok=True)
            out_path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", errors="replace"
            )

        rel = None
        try:
            rel = str(out_path.relative_to(repo_root)).replace("\\", "/")
        except Exception:
            rel = str(out_path)

        return {"ok": True, "path": str(out_path), "relpath": rel, "title": title}

    @app.get("/api/tasks/proposals/list")
    async def api_tasks_proposals_list(limit: int = 50):
        limit = max(1, min(int(limit or 50), 200))
        d = _task_proposals_dir()
        if not d.exists():
            return {"ok": True, "dir": str(d), "items": []}
        items = []
        try:
            for p in sorted(d.glob("*.json"), key=lambda x: x.stat().st_mtime, reverse=True)[:limit]:
                try:
                    st = p.stat()
                    items.append(
                        {
                            "name": p.name,
                            "path": str(p),
                            "mtime_utc": datetime.fromtimestamp(st.st_mtime, tz=timezone.utc).isoformat(),
                            "size": int(st.st_size),
                        }
                    )
                except Exception:
                    items.append({"name": p.name, "path": str(p)})
        except Exception:
            items = []
        return {"ok": True, "dir": str(d), "items": items}

    @app.get("/api/secretary/brief")
    async def api_secretary_brief(n_memory: int = 80, proposals_limit: int = 20):
        mem = _tail_jsonl(_memory_ledger_path(), n=n_memory)
        props = await api_tasks_proposals_list(limit=proposals_limit)
        targets_path = _targets_path()
        targets = None
        try:
            if targets_path.exists():
                targets = json.loads(targets_path.read_text(encoding="utf-8", errors="replace") or "null")
        except Exception:
            targets = None
        return {
            "ok": True,
            "ts_utc": datetime.now(timezone.utc).isoformat(),
            "targets": targets,
            "memory_tail": mem,
            "proposals": props.get("items", []) if isinstance(props, dict) else [],
        }

    @app.get("/api/secretary/targets")
    async def api_secretary_targets_get():
        p = _targets_path()
        if not p.exists():
            return {"ok": True, "path": str(p), "targets": None}
        try:
            return {
                "ok": True,
                "path": str(p),
                "targets": json.loads(p.read_text(encoding="utf-8", errors="replace") or "null"),
            }
        except Exception as e:
            return JSONResponse(status_code=500, content={"ok": False, "error": f"read_failed: {e}"})

    @app.post("/api/secretary/targets")
    async def api_secretary_targets_set(request: Request):
        body = await request.json()
        if not isinstance(body, dict):
            return JSONResponse(status_code=400, content={"ok": False, "error": "invalid_body"})
        p = _targets_path()
        payload = {
            "ts_utc": datetime.now(timezone.utc).isoformat(),
            "targets": body,
        }
        try:
            p.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", errors="replace")
        except Exception as e:
            return JSONResponse(status_code=500, content={"ok": False, "error": f"write_failed: {e}"})
        return {"ok": True, "path": str(p), "saved": True}

    @app.get("/app")
    async def legacy_app_redirect():
        return RedirectResponse(url="/", status_code=307)

    @app.get("/app/{path:path}")
    async def legacy_app_redirect_path(path: str):
        path = (path or "").lstrip("/")
        return RedirectResponse(url=f"/{path}", status_code=307)

    @app.get("/scc/system/service_registry")
    async def scc_system_service_registry():
        cfg = load_service_registry_config(repo_root=repo_root)
        if not cfg:
            return JSONResponse(status_code=404, content={"ok": False, "error": "service_registry_config_not_found"})
        return {"ok": True, "path": str(cfg.path.relative_to(repo_root)).replace("\\", "/"), "config": cfg.raw}
    @app.get("/dashboard", response_class=HTMLResponse)
    async def dashboard():
        # Deprecated: dashboard content moved into Workbench -> Settings.
        return RedirectResponse(url="/?view=settings", status_code=307)


    # SCC Console (mobile-friendly): send commands to executors on the always-on Windows host.
    @app.get("/scc", response_class=HTMLResponse)
    async def scc_console():
        return """
<!doctype html>
<html lang="zh-CN">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>SCC 鎺у埗鍙?/title>
    <style>
      :root {
        --bg: #0b1020;
        --card: #121a33;
        --muted: #9aa6c2;
        --text: #e8ecf8;
        --line: rgba(255,255,255,0.10);
        --accent: #6ea8fe;
        --danger: #ff6b6b;
        --ok: #2ecc71;
        --mono: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace;
        --sans: system-ui, -apple-system, Segoe UI, Roboto, sans-serif;
      }
      body { margin: 0; font-family: var(--sans); background: radial-gradient(1200px 800px at 10% 10%, #18224a, var(--bg)); color: var(--text); }
      .wrap { max-width: 980px; margin: 0 auto; padding: 18px 14px 30px; }
      .layout { display: flex; gap: 12px; align-items: flex-start; }
      .sidebar { width: 210px; position: sticky; top: 14px; }
      .content { flex: 1; min-width: 0; }
      .title { display: flex; align-items: baseline; justify-content: space-between; gap: 10px; flex-wrap: wrap; }
      h1 { margin: 0; font-size: 18px; letter-spacing: 0.2px; }
      .pill { border: 1px solid var(--line); border-radius: 999px; padding: 6px 10px; color: var(--muted); font-size: 12px; }
      .grid { display: grid; grid-template-columns: 1fr; gap: 12px; margin-top: 12px; }
      @media (min-width: 900px) { .grid { grid-template-columns: 1.1fr 0.9fr; } }
      @media (min-width: 900px) { .full { grid-column: 1 / -1; } }
      @media (max-width: 899px) { .layout { flex-direction: column; } .sidebar { width: 100%; position: static; } }
      .sidelinks { display: flex; gap: 8px; flex-wrap: wrap; }
      .card { background: color-mix(in srgb, var(--card) 96%, black); border: 1px solid var(--line); border-radius: 14px; padding: 14px; }
      .card h2 { margin: 0 0 10px 0; font-size: 14px; color: #d9e2ff; }
      label { display: block; font-size: 12px; color: var(--muted); margin: 10px 0 6px; }
      input, select, textarea { width: 100%; box-sizing: border-box; border-radius: 10px; border: 1px solid var(--line); background: rgba(0,0,0,0.18); color: var(--text); padding: 10px 10px; font-size: 13px; outline: none; }
      textarea { min-height: 120px; font-family: var(--sans); resize: vertical; }
      .row { display: grid; grid-template-columns: 1fr; gap: 10px; }
      @media (min-width: 520px) { .row { grid-template-columns: 1fr 1fr; } }
      .btnrow { display: flex; gap: 10px; flex-wrap: wrap; margin-top: 12px; }
      button { border: 1px solid var(--line); background: rgba(255,255,255,0.06); color: var(--text); padding: 10px 12px; border-radius: 10px; font-size: 13px; cursor: pointer; }
      button.primary { background: rgba(110,168,254,0.22); border-color: rgba(110,168,254,0.45); }
      button:disabled { opacity: 0.5; cursor: not-allowed; }
      .small { font-size: 12px; color: var(--muted); }
      .links { display: flex; gap: 8px; flex-wrap: wrap; margin-top: 10px; }
      a { color: var(--accent); text-decoration: none; border: 1px solid var(--line); border-radius: 999px; padding: 6px 10px; font-size: 12px; background: rgba(255,255,255,0.04); }
      a:hover { background: rgba(255,255,255,0.08); }
      pre { background: rgba(0,0,0,0.22); border: 1px solid var(--line); border-radius: 12px; padding: 10px; overflow: auto; font-family: var(--mono); font-size: 12px; line-height: 1.35; }
      .status { display: flex; gap: 10px; align-items: center; flex-wrap: wrap; }
      .dot { width: 8px; height: 8px; border-radius: 50%; background: var(--muted); }
      .dot.ok { background: var(--ok); }
      .dot.bad { background: var(--danger); }
      .kbd { font-family: var(--mono); font-size: 12px; background: rgba(255,255,255,0.06); border: 1px solid var(--line); border-radius: 8px; padding: 2px 6px; }
    </style>
  </head>
  <body>
    <div class="wrap">
      <div class="layout">
        <div class="sidebar">
          <div class="card">
            <h2>导航</h2>
            <div class="sidelinks">
              <a href="#run">执行</a>
              <a href="#browser">浏览器</a>
              <a href="#outCard">输出</a>
            </div>
            <div class="small" style="margin-top:10px">
              内置浏览器用于登录 ChatGPT，并从 DOM 抓取 <span class="kbd">SCC_*_JSON:</span>，转发到 <span class="kbd">/intake/directive</span>。
            </div>
          </div>
        </div>

        <div class="content">
          <div class="title">
            <h1>SCC 控制台（单域名 / 单入口）</h1>
            <div class="pill">建议：用 <span class="kbd">UNIFIED_SERVER_ADMIN_TOKEN</span> 保护</div>
          </div>

          <div class="grid">
        <div class="card" id="run">
          <h2>执行指令</h2>
          <div class="row">
            <div>
              <label>统一服务器 Base URL</label>
              <input id="baseUrl" placeholder="https://your-domain" />
              <div class="small">默认使用当前域名；本地可填 <span class="kbd">http://127.0.0.1:18788</span></div>
            </div>
            <div>
              <label>Admin Token（可空）</label>
              <input id="token" placeholder="X-Admin-Token / ?token= / Cookie" />
              <div class="small">会保存在本机浏览器 localStorage</div>
            </div>
          </div>

          <div class="row">
            <div>
              <label>执行器</label>
              <select id="executor">
                <option value="codex">codex</option>
              </select>
            </div>
            <div>
              <label>codex 模型（仅 codex）</label>
              <input id="codexModel" placeholder="gpt-5.2-codex" />
            </div>
          </div>

          <label>Prompt</label>
          <textarea id="prompt" placeholder="输入要执行的指令（手机端也可）"></textarea>

          <div class="btnrow">
            <button class="primary" id="runBtn">运行</button>
            <button id="healthBtn">检查健康</button>
            <button id="saveBtn">保存配置</button>
          </div>

          <div style="margin-top:12px" class="status">
            <span class="dot" id="healthDot"></span>
             <span class="small" id="healthText">未检查</span>
          </div>
        </div>

        <div class="card" id="outCard">
          <h2>结果输出</h2>
          <pre id="out">(empty)</pre>
          <div class="links">
              <a href="/scc/executor/waterfall" rel="noreferrer">执行器瀑布流</a>
              <a href="/scc/automation/waterfall" rel="noreferrer">自动化瀑布流</a>
              <a href="/cp/files/list?prefix=artifacts/scc_state/top_validator&recursive=true" rel="noreferrer">top_validator 报告</a>
              <a href="/health/ready" rel="noreferrer">/health/ready</a>
              <a href="/health" rel="noreferrer">/health</a>
              <a href="/mcp" rel="noreferrer">/mcp</a>
              <a href="/dashboard" rel="noreferrer">/dashboard</a>
            </div>
            <div class="small" style="margin-top:10px">
              提示：如果开启了 Admin Token，可用 <span class="kbd">?token=...</span> 在手机端打开本页快速授权。
            </div>
        </div>

        <div class="card full" id="browser">
          <h2>内置浏览器（ChatGPT）</h2>
          <div class="row">
            <div>
              <label>启动 URL</label>
              <input id="browserUrl" placeholder="https://chatgpt.com/" />
              <div class="small">首次启动后请在窗口内手动登录（验证码/2FA 需要人工完成）。</div>
            </div>
            <div>
              <label>Autosend</label>
              <select id="browserAutosend">
                <option value="false">false</option>
                <option value="true">true</option>
              </select>
              <div class="small">当新 assistant 消息出现且检测到指令时自动投递（失败最多重试 2 次）。</div>
            </div>
          </div>
          <div class="row">
            <div>
              <label>投递 Endpoint（可选覆盖）</label>
              <input id="browserEndpoint" placeholder="(default) /intake/directive" />
              <div class="small">留空则使用当前 Unified Server：<span class="kbd">/intake/directive</span></div>
            </div>
            <div>
              <label>状态</label>
              <div class="status">
                <span class="dot" id="browserDot"></span>
                <span class="small" id="browserText">未启动</span>
              </div>
            </div>
          </div>
          <div class="btnrow">
            <button class="primary" id="browserStartBtn">启动</button>
            <button id="browserStopBtn">停止</button>
            <button id="browserRefreshBtn">刷新状态</button>
          </div>
          <div class="small" style="margin-top:10px">
            若返回 <span class="kbd">node_modules_missing</span>，请先在
            <span class="kbd">tools/scc/apps/browser/scc-chatgpt-browser</span> 执行 <span class="kbd">npm install</span>。
          </div>
        </div>
      </div>
        </div>
      </div>
    </div>

    <script>
      const $ = (id) => document.getElementById(id);
      const storeKey = "scc_console_v1";

      function load() {
        const saved = JSON.parse(localStorage.getItem(storeKey) || "{}");
        const defaultBase = location.origin;
        $("baseUrl").value = saved.baseUrl || defaultBase;
        $("token").value = saved.token || (new URLSearchParams(location.search).get("token") || "");
        $("executor").value = saved.executor || "codex";
        $("codexModel").value = saved.codexModel || "";
        $("prompt").value = saved.prompt || "";
        $("browserUrl").value = saved.browserUrl || "https://chatgpt.com/";
        $("browserAutosend").value = String(saved.browserAutosend ?? "false");
        $("browserEndpoint").value = saved.browserEndpoint || "";
      }

      function save() {
        const data = {
          baseUrl: $("baseUrl").value.trim(),
          token: $("token").value.trim(),
          executor: $("executor").value,
          codexModel: $("codexModel").value.trim(),
          prompt: $("prompt").value,
          browserUrl: $("browserUrl").value.trim(),
          browserAutosend: $("browserAutosend").value === "true",
          browserEndpoint: $("browserEndpoint").value.trim(),
        };
        localStorage.setItem(storeKey, JSON.stringify(data));
        return data;
      }

      function setBrowserStatus(ok, text) {
        $("browserText").textContent = text || "";
        $("browserDot").className = "dot " + (ok === true ? "ok" : ok === false ? "bad" : "");
      }

      async function apiFetch(path, opts) {
        const cfg = save();
        const base = cfg.baseUrl.replace(/\\/+$/, "");
        const headers = Object.assign({}, (opts && opts.headers) ? opts.headers : {});
        if (cfg.token) headers["X-Admin-Token"] = cfg.token;
        const url = base + path;
        return await fetch(url, Object.assign({}, opts || {}, { headers }));
      }

      async function browserStatus() {
        setBrowserStatus(null, "检查中...");
        try {
          const res = await apiFetch("/scc/browser/status", { method: "GET", cache: "no-store" });
          const j = await res.json().catch(() => ({}));
          if (!res.ok) {
            setBrowserStatus(false, "HTTP " + res.status);
            return;
          }
          if (j.running) setBrowserStatus(true, "running (pid=" + j.pid + ")");
          else setBrowserStatus(null, "stopped");
        } catch (e) {
          setBrowserStatus(false, "澶辫触锛? + (e && e.message ? e.message : String(e)) + ")");
        }
      }

      async function browserStart() {
        const cfg = save();
        setBrowserStatus(null, "启动中...");
        $("browserStartBtn").disabled = true;
        try {
          const body = { url: cfg.browserUrl || "https://chatgpt.com/", autosend: !!cfg.browserAutosend };
          if (cfg.browserEndpoint) body.endpoint = cfg.browserEndpoint;
          const res = await apiFetch("/scc/browser/start", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(body),
          });
          const text = await res.text();
          $("out").textContent = text;
          await browserStatus();
        } catch (e) {
          setBrowserStatus(false, "启动失败: " + (e && e.message ? e.message : String(e)));
        } finally {
          $("browserStartBtn").disabled = false;
        }
      }

      async function browserStop() {
        setBrowserStatus(null, "停止中...");
        $("browserStopBtn").disabled = true;
        try {
          const res = await apiFetch("/scc/browser/stop", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ timeout_s: 5.0 }),
          });
          const text = await res.text();
          $("out").textContent = text;
          await browserStatus();
        } catch (e) {
          setBrowserStatus(false, "停止失败: " + (e && e.message ? e.message : String(e)));
        } finally {
          $("browserStopBtn").disabled = false;
        }
      }

      async function checkHealth() {
        const cfg = save();
        const url = cfg.baseUrl.replace(/\\/+$/, "") + "/health/ready";
        $("healthText").textContent = "检查中...";
        $("healthDot").className = "dot";
        try {
          const headers = {};
          if (cfg.token) headers["X-Admin-Token"] = cfg.token;
          const res = await fetch(url, { method: "GET", headers, cache: "no-store" });
          $("healthText").textContent = res.ok ? "鍋ュ悍锛歄K" : ("鍋ュ悍锛欻TTP " + res.status);
          $("healthDot").className = "dot " + (res.ok ? "ok" : "bad");
        } catch (e) {
          $("healthText").textContent = "鍋ュ悍锛氬け璐ワ紙" + (e && e.message ? e.message : String(e)) + ")";
          $("healthDot").className = "dot bad";
        }
      }

      async function run() {
        const cfg = save();
        const base = cfg.baseUrl.replace(/\\/+$/, "");
        const ex = cfg.executor;
        const prompt = (cfg.prompt || "").trim();
        if (!prompt) {
          $("out").textContent = "prompt 涓嶈兘涓虹┖";
          return;
        }

        $("runBtn").disabled = true;
        $("out").textContent = "running鈥?;

        try {
          const headers = { "Content-Type": "application/json" };
          if (cfg.token) headers["X-Admin-Token"] = cfg.token;

          let url = base + "/executor/" + ex;
          let body = null;

          body = JSON.stringify({ prompt, model: cfg.codexModel || "" });

          const res = await fetch(url, { method: "POST", headers, body });
          const text = await res.text();
          $("out").textContent = text;
        } catch (e) {
          $("out").textContent = "error: " + (e && e.message ? e.message : String(e));
        } finally {
          $("runBtn").disabled = false;
        }
      }

      $("saveBtn").addEventListener("click", () => { save(); $("out").textContent = "saved"; });
      $("healthBtn").addEventListener("click", checkHealth);
      $("runBtn").addEventListener("click", run);
      $("browserStartBtn").addEventListener("click", browserStart);
      $("browserStopBtn").addEventListener("click", browserStop);
      $("browserRefreshBtn").addEventListener("click", browserStatus);
      load();
      browserStatus();
    </script>
  </body>
</html>
        """.strip()

    # --- Delegation waterfall (Executor/Codex batches) ---
    def _read_json_best_effort(path: Path) -> dict:
        try:
            return json.loads(path.read_text(encoding="utf-8", errors="replace") or "{}")
        except Exception:
            return {}

    def _iso_now() -> str:
        return datetime.now(timezone.utc).isoformat()

    def _safe_repo_rel(p: Path) -> str:
        try:
            return str(p.relative_to(repo_root)).replace("\\", "/")
        except Exception:
            return str(p).replace("\\", "/")

    def _safe_artifacts_rel(abs_path: str) -> str | None:
        try:
            ap = Path(str(abs_path or "")).resolve()
            ar = (repo_root / "artifacts").resolve()
            if str(ap).startswith(str(ar)):
                return str(ap.relative_to(ar)).replace("\\", "/")
        except Exception:
            pass
        return None

    def _summarize_executor_manifest(manifest: dict) -> dict:
        out = {
            "run_id": str(manifest.get("run_id") or ""),
            "start": manifest.get("start"),
            "end": manifest.get("end"),
            "model": manifest.get("model"),
            "timeout_s": manifest.get("timeout_s"),
            "max_outstanding": manifest.get("max_outstanding"),
            "dangerously_bypass": manifest.get("dangerously_bypass"),
            "parents": [],
        }
        parents = manifest.get("parents") if isinstance(manifest.get("parents"), list) else []
        now = datetime.now(timezone.utc)
        for p in parents:
            if not isinstance(p, dict):
                continue
            start_s = str(p.get("start") or "")
            end_s = str(p.get("end") or "")
            dur = None
            try:
                if start_s:
                    st = datetime.fromisoformat(start_s).astimezone(timezone.utc)
                    et = datetime.fromisoformat(end_s).astimezone(timezone.utc) if end_s else now
                    dur = max(0.0, (et - st).total_seconds())
            except Exception:
                dur = None
            ad = str(p.get("artifacts_dir") or "")
            out["parents"].append(
                {
                    "id": str(p.get("id") or ""),
                    "start": start_s or None,
                    "end": end_s or None,
                    "exit_code": p.get("exit_code", None),
                    "duration_s": dur,
                    "artifacts_dir": ad,
                    "artifacts_prefix": _safe_artifacts_rel(ad),
                }
            )
        return out

    def _read_parent_status(step_dir: Path) -> dict:
        try:
            p = (step_dir / "status.json").resolve()
            if not p.exists():
                return {}
            st = _read_json_best_effort(p)
            return st if isinstance(st, dict) else {}
        except Exception:
            return {}

    def _read_parent_usage(step_dir: Path) -> dict:
        try:
            p = (step_dir / "usage.json").resolve()
            if not p.exists():
                return {}
            u = _read_json_best_effort(p)
            return u if isinstance(u, dict) else {}
        except Exception:
            return {}

    def _read_parent_context_selection(step_dir: Path) -> dict:
        try:
            p = (step_dir / "context_selection.json").resolve()
            if not p.exists():
                return {}
            j = _read_json_best_effort(p)
            return j if isinstance(j, dict) else {}
        except Exception:
            return {}

    def _tail_text_file(path: Path, *, max_lines: int = 12, max_chars: int = 4000) -> str:
        try:
            if not path.exists() or not path.is_file():
                return ""
            txt = path.read_text(encoding="utf-8", errors="replace")
            lines = txt.splitlines()
            tail = "\n".join(lines[-max_lines:])
            if len(tail) > max_chars:
                tail = tail[-max_chars:]
            return tail
        except Exception:
            return ""

    @app.get("/scc/executor/active_runs")
    async def scc_executor_active_runs():
        state_file = (repo_root / "artifacts" / "codexcli_remote_runs" / "_state" / "active_runs.json").resolve()
        state = _read_json_best_effort(state_file)
        runs = state.get("runs") if isinstance(state.get("runs"), dict) else {}
        out_runs: list[dict] = []
        now = datetime.now(timezone.utc)
        for rid, entry in runs.items():
            if not isinstance(entry, dict):
                continue
            mp = Path(str(entry.get("manifest_file") or "")).resolve()
            manifest = _read_json_best_effort(mp) if mp.exists() else {}
            summary = _summarize_executor_manifest(manifest)
            updated_utc = entry.get("updated_utc")
            age_s = None
            try:
                if updated_utc:
                    udt = datetime.fromisoformat(str(updated_utc)).astimezone(timezone.utc)
                    age_s = max(0.0, (now - udt).total_seconds())
            except Exception:
                age_s = None
            # Attach small "live state" from parent artifacts: phase + log tail.
            try:
                if isinstance(summary, dict) and isinstance(summary.get("parents"), list):
                    for p in summary["parents"]:
                        if not isinstance(p, dict):
                            continue
                        ad = str(p.get("artifacts_dir") or "")
                        if not ad:
                            continue
                        sd = Path(ad).resolve()
                        st = _read_parent_status(sd)
                        if st:
                            p["state"] = {
                                "ts_utc": st.get("ts_utc"),
                                "phase": st.get("phase"),
                                "message": st.get("message"),
                            }
                        usage = _read_parent_usage(sd)
                        if usage:
                            p["usage"] = {"tokens_used": usage.get("tokens_used")}
                        ctx_sel = _read_parent_context_selection(sd)
                        if ctx_sel:
                            sel = ctx_sel.get("selection") if isinstance(ctx_sel.get("selection"), dict) else {}
                            picked = sel.get("picked") if isinstance(sel.get("picked"), list) else []
                            p["context"] = {
                                "source": sel.get("source"),
                                "picked_count": len(picked),
                            }
                        p["log_tail"] = {
                            "stderr": _tail_text_file(sd / "stderr.log"),
                            "stdout": _tail_text_file(sd / "stdout.log"),
                        }
            except Exception:
                pass
            out_runs.append(
                {
                    "run_id": str(rid),
                    "updated_utc": updated_utc,
                    "age_s": age_s,
                    "stale_120s": bool(age_s is not None and age_s > 120.0),
                    "manifest_file": _safe_repo_rel(mp),
                    "summary": summary,
                }
            )
        out_runs.sort(key=lambda x: x.get("run_id") or "", reverse=True)
        return {"ok": True, "ts_utc": _iso_now(), "active_runs_file": _safe_repo_rel(state_file), "runs": out_runs}

    @app.post("/scc/executor/prune_stale")
    async def scc_executor_prune_stale(payload: dict):
        """
        Remove stale entries from artifacts/codexcli_remote_runs/_state/active_runs.json.
        This only affects the UI/registry; it does not kill processes.
        """
        state_file = (repo_root / "artifacts" / "codexcli_remote_runs" / "_state" / "active_runs.json").resolve()
        cutoff_s = 600.0
        try:
            cutoff_s = float((payload or {}).get("cutoff_s") or 600.0)
        except Exception:
            cutoff_s = 600.0
        cutoff_s = max(30.0, min(86400.0, cutoff_s))
        state = _read_json_best_effort(state_file)
        runs = state.get("runs") if isinstance(state.get("runs"), dict) else {}
        now = datetime.now(timezone.utc)
        removed: list[str] = []
        kept: dict = {}
        for rid, entry in runs.items():
            if not isinstance(entry, dict):
                removed.append(str(rid))
                continue
            updated_utc = entry.get("updated_utc")
            age_s = None
            try:
                if updated_utc:
                    udt = datetime.fromisoformat(str(updated_utc)).astimezone(timezone.utc)
                    age_s = max(0.0, (now - udt).total_seconds())
            except Exception:
                age_s = None
            if age_s is not None and age_s > cutoff_s:
                removed.append(str(rid))
                continue
            kept[str(rid)] = entry
        try:
            state_file.parent.mkdir(parents=True, exist_ok=True)
            tmp = state_file.with_suffix(".json.tmp")
            tmp.write_text(json.dumps({"runs": kept}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", errors="replace")
            os.replace(tmp, state_file)
        except Exception:
            pass
        return {"ok": True, "ts_utc": _iso_now(), "cutoff_s": cutoff_s, "removed": removed, "kept": sorted(list(kept.keys()))}

    @app.get("/scc/executor/waterfall", response_class=HTMLResponse)
    async def scc_executor_waterfall():
        return """
<!doctype html>
<html lang="zh-CN">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>SCC 瀑布流 - 执行器</title>
    <style>
      :root { --bg:#ffffff; --card:#ffffff; --text:#111827; --muted:#6b7280; --line: rgba(17,24,39,0.14); --ok:#16a34a; --bad:#dc2626; --warn:#d97706; --mono: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace; --sans: system-ui, -apple-system, Segoe UI, Roboto, sans-serif; }
      body { margin:0; font-family: var(--sans); background: var(--bg); color: var(--text); }
      .wrap { max-width: 1180px; margin: 0 auto; padding: 16px 12px 30px; }
      h1 { margin: 0 0 10px 0; font-size: 16px; }
      .row { display:flex; gap:10px; flex-wrap:wrap; align-items:center; }
      .pill { border:1px solid var(--line); border-radius: 999px; padding:6px 10px; color: var(--muted); font-size:12px; background: rgba(17,24,39,0.02); }
      button { border:1px solid var(--line); background: rgba(17,24,39,0.03); color: var(--text); padding: 8px 10px; border-radius: 10px; font-size: 12px; cursor:pointer; }
      button.primary { background: rgba(37,99,235,0.10); border-color: rgba(37,99,235,0.28); }
      button.danger { background: rgba(220,38,38,0.10); border-color: rgba(220,38,38,0.22); }
      .card { background: var(--card); border: 1px solid var(--line); border-radius: 14px; padding: 12px; margin-top: 12px; }
      .mono { font-family: var(--mono); font-size: 12px; }
      .table { width:100%; border-collapse: collapse; }
      .table th, .table td { border-bottom: 1px solid rgba(17,24,39,0.08); padding: 8px 6px; vertical-align: top; }
      .badge { display:inline-block; padding: 2px 8px; border-radius: 999px; border:1px solid var(--line); font-size: 11px; color: var(--muted); }
       .badge.ok { color: var(--ok); border-color: rgba(22,163,74,0.35); }
       .badge.bad { color: var(--bad); border-color: rgba(220,38,38,0.35); }
       .badge.warn { color: var(--warn); border-color: rgba(217,119,6,0.35); }
       .dots::after { content: '...'; display:inline-block; width: 16px; overflow:hidden; vertical-align: bottom; animation: dots 1.2s steps(4,end) infinite; }
       @keyframes dots { 0%{width:0px} 100%{width:16px} }
       .small { color: var(--muted); font-size: 12px; }
       a { color: #2563eb; text-decoration: none; }
       a:hover { text-decoration: underline; }

       .overlay { position: fixed; inset: 0; z-index: 50; background: rgba(0,0,0,0.20); display: none; grid-template-rows: 44px 1fr; }
       .ov_top { display:flex; align-items:center; justify-content:space-between; gap:10px; padding: 0 10px; background: #ffffff; border-bottom: 1px solid rgba(17,24,39,0.14); }
       .ov_title { font-size: 12px; color: rgba(17,24,39,0.72); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
       .ov_frame { width: 100%; height: 100%; border: 0; background: #ffffff; }
     </style>
  </head>
  <body>
    <div class="wrap">
       <div class="row">
         <h1 style="flex:1">瀑布流（执行器 / Codex 运行）</h1>
          <span class="pill">自动刷新：2s</span>
          <button class="danger" onclick="pruneStale()">清理陈旧（&gt;10分钟）</button>
          <button class="primary" onclick="openOverlay('/scc', 'SCC 控制台')">打开 SCC 控制台</button>
        </div>
        <div class="small">说明：每 2 秒刷新一次；必要时可取消 Run/Parent 终止卡住的任务。</div>
        <div id="root" class="card mono">loading...</div>
    </div>
    <div id="overlay" class="overlay" role="dialog" aria-label="内置查看器">
      <div class="ov_top">
        <div class="ov_title" id="ov_title">查看</div>
        <button onclick="closeOverlay()">关闭</button>
      </div>
      <iframe id="ov_iframe" class="ov_frame" title="viewer"></iframe>
    </div>
    <script>
       function openOverlay(url, title){
         try{
           const ov = document.getElementById('overlay');
           const fr = document.getElementById('ov_iframe');
           const tt = document.getElementById('ov_title');
           if (tt) tt.textContent = String(title||url||'查看');
           if (fr) fr.src = String(url||'');
           if (ov) ov.style.display = 'grid';
         }catch(e){}
       }
       function closeOverlay(){
         try{
           const ov = document.getElementById('overlay');
           const fr = document.getElementById('ov_iframe');
           if (fr) fr.src = 'about:blank';
           if (ov) ov.style.display = 'none';
         }catch(e){}
       }
       async function jget(path){
         const r = await fetch(path, {headers: {'Content-Type':'application/json'}});
         const t = await r.text();
         try { return JSON.parse(t); } catch(e) { return {ok:false, error:'json_parse', raw:t}; }
       }
      async function jpost(path, payload){
        const r = await fetch(path, {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(payload)});
        const t = await r.text();
        try { return JSON.parse(t); } catch(e) { return {ok:false, error:'json_parse', raw:t}; }
      }
       function badgeFor(p){
         if (p.end && p.exit_code === 0) return '<span class="badge ok">done:0</span>';
         if (p.end && p.exit_code !== 0) return '<span class="badge bad">done:fail</span>';
         if (!p.end && p.start) return '<span class="badge warn">running<span class="dots"></span></span>';
         return '<span class="badge">pending</span>';
       }
       function phaseLine(p){
         const st = p.state || {};
         const ph = st.phase || '';
         const msg = st.message || '';
         const u = p.usage || {};
         const tok = u.tokens_used;
         const c = p.context || {};
         const ctxSrc = c.source;
         const ctxN = c.picked_count;
         if (!ph && !msg && (tok==null) && (ctxSrc==null) && (ctxN==null)) return '';
         const tokLine = (tok==null) ? '' : (' tok=' + esc(tok));
         const ctxLine = (ctxSrc==null && ctxN==null) ? '' : (' ctx=' + esc(ctxSrc||'') + ':' + esc(ctxN||0));
         return '<div class="small">phase=' + esc(ph) + (msg ? (' msg=' + esc(msg)) : '') + tokLine + ctxLine + '</div>';
       }
       function esc(s){
         return String(s||'').replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;');
       }
       function fmtS(n){
         if (n == null) return '-';
         const s = Math.round(n);
         if (s < 60) return s+'s';
        const m = Math.floor(s/60);
        const r = s%60;
        return m+'m'+r+'s';
      }
        async function render(){
          const root = document.getElementById('root');
          const data = await jget('/scc/executor/active_runs');
           if (!data || data.ok !== true){
             root.textContent = '失败: ' + JSON.stringify(data);
             return;
           }
           let html = '<div class="small">ts_utc: '+(data.ts_utc||'-')+'</div>';
           const runs = (data.runs||[]);
          if (!runs.length){
            html += '<div style="margin-top:8px">暂无运行。</div>';
            root.innerHTML = html;
            return;
          }
          for (const r of runs){
           const s = (r.summary||{});
           html += '<div class="card" style="margin-top:12px">';
           const stale = r.stale_120s ? '<span class="badge warn">stale&gt;120s</span>' : '';
           const age = (r.age_s==null?'-':fmtS(r.age_s));
           html += '<div class="row"><div class="mono" style="flex:1"><b>run_id</b>: '+(r.run_id||'-')+' '+stale+'</div>';
           html += '<button class="danger" onclick="cancelRun(\\''+(r.run_id||'')+'\\')">取消 Run</button></div>';
            html += '<div class="small">model='+(s.model||'-')+' max_outstanding='+(s.max_outstanding??'-')+' timeout_s='+(s.timeout_s??'-')+' updated='+(r.updated_utc||'-')+' age='+age+'</div>';
            html += '<table class="table mono" style="margin-top:8px"><thead><tr><th>父任务</th><th>状态</th><th>耗时</th><th>产物</th><th>操作</th></tr></thead><tbody>';
            for (const p of (s.parents||[])){
              const pref = p.artifacts_prefix || '';
              html += '<tr>';
              html += '<td>'+ (p.id||'') +'</td>';
              html += '<td>'+ badgeFor(p) +' exit='+(p.exit_code==null?'-':p.exit_code) + phaseLine(p) +'</td>';
              html += '<td>'+ fmtS(p.duration_s) +'</td>';
              html += '<td>'+(pref?('<button class=\"primary\" onclick=\"openOverlay(\\'/cp/files/list?prefix='+encodeURIComponent(pref)+'&recursive=true\\',\\'产物：'+esc(pref)+'\\')\">查看</button>'):'-')+'</td>';
              const tail = p.log_tail || {};
              const stderr = (tail.stderr||'').trim();
              const stdout = (tail.stdout||'').trim();
              html += '<td><button class="danger" onclick="cancelParent(\\''+(r.run_id||'')+'\\',\\''+(p.id||'')+'\\')">取消 Parent</button>';
              if (stderr || stdout){
                html += '<details style="margin-top:6px"><summary class="small" style="cursor:pointer">日志</summary>';
                if (stderr) html += '<div class="small">stderr tail</div><pre class="mono" style="white-space:pre-wrap; margin:6px 0; border:1px solid rgba(255,255,255,0.10); padding:8px; border-radius:10px;">'+esc(stderr)+'</pre>';
                if (stdout) html += '<div class="small">stdout tail</div><pre class="mono" style="white-space:pre-wrap; margin:6px 0; border:1px solid rgba(255,255,255,0.10); padding:8px; border-radius:10px;">'+esc(stdout)+'</pre>';
                html += '</details>';
              }
              html += '</td>';
              html += '</tr>';
            }
          html += '</tbody></table>';
          html += '</div>';
        }
        root.innerHTML = html;
      }
      async function cancelRun(runId){
        if (!runId) return;
        await jpost('/executor/codex/cancel', {run_id: runId, reason:'ui_cancel_run'});
        await render();
      }
       async function cancelParent(runId, parentId){
         if (!runId || !parentId) return;
         await jpost('/executor/codex/cancel', {run_id: runId, parent_id: parentId, reason:'ui_cancel_parent'});
         await render();
       }
       async function pruneStale(){
         await jpost('/scc/executor/prune_stale', {cutoff_s: 600});
         await render();
       }
       render();
       setInterval(render, 2000);
     </script>
  </body>
</html>
        """.strip()

    # --- Delegation waterfall (Automation runs) ---
    @app.get("/scc/automation/active_runs")
    async def scc_automation_active_runs():
        base = (repo_root / "artifacts" / "scc_state" / "automation_runs").resolve()
        runs: list[dict] = []
        if base.exists():
            dirs = [p for p in base.iterdir() if p.is_dir()]
            dirs = sorted(dirs, key=lambda p: p.name, reverse=True)[:30]
            for d in dirs:
                mf = (d / "automation_manifest.json").resolve()
                runs.append({"run_id": d.name, "manifest_file": _safe_repo_rel(mf), "manifest": _read_json_best_effort(mf) if mf.exists() else {}})
        return {"ok": True, "ts_utc": _iso_now(), "runs": runs}

    @app.get("/scc/automation/waterfall", response_class=HTMLResponse)
    async def scc_automation_waterfall():
        return """
<!doctype html>
<html lang="zh-CN">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>SCC 瀑布流 - 自动化</title>
    <style>
      :root { --bg:#ffffff; --card:#ffffff; --text:#111827; --muted:#6b7280; --line: rgba(17,24,39,0.14); --ok:#16a34a; --bad:#dc2626; --warn:#d97706; --mono: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace; --sans: system-ui, -apple-system, Segoe UI, Roboto, sans-serif; }
      body { margin:0; font-family: var(--sans); background: var(--bg); color: var(--text); }
      .wrap { max-width: 1180px; margin: 0 auto; padding: 16px 12px 30px; }
      h1 { margin: 0 0 10px 0; font-size: 16px; }
      .row { display:flex; gap:10px; flex-wrap:wrap; align-items:center; }
      .pill { border:1px solid var(--line); border-radius: 999px; padding:6px 10px; color: var(--muted); font-size:12px; background: rgba(17,24,39,0.02); }
      button { border:1px solid var(--line); background: rgba(17,24,39,0.03); color: var(--text); padding: 8px 10px; border-radius: 10px; font-size: 12px; cursor:pointer; }
      button.primary { background: rgba(37,99,235,0.10); border-color: rgba(37,99,235,0.28); }
      .card { background: var(--card); border: 1px solid var(--line); border-radius: 14px; padding: 12px; margin-top: 12px; }
      .mono { font-family: var(--mono); font-size: 12px; }
      .table { width:100%; border-collapse: collapse; }
      .table th, .table td { border-bottom: 1px solid rgba(17,24,39,0.08); padding: 8px 6px; vertical-align: top; }
      .badge { display:inline-block; padding: 2px 8px; border-radius: 999px; border:1px solid var(--line); font-size: 11px; color: var(--muted); }
      .badge.ok { color: var(--ok); border-color: rgba(22,163,74,0.35); }
      .badge.bad { color: var(--bad); border-color: rgba(220,38,38,0.35); }
      .badge.warn { color: var(--warn); border-color: rgba(217,119,6,0.35); }
      .small { color: var(--muted); font-size: 12px; }
      a { color: #2563eb; text-decoration: none; }
      a:hover { text-decoration: underline; }

      .overlay { position: fixed; inset: 0; z-index: 50; background: rgba(0,0,0,0.20); display: none; grid-template-rows: 44px 1fr; }
      .ov_top { display:flex; align-items:center; justify-content:space-between; gap:10px; padding: 0 10px; background: #ffffff; border-bottom: 1px solid rgba(17,24,39,0.14); }
      .ov_title { font-size: 12px; color: rgba(17,24,39,0.72); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
      .ov_frame { width: 100%; height: 100%; border: 0; background: #ffffff; }
    </style>
  </head>
  <body>
    <div class="wrap">
      <div class="row">
        <h1 style="flex:1">瀑布流（自动化运行）</h1>
        <span class="pill">自动刷新：2s</span>
        <button class="primary" onclick="openOverlay('/scc', 'SCC 控制台')">打开 SCC 控制台</button>
      </div>
      <div id="root" class="card mono">loading...</div>
    </div>
    <div id="overlay" class="overlay" role="dialog" aria-label="内置查看器">
      <div class="ov_top">
        <div class="ov_title" id="ov_title">查看</div>
        <button onclick="closeOverlay()">关闭</button>
      </div>
      <iframe id="ov_iframe" class="ov_frame" title="viewer"></iframe>
    </div>
    <script>
      function openOverlay(url, title){
        try{
          const ov = document.getElementById('overlay');
          const fr = document.getElementById('ov_iframe');
          const tt = document.getElementById('ov_title');
          if (tt) tt.textContent = String(title||url||'查看');
          if (fr) fr.src = String(url||'');
          if (ov) ov.style.display = 'grid';
        }catch(e){}
      }
      function closeOverlay(){
        try{
          const ov = document.getElementById('overlay');
          const fr = document.getElementById('ov_iframe');
          if (fr) fr.src = 'about:blank';
          if (ov) ov.style.display = 'none';
        }catch(e){}
      }
      async function jget(path){
        const r = await fetch(path, {headers: {'Content-Type':'application/json'}});
        const t = await r.text();
        try { return JSON.parse(t); } catch(e) { return {ok:false, error:'json_parse', raw:t}; }
      }
      function badge(ok, end){
        if (!end) return '<span class="badge warn">运行中</span>';
        return ok ? '<span class="badge ok">成功</span>' : '<span class="badge bad">失败</span>';
      }
      async function render(){
        const root = document.getElementById('root');
        const data = await jget('/scc/automation/active_runs');
        if (!data || data.ok !== true){
          root.textContent = '失败: ' + JSON.stringify(data);
          return;
        }
        let html = '<div class="small">ts_utc: '+(data.ts_utc||'-')+'</div>';
        const runs = (data.runs||[]);
        if (!runs.length){
          html += '<div style="margin-top:8px">暂无自动化运行。</div>';
          root.innerHTML = html;
          return;
        }
        html += '<table class="table mono" style="margin-top:8px"><thead><tr><th>run_id</th><th>状态</th><th>模型</th><th>区间</th><th>产物</th></tr></thead><tbody>';
        for (const r of runs){
          const m = r.manifest||{};
          const ok = !!m.ok;
          html += '<tr>';
          html += '<td>'+ (r.run_id||'-') +'</td>';
          html += '<td>'+ badge(ok, m.end_utc) +'</td>';
          html += '<td>'+ (m.model||'-') +'</td>';
          html += '<td>'+ (m.start_utc||'-') +' -> '+ (m.end_utc||'-') +'</td>';
          if (r.manifest_file){
            html += '<td><button class=\"primary\" onclick=\"openOverlay(\\'/cp/files/download?path='+encodeURIComponent(r.manifest_file)+'&inline=true\\',\\'清单：'+String(r.run_id||'')+'\\')\">清单</button></td>';
          } else {
            html += '<td>-</td>';
          }
          html += '</tr>';
        }
        html += '</tbody></table>';
        root.innerHTML = html;
      }
      render();
      setInterval(render, 3000);
    </script>
  </body>
</html>
        """.strip()

    @app.get("/scc/board", response_class=HTMLResponse)
    async def scc_board():
        """
        SCC Live Board: cursor-like scrolling + modular lists.
        Implemented with polling (no SSE) to keep the server minimal.
        """
        return """
<!doctype html>
<html lang="zh-CN">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>SCC Board</title>
    <style>
      :root{
        --bg:#0b1020; --card:#121a33; --muted:#9aa6c2; --text:#e8ecf8;
        --line:rgba(255,255,255,0.10); --accent:#6ea8fe; --danger:#ff6b6b; --ok:#2ecc71;
        --mono: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace;
        --sans: system-ui, -apple-system, Segoe UI, Roboto, sans-serif;
      }
      body{ margin:0; font-family:var(--sans); background: radial-gradient(1200px 800px at 10% 10%, #18224a, var(--bg)); color:var(--text); }
      .wrap{ max-width:1200px; margin:0 auto; padding:14px; }
      .top{ display:flex; gap:10px; align-items:center; justify-content:space-between; flex-wrap:wrap; }
      h1{ margin:0; font-size:16px; }
      .pill{ border:1px solid var(--line); border-radius:999px; padding:6px 10px; font-size:12px; color:var(--muted); background:rgba(255,255,255,0.04); }
      .row{ display:flex; gap:12px; margin-top:12px; align-items:stretch; }
      .col{ flex:1; min-width:0; }
      .left{ width:360px; flex:0 0 360px; }
      @media (max-width: 980px){ .row{ flex-direction:column; } .left{ width:auto; flex:1; } }
      .card{ background: color-mix(in srgb, var(--card) 96%, black); border:1px solid var(--line); border-radius:14px; padding:12px; }
      .card h2{ margin:0 0 10px; font-size:13px; color:#d9e2ff; }
      input,select{ width:100%; box-sizing:border-box; border-radius:10px; border:1px solid var(--line); background: rgba(0,0,0,0.18); color:var(--text); padding:9px; font-size:13px; outline:none; }
      .small{ font-size:12px; color:var(--muted); }
      .btnrow{ display:flex; gap:8px; flex-wrap:wrap; margin-top:10px; }
      button{ border:1px solid var(--line); background: rgba(255,255,255,0.06); color:var(--text); padding:9px 10px; border-radius:10px; font-size:12px; cursor:pointer; }
      button.primary{ background: rgba(110,168,254,0.22); border-color: rgba(110,168,254,0.45); }
      button.danger{ background: rgba(255,107,107,0.16); border-color: rgba(255,107,107,0.36); }
      button:disabled{ opacity:.5; cursor:not-allowed; }
      .split{ display:grid; grid-template-columns: 1fr; gap:12px; }
      @media (min-width: 980px){ .split{ grid-template-columns: 1fr 1fr; } }
      .list{ border:1px solid var(--line); border-radius:12px; overflow:hidden; }
      .item{ display:flex; gap:8px; align-items:center; padding:10px; border-top:1px solid var(--line); cursor:pointer; background: rgba(0,0,0,0.12); }
      .item:first-child{ border-top:none; }
      .item:hover{ background: rgba(255,255,255,0.06); }
      .item.active{ outline: 2px solid rgba(110,168,254,0.45); outline-offset:-2px; }
      .badge{ font-size:11px; padding:3px 8px; border-radius:999px; border:1px solid var(--line); color:var(--muted); }
      .badge.ok{ color: var(--ok); border-color: rgba(46,204,113,0.35); }
      .badge.bad{ color: var(--danger); border-color: rgba(255,107,107,0.35); }
      .mono{ font-family:var(--mono); }
      .log{ height: 560px; overflow:auto; border:1px solid var(--line); border-radius:12px; background: rgba(0,0,0,0.22); padding:10px; }
      .logline{ white-space: pre-wrap; word-break: break-word; font-family: var(--mono); font-size:12px; color:#dbe3ff; margin:0; }
      .kv{ display:grid; grid-template-columns: 140px 1fr; gap:6px 10px; font-size:12px; color:var(--muted); }
      .kv code{ color: var(--text); background: rgba(255,255,255,0.06); padding:2px 6px; border-radius:8px; }
      a{ color:var(--accent); text-decoration:none; }
      a:hover{ text-decoration:underline; }
      .tabs{ display:flex; gap:8px; flex-wrap:wrap; }
      .tab{ padding:6px 10px; border-radius:10px; border:1px solid var(--line); background: rgba(0,0,0,0.12); font-size:12px; cursor:pointer; }
      .tab.active{ background: rgba(110,168,254,0.18); border-color: rgba(110,168,254,0.45); }
    </style>
  </head>
  <body>
    <div class="wrap">
      <div class="top">
        <div style="display:flex; gap:10px; align-items:center; flex-wrap:wrap;">
          <h1>SCC Board</h1>
          <span class="pill mono" id="basePill"></span>
          <span class="pill" id="patchGatePill">patch_apply_enabled=?</span>
          <a class="pill" href="/scc" target="_blank" rel="noreferrer">SCC 鎺у埗鍙?/a>
        </div>
        <div class="tabs">
          <div class="tab active" id="tabStream">婊氬姩锛圕ursor 椋庢牸锛?/div>
          <div class="tab" id="tabModules">妯″潡鍖栧垪琛?/div>
          <div class="tab" id="tabChat">Chat</div>
        </div>
      </div>

      <div class="row">
        <div class="left col">
          <div class="card">
            <h2>浠诲姟鍒楄〃</h2>
            <label class="small">鍒锋柊闂撮殧锛堢锛?/label>
            <input id="pollSec" value="1.0" />
            <label class="small" style="margin-top:10px;">绛涢€夛紙task_id 鎴?goal 鍏抽敭瀛楋級</label>
            <input id="filter" placeholder="e.g. fullagent / CODEXDEMO / 2026..." />
            <div class="btnrow">
              <button id="refreshBtn" class="primary">绔嬪嵆鍒锋柊</button>
              <button id="togglePollBtn">鏆傚仠杞</button>
            </div>
            <div class="small" style="margin-top:10px;">鐐瑰嚮浠诲姟 鈫?鍙充晶鏄剧ず events / patches / subtasks</div>
            <div class="list" id="tasksList" style="margin-top:10px; max-height:520px; overflow:auto;"></div>
          </div>
        </div>

        <div class="col">
          <div id="viewStream" class="card">
            <h2>婊氬姩杈撳嚭锛坋vents.jsonl tail锛?/h2>
            <div class="kv" style="margin-bottom:10px;">
              <div>selected</div><div><code id="selTask">(none)</code></div>
              <div>run_id</div><div><code id="selRunId">(none)</code></div>
              <div>events API</div><div class="mono"><a id="eventsLink" href="#" target="_blank" rel="noreferrer">(none)</a></div>
              <div>follow</div><div><code id="followState">on</code>锛堢敤鎴锋粴鍔ㄧ搴曢儴浼氳嚜鍔ㄥ叧闂級</div>
              <div>cursor</div><div><code id="selCursor">(none)</code></div>
            </div>
            <div class="btnrow">
              <button id="followBtn">Follow: ON</button>
              <button id="clearLogBtn">娓呯┖</button>
              <button id="openContinuationBtn">鎵撳紑 continuation</button>
              <button id="openPatchesBtn">鎵撳紑 patches</button>
              <button id="exportSubmitBtn">Export SUBMIT</button>
            </div>
            <div class="btnrow" style="margin-top:8px;">
              <input id="replayRunId" placeholder="replay run_id" style="flex:1; width:auto;" />
              <input id="replayCursor" placeholder="cursor (byte offset)" style="width:220px;" />
              <button id="replayBtn">Replay</button>
              <button id="copyReplayBtn">Copy Pointer</button>
            </div>
            <div class="log" id="logBox"></div>
          </div>

          <div id="viewModules" class="card" style="display:none;">
            <h2>妯″潡鍖栵紙Task / Patches / Subtasks锛?/h2>
            <div class="split">
              <div>
                <div class="kv">
                  <div>task</div><div><code id="modTask">(none)</code></div>
                  <div>status</div><div><code id="modStatus">-</code></div>
                  <div>goal</div><div><code id="modGoal">-</code></div>
                </div>
                <div class="btnrow">
                  <button id="modRefreshBtn" class="primary">鍒锋柊妯″潡</button>
                  <button id="modOpenReportBtn">鎵撳紑 report</button>
                </div>
              </div>
              <div>
                <div class="kv">
                  <div>patches</div><div><code id="modPatchesCount">0</code></div>
                  <div>subtasks</div><div><code id="modSubtasksCount">0</code></div>
                  <div>summaries</div><div><code id="modSummariesCount">0</code></div>
                </div>
              </div>
            </div>
            <div class="split" style="margin-top:12px;">
              <div class="card" style="margin:0;">
                <h2 style="margin-bottom:8px;">Patches</h2>
                <div class="list" id="patchesList"></div>
              </div>
              <div class="card" style="margin:0;">
                <h2 style="margin-bottom:8px;">Subtasks</h2>
                <div class="list" id="subtasksList"></div>
                <h2 style="margin-top:12px; margin-bottom:8px;">Subtask Summaries</h2>
                <div class="list" id="subtaskSummariesList"></div>
              </div>
            </div>
            <div class="small" style="margin-top:10px;">Patch Apply 浠嶅彈 gate 鎺у埗锛?span class="mono">SCC_PATCH_APPLY_ENABLED=true</span></div>
          </div>

          <div id="viewChat" class="card" style="display:none;">
            <h2>Chat Sessions锛堟寔涔呬笂涓嬫枃锛?/h2>
            <div class="split">
              <div>
                <div class="kv">
                  <div>chat_id</div><div><code id="chatIdPill">(none)</code></div>
                </div>
                <div class="btnrow">
                  <button id="chatNewBtn" class="primary">New Chat</button>
                  <button id="chatRefreshBtn">Refresh</button>
                  <button id="chatFollowBtn">Follow: ON</button>
                </div>
                <div class="btnrow" style="margin-top:8px;">
                  <input id="chatInput" placeholder="append message (server will persist JSONL)" style="flex:1; padding:10px; border-radius:10px; border:1px solid rgba(255,255,255,0.10); background:rgba(0,0,0,0.25); color:#e8f0ff;" />
                  <button id="chatSendBtn">Append</button>
                </div>
              </div>
              <div>
                <div class="kv">
                  <div>chats</div><div><code id="chatCountPill">0</code></div>
                </div>
                <div class="small">鐢ㄩ€旓細涓€涓?chat_id 缁存寔闀挎湡涓婁笅鏂囷紱鏈嶅姟绔繚瀛?JSONL锛屽悗缁彲琚?AI 璇诲彇鍋氳嚜鍔ㄥ寲銆?/div>
              </div>
            </div>
            <div class="split" style="margin-top:12px;">
              <div class="card" style="margin:0;">
                <h2 style="margin-bottom:8px;">Chats</h2>
                <div class="list" id="chatList"></div>
              </div>
              <div class="card" style="margin:0;">
                <h2 style="margin-bottom:8px;">Chat Stream</h2>
                <div class="log" id="chatLogBox"></div>
              </div>
            </div>
            <div class="small" style="margin-top:10px;">API: <span class="mono">/scc/chat/*</span> + <span class="mono">/scc/chat/{chat_id}/messages/tail</span></div>
          </div>
        </div>
      </div>
    </div>

    <script>
      const $ = (id) => document.getElementById(id);
      const base = location.origin;
      $("basePill").textContent = base;

      let pollOn = true;
      let selectedTaskId = "";
      let streamMode = "task"; // task|run
      let streamRunId = "";
      let lastLines = [];
      let follow = true;
      let patchApplyEnabled = false;
      let chatFollow = true;
      let selectedChatId = "";
      let chatCursor = null;

      function setTab(name){
        const stream = name === "stream";
        const modules = name === "modules";
        const chat = name === "chat";
        $("tabStream").classList.toggle("active", stream);
        $("tabModules").classList.toggle("active", modules);
        $("tabChat").classList.toggle("active", chat);
        $("viewStream").style.display = stream ? "" : "none";
        $("viewModules").style.display = modules ? "" : "none";
        $("viewChat").style.display = chat ? "" : "none";
      }

      $("tabStream").onclick = () => setTab("stream");
      $("tabModules").onclick = () => setTab("modules");
      $("tabChat").onclick = () => setTab("chat");

      async function apiGet(path){
        const r = await fetch(base + path, { cache: "no-store" });
        if(!r.ok) throw new Error(await r.text());
        return await r.json();
      }
      async function apiPost(path, body){
        const r = await fetch(base + path, { method: "POST", headers: {"Content-Type":"application/json"}, body: JSON.stringify(body||{}), cache:"no-store" });
        if(!r.ok) throw new Error(await r.text());
        return await r.json();
      }

      function badge(status){
        const s = String(status||"");
        const cls = s === "done" ? "ok" : (s === "failed" ? "bad" : "");
        return `<span class="badge ${cls}">${s||"?"}</span>`;
      }

      function safeStr(x){
        return String(x||"").replace(/[<>&]/g, (c)=>({ "<":"&lt;", ">":"&gt;", "&":"&amp;" }[c]));
      }

      function setSelectedChat(chatId){
        selectedChatId = chatId || "";
        $("chatIdPill").textContent = selectedChatId || "(none)";
        chatCursor = null;
        $("chatLogBox").innerHTML = "";
      }

      function maybeChatFollow(){
        if(!chatFollow) return;
        const box = $("chatLogBox");
        box.scrollTop = box.scrollHeight;
      }

      function renderTasks(items){
        const q = $("filter").value.trim().toLowerCase();
        const filtered = items.filter(it=>{
          const id = String(it.task_id||"");
          const goal = String(it.request?.task?.goal ?? it.request?.goal ?? "");
          const hay = (id + " " + goal).toLowerCase();
          return !q || hay.includes(q);
        });
        $("tasksList").innerHTML = filtered.map(it=>{
          const id = String(it.task_id||"");
          const goal = String(it.request?.task?.goal ?? it.request?.goal ?? "");
          const cls = id === selectedTaskId ? "item active" : "item";
          return `<div class="${cls}" data-id="${safeStr(id)}">
            ${badge(it.status)}
            <div style="min-width:0; flex:1;">
              <div class="mono" style="font-size:12px; color:#dbe3ff; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;">${safeStr(id)}</div>
              <div class="small" style="overflow:hidden; text-overflow:ellipsis; white-space:nowrap;">${safeStr(goal)}</div>
            </div>
          </div>`;
        }).join("") || `<div class="small" style="padding:10px;">(no tasks)</div>`;
        Array.from($("tasksList").querySelectorAll(".item")).forEach(el=>{
          el.onclick = ()=>selectTask(el.getAttribute("data-id")||"");
        });
      }

      async function refreshGate(){
        try{
          const cfg = await apiGet("/scc/patch/config");
          const enabled = !!cfg.patch_apply_enabled;
          patchApplyEnabled = enabled;
          $("patchGatePill").textContent = "patch_apply_enabled=" + (enabled ? "true" : "false");
          $("patchGatePill").style.borderColor = enabled ? "rgba(46,204,113,0.35)" : "rgba(255,255,255,0.10)";
        }catch(e){
          patchApplyEnabled = false;
          $("patchGatePill").textContent = "patch_apply_enabled=?";
        }
      }

      async function refreshTasks(){
        const data = await apiGet("/scc/tasks?limit=80");
        renderTasks(data.items||[]);
      }

      function maybeFollow(){
        if(!follow) return;
        const box = $("logBox");
        box.scrollTop = box.scrollHeight;
      }

      function setSelected(taskId){
        selectedTaskId = taskId;
        streamMode = "task";
        streamRunId = "";
        $("selTask").textContent = taskId || "(none)";
        $("selRunId").textContent = "(none)";
        $("selCursor").textContent = "(none)";
        $("modTask").textContent = taskId || "(none)";
        const link = taskId ? `/scc/task/${encodeURIComponent(taskId)}/events?limit=5000` : "#";
        $("eventsLink").textContent = taskId ? link : "(none)";
        $("eventsLink").href = link;
      }

      async function selectTask(taskId){
        setSelected(taskId);
        lastLines = [];
        window.__sccCursor = null;
        $("logBox").innerHTML = "";
        await refreshGate();
        await refreshModules();
        await refreshEvents();
        await refreshTasks();
      }

      async function refreshEvents(){
        if(streamMode === "task" && !selectedTaskId) return;
        if(streamMode === "run" && !streamRunId) return;
        const cur = (window.__sccCursor === null || window.__sccCursor === undefined) ? "" : window.__sccCursor;
        const box = $("logBox");
        try{
          const url = (streamMode === "run")
            ? `/scc/run/${encodeURIComponent(streamRunId)}/events/tail?cursor=${cur}&max_bytes=256000&max_lines=2000`
            : `/scc/task/${encodeURIComponent(selectedTaskId)}/events/tail?cursor=${cur}&max_bytes=256000&max_lines=2000`;
          const data = await apiGet(url);
          const lines = data.lines || [];
          window.__sccCursor = data.cursor;
          $("selCursor").textContent = String(window.__sccCursor ?? "(none)");
          if(streamMode === "run"){
            $("selTask").textContent = `(run) ${streamRunId}`;
            $("selRunId").textContent = streamRunId || "(none)";
            $("eventsLink").textContent = url;
            $("eventsLink").href = url;
          }else{
            const rid = data.run_id ? String(data.run_id) : "";
            $("selRunId").textContent = rid || "(none)";
            if(rid) $("replayRunId").value = rid;
            $("replayCursor").value = String(window.__sccCursor ?? "");
          }

          if(lines.length){
            lines.forEach(ln=>{
              const pre = document.createElement("pre");
              pre.className = "logline";
              pre.textContent = ln;
              box.appendChild(pre);
            });

            // Prevent unbounded DOM growth (Cursor-like streaming view).
            const MAX_LINES = 6000;
            const TRIM_TO = 5000;
            while(box.children.length > MAX_LINES){
              const n = Math.max(1, box.children.length - TRIM_TO);
              for(let i=0;i<n;i++) box.removeChild(box.firstChild);
            }

            if(follow) maybeFollow();
          }
        }catch(e){
          const pre = document.createElement("pre");
          pre.className = "logline";
          pre.textContent = "[events] error: " + (e && e.message ? e.message : String(e));
          box.appendChild(pre);
          if(follow) maybeFollow();
        }
      }

      function updateFollowFromScroll(){
        const box = $("logBox");
        const nearBottom = (box.scrollTop + box.clientHeight) >= (box.scrollHeight - 10);
        if(nearBottom && !follow){
          follow = true;
          $("followBtn").textContent = "Follow: ON";
          $("followState").textContent = "on";
        }
        if(!nearBottom && follow){
          follow = false;
          $("followBtn").textContent = "Follow: OFF";
          $("followState").textContent = "off";
        }
      }

      $("logBox").addEventListener("scroll", ()=>updateFollowFromScroll());
      $("followBtn").onclick = ()=>{
        follow = !follow;
        $("followBtn").textContent = "Follow: " + (follow ? "ON" : "OFF");
        $("followState").textContent = follow ? "on" : "off";
        if(follow) maybeFollow();
      };
      $("clearLogBtn").onclick = ()=>{ $("logBox").innerHTML=""; lastLines=[]; };
      $("refreshBtn").onclick = async()=>{ await refreshGate(); await refreshTasks(); await refreshModules(); await refreshEvents(); };
      $("togglePollBtn").onclick = ()=>{ pollOn = !pollOn; $("togglePollBtn").textContent = pollOn ? "鏆傚仠杞" : "鎭㈠杞"; };

      $("openContinuationBtn").onclick = async()=>{
        if(!selectedTaskId) return;
        const url = `/scc/task/${encodeURIComponent(selectedTaskId)}/continuation?refresh=true`;
        window.open(url, "_blank");
      };
      $("openPatchesBtn").onclick = async()=>{
        if(!selectedTaskId) return;
        const url = `/scc/task/${encodeURIComponent(selectedTaskId)}/patches`;
        window.open(url, "_blank");
      };

      $("exportSubmitBtn").onclick = async()=>{
        if(!selectedTaskId) return;
        try{
          const out = await apiGet(`/scc/task/${encodeURIComponent(selectedTaskId)}/submit/export`);
          const text = JSON.stringify(out?.submit ?? out, null, 2);
          await navigator.clipboard.writeText(text);
        }catch(e){}
      };

      $("copyReplayBtn").onclick = async()=>{
        try{
          const runId = String($("replayRunId").value||"").trim();
          const cur = String($("replayCursor").value||"").trim();
          const ptr = { run_id: runId || undefined, cursor: cur ? Number(cur) : 0 };
          await navigator.clipboard.writeText(JSON.stringify(ptr));
        }catch(e){}
      };

      $("replayBtn").onclick = async()=>{
        const runId = String($("replayRunId").value||"").trim();
        const cur = String($("replayCursor").value||"").trim();
        if(!runId) return;
        streamMode = "run";
        streamRunId = runId;
        window.__sccCursor = cur ? Number(cur) : null;
        $("logBox").innerHTML = "";
        await refreshEvents();
      };

      async function refreshModules(){
        if(!selectedTaskId){
          $("modStatus").textContent = "-";
          $("modGoal").textContent = "-";
          $("patchesList").innerHTML = "";
          $("subtasksList").innerHTML = "";
          $("subtaskSummariesList").innerHTML = "";
          $("modSummariesCount").textContent = "0";
          return;
        }
        try{
          const task = await apiGet(`/scc/task/${encodeURIComponent(selectedTaskId)}`);
          $("modStatus").textContent = String(task.status||"-");
          $("modGoal").textContent = String(task.request?.task?.goal ?? task.request?.goal ?? "-").slice(0, 240);
        }catch(e){}

        // patches
        try{
          const pp = await apiGet(`/scc/task/${encodeURIComponent(selectedTaskId)}/patches`);
          const items = pp.items || [];
          $("modPatchesCount").textContent = String(items.length||0);
          $("patchesList").innerHTML = items.map(it=>{
            const name = String(it.name||"");
            const disabled = patchApplyEnabled ? "" : "disabled";
            return `<div class="item" data-name="${safeStr(name)}">
              <span class="badge">diff</span>
              <div style="flex:1; min-width:0;">
                <div class="mono" style="font-size:12px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;">${safeStr(name)}</div>
                <div class="small">鍙抽敭鍦?VS Code 閲屾洿鏂逛究锛涜繖閲屾彁渚涘揩鎹锋寜閽?/div>
              </div>
              <button data-act="preview">Preview</button>
              <button data-act="apply" ${disabled}>Apply</button>
              <button data-act="rollback" ${disabled}>Rollback</button>
            </div>`;
          }).join("") || `<div class="small" style="padding:10px;">(no patches)</div>`;

          Array.from($("patchesList").querySelectorAll(".item")).forEach(el=>{
            const name = el.getAttribute("data-name")||"";
            el.querySelectorAll("button").forEach(btn=>{
              btn.onclick = async(ev)=>{
                ev.stopPropagation();
                const act = btn.getAttribute("data-act");
                if(act==="preview"){
                  const out = await apiPost(`/scc/task/${encodeURIComponent(selectedTaskId)}/patches/${encodeURIComponent(name)}/preview`, {});
                  alert(JSON.stringify(out, null, 2).slice(0, 8000));
                } else if(act==="rollback"){
                  if(!patchApplyEnabled){ alert("Patch apply disabled by gate"); return; }
                  const out = await apiPost(`/scc/task/${encodeURIComponent(selectedTaskId)}/patches/${encodeURIComponent(name)}/apply`, { reverse: true });
                  alert(JSON.stringify(out, null, 2).slice(0, 8000));
                } else {
                  if(!patchApplyEnabled){ alert("Patch apply disabled by gate"); return; }
                  const out = await apiPost(`/scc/task/${encodeURIComponent(selectedTaskId)}/patches/${encodeURIComponent(name)}/apply`, {});
                  alert(JSON.stringify(out, null, 2).slice(0, 8000));
                }
                await refreshGate();
              };
            });
            el.onclick = ()=>window.open(`/scc/task/${encodeURIComponent(selectedTaskId)}/patches/${encodeURIComponent(name)}`, "_blank");
          });
        }catch(e){
          $("patchesList").innerHTML = `<div class="small" style="padding:10px;">patches error</div>`;
        }

        // subtasks
        try{
          const st = await apiGet(`/scc/task/${encodeURIComponent(selectedTaskId)}/subtasks?limit=50`);
          const items = st.items || [];
          $("modSubtasksCount").textContent = String(items.length||0);
          $("subtasksList").innerHTML = items.map(it=>{
            const id = String(it.task_id||"");
            const status = String(it.status||"");
            return `<div class="item" data-id="${safeStr(id)}">
              ${badge(status)}
              <div style="flex:1; min-width:0;">
                <div class="mono" style="font-size:12px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;">${safeStr(id)}</div>
                <div class="small">click to open events</div>
              </div>
            </div>`;
          }).join("") || `<div class="small" style="padding:10px;">(no subtasks)</div>`;
          Array.from($("subtasksList").querySelectorAll(".item")).forEach(el=>{
            el.onclick = ()=>window.open(`/scc/task/${encodeURIComponent(el.getAttribute("data-id")||"")}/events?limit=2000`, "_blank");
          });
        }catch(e){
          $("subtasksList").innerHTML = `<div class="small" style="padding:10px;">subtasks error</div>`;
        }

        // subtask summaries
        try{
          const ss = await apiGet(`/scc/task/${encodeURIComponent(selectedTaskId)}/subtask_summaries?limit=200`);
          const items = ss.items || [];
          $("modSummariesCount").textContent = String(items.length||0);
          $("subtaskSummariesList").innerHTML = items.map(it=>{
            const name = String(it.name||"");
            return `<div class="item" data-name="${safeStr(name)}">
              <span class="badge">json</span>
              <div style="flex:1; min-width:0;">
                <div class="mono" style="font-size:12px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;">${safeStr(name)}</div>
                <div class="small">click to view json</div>
              </div>
              <button data-act="view">View</button>
            </div>`;
          }).join("") || `<div class="small" style="padding:10px;">(no summaries)</div>`;

          Array.from($("subtaskSummariesList").querySelectorAll(".item")).forEach(el=>{
            const name = el.getAttribute("data-name")||"";
            const btn = el.querySelector("button[data-act='view']");
            if(btn){
              btn.onclick = async(ev)=>{
                ev.stopPropagation();
                const out = await apiGet(`/scc/task/${encodeURIComponent(selectedTaskId)}/subtask_summaries/${encodeURIComponent(name)}`);
                alert(String(out.json_text||"").slice(0, 8000));
              };
            }
            el.onclick = ()=>window.open(`/scc/task/${encodeURIComponent(selectedTaskId)}/subtask_summaries/${encodeURIComponent(name)}`, "_blank");
          });
        }catch(e){
          $("subtaskSummariesList").innerHTML = `<div class="small" style="padding:10px;">summaries error</div>`;
          $("modSummariesCount").textContent = "?";
        }
      }

      $("modRefreshBtn").onclick = refreshModules;
      $("modOpenReportBtn").onclick = async()=>{
        if(!selectedTaskId) return;
        const task = await apiGet(`/scc/task/${encodeURIComponent(selectedTaskId)}`);
        const path = String(task.report_md||"");
        if(path) window.open(path, "_blank");
      };

      async function refreshChats(){
        try{
          const data = await apiGet(`/scc/chats?limit=80`);
          const items = data.items || [];
          $("chatCountPill").textContent = String(items.length||0);
          $("chatList").innerHTML = items.map(it=>{
            const id = String(it.chat_id||"");
            const title = String(it.meta?.title||"");
            const cls = id === selectedChatId ? "item active" : "item";
            return `<div class="${cls}" data-id="${safeStr(id)}">
              <span class="badge">chat</span>
              <div style="min-width:0; flex:1;">
                <div class="mono" style="font-size:12px; color:#dbe3ff; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;">${safeStr(id)}</div>
                <div class="small" style="overflow:hidden; text-overflow:ellipsis; white-space:nowrap;">${safeStr(title)}</div>
              </div>
            </div>`;
          }).join("") || `<div class="small" style="padding:10px;">(no chats)</div>`;
          Array.from($("chatList").querySelectorAll(".item")).forEach(el=>{
            el.onclick = async()=>{ setSelectedChat(el.getAttribute("data-id")||""); await refreshChatTail(); };
          });
        }catch(e){
          $("chatList").innerHTML = `<div class="small" style="padding:10px;">chats error</div>`;
        }
      }

      async function refreshChatTail(){
        if(!selectedChatId) return;
        const cur = (chatCursor === null || chatCursor === undefined) ? "" : chatCursor;
        const box = $("chatLogBox");
        try{
          const data = await apiGet(`/scc/chat/${encodeURIComponent(selectedChatId)}/messages/tail?cursor=${cur}&max_bytes=256000&max_lines=2000`);
          const lines = data.lines || [];
          chatCursor = data.cursor;
          if(lines.length){
            lines.forEach(ln=>{
              const pre = document.createElement("pre");
              pre.className = "logline";
              pre.textContent = ln;
              box.appendChild(pre);
            });
            if(chatFollow) maybeChatFollow();
          }
        }catch(e){
          const pre = document.createElement("pre");
          pre.className = "logline";
          pre.textContent = "[chat] error: " + (e && e.message ? e.message : String(e));
          box.appendChild(pre);
          if(chatFollow) maybeChatFollow();
        }
      }

      $("chatNewBtn").onclick = async()=>{
        const out = await apiPost("/scc/chat/new", { title: "board" });
        if(out && out.chat_id){
          await refreshChats();
          setSelectedChat(String(out.chat_id));
          await refreshChatTail();
        }
      };
      $("chatRefreshBtn").onclick = async()=>{ await refreshChats(); await refreshChatTail(); };
      $("chatFollowBtn").onclick = ()=>{ chatFollow=!chatFollow; $("chatFollowBtn").textContent = "Follow: " + (chatFollow ? "ON" : "OFF"); if(chatFollow) maybeChatFollow(); };
      $("chatSendBtn").onclick = async()=>{
        if(!selectedChatId) return;
        const t = ($("chatInput").value||"").trim();
        if(!t) return;
        $("chatInput").value = "";
        await apiPost(`/scc/chat/${encodeURIComponent(selectedChatId)}/append`, { role:"user", content:t, meta:{ source:"board" }});
        await refreshChatTail();
      };

      async function loop(){
        if(pollOn){
          try{ await refreshGate(); }catch(e){}
          try{ await refreshTasks(); }catch(e){}
          try{ await refreshEvents(); }catch(e){}
          try{
            const chatVisible = $("viewChat").style.display !== "none";
            if(chatVisible) await refreshChatTail();
          }catch(e){}
        }
        const sec = Math.max(0.3, Math.min(5.0, parseFloat($("pollSec").value||"1") || 1.0));
        setTimeout(loop, sec*1000);
      }

      // init
      refreshGate();
      refreshTasks();
      refreshChats();
      loop();
    </script>
  </body>
</html>
        """.strip()

    # SCC Intake: receive directive payloads forwarded by browser tooling (extension / embedded browser).
    @app.post("/intake/directive")
    async def scc_intake_directive(payload: dict, request: Request):
        try:
            from datetime import datetime, timezone
            import json

            directives = payload.get("directives")
            if directives is None:
                return JSONResponse(status_code=400, content={"ok": False, "error": "missing_field: directives"})
            if not isinstance(directives, list):
                return JSONResponse(status_code=400, content={"ok": False, "error": "invalid_field: directives"})

            received_at = datetime.now(timezone.utc).isoformat()
            envelope = {
                "received_at": received_at,
                "client": request.client.host if request.client else "",
                "payload": payload,
            }

            p = (repo_root / "artifacts" / "scc_state" / "intake_directives.jsonl").resolve()
            p.parent.mkdir(parents=True, exist_ok=True)
            with open(p, "a", encoding="utf-8") as f:
                f.write(json.dumps(envelope, ensure_ascii=False) + "\n")

            return {"ok": True, "received_at": received_at}
        except Exception as e:
            return JSONResponse(status_code=500, content={"ok": False, "error": str(e)})

    # WebGPT intake + archive (single-port, repo-local).
    try:
        from tools.unified_server.services.webgpt_archive_service import WebGPTArchiveService
        from tools.unified_server.services.webgpt_memory_service import WebGPTMemoryService

        _webgpt_archive = WebGPTArchiveService(repo_root=repo_root)
        _webgpt_memory = WebGPTMemoryService(repo_root=repo_root)

        @app.get("/scc/webgpt/status")
        async def scc_webgpt_status():
            return _webgpt_archive.status()

        @app.get("/scc/webgpt/list")
        async def scc_webgpt_list(limit: int = 50):
            try:
                return {"ok": True, "conversations": _webgpt_archive.list_conversations(limit=limit)}
            except Exception as e:
                return JSONResponse(status_code=500, content={"ok": False, "error": str(e)})

        @app.post("/scc/webgpt/intake")
        async def scc_webgpt_intake(payload: dict, request: Request):
            try:
                from datetime import datetime, timezone
                import json as _json

                conversation_id = str(payload.get("conversation_id") or "").strip()
                title = payload.get("title")
                title = str(title).strip() if title is not None else None
                source = str(payload.get("source") or "webgpt_embedded_browser").strip()
                messages = payload.get("messages") or []
                if not conversation_id:
                    return JSONResponse(status_code=400, content={"ok": False, "error": "missing_field: conversation_id"})
                if not isinstance(messages, list):
                    return JSONResponse(status_code=400, content={"ok": False, "error": "invalid_field: messages"})

                received_at = datetime.now(timezone.utc).isoformat()
                envelope = {
                    "received_at": received_at,
                    "client": request.client.host if request.client else "",
                    "payload": payload,
                }

                # Evidence: append jsonl + per-intake snapshot
                base = (repo_root / "artifacts" / "webgpt").resolve()
                base.mkdir(parents=True, exist_ok=True)
                p = (base / "intake.jsonl").resolve()
                with open(p, "a", encoding="utf-8") as f:
                    f.write(_json.dumps(envelope, ensure_ascii=False) + "\n")
                snap_dir = (base / "intakes").resolve()
                snap_dir.mkdir(parents=True, exist_ok=True)
                ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
                snap = (snap_dir / f"{ts}__{conversation_id}.json").resolve()
                snap.write_text(_json.dumps(envelope, ensure_ascii=False, indent=2), encoding="utf-8")

                res = _webgpt_archive.intake(
                    conversation_id=conversation_id,
                    title=title,
                    source=source,
                    messages=[m for m in messages if isinstance(m, dict)],
                )
                return {
                    "ok": True,
                    "received_at": received_at,
                    "inserted": res.inserted,
                    "duplicates": res.duplicates,
                    "last_seq": res.last_seq,
                }
            except ValueError as e:
                return JSONResponse(status_code=400, content={"ok": False, "error": str(e)})
            except RuntimeError as e:
                return JSONResponse(status_code=423, content={"ok": False, "error": str(e)})
            except Exception as e:
                return JSONResponse(status_code=500, content={"ok": False, "error": str(e)})

        @app.post("/scc/webgpt/export")
        async def scc_webgpt_export(payload: dict):
            try:
                conversation_id = str((payload or {}).get("conversation_id") or "").strip()
                if not conversation_id:
                    return JSONResponse(status_code=400, content={"ok": False, "error": "missing_field: conversation_id"})
                return _webgpt_archive.export_markdown_if_changed(conversation_id=conversation_id)
            except KeyError:
                return JSONResponse(status_code=404, content={"ok": False, "error": "conversation not found"})
            except Exception as e:
                return JSONResponse(status_code=500, content={"ok": False, "error": str(e)})

        @app.post("/scc/webgpt/export_all")
        async def scc_webgpt_export_all(payload: dict):
            try:
                limit = 500
                if isinstance(payload, dict) and isinstance(payload.get("limit"), int):
                    limit = int(payload["limit"])
                return _webgpt_archive.export_all_markdown(limit=limit)
            except Exception as e:
                return JSONResponse(status_code=500, content={"ok": False, "error": str(e)})

        @app.post("/scc/webgpt/memory/intake")
        async def scc_webgpt_memory_intake(payload: dict):
            try:
                if not isinstance(payload, dict):
                    return JSONResponse(status_code=400, content={"ok": False, "error": "invalid_payload"})
                res = _webgpt_memory.intake(payload=payload)
                return {"ok": True, "doc_path": res.doc_path}
            except Exception as e:
                return JSONResponse(status_code=500, content={"ok": False, "error": str(e)})

    except Exception:
        _webgpt_archive = None

    # SCC Embedded Browser control endpoints (start/stop/status).
    try:
        from tools.scc.browser.embedded_browser_manager import SCCEmbeddedBrowserManager
        import json as _json

        _scc_browser_manager = SCCEmbeddedBrowserManager(
            app_dir=(repo_root / "tools" / "scc" / "apps" / "browser" / "scc-chatgpt-browser").resolve()
        )

        @app.get("/scc/browser/status")
        async def scc_browser_status():
            return _scc_browser_manager.status()

        @app.post("/scc/browser/command")
        async def scc_browser_command(payload: dict, request: Request):
            """
            Send a best-effort command to the running embedded browser via a repo-local JSONL queue.

            This avoids restarting the Electron process (keeps login/session stable).
            """
            try:
                from datetime import datetime, timezone

                if not isinstance(payload, dict):
                    return JSONResponse(status_code=400, content={"ok": False, "error": "invalid_payload"})

                cmd = str(payload.get("cmd") or "").strip()
                if not cmd:
                    return JSONResponse(status_code=400, content={"ok": False, "error": "missing_field: cmd"})

                args = payload.get("args") if isinstance(payload.get("args"), dict) else {}
                cmd_id = str(payload.get("id") or "").strip()
                if not cmd_id:
                    cmd_id = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S") + "_" + cmd

                envelope = {
                    "id": cmd_id,
                    "cmd": cmd,
                    "args": args,
                    "received_at": datetime.now(timezone.utc).isoformat(),
                    "client": request.client.host if request.client else "",
                }

                q = (repo_root / "artifacts" / "scc_state" / "browser_commands.jsonl").resolve()
                q.parent.mkdir(parents=True, exist_ok=True)
                with open(q, "a", encoding="utf-8") as f:
                    f.write(_json.dumps(envelope, ensure_ascii=False) + "\n")

                return {"ok": True, "id": cmd_id, "queue_path": str(q.relative_to(repo_root)).replace("\\", "/")}
            except Exception as e:
                return JSONResponse(status_code=500, content={"ok": False, "error": str(e)})

        @app.post("/scc/browser/start")
        async def scc_browser_start(payload: dict, request: Request):
            boot_url = payload.get("url") if isinstance(payload, dict) else None
            home_url = payload.get("home_url") if isinstance(payload, dict) else None
            autosend = payload.get("autosend") if isinstance(payload, dict) else None
            default_endpoint = payload.get("endpoint") if isinstance(payload, dict) else None
            if not default_endpoint:
                default_endpoint = str(request.base_url).rstrip("/") + "/intake/directive"
            webgpt_intake_endpoint = str(request.base_url).rstrip("/") + "/scc/webgpt/intake"
            webgpt_export_endpoint = str(request.base_url).rstrip("/") + "/scc/webgpt/export"

            backfill = payload.get("webgpt_backfill") if isinstance(payload, dict) else None
            webgpt_backfill_autostart = None
            webgpt_backfill_limit = None
            webgpt_backfill_scroll_steps = None
            if isinstance(backfill, dict):
                if isinstance(backfill.get("autostart"), bool):
                    webgpt_backfill_autostart = bool(backfill.get("autostart"))
                if isinstance(backfill.get("limit"), int):
                    webgpt_backfill_limit = int(backfill.get("limit"))
                if isinstance(backfill.get("scroll_steps"), int):
                    webgpt_backfill_scroll_steps = int(backfill.get("scroll_steps"))
            return _scc_browser_manager.start(
                boot_url=boot_url,
                home_url=home_url,
                default_endpoint=default_endpoint,
                webgpt_intake_endpoint=webgpt_intake_endpoint,
                webgpt_export_endpoint=webgpt_export_endpoint,
                webgpt_backfill_autostart=webgpt_backfill_autostart,
                webgpt_backfill_limit=webgpt_backfill_limit,
                webgpt_backfill_scroll_steps=webgpt_backfill_scroll_steps,
                default_autosend=autosend if isinstance(autosend, bool) else None,
            )

        @app.post("/scc/browser/stop")
        async def scc_browser_stop(payload: dict):
            timeout_s = 5.0
            if isinstance(payload, dict) and isinstance(payload.get("timeout_s"), (int, float)):
                timeout_s = float(payload["timeout_s"])
            return _scc_browser_manager.stop(timeout_s=timeout_s)

    except Exception:
        # Optional feature: don't block server startup if browser tooling isn't available on this host.
        _scc_browser_manager = None

    # SCC minimal task runner API (standard interfaces only):
    # - Task Contract (goal, success_criteria, stop_condition, commands_hint, artifacts_expectation)
    # - Workspace Adapter (repo_path, bootstrap_cmds, test_cmds, artifact_paths)
    # - Evidence + Verdict (selftest.log, report.md, evidence/)
    @app.post("/scc/task/run")
    async def scc_task_run(payload: dict):
        try:
            from tools.scc.task_runner import (
                SCCTaskRequest,
                TaskContract,
                WorkspaceAdapter,
                run_scc_task,
            )

            task = payload.get("task") or {}
            workspace = payload.get("workspace") or payload

            goal = str(task.get("goal") or payload.get("goal") or "").strip()
            if not goal:
                goal = "Run commands (no goal provided)"

            req = SCCTaskRequest(
                task=TaskContract(
                    goal=goal,
                    scope_allow=list(task.get("scope_allow") or []),
                    success_criteria=list(task.get("success_criteria") or []),
                    stop_condition=list(task.get("stop_condition") or []),
                    commands_hint=list(task.get("commands_hint") or payload.get("commands_hint") or []),
                    artifacts_expectation=list(task.get("artifacts_expectation") or []),
                    difficulty=str(task.get("difficulty") or payload.get("difficulty") or "").strip(),
                ),
                workspace=WorkspaceAdapter(
                    repo_path=str(workspace.get("repo_path") or ""),
                    bootstrap_cmds=list(workspace.get("bootstrap_cmds") or []),
                    test_cmds=list(workspace.get("test_cmds") or payload.get("test_cmds") or []),
                    artifact_paths=list(workspace.get("artifact_paths") or []),
                ),
                timeout_s=float(payload.get("timeout_s") or 0.0),
            )

            result = run_scc_task(req, repo_root=repo_root)
            return JSONResponse(
                content={
                    "ok": True,
                    "run_id": result.run_id,
                    "exit_code": result.exit_code,
                    "verdict": "PASS" if result.ok else "FAIL",
                    "out_dir": result.out_dir,
                    "selftest_log": result.selftest_log,
                    "report_md": result.report_md,
                    "evidence_dir": result.evidence_dir,
                    "copied_artifacts": result.copied_artifacts,
                }
            )
        except Exception as e:
            return JSONResponse(
                status_code=400,
                content={"ok": False, "error": str(e)},
            )

    # SCC autonomous queue: submit tasks and let SCC execute them automatically.
    # This keeps business coupling to the same contracts as /scc/task/run.
    try:
        from tools.scc.task_queue import SCCTaskQueue

        task_queue = SCCTaskQueue(repo_root=repo_root)
        from tools.scc.capabilities.skills_catalog import build_default_catalog

        skills_catalog = build_default_catalog(repo_root=repo_root)

        @app.post("/scc/task/submit")
        async def scc_task_submit(payload: dict):
            try:
                rec = task_queue.submit(payload)
                return JSONResponse(content={"ok": True, "task_id": rec.task_id, "status": rec.status})
            except Exception as e:
                return JSONResponse(status_code=400, content={"ok": False, "error": str(e)})

        @app.post("/scc/task/plan")
        async def scc_task_plan(payload: dict):
            """
            Build a deterministic execution plan without running commands.
            """
            try:
                from tools.scc.orchestrators.execution_plan import PlannedStep, build_execution_plan
                from tools.scc.capabilities.permission_floor import pdp_decide_command
                from tools.scc.orchestrators.execution_plan import is_command_concurrency_safe

                # Reuse the same payload-to-request conversion as the queue (contract stability).
                req = task_queue.payload_to_request(payload)  # type: ignore[attr-defined]

                all_cmds = []
                for c in req.workspace.bootstrap_cmds or []:
                    all_cmds.append(("bootstrap", c))
                for c in req.task.commands_hint or []:
                    all_cmds.append(("hint", c))
                for c in req.workspace.test_cmds or []:
                    all_cmds.append(("test", c))

                steps = []
                for idx, (kind, cmd) in enumerate(all_cmds, start=1):
                    tid = str(payload.get("task_id") or "").strip() or None
                    ev_root = _task_evidence_dir(tid) if tid else Path(repo_root)
                    pdp = pdp_decide_command(
                        cmd=str(cmd or ""),
                        task_id=tid,
                        evidence_root=ev_root,
                        enqueue=False,
                    )
                    steps.append(
                        PlannedStep(
                            idx=idx,
                            kind=kind,
                            cmd=str(cmd or ""),
                            risk=str(pdp.get("risk") or "allow"),
                            concurrency_safe=is_command_concurrency_safe(cmd),
                        )
                    )
                plan = build_execution_plan(steps=steps)
                return JSONResponse(content={"ok": True, **plan.to_dict()})
            except Exception as e:
                return JSONResponse(status_code=400, content={"ok": False, "error": str(e)})

        @app.get("/scc/orchestrator/profiles")
        async def scc_orchestrator_profiles():
            try:
                from tools.scc.orchestrators.profiles import get_builtin_profiles

                profiles = {k: v.to_dict() for k, v in get_builtin_profiles().items()}
                return JSONResponse(content={"ok": True, "profiles": profiles})
            except Exception as e:
                return JSONResponse(status_code=500, content={"ok": False, "error": str(e)})

        @app.post("/scc/task/orchestrate")
        async def scc_task_orchestrate(payload: dict):
            """
            Dry-run orchestration scaffold (plan/chat/fullagent).

            Default is plan mode; fullagent requires SCC_MODEL_ENABLED=true.
            This endpoint never auto-starts the SCC worker thread.
            """
            try:
                from tools.scc.orchestrators.profiles import resolve_profile

                orch = payload.get("orchestrator") if isinstance(payload.get("orchestrator"), dict) else {}
                profile_name = str(orch.get("profile") or payload.get("profile") or "plan")
                task_id = orch.get("task_id") or payload.get("task_id")
                if task_id is not None:
                    task_id = str(task_id)

                profile = resolve_profile(profile_name)
                if profile.name == "fullagent":
                    from tools.scc.orchestrators.fullagent_loop import fullagent_orchestrate

                    out = fullagent_orchestrate(
                        repo_root=repo_root,
                        task_queue=task_queue,
                        payload=payload,
                        profile=profile,
                        task_id=task_id,
                    )
                    return JSONResponse(content=out)
                else:
                    from tools.scc.orchestrators.cc_like import orchestrate_dry_run

                    res = orchestrate_dry_run(
                        repo_root=repo_root,
                        task_queue=task_queue,
                        payload=payload,
                        profile=profile,
                        task_id=task_id,
                    )
                    return JSONResponse(
                        content={
                            "ok": True,
                            "task_id": res.task_id,
                            "profile": res.profile,
                            "plan_graph": res.plan_graph,
                            "execution_plan": res.execution_plan,
                            "todo_state": res.todo_state,
                            "evidence_dir": res.evidence_dir,
                        }
                    )
            except Exception as e:
                return JSONResponse(status_code=400, content={"ok": False, "error": str(e)})

        @app.get("/scc/task/{task_id}")
        async def scc_task_get(task_id: str):
            try:
                rec = task_queue.get(task_id)
                return JSONResponse(content={"ok": True, **rec.__dict__})
            except Exception as e:
                return JSONResponse(status_code=404, content={"ok": False, "error": str(e)})

        @app.get("/scc/task/{task_id}/orchestrator_state")
        async def scc_task_orchestrator_state(task_id: str):
            try:
                from tools.scc.orchestrators.state_store import OrchestratorStateStore

                store = OrchestratorStateStore(repo_root=repo_root, task_id=task_id)
                state = store.read()
                if not state:
                    return JSONResponse(status_code=404, content={"ok": False, "error": "state_not_found"})
                return JSONResponse(content={"ok": True, **state.__dict__})
            except Exception as e:
                return JSONResponse(status_code=500, content={"ok": False, "error": str(e)})

        @app.get("/scc/task/{task_id}/events")
        async def scc_task_events(task_id: str, limit: int = 200):
            try:
                from tools.scc.event_log import resolve_events_path_for_task
                from pathlib import Path

                resolved = resolve_events_path_for_task(repo_root, task_id)
                p = Path(resolved.get("path") or "").resolve()
                if not p.exists():
                    return JSONResponse(status_code=404, content={"ok": False, "error": "events_not_found"})
                lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
                lim = max(1, min(5000, int(limit or 200)))
                return JSONResponse(
                    content={
                        "ok": True,
                        "path": str(p),
                        "source": resolved.get("source"),
                        "run_id": resolved.get("run_id"),
                        "lines": lines[-lim:],
                    }
                )
            except Exception as e:
                return JSONResponse(status_code=500, content={"ok": False, "error": str(e)})

        @app.get("/scc/task/{task_id}/events/tail")
        async def scc_task_events_tail(task_id: str, cursor: str | None = None, max_bytes: int = 256000, max_lines: int = 2000):
            """
            Cursor-based JSONL tailing for UI.
            - cursor=None: start from EOF-max_bytes
            - cursor=int: byte offset (0..EOF)
            returns new cursor at current EOF.
            """
            try:
                from tools.scc.event_log import resolve_events_path_for_task
                from tools.scc.event_tail import tail_jsonl_with_cursor
                from pathlib import Path

                resolved = resolve_events_path_for_task(repo_root, task_id)
                p = Path(resolved.get("path") or "").resolve()
                cur: int | None
                if cursor is None:
                    cur = None
                else:
                    c = str(cursor).strip()
                    if not c:
                        cur = None
                    else:
                        try:
                            cur = int(c)
                        except Exception:
                            return JSONResponse(status_code=400, content={"ok": False, "error": "invalid_cursor"})

                res = tail_jsonl_with_cursor(path=p, cursor=cur, max_bytes=max_bytes, max_lines=max_lines)
                payload = {**res.to_dict(), "task_id": task_id, "source": resolved.get("source"), "run_id": resolved.get("run_id")}
                if not res.ok and str(res.error) == "not_found":
                    # Keep polling UIs alive: events.jsonl may appear slightly after task/run creation.
                    return JSONResponse(content=payload)
                if not res.ok:
                    return JSONResponse(status_code=404, content={"ok": False, "error": res.error, "path": res.path})
                return JSONResponse(content=payload)
            except Exception as e:
                return JSONResponse(status_code=500, content={"ok": False, "error": str(e)})

        @app.get("/scc/run/{run_id}/events/tail")
        async def scc_run_events_tail(run_id: str, cursor: str | None = None, max_bytes: int = 256000, max_lines: int = 2000):
            """
            Cursor-based JSONL tailing for artifacts/scc_runs/<run_id>/events.jsonl (replay support).
            """
            try:
                from tools.scc.event_log import run_events_path
                from tools.scc.event_tail import tail_jsonl_with_cursor

                p = run_events_path(repo_root, run_id)
                cur: int | None
                if cursor is None:
                    cur = None
                else:
                    c = str(cursor).strip()
                    if not c:
                        cur = None
                    else:
                        try:
                            cur = int(c)
                        except Exception:
                            return JSONResponse(status_code=400, content={"ok": False, "error": "invalid_cursor"})

                res = tail_jsonl_with_cursor(path=p, cursor=cur, max_bytes=max_bytes, max_lines=max_lines)
                payload = {**res.to_dict(), "run_id": run_id}
                if not res.ok and str(res.error) == "not_found":
                    return JSONResponse(content=payload)
                if not res.ok:
                    return JSONResponse(status_code=404, content={"ok": False, "error": res.error, "path": res.path})
                return JSONResponse(content=payload)
            except Exception as e:
                return JSONResponse(status_code=500, content={"ok": False, "error": str(e)})

        @app.get("/scc/task/{task_id}/submit/export")
        async def scc_task_submit_export(task_id: str):
            """
            Export a machine-parseable SUBMIT payload for reproducibility.
            The returned object can be POSTed back to /scc/task/submit.
            """
            try:
                rec = task_queue.get(task_id)
                return JSONResponse(content={"ok": True, "task_id": rec.task_id, "submit": rec.request, "run_id": rec.run_id})
            except Exception as e:
                return JSONResponse(status_code=404, content={"ok": False, "error": str(e)})

        @app.get("/scc/task/{task_id}/todos")
        async def scc_task_todos_get(task_id: str):
            try:
                from tools.scc.orchestrators.todo_state import TodoStateStore

                store = TodoStateStore(repo_root=repo_root, task_id=task_id)
                state = store.read()
                if not state:
                    return JSONResponse(content={"ok": True, "items": [], "updated_utc": None})
                return JSONResponse(content={"ok": True, **state.to_dict()})
            except Exception as e:
                return JSONResponse(status_code=500, content={"ok": False, "error": str(e)})

        @app.post("/scc/task/{task_id}/todos")
        async def scc_task_todos_set(task_id: str, payload: dict):
            try:
                from tools.scc.event_log import get_task_logger
                from tools.scc.orchestrators.todo_state import TodoStateStore

                items = payload.get("items")
                if not isinstance(items, list):
                    return JSONResponse(status_code=400, content={"ok": False, "error": "items_list_required"})
                store = TodoStateStore(repo_root=repo_root, task_id=task_id)
                state = store.write(items)
                get_task_logger(repo_root=repo_root, task_id=task_id).emit(
                    "todo_updated",
                    task_id=task_id,
                    data={"updated_utc": state.updated_utc, "count": len(state.items)},
                )
                return JSONResponse(content={"ok": True, **state.to_dict()})
            except Exception as e:
                return JSONResponse(status_code=400, content={"ok": False, "error": str(e)})

        @app.get("/scc/task/{task_id}/reminders")
        async def scc_task_reminders(task_id: str):
            try:
                from tools.scc.orchestrators.reminders import compute_reminders

                reminders = compute_reminders(repo_root=repo_root, task_id=task_id)
                return JSONResponse(content={"ok": True, "items": [r.to_dict() for r in reminders]})
            except Exception as e:
                return JSONResponse(status_code=500, content={"ok": False, "error": str(e)})

        @app.get("/scc/task/{task_id}/continuation")
        async def scc_task_continuation(task_id: str, refresh: bool = False):
            try:
                from tools.scc.orchestrators.continuation_context import write_continuation_context

                if refresh:
                    try:
                        write_continuation_context(repo_root=repo_root, task_id=task_id)
                    except Exception:
                        pass

                p = (repo_root / "artifacts" / "scc_tasks" / str(task_id) / "continuation.md").resolve()
                if not p.exists():
                    return JSONResponse(status_code=404, content={"ok": False, "error": "continuation_not_found"})
                text = p.read_text(encoding="utf-8", errors="replace")
                return JSONResponse(content={"ok": True, "path": str(p), "content": text})
            except Exception as e:
                return JSONResponse(status_code=500, content={"ok": False, "error": str(e)})

        @app.get("/scc/task/{task_id}/subtasks")
        async def scc_task_subtasks(task_id: str, limit: int = 200):
            try:
                from tools.scc.orchestrators.subtask_pool import list_subtasks

                items = [r.__dict__ for r in list_subtasks(queue=task_queue, parent_task_id=task_id, limit=limit)]
                return JSONResponse(content={"ok": True, "items": items})
            except Exception as e:
                return JSONResponse(status_code=500, content={"ok": False, "error": str(e)})

        def _subtask_summaries_dir(task_id: str) -> Path:
            return (Path(repo_root).resolve() / "artifacts" / "scc_tasks" / str(task_id) / "evidence" / "subtask_summaries").resolve()

        @app.get("/scc/task/{task_id}/subtask_summaries")
        async def scc_task_subtask_summaries(task_id: str, limit: int = 200):
            """
            List subtask summary JSON files.
            """
            try:
                tid = str(task_id)
                d = _subtask_summaries_dir(tid)
                items = []
                if d.exists():
                    for p in sorted(d.glob("*.json"))[-max(1, min(2000, int(limit or 200))):]:
                        items.append({"name": p.name, "path": str(p)})
                return JSONResponse(content={"ok": True, "task_id": tid, "items": items})
            except Exception as e:
                return JSONResponse(status_code=500, content={"ok": False, "error": str(e)})

        @app.get("/scc/task/{task_id}/subtask_summaries/{name}")
        async def scc_task_subtask_summary_content(task_id: str, name: str):
            """
            Read a subtask summary JSON by filename (safe: only from evidence/subtask_summaries).
            """
            try:
                tid = str(task_id)
                n = str(name or "").strip()
                if not n or "/" in n or "\\" in n or ".." in n:
                    return JSONResponse(status_code=400, content={"ok": False, "error": "invalid_name"})
                p = (_subtask_summaries_dir(tid) / n).resolve()
                p.relative_to(_subtask_summaries_dir(tid))
                if not p.exists():
                    return JSONResponse(status_code=404, content={"ok": False, "error": "not_found"})
                text = p.read_text(encoding="utf-8", errors="replace")
                return JSONResponse(content={"ok": True, "task_id": tid, "name": n, "json_text": text})
            except Exception as e:
                return JSONResponse(status_code=500, content={"ok": False, "error": str(e)})

        @app.post("/scc/task/{task_id}/subtasks")
        async def scc_task_subtasks_create(task_id: str, payload: dict):
            try:
                from tools.scc.event_log import get_task_logger
                from tools.scc.orchestrators.subtask_pool import submit_subtask

                task_type = str(payload.get("task_type") or "general").strip().lower()
                sub_payload = payload.get("payload")
                if not isinstance(sub_payload, dict):
                    return JSONResponse(status_code=400, content={"ok": False, "error": "payload_object_required"})
                rec = submit_subtask(queue=task_queue, parent_task_id=task_id, task_type=task_type, payload=sub_payload)  # type: ignore[arg-type]
                get_task_logger(repo_root=repo_root, task_id=task_id).emit(
                    "subtask_submitted",
                    task_id=task_id,
                    data={"child_task_id": rec.task_id, "task_type": task_type},
                )
                return JSONResponse(content={"ok": True, "child_task_id": rec.task_id, "status": rec.status})
            except Exception as e:
                return JSONResponse(status_code=400, content={"ok": False, "error": str(e)})

        @app.get("/scc/tasks")
        async def scc_tasks(limit: int = 50, status: str | None = None, q: str | None = None, after: str | None = None):
            try:
                lim = max(1, min(200, int(limit or 50)))
                want_status = str(status or "").strip().lower() or None
                query = str(q or "").strip().lower() or None
                after_id = str(after or "").strip() or None

                # Deterministic pagination by task_id order (directory names sorted desc).
                all_items = task_queue.list(limit=5000)
                out = []
                started = after_id is None
                for rec in all_items:
                    if not started:
                        if str(rec.task_id) == after_id:
                            started = True
                        continue
                    if want_status and str(rec.status).lower() != want_status:
                        continue
                    if query:
                        goal = ""
                        try:
                            req = rec.request if isinstance(rec.request, dict) else {}
                            t = req.get("task") if isinstance(req.get("task"), dict) else {}
                            goal = str(t.get("goal") or req.get("goal") or "")
                        except Exception:
                            goal = ""
                        hay = (str(rec.task_id) + " " + goal).lower()
                        if query not in hay:
                            continue
                    out.append(rec.__dict__)
                    if len(out) >= lim:
                        break

                next_cursor = out[-1]["task_id"] if out else None
                return JSONResponse(content={"ok": True, "items": out, "next_after": next_cursor})
            except Exception as e:
                return JSONResponse(status_code=500, content={"ok": False, "error": str(e)})

        @app.get("/scc/system/metrics")
        async def scc_system_metrics():
            """
            System resource metrics for deciding parallelism caps (CPU/memory/disk).
            """
            try:
                from tools.scc.automation.system_metrics import sample_system_metrics

                m = sample_system_metrics(disk_path=str(repo_root.anchor or "C:\\"))
                return JSONResponse(content={"ok": True, "metrics": m.to_dict()})
            except Exception as e:
                return JSONResponse(status_code=500, content={"ok": False, "error": str(e)})

        @app.get("/scc/system/runtime_config")
        async def scc_system_runtime_config():
            """
            Return effective SCC runtime config (file defaults + env overrides).
            """
            try:
                from tools.scc.runtime_config import load_runtime_config

                cfg = load_runtime_config(repo_root=repo_root)
                return JSONResponse(content={"ok": True, "runtime": cfg.to_dict()})
            except Exception as e:
                return JSONResponse(status_code=500, content={"ok": False, "error": str(e)})

        @app.get("/scc/system/dlq")
        async def scc_system_dlq(limit: int = 50):
            """
            List SCC DLQ items (autopilot or other system-level dead-letter queue).

            Files live at: artifacts/scc_state/dlq/*.json
            """
            try:
                from tools.scc.dlq_tool import list_dlq_items

                return JSONResponse(content=list_dlq_items(repo_root=repo_root, limit=int(limit)))
            except Exception as e:
                return JSONResponse(status_code=500, content={"ok": False, "error": str(e)})

        @app.get("/scc/system/dlq/peek")
        async def scc_system_dlq_peek(name: str):
            """
            Peek a DLQ item content by filename.
            """
            try:
                from tools.scc.dlq_tool import peek_dlq_item

                return JSONResponse(content=peek_dlq_item(repo_root=repo_root, name=str(name)))
            except Exception as e:
                return JSONResponse(status_code=500, content={"ok": False, "error": str(e)})

        @app.post("/scc/system/dlq/ack")
        async def scc_system_dlq_ack(request: Request):
            """
            Ack a DLQ item (delete it), optionally writing a small sidecar for traceability.

            Body:
              {"name": "...json", "reason": "..."}
            """
            try:
                from tools.scc.dlq_tool import ack_dlq_item

                body = await request.json()
                if not isinstance(body, dict):
                    body = {}
                name = str(body.get("name") or "").strip()
                reason = str(body.get("reason") or "").strip()
                if not name:
                    return JSONResponse(status_code=400, content={"ok": False, "error": "name_required"})
                out = ack_dlq_item(repo_root=repo_root, name=name, reason=reason)
                return JSONResponse(content=out)
            except Exception as e:
                return JSONResponse(status_code=500, content={"ok": False, "error": str(e)})

        @app.post("/scc/system/dlq/replay")
        async def scc_system_dlq_replay(request: Request):
            """
            Replay a DLQ item by re-queuing its stored task request.

            Body:
              {"name": "...json", "autostart": false, "keep_in_dlq": true}
            """
            try:
                from tools.scc.dlq_tool import replay_dlq_item

                body = await request.json()
                if not isinstance(body, dict):
                    body = {}
                name = str(body.get("name") or "").strip()
                if not name:
                    return JSONResponse(status_code=400, content={"ok": False, "error": "name_required"})
                autostart = body.get("autostart")
                keep_in_dlq = body.get("keep_in_dlq")
                out = replay_dlq_item(
                    repo_root=repo_root,
                    name=name,
                    autostart=(None if autostart is None else bool(autostart)),
                    keep_in_dlq=(True if keep_in_dlq is None else bool(keep_in_dlq)),
                )
                return JSONResponse(content=out)
            except Exception as e:
                return JSONResponse(status_code=500, content={"ok": False, "error": str(e)})

        @app.get("/scc/task/evidence_index")
        async def scc_task_evidence_index(task_id: str):
            """
            Build (if needed) and return task evidence index.json.
            """
            try:
                from tools.scc.evidence_index import build_task_evidence_index

                out = build_task_evidence_index(repo_root=repo_root, task_id=str(task_id))
                return JSONResponse(content={"ok": True, "index": out})
            except Exception as e:
                return JSONResponse(status_code=500, content={"ok": False, "error": str(e)})

        def _parent_inbox_path() -> Path:
            return (repo_root / "artifacts" / "scc_state" / "parent_inbox.jsonl").resolve()

        def _automation_daemon_state_path() -> Path:
            return (repo_root / "artifacts" / "scc_state" / "automation_daemon" / "daemon_state.json").resolve()

        def _automation_runs_root() -> Path:
            return (repo_root / "artifacts" / "scc_state" / "automation_daemon" / "runs").resolve()

        def _read_parent_inbox_items() -> list[dict]:
            inbox = _parent_inbox_path()
            if not inbox.exists():
                return []
            out: list[dict] = []
            for ln in inbox.read_text(encoding="utf-8", errors="replace").splitlines():
                try:
                    j = json.loads(ln)
                except Exception:
                    continue
                if not isinstance(j, dict):
                    continue
                pid = str(j.get("id") or "").strip()
                desc = str(j.get("description") or "").strip()
                if not pid or not desc:
                    continue
                out.append(
                    {
                        "id": pid,
                        "description": desc,
                        "submitted_utc": str(j.get("submitted_utc") or "").strip() or None,
                    }
                )
            return out

        def _build_parent_status_index() -> dict[str, dict]:
            """
            Scan automation_daemon/runs/* to build latest status per parent id.
            """
            runs_root = _automation_runs_root()
            if not runs_root.exists():
                return {}
            latest: dict[str, dict] = {}
            run_dirs = sorted([p for p in runs_root.glob("*") if p.is_dir()], key=lambda p: p.name)
            # Iterate in chronological order; overwrite to keep latest.
            for rd in run_dirs[-500:]:
                parents_path = (rd / "parents.json").resolve()
                if not parents_path.exists():
                    continue
                try:
                    parents_obj = json.loads(parents_path.read_text(encoding="utf-8", errors="replace") or "{}")
                except Exception:
                    parents_obj = {}
                items = parents_obj.get("parents") if isinstance(parents_obj, dict) else None
                if not isinstance(items, list):
                    continue

                resp_path = (rd / "response.json").resolve()
                resp_obj: dict | None = None
                if resp_path.exists():
                    try:
                        resp_obj = json.loads(resp_path.read_text(encoding="utf-8", errors="replace") or "{}")
                    except Exception:
                        resp_obj = {"_raw": "invalid_json"}

                for it in items:
                    if not isinstance(it, dict):
                        continue
                    pid = str(it.get("id") or "").strip()
                    if not pid:
                        continue
                    st = "running" if resp_obj is None else ("done" if bool(resp_obj.get("success")) and int(resp_obj.get("exit_code") or 1) == 0 else "failed")
                    latest[pid] = {
                        "id": pid,
                        "run_dir": str(rd),
                        "daemon_run_id": rd.name,
                        "status": st,
                        "response_file": str(resp_path) if resp_path.exists() else None,
                        "executor_run_id": str(resp_obj.get("run_id") or "") if isinstance(resp_obj, dict) else "",
                        "run_manifest_file": str(resp_obj.get("run_manifest_file") or "") if isinstance(resp_obj, dict) else "",
                        "exit_code": int(resp_obj.get("exit_code") or 1) if isinstance(resp_obj, dict) and resp_obj.get("exit_code") is not None else None,
                        "updated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(resp_path.stat().st_mtime)) if resp_path.exists() else None,
                    }
            return latest

        @app.post("/scc/parents/submit")
        async def scc_parents_submit(payload: dict):
            """
            Submit a parent task into SCC automation inbox (JSONL).
            The automation daemon consumes this inbox and executes parents in parallel batches.
            """
            try:
                pid = str(payload.get("id") or payload.get("task_id") or "").strip()
                desc = str(payload.get("description") or payload.get("goal") or "").strip()
                if not pid:
                    return JSONResponse(status_code=400, content={"ok": False, "error": "id_required"})
                if not desc:
                    return JSONResponse(status_code=400, content={"ok": False, "error": "description_required"})

                inbox = _parent_inbox_path()
                inbox.parent.mkdir(parents=True, exist_ok=True)
                obj = {
                    "id": pid,
                    "description": desc,
                    "submitted_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                }
                with open(inbox, "a", encoding="utf-8", errors="replace") as f:
                    f.write(json.dumps(obj, ensure_ascii=False) + "\n")
                return JSONResponse(content={"ok": True, "inbox": str(inbox), "item": obj})
            except Exception as e:
                return JSONResponse(status_code=500, content={"ok": False, "error": str(e)})

        @app.get("/scc/parents/daemon/state")
        async def scc_parents_daemon_state():
            """
            Read automation daemon state (best-effort).
            """
            try:
                p = _automation_daemon_state_path()
                if not p.exists():
                    return JSONResponse(content={"ok": True, "state": None})
                st = json.loads(p.read_text(encoding="utf-8", errors="replace") or "{}")
                return JSONResponse(content={"ok": True, "state": st})
            except Exception as e:
                return JSONResponse(status_code=500, content={"ok": False, "error": str(e)})

        @app.get("/scc/parents/status")
        async def scc_parents_status(limit: int = 200):
            """
            Aggregate parent task status from inbox + automation daemon runs.
            """
            try:
                lim = max(1, min(2000, int(limit or 200)))
                inbox_items = _read_parent_inbox_items()
                idx = _build_parent_status_index()

                out: list[dict] = []
                for item in inbox_items:
                    pid = str(item.get("id") or "").strip()
                    row = dict(item)
                    st = idx.get(pid)
                    if st:
                        row.update(st)
                    else:
                        row["status"] = "pending"
                        row["daemon_run_id"] = None
                        row["executor_run_id"] = None
                        row["run_manifest_file"] = None
                        row["response_file"] = None
                        row["exit_code"] = None
                    out.append(row)

                # newest-first by submitted_utc (fallback: keep file order)
                def _key(x: dict):
                    su = str(x.get("submitted_utc") or "")
                    return su

                out_sorted = sorted(out, key=_key, reverse=True)[:lim]
                counts = {"pending": 0, "running": 0, "done": 0, "failed": 0}
                for r in out_sorted:
                    s = str(r.get("status") or "pending")
                    if s in counts:
                        counts[s] += 1
                return JSONResponse(content={"ok": True, "counts": counts, "items": out_sorted})
            except Exception as e:
                return JSONResponse(status_code=500, content={"ok": False, "error": str(e)})

        @app.get("/scc/parents/inbox/tail")
        async def scc_parents_inbox_tail(cursor: str | None = None, max_bytes: int = 65536, max_lines: int = 200):
            """
            Cursor tail for parent inbox (Cursor-like scroll).
            cursor is a byte offset (int as string).
            """
            try:
                inbox = _parent_inbox_path()
                if not inbox.exists():
                    return JSONResponse(content={"ok": True, "cursor": 0, "lines": []})

                cur = 0
                try:
                    cur = int(str(cursor or "").strip() or "0")
                except Exception:
                    cur = 0
                cur = max(0, cur)
                mb = max(1024, min(1024 * 1024, int(max_bytes or 65536)))
                ml = max(1, min(2000, int(max_lines or 200)))

                with open(inbox, "rb") as f:
                    f.seek(cur)
                    data = f.read(mb)
                    new_cursor = f.tell()
                if not data:
                    return JSONResponse(content={"ok": True, "cursor": new_cursor, "lines": []})
                lines = data.splitlines()
                out_lines = []
                for b in lines[-ml:]:
                    try:
                        out_lines.append(b.decode("utf-8", errors="replace"))
                    except Exception:
                        out_lines.append(str(b))
                return JSONResponse(content={"ok": True, "cursor": new_cursor, "lines": out_lines})
            except Exception as e:
                return JSONResponse(status_code=500, content={"ok": False, "error": str(e)})

        @app.post("/scc/task/{task_id}/cancel")
        async def scc_task_cancel(task_id: str):
            try:
                rec = task_queue.cancel(task_id)
                return JSONResponse(content={"ok": True, "task_id": rec.task_id, "status": rec.status})
            except Exception as e:
                return JSONResponse(status_code=400, content={"ok": False, "error": str(e)})

        @app.post("/scc/worker/start")
        async def scc_worker_start():
            task_queue.start()
            return JSONResponse(content={"ok": True, "status": "started"})

        @app.post("/scc/worker/stop")
        async def scc_worker_stop():
            task_queue.stop()
            return JSONResponse(content={"ok": True, "status": "stopped"})

        @app.get("/scc/skills")
        async def scc_skills():
            try:
                skills_catalog.reload()
                items = [s.__dict__ for s in skills_catalog.list()]
                return JSONResponse(content={"ok": True, "items": items})
            except Exception as e:
                return JSONResponse(status_code=500, content={"ok": False, "error": str(e)})

        @app.get("/scc/skills/{name}")
        async def scc_skill_get(name: str):
            try:
                skills_catalog.reload()
                s = skills_catalog.get(name)
                if not s:
                    return JSONResponse(status_code=404, content={"ok": False, "error": "skill_not_found"})
                return JSONResponse(content={"ok": True, **s.__dict__})
            except Exception as e:
                return JSONResponse(status_code=500, content={"ok": False, "error": str(e)})

        @app.post("/scc/mentions/parse")
        async def scc_mentions_parse(payload: dict):
            try:
                from tools.scc.capabilities.mentions import parse_mentions

                text = str(payload.get("text") or "")
                res = parse_mentions(text, repo_root=repo_root)
                return JSONResponse(content={"ok": True, **res.to_dict()})
            except Exception as e:
                return JSONResponse(status_code=400, content={"ok": False, "error": str(e)})

        @app.post("/scc/permission/check_path")
        async def scc_permission_check_path(payload: dict):
            try:
                from tools.scc.capabilities.permission_floor import evaluate_write_path

                repo_path = str(payload.get("repo_path") or "").strip()
                action = str(payload.get("action") or "write").strip()
                target_path = str(payload.get("path") or "").strip()
                scope_allow = payload.get("scope_allow")
                if not repo_path:
                    return JSONResponse(status_code=400, content={"ok": False, "error": "repo_path_required"})
                decision = evaluate_write_path(
                    repo_path=Path(repo_path),
                    target_path=target_path,
                    action=action,
                    scope_allow=scope_allow if isinstance(scope_allow, list) else None,
                )
                return JSONResponse(content={"ok": True, **decision.to_dict()})
            except Exception as e:
                return JSONResponse(status_code=400, content={"ok": False, "error": str(e)})

        @app.post("/scc/permission/check_command")
        async def scc_permission_check_command(payload: dict):
            try:
                from tools.scc.capabilities.permission_floor import pdp_decide_command

                cmd = str(payload.get("cmd") or "")
                task_id = payload.get("task_id")
                task_id = str(task_id).strip() if task_id is not None else None
                ev_root = _task_evidence_dir(task_id) if task_id else Path(repo_root)
                decision = pdp_decide_command(cmd=cmd, task_id=task_id, evidence_root=ev_root, enqueue=False)
                return JSONResponse(content={"ok": True, **decision})
            except Exception as e:
                return JSONResponse(status_code=400, content={"ok": False, "error": str(e)})

        @app.get("/scc/permission/requests")
        async def scc_permission_requests(status: str = "pending", limit: int = 200):
            """
            List approval-required PDP requests.
            """
            try:
                from tools.scc.capabilities.permission_floor import pdp_list_requests

                return JSONResponse(content=pdp_list_requests(evidence_root=Path(repo_root), status=status, limit=int(limit or 200)))
            except Exception as e:
                return JSONResponse(status_code=500, content={"ok": False, "error": str(e)})

        @app.post("/scc/permission/requests/{request_id}/resolve")
        async def scc_permission_request_resolve(request_id: str, payload: dict):
            """
            Resolve a pending approval request (human-in-the-loop).
            """
            try:
                from tools.scc.capabilities.permission_floor import pdp_resolve_request

                verdict = str(payload.get("verdict") or "").strip().lower()
                if verdict not in {"approved", "denied"}:
                    return JSONResponse(status_code=400, content={"ok": False, "error": "verdict_must_be_approved_or_denied"})
                note = str(payload.get("note") or payload.get("reason") or "")
                out = pdp_resolve_request(evidence_root=Path(repo_root), request_id=str(request_id), verdict=verdict, note=note)
                code = 200 if bool(out.get("ok")) else 404
                return JSONResponse(status_code=code, content=out)
            except Exception as e:
                return JSONResponse(status_code=500, content={"ok": False, "error": str(e)})

        # SCC persistent chat store (long-running CLI/IDE sessions)
        try:
            from tools.scc.chat_store import SCCChatStore
            from tools.scc.event_tail import tail_jsonl_with_cursor

            chat_store = SCCChatStore(repo_root=repo_root)

            @app.post("/scc/chat/new")
            async def scc_chat_new(payload: dict):
                try:
                    title = str(payload.get("title") or "")
                    chat_id = payload.get("chat_id")
                    res = chat_store.create(chat_id=str(chat_id) if chat_id is not None else None, title=title)
                    return JSONResponse(content={"ok": True, **res})
                except Exception as e:
                    return JSONResponse(status_code=400, content={"ok": False, "error": str(e)})

            @app.get("/scc/chats")
            async def scc_chats(limit: int = 100):
                try:
                    items = chat_store.list_chats(limit=int(limit or 100))
                    return JSONResponse(content={"ok": True, "items": items})
                except Exception as e:
                    return JSONResponse(status_code=500, content={"ok": False, "error": str(e)})

            @app.post("/scc/chat/{chat_id}/append")
            async def scc_chat_append(chat_id: str, payload: dict):
                try:
                    role = str(payload.get("role") or "user")
                    content = str(payload.get("content") or "")
                    meta = payload.get("meta") if isinstance(payload.get("meta"), dict) else {}
                    res = chat_store.append(chat_id=chat_id, role=role, content=content, meta=meta)
                    # Mirror into the global memory ledger so secretary agents can
                    # summarize across tools without depending on chat_store internals.
                    try:
                        c = content.strip()
                        if c:
                            item = {
                                "ts_utc": datetime.now(timezone.utc).isoformat(),
                                "source": "scc_chat",
                                "role": role,
                                "kind": "message",
                                "content": c,
                                "meta": {"chat_id": chat_id, **(meta or {})},
                            }
                            path = _memory_ledger_path()
                            line = (json.dumps(item, ensure_ascii=False) + "\n").encode("utf-8", errors="replace")
                            with _memory_lock:
                                path.parent.mkdir(parents=True, exist_ok=True)
                                with path.open("ab") as f:
                                    f.write(line)
                    except Exception:
                        pass
                    return JSONResponse(content=res)
                except Exception as e:
                    return JSONResponse(status_code=400, content={"ok": False, "error": str(e)})

            @app.get("/scc/chat/{chat_id}/snapshot")
            async def scc_chat_snapshot(chat_id: str, tail: int = 50):
                try:
                    res = chat_store.snapshot(chat_id=chat_id, tail=int(tail or 50))
                    return JSONResponse(content=res)
                except Exception as e:
                    return JSONResponse(status_code=400, content={"ok": False, "error": str(e)})

            @app.post("/scc/chat/{chat_id}/summary")
            async def scc_chat_set_summary(chat_id: str, payload: dict):
                try:
                    summary = str(payload.get("summary") or "")
                    res = chat_store.set_summary(chat_id=chat_id, summary=summary)
                    return JSONResponse(content=res)
                except Exception as e:
                    return JSONResponse(status_code=400, content={"ok": False, "error": str(e)})

            @app.get("/scc/chat/{chat_id}/messages/tail")
            async def scc_chat_messages_tail(
                chat_id: str,
                cursor: str | None = None,
                max_bytes: int = 256000,
                max_lines: int = 2000,
            ):
                """
                Cursor-tail chat messages.jsonl for UI (Cursor-like scroll).
                """
                try:
                    cur: int | None
                    if cursor is None:
                        cur = None
                    else:
                        c = str(cursor).strip()
                        if not c:
                            cur = None
                        else:
                            try:
                                cur = int(c)
                            except Exception:
                                return JSONResponse(status_code=400, content={"ok": False, "error": "invalid_cursor"})

                    # Ensure chat exists
                    meta = chat_store.create(chat_id=chat_id)
                    msg_path = (Path(meta["dir"]).resolve() / "messages.jsonl").resolve()
                    res = tail_jsonl_with_cursor(path=msg_path, cursor=cur, max_bytes=max_bytes, max_lines=max_lines)
                    if not res.ok:
                        return JSONResponse(status_code=404, content={"ok": False, "error": res.error, "path": res.path})
                    return JSONResponse(content=res.to_dict())
                except Exception as e:
                    return JSONResponse(status_code=500, content={"ok": False, "error": str(e)})

            @app.post("/scc/chat/{chat_id}/context_pack")
            async def scc_chat_context_pack(chat_id: str, payload: dict):
                """
                Token-saving strategy layer (deterministic, no model call):
                - summary + last N messages + optional pins
                """
                try:
                    from tools.scc.capabilities.context_pack import build_context_pack
                    from tools.scc.capabilities.context_pins import PinRequestItem

                    tail = int(payload.get("tail") or 40)
                    pin_repo_path = payload.get("repo_path")
                    pin_items_in = payload.get("pin_items")
                    include_pin_content = bool(payload.get("include_pin_content", True))
                    max_chars_per_pin = int(payload.get("max_chars_per_pin") or 8000)
                    max_total_pin_chars = int(payload.get("max_total_pin_chars") or 50000)

                    pin_items = []
                    if isinstance(pin_items_in, list):
                        for it in pin_items_in[:200]:
                            if not isinstance(it, dict):
                                continue
                            pin_items.append(
                                PinRequestItem(
                                    path=str(it.get("path") or ""),
                                    kind=str(it.get("kind") or "file"),
                                    start_line=it.get("start_line"),
                                    end_line=it.get("end_line"),
                                    label=str(it.get("label") or ""),
                                )
                            )

                    pack = build_context_pack(
                        repo_root=repo_root,
                        chat_id=chat_id,
                        tail=tail,
                        pin_repo_path=Path(str(pin_repo_path)).resolve() if pin_repo_path else None,
                        pin_items=pin_items if pin_items else None,
                        include_pin_content=include_pin_content,
                        max_chars_per_pin=max_chars_per_pin,
                        max_total_pin_chars=max_total_pin_chars,
                    )
                    return JSONResponse(content=pack.to_dict())
                except Exception as e:
                    return JSONResponse(status_code=400, content={"ok": False, "error": str(e)})

        except Exception:
            chat_store = None

        @app.post("/scc/pins/build")
        async def scc_pins_build(payload: dict):
            """
            Build deterministic "Pins" for IDE context (Cursor-like).
            Input:
              - repo_path
              - items: [{path, kind=file|range, start_line?, end_line?, label?}]
            Output:
              - pins[] with optional content snippets
            """
            try:
                from tools.scc.capabilities.context_pins import PinRequestItem, build_pins

                repo_path = str(payload.get("repo_path") or "").strip()
                if not repo_path:
                    return JSONResponse(status_code=400, content={"ok": False, "error": "repo_path_required"})
                items_in = payload.get("items")
                if not isinstance(items_in, list):
                    return JSONResponse(status_code=400, content={"ok": False, "error": "items_list_required"})

                items = []
                for it in items_in[:200]:
                    if not isinstance(it, dict):
                        continue
                    items.append(
                        PinRequestItem(
                            path=str(it.get("path") or ""),
                            kind=str(it.get("kind") or "file"),
                            start_line=it.get("start_line"),
                            end_line=it.get("end_line"),
                            label=str(it.get("label") or ""),
                        )
                    )

                include_content = bool(payload.get("include_content", True))
                max_chars_per_item = int(payload.get("max_chars_per_item") or 8000)
                max_total_chars = int(payload.get("max_total_chars") or 50000)

                res = build_pins(
                    repo_path=Path(repo_path),
                    items=items,
                    include_content=include_content,
                    max_chars_per_item=max_chars_per_item,
                    max_total_chars=max_total_chars,
                )
                return JSONResponse(content=res.to_dict())
            except Exception as e:
                return JSONResponse(status_code=400, content={"ok": False, "error": str(e)})

        @app.post("/scc/patch/preview")
        async def scc_patch_preview(payload: dict):
            """
            Preview a unified diff patch:
            - extract affected files
            - compute add/del stats
            - evaluate path permission floor
            """
            try:
                from tools.scc.capabilities.patch_pipeline import preview_patch

                repo_path = str(payload.get("repo_path") or "").strip()
                patch_text = str(payload.get("patch_text") or "")
                scope_allow = payload.get("scope_allow")
                if not repo_path:
                    return JSONResponse(status_code=400, content={"ok": False, "error": "repo_path_required"})
                prev = preview_patch(
                    repo_path=Path(repo_path),
                    patch_text=patch_text,
                    scope_allow=scope_allow if isinstance(scope_allow, list) else None,
                )
                return JSONResponse(content={"ok": True, **prev.to_dict()})
            except Exception as e:
                return JSONResponse(status_code=400, content={"ok": False, "error": str(e)})

        @app.get("/scc/patch/config")
        async def scc_patch_config():
            """
            Patch pipeline feature flags (for IDE clients).
            """
            try:
                from tools.scc.capabilities.patch_pipeline import patch_apply_enabled

                return JSONResponse(content={"ok": True, "patch_apply_enabled": bool(patch_apply_enabled())})
            except Exception as e:
                return JSONResponse(status_code=500, content={"ok": False, "error": str(e)})

        @app.post("/scc/patch/apply")
        async def scc_patch_apply(payload: dict):
            """
            Apply a unified diff patch using git apply (gated by SCC_PATCH_APPLY_ENABLED).
            """
            try:
                from tools.scc.capabilities.patch_pipeline import apply_patch_text
                from tools.scc.event_log import get_task_logger

                repo_path = str(payload.get("repo_path") or "").strip()
                patch_text = str(payload.get("patch_text") or "")
                scope_allow = payload.get("scope_allow")
                check_only = bool(payload.get("check_only"))
                reverse = bool(payload.get("reverse"))
                reject = bool(payload.get("reject"))
                task_id = str(payload.get("task_id") or "").strip() or None
                if not repo_path:
                    return JSONResponse(status_code=400, content={"ok": False, "error": "repo_path_required"})

                try:
                    if task_id:
                        get_task_logger(repo_root=repo_root, task_id=task_id).emit(
                            "patch_apply_requested",
                            task_id=task_id,
                            data={
                                "endpoint": "/scc/patch/apply",
                                "check_only": check_only,
                                "reverse": reverse,
                                "reject": reject,
                            },
                        )
                except Exception:
                    pass

                res = apply_patch_text(
                    repo_path=Path(repo_path),
                    patch_text=patch_text,
                    scope_allow=scope_allow if isinstance(scope_allow, list) else None,
                    check_only=check_only,
                    reverse=reverse,
                    reject=reject,
                    task_id=task_id,
                )

                if str(res.error or "") == "approval_required":
                    return JSONResponse(status_code=409, content={"ok": False, "error": "approval_required", **res.to_dict()})
                if str(res.error or "") == "pdp_denied":
                    return JSONResponse(status_code=403, content={"ok": False, "error": "pdp_denied", **res.to_dict()})

                # Optional: write evidence under task folder if provided (IDE-friendly).
                try:
                    if task_id:
                        ev_dir = (Path(repo_root).resolve() / "artifacts" / "scc_tasks" / task_id / "evidence").resolve()
                        ev_dir.mkdir(parents=True, exist_ok=True)
                        (ev_dir / "patch_apply.json").write_text(
                            json.dumps(res.to_dict(), ensure_ascii=False, indent=2),
                            encoding="utf-8",
                        )
                except Exception:
                    pass

                try:
                    if task_id:
                        get_task_logger(repo_root=repo_root, task_id=task_id).emit(
                            "patch_apply_finished",
                            task_id=task_id,
                            data={
                                "endpoint": "/scc/patch/apply",
                                "ok": bool(res.ok),
                                "applied": bool(res.applied),
                                "exit_code": int(res.exit_code),
                                "check_only": check_only,
                                "reverse": reverse,
                            },
                        )
                except Exception:
                    pass

                return JSONResponse(content={"ok": True, **res.to_dict()})
            except Exception as e:
                return JSONResponse(status_code=400, content={"ok": False, "error": str(e)})

        def _task_evidence_patches_dir(task_id: str) -> Path:
            return (Path(repo_root).resolve() / "artifacts" / "scc_tasks" / str(task_id) / "evidence" / "patches").resolve()

        def _task_evidence_dir(task_id: str) -> Path:
            return (Path(repo_root).resolve() / "artifacts" / "scc_tasks" / str(task_id) / "evidence").resolve()

        def _task_patch_gate_dir(task_id: str) -> Path:
            return (_task_evidence_dir(task_id) / "patch_gate").resolve()

        def _sanitize_patch_name_for_dir(name: str) -> str:
            n = str(name or "").strip()
            n = n.replace("\\", "_").replace("/", "_").replace("..", "_")
            return (n or "patch")[:120]

        def _git_snapshot(repo_path: Path) -> dict:
            repo_path = Path(repo_path).resolve()
            head = ""
            status = ""
            try:
                p = subprocess.run(["git", "rev-parse", "HEAD"], cwd=str(repo_path), capture_output=True, text=True)
                head = (p.stdout or "").strip()
            except Exception:
                head = ""
            try:
                p = subprocess.run(["git", "status", "--porcelain"], cwd=str(repo_path), capture_output=True, text=True)
                status = p.stdout or ""
            except Exception:
                status = ""
            return {
                "ok": True,
                "repo_path": str(repo_path),
                "head": head,
                "dirty": bool(status.strip()),
                "status_porcelain": status,
                "ts_utc": datetime.utcnow().isoformat() + "Z",
            }

        def _read_task_workspace(task_id: str) -> dict:
            """
            Best-effort: read artifacts/scc_tasks/<task_id>/task.json and return workspace dict.
            """
            tid = str(task_id)
            task_json = (Path(repo_root).resolve() / "artifacts" / "scc_tasks" / tid / "task.json").resolve()
            if not task_json.exists():
                return {}
            try:
                t = json.loads(task_json.read_text(encoding="utf-8"))
            except Exception:
                return {}
            if not isinstance(t, dict):
                return {}
            req = t.get("request") if isinstance(t.get("request"), dict) else {}
            w = req.get("workspace") if isinstance(req.get("workspace"), dict) else req
            return w if isinstance(w, dict) else {}

        def _write_patch_gate_status(task_id: str, payload: dict) -> dict:
            """
            Write patch gate state to artifacts/scc_tasks/<task_id>/evidence/patch_gate/status.json.
            Keeps a small rolling history for UI replay.
            """
            tid = str(task_id)
            pg_dir = _task_patch_gate_dir(tid)
            pg_dir.mkdir(parents=True, exist_ok=True)
            st_path = (pg_dir / "status.json").resolve()
            cur = {
                "ok": True,
                "task_id": tid,
                "updated_utc": datetime.utcnow().isoformat() + "Z",
                "current": None,
                "history": [],
            }
            try:
                if st_path.exists():
                    cur0 = json.loads(st_path.read_text(encoding="utf-8"))
                    if isinstance(cur0, dict):
                        cur = cur0
            except Exception:
                pass
            hist = cur.get("history") if isinstance(cur.get("history"), list) else []
            cur["updated_utc"] = datetime.utcnow().isoformat() + "Z"
            cur["current"] = payload
            try:
                hist.append(payload)
                cur["history"] = hist[-50:]
            except Exception:
                cur["history"] = hist[-50:]
            st_path.write_text(json.dumps(cur, ensure_ascii=False, indent=2), encoding="utf-8")
            return cur

        def _run_patch_gate_selftest(
            *,
            task_id: str,
            repo_path: Path,
            patch_name: str,
            test_cmds: list[str],
            timeout_s: float,
        ) -> dict:
            """
            Cursor-like selftest deliverables under evidence/patch_gate:
              - selftest.log
              - report.md
              - evidence/
            """
            from tools.scc.capabilities.permission_floor import pdp_decide_command
            from tools.scc.event_log import get_task_logger

            tid = str(task_id)
            repo_path = Path(repo_path).resolve()
            stamp = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
            safe = _sanitize_patch_name_for_dir(patch_name)
            out_dir = (_task_patch_gate_dir(tid) / f"{stamp}__selftest__{safe}").resolve()
            evidence_dir = (out_dir / "evidence").resolve()
            logs_dir = (out_dir / "logs").resolve()
            evidence_dir.mkdir(parents=True, exist_ok=True)
            logs_dir.mkdir(parents=True, exist_ok=True)

            task_logger = get_task_logger(repo_root=repo_root, task_id=tid)
            task_logger.emit(
                "patch_gate_selftest_started",
                task_id=tid,
                data={
                    "patch_name": patch_name,
                    "repo_path": str(repo_path),
                    "out_dir": str(out_dir),
                    "test_cmds": list(test_cmds),
                    "timeout_s": float(timeout_s or 0.0),
                },
            )

            def _run_shell(cmd: str) -> tuple[int, str, str, float]:
                start = time.time()
                if os.name == "nt":
                    argv = ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", cmd]
                    proc = subprocess.run(
                        argv,
                        cwd=str(repo_path),
                        capture_output=True,
                        text=True,
                        timeout=timeout_s if timeout_s > 0 else None,
                    )
                else:
                    proc = subprocess.run(
                        ["bash", "-lc", cmd],
                        cwd=str(repo_path),
                        capture_output=True,
                        text=True,
                        timeout=timeout_s if timeout_s > 0 else None,
                    )
                dur = max(0.0, time.time() - start)
                return int(proc.returncode), proc.stdout or "", proc.stderr or "", float(dur)

            steps = []
            decisions = []
            final_exit = 0
            for idx, cmd in enumerate(list(test_cmds or [])[:50], start=1):
                cmd = str(cmd or "").strip()
                if not cmd:
                    continue
                pdp = pdp_decide_command(cmd=cmd, task_id=tid, evidence_root=Path(repo_root))
                decisions.append({"idx": idx, **(pdp or {})})
                task_logger.emit("patch_gate_selftest_command_pdp", task_id=tid, data={"idx": idx, **(pdp or {})})

                if str(pdp.get("decision") or "") == "deny":
                    steps.append(
                        {"idx": idx, "cmd": cmd, "status": "blocked", "exit_code": 97, "duration_s": 0.0, "log": "", "pdp": pdp}
                    )
                    final_exit = 97
                    task_logger.emit("patch_gate_selftest_command_blocked", task_id=tid, data={"idx": idx, **(pdp or {})})
                    break

                if str(pdp.get("decision") or "") == "ask":
                    steps.append(
                        {
                            "idx": idx,
                            "cmd": cmd,
                            "status": "needs_approval",
                            "exit_code": 95,
                            "duration_s": 0.0,
                            "log": "",
                            "pdp": pdp,
                        }
                    )
                    final_exit = 95
                    task_logger.emit("patch_gate_selftest_command_needs_approval", task_id=tid, data={"idx": idx, **(pdp or {})})
                    break

                log_path = (logs_dir / f"{idx:03d}_test.log").resolve()
                try:
                    code, out, err, dur = _run_shell(cmd)
                except Exception as e:
                    code, out, err, dur = 98, "", f"{e}", 0.0
                log_path.write_text(out + ("\n\n== STDERR ==\n" + err if err else ""), encoding="utf-8", errors="replace")
                steps.append(
                    {
                        "idx": idx,
                        "cmd": cmd,
                        "status": "done" if code == 0 else "failed",
                        "exit_code": int(code),
                        "duration_s": float(dur),
                        "log": str(log_path),
                        "pdp": pdp,
                    }
                )
                if code != 0:
                    final_exit = int(code)
                    break

            if final_exit == 0:
                verdict = "PASS"
            elif final_exit == 95:
                verdict = "ASK"
            else:
                verdict = "FAIL"
            selftest_log = (out_dir / "selftest.log").resolve()
            report_md = (out_dir / "report.md").resolve()

            evidence_dir.joinpath("git_snapshot.json").write_text(
                json.dumps(_git_snapshot(repo_path), ensure_ascii=False, indent=2), encoding="utf-8"
            )
            evidence_dir.joinpath("command_floor.json").write_text(
                json.dumps({"decisions": decisions}, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            evidence_dir.joinpath("steps.json").write_text(
                json.dumps({"steps": steps, "exit_code": final_exit}, ensure_ascii=False, indent=2), encoding="utf-8"
            )

            with open(selftest_log, "w", encoding="utf-8", errors="replace") as f:
                f.write("SCC PATCH-GATE SELFTEST LOG\n")
                f.write(f"ts_utc={datetime.utcnow().isoformat()}Z\n")
                f.write(f"task_id={tid}\n")
                f.write(f"patch={patch_name}\n")
                f.write(f"repo_path={repo_path}\n")
                f.write(f"steps={len(steps)}\n")
                for s in steps:
                    f.write(
                        f"STEP idx={s['idx']} exit_code={s['exit_code']} duration_s={s['duration_s']:.3f} cmd={s['cmd']}\n"
                    )
                f.write(f"EXIT_CODE={final_exit}\n")

            with open(report_md, "w", encoding="utf-8", errors="replace") as f:
                f.write("# SCC Patch Gate Report\n\n")
                f.write(f"- ts_utc: `{datetime.utcnow().isoformat()}Z`\n")
                f.write(f"- task_id: `{tid}`\n")
                f.write(f"- patch: `{patch_name}`\n")
                f.write(f"- repo_path: `{repo_path}`\n")
                f.write(f"- verdict: `{verdict}`\n")
                f.write(f"- exit_code: `{final_exit}`\n\n")
                f.write("## Test Commands\n")
                if not test_cmds:
                    f.write("(no test_cmds)\n")
                else:
                    for c in test_cmds:
                        f.write(f"- `{c}`\n")
                f.write("\n## Steps\n")
                if not steps:
                    f.write("(no steps)\n")
                else:
                    for s in steps:
                        f.write(
                            f"- idx={s['idx']} exit_code={s['exit_code']} duration_s={s['duration_s']:.3f} log=`{s['log']}`\n"
                        )
                f.write("\n## Evidence\n")
                f.write("- `evidence/git_snapshot.json`\n")
                f.write("- `evidence/command_floor.json`\n")
                f.write("- `evidence/steps.json`\n")

            out = {
                "ok": verdict == "PASS",
                "verdict": verdict,
                "exit_code": int(final_exit),
                "out_dir": str(out_dir),
                "selftest_log": str(selftest_log),
                "report_md": str(report_md),
                "evidence_dir": str(evidence_dir),
                "logs_dir": str(logs_dir),
                "steps": steps,
            }
            task_logger.emit("patch_gate_selftest_finished", task_id=tid, data=out)
            return out

        @app.get("/scc/task/{task_id}/patches")
        async def scc_task_patches(task_id: str):
            """
            List patch files under artifacts/scc_tasks/<task_id>/evidence/patches/*.diff
            """
            try:
                from tools.scc.event_log import get_task_logger

                tid = str(task_id)
                pdir = _task_evidence_patches_dir(tid)
                items = []
                if pdir.exists():
                    for p in sorted(pdir.glob("*.diff"))[-200:]:
                        items.append({"name": p.name, "path": str(p)})
                try:
                    get_task_logger(repo_root=repo_root, task_id=tid).emit("patches_listed", task_id=tid, data={"count": len(items)})
                except Exception:
                    pass
                return JSONResponse(content={"ok": True, "task_id": tid, "items": items})
            except Exception as e:
                return JSONResponse(status_code=400, content={"ok": False, "error": str(e)})

        @app.get("/scc/task/{task_id}/patches/index")
        async def scc_task_patches_index(task_id: str):
            """
            Read (or build) patches index.json under evidence/patches.
            """
            try:
                from tools.scc.event_log import get_task_logger

                tid = str(task_id)
                pdir = _task_evidence_patches_dir(tid)
                idx_path = (pdir / "index.json").resolve()
                if idx_path.exists():
                    try:
                        get_task_logger(repo_root=repo_root, task_id=tid).emit("patch_index_read", task_id=tid, data={"source": "index.json"})
                    except Exception:
                        pass
                    return JSONResponse(content={"ok": True, "task_id": tid, "index": json.loads(idx_path.read_text(encoding="utf-8"))})

                # Build a minimal index without previews (safe, fast)
                items = []
                if pdir.exists():
                    for p in sorted(pdir.glob("*.diff"))[-200:]:
                        items.append({"name": p.name, "path": str(p), "preview": None})
                idx = {"ok": True, "task_id": tid, "updated_utc": datetime.utcnow().isoformat() + "Z", "items": items}
                pdir.mkdir(parents=True, exist_ok=True)
                idx_path.write_text(json.dumps(idx, ensure_ascii=False, indent=2), encoding="utf-8")
                try:
                    get_task_logger(repo_root=repo_root, task_id=tid).emit("patch_index_built", task_id=tid, data={"count": len(items)})
                except Exception:
                    pass
                return JSONResponse(content={"ok": True, "task_id": tid, "index": idx})
            except Exception as e:
                return JSONResponse(status_code=500, content={"ok": False, "error": str(e)})

        @app.get("/scc/task/{task_id}/patches/{name}")
        async def scc_task_patch_content(task_id: str, name: str):
            """
            Read patch content by filename (safe: only from evidence/patches).
            """
            try:
                from tools.scc.event_log import get_task_logger

                tid = str(task_id)
                n = str(name or "").strip()
                if not n or "/" in n or "\\" in n or ".." in n:
                    return JSONResponse(status_code=400, content={"ok": False, "error": "invalid_name"})
                p = (_task_evidence_patches_dir(tid) / n).resolve()
                # Ensure it's under expected dir
                p.relative_to(_task_evidence_patches_dir(tid))
                if not p.exists():
                    return JSONResponse(status_code=404, content={"ok": False, "error": "not_found"})
                text = p.read_text(encoding="utf-8", errors="replace")
                try:
                    get_task_logger(repo_root=repo_root, task_id=tid).emit(
                        "patch_read",
                        task_id=tid,
                        data={"name": n, "bytes": len(text.encode("utf-8", errors="replace"))},
                    )
                except Exception:
                    pass
                return JSONResponse(content={"ok": True, "task_id": tid, "name": n, "patch_text": text})
            except Exception as e:
                return JSONResponse(status_code=400, content={"ok": False, "error": str(e)})

        @app.get("/scc/task/{task_id}/patch_gate/status")
        async def scc_task_patch_gate_status(task_id: str):
            """
            Read patch gate status for a task (apply/selftest lifecycle).
            """
            try:
                from tools.scc.event_log import get_task_logger
                from tools.scc.capabilities.patch_pipeline import patch_gate_sync_from_patches_dir

                tid = str(task_id)
                ev_dir = _task_evidence_dir(tid)
                # Always return a stable JSON structure, even when dirs/files don't exist yet.
                try:
                    status = patch_gate_sync_from_patches_dir(evidence_dir=ev_dir, task_id=tid)
                except Exception:
                    status = {"ok": True, "task_id": tid, "phase": "idle", "last_action": None, "updated_utc": datetime.utcnow().isoformat() + "Z", "items": []}
                try:
                    get_task_logger(repo_root=repo_root, task_id=tid).emit("patch_gate_status_read", task_id=tid, data={})
                except Exception:
                    pass
                return JSONResponse(content=status)
            except Exception as e:
                return JSONResponse(status_code=400, content={"ok": False, "error": str(e)})

        @app.post("/scc/task/{task_id}/patches/{name}/preview")
        async def scc_task_patch_preview(task_id: str, name: str, payload: dict):
            """
            Preview a task patch by name (reads from evidence/patches).
            """
            try:
                from tools.scc.capabilities.patch_pipeline import preview_patch
                from tools.scc.capabilities.patch_pipeline import patch_gate_record_preview, patch_gate_sync_from_patches_dir
                from tools.scc.event_log import get_task_logger

                tid = str(task_id)
                n = str(name or "").strip()
                if not n or "/" in n or "\\" in n or ".." in n:
                    return JSONResponse(status_code=400, content={"ok": False, "error": "invalid_name"})
                patch_path = (_task_evidence_patches_dir(tid) / n).resolve()
                patch_path.relative_to(_task_evidence_patches_dir(tid))
                if not patch_path.exists():
                    return JSONResponse(status_code=404, content={"ok": False, "error": "not_found"})

                # Determine repo_path from task.json if available, fallback to payload.
                ws = _read_task_workspace(tid)
                repo_path = str(ws.get("repo_path") or "")
                if not repo_path:
                    repo_path = str(payload.get("repo_path") or "").strip()
                if not repo_path:
                    return JSONResponse(status_code=400, content={"ok": False, "error": "repo_path_required"})

                patch_text = patch_path.read_text(encoding="utf-8", errors="replace")
                scope_allow = payload.get("scope_allow")
                prev = preview_patch(
                    repo_path=Path(repo_path),
                    patch_text=patch_text,
                    scope_allow=scope_allow if isinstance(scope_allow, list) else None,
                )
                # Persist patch gate state + evidence.
                try:
                    ev_dir = _task_evidence_dir(tid)
                    patch_gate_sync_from_patches_dir(evidence_dir=ev_dir, task_id=tid)
                    gate_status = patch_gate_record_preview(
                        evidence_dir=ev_dir,
                        task_id=tid,
                        name=n,
                        repo_path=str(repo_path),
                        patch_path=str(patch_path),
                        preview=prev,
                        scope_allow=scope_allow if isinstance(scope_allow, list) else None,
                    )
                except Exception:
                    gate_status = None
                try:
                    get_task_logger(repo_root=repo_root, task_id=tid).emit(
                        "patch_previewed",
                        task_id=tid,
                        data={"name": n, "ok": bool(prev.ok), "error": str(prev.error or "")},
                    )
                except Exception:
                    pass
                return JSONResponse(content={"ok": True, **prev.to_dict(), "task_id": tid, "name": n, "patch_gate_status": gate_status})
            except Exception as e:
                return JSONResponse(status_code=400, content={"ok": False, "error": str(e)})

        @app.post("/scc/task/{task_id}/patches/{name}/apply")
        async def scc_task_patch_apply(task_id: str, name: str, payload: dict):
            """
            Apply/rollback a task patch by name (reads from evidence/patches).
            Apply is still gated by SCC_PATCH_APPLY_ENABLED.
            """
            try:
                from tools.scc.capabilities.patch_pipeline import apply_patch_text
                from tools.scc.capabilities.patch_pipeline import patch_gate_record_apply, patch_gate_record_selftest, patch_gate_sync_from_patches_dir
                from tools.scc.event_log import get_task_logger

                tid = str(task_id)
                n = str(name or "").strip()
                if not n or "/" in n or "\\" in n or ".." in n:
                    return JSONResponse(status_code=400, content={"ok": False, "error": "invalid_name"})
                patch_path = (_task_evidence_patches_dir(tid) / n).resolve()
                patch_path.relative_to(_task_evidence_patches_dir(tid))
                if not patch_path.exists():
                    return JSONResponse(status_code=404, content={"ok": False, "error": "not_found"})

                # Determine repo_path from task.json if available, fallback to payload.
                ws = _read_task_workspace(tid)
                repo_path = str(ws.get("repo_path") or "")
                if not repo_path:
                    repo_path = str(payload.get("repo_path") or "").strip()
                if not repo_path:
                    return JSONResponse(status_code=400, content={"ok": False, "error": "repo_path_required"})

                patch_text = patch_path.read_text(encoding="utf-8", errors="replace")
                scope_allow = payload.get("scope_allow")
                check_only = bool(payload.get("check_only"))
                reverse = bool(payload.get("reverse"))
                reject = bool(payload.get("reject"))

                task_logger = get_task_logger(repo_root=repo_root, task_id=tid)
                task_logger.emit(
                    "patch_gate_action_requested",
                    task_id=tid,
                    data={"name": n, "check_only": check_only, "reverse": reverse, "reject": reject},
                )

                pre = {}
                try:
                    pre = _git_snapshot(Path(repo_path))
                    pg_dir = _task_patch_gate_dir(tid)
                    pg_dir.mkdir(parents=True, exist_ok=True)
                    stamp = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
                    snap_path = (pg_dir / "snapshots" / f"{stamp}__before__{_sanitize_patch_name_for_dir(n)}.json").resolve()
                    snap_path.parent.mkdir(parents=True, exist_ok=True)
                    snap_path.write_text(json.dumps(pre, ensure_ascii=False, indent=2), encoding="utf-8")
                except Exception:
                    pre = {}

                res = apply_patch_text(
                    repo_path=Path(repo_path),
                    patch_text=patch_text,
                    scope_allow=scope_allow if isinstance(scope_allow, list) else None,
                    check_only=check_only,
                    reverse=reverse,
                    reject=reject,
                    task_id=tid,
                )

                if str(res.error or "") == "approval_required":
                    return JSONResponse(status_code=409, content={"ok": False, "error": "approval_required", **res.to_dict(), "task_id": tid, "name": n})
                if str(res.error or "") == "pdp_denied":
                    return JSONResponse(status_code=403, content={"ok": False, "error": "pdp_denied", **res.to_dict(), "task_id": tid, "name": n})

                # Always write evidence for this action under the parent task.
                patch_apply_evidence_path = None
                try:
                    ev_dir = (Path(repo_root).resolve() / "artifacts" / "scc_tasks" / tid / "evidence" / "patch_applies").resolve()
                    ev_dir.mkdir(parents=True, exist_ok=True)
                    stamp = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
                    action = "check" if check_only else ("rollback" if reverse else "apply")
                    out_path = (ev_dir / f"{stamp}__{action}__{n}.json").resolve()
                    out_path.write_text(json.dumps(res.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
                    patch_apply_evidence_path = str(out_path)
                except Exception:
                    pass

                selftest_out = None
                if (not check_only) and (not reverse) and bool(res.ok) and bool(res.applied):
                    try:
                        test_cmds = ws.get("test_cmds") if isinstance(ws.get("test_cmds"), list) else []
                        timeout_s = float(payload.get("selftest_timeout_s") or 0.0)
                        selftest_out = _run_patch_gate_selftest(
                            task_id=tid,
                            repo_path=Path(repo_path),
                            patch_name=n,
                            test_cmds=[str(x) for x in list(test_cmds or [])],
                            timeout_s=timeout_s,
                        )
                    except Exception as e:
                        selftest_out = {"ok": False, "verdict": "FAIL", "exit_code": 99, "error": str(e)}

                post = {}
                try:
                    post = _git_snapshot(Path(repo_path))
                except Exception:
                    post = {}

                action = "check" if check_only else ("rollback" if reverse else "apply")
                try:
                    ev_dir = _task_evidence_dir(tid)
                    patch_gate_sync_from_patches_dir(evidence_dir=ev_dir, task_id=tid)
                    status_obj = patch_gate_record_apply(
                        evidence_dir=ev_dir,
                        task_id=tid,
                        name=n,
                        action=action,
                        repo_path=str(repo_path),
                        patch_path=str(patch_path),
                        pre_git=pre,
                        post_git=post,
                        apply_result=res,
                        selftest=selftest_out,
                        patch_apply_evidence_path=patch_apply_evidence_path,
                    )
                    if isinstance(selftest_out, dict):
                        try:
                            status_obj = patch_gate_record_selftest(
                                evidence_dir=ev_dir,
                                task_id=tid,
                                name=n,
                                result=selftest_out,
                                out_dir=str(selftest_out.get("out_dir") or ""),
                            )
                        except Exception:
                            pass
                except Exception:
                    status_obj = None

                task_logger.emit(
                    "patch_gate_action_finished",
                    task_id=tid,
                    data={"name": n, "action": action, "ok": bool(res.ok), "applied": bool(res.applied), "selftest": selftest_out},
                )

                return JSONResponse(
                    content={
                        "ok": True,
                        **res.to_dict(),
                        "task_id": tid,
                        "name": n,
                        "selftest": selftest_out,
                        "patch_gate_status": status_obj,
                    }
                )
            except Exception as e:
                return JSONResponse(status_code=400, content={"ok": False, "error": str(e)})

        @app.post("/scc/task/{task_id}/patches/{name}/rollback")
        async def scc_task_patch_rollback(task_id: str, name: str, payload: dict):
            """
            Roll back (reverse-apply) a task patch by name.
            This is a thin alias over /apply with reverse=true for client compatibility.
            """
            p = dict(payload or {})
            p["reverse"] = True
            # Default to an actual rollback, not a check-only.
            if "check_only" not in p:
                p["check_only"] = False
            return await scc_task_patch_apply(task_id=task_id, name=name, payload=p)

        @app.post("/scc/task/{task_id}/patches/{name}/selftest")
        async def scc_task_patch_selftest(task_id: str, name: str, payload: dict):
            """
            Run patch gate selftest for a given patch (no apply; runs on current repo state).
            Writes evidence under evidence/patch_gate and updates patch gate status.
            """
            try:
                from tools.scc.capabilities.patch_pipeline import patch_gate_record_selftest, patch_gate_sync_from_patches_dir
                from tools.scc.event_log import get_task_logger

                tid = str(task_id)
                n = str(name or "").strip()
                if not n or "/" in n or "\\" in n or ".." in n:
                    return JSONResponse(status_code=400, content={"ok": False, "error": "invalid_name"})

                ws = _read_task_workspace(tid)
                repo_path = str(ws.get("repo_path") or "")
                if not repo_path:
                    repo_path = str(payload.get("repo_path") or "").strip()
                if not repo_path:
                    return JSONResponse(status_code=400, content={"ok": False, "error": "repo_path_required"})

                test_cmds = ws.get("test_cmds") if isinstance(ws.get("test_cmds"), list) else []
                timeout_s = float(payload.get("timeout_s") or payload.get("selftest_timeout_s") or 0.0)
                out = _run_patch_gate_selftest(
                    task_id=tid,
                    repo_path=Path(repo_path),
                    patch_name=n,
                    test_cmds=[str(x) for x in list(test_cmds or [])],
                    timeout_s=timeout_s,
                )

                ev_dir = _task_evidence_dir(tid)
                patch_gate_sync_from_patches_dir(evidence_dir=ev_dir, task_id=tid)
                status_obj = patch_gate_record_selftest(
                    evidence_dir=ev_dir,
                    task_id=tid,
                    name=n,
                    result=out,
                    out_dir=str(out.get("out_dir") or ""),
                )
                try:
                    get_task_logger(repo_root=repo_root, task_id=tid).emit(
                        "patch_gate_selftest_api_finished", task_id=tid, data={"name": n, "ok": bool(out.get("ok")), "verdict": str(out.get("verdict") or "")}
                    )
                except Exception:
                    pass
                return JSONResponse(content={"ok": True, "task_id": tid, "name": n, "selftest": out, "patch_gate_status": status_obj})
            except Exception as e:
                return JSONResponse(status_code=400, content={"ok": False, "error": str(e)})

        @app.post("/scc/task/{task_id}/patches/{name}/verdict")
        async def scc_task_patch_verdict(task_id: str, name: str, payload: dict):
            """
            Record a human/agent verdict for a patch gate item.
            Writes evidence under evidence/patch_gate and updates patch gate status.
            """
            try:
                from tools.scc.capabilities.patch_pipeline import patch_gate_set_verdict, patch_gate_sync_from_patches_dir
                from tools.scc.event_log import get_task_logger

                tid = str(task_id)
                n = str(name or "").strip()
                if not n or "/" in n or "\\" in n or ".." in n:
                    return JSONResponse(status_code=400, content={"ok": False, "error": "invalid_name"})
                verdict = str(payload.get("verdict") or "").strip()
                note = str(payload.get("note") or payload.get("reason") or "").strip()
                if not verdict:
                    return JSONResponse(status_code=400, content={"ok": False, "error": "verdict_required"})

                ev_dir = _task_evidence_dir(tid)
                patch_gate_sync_from_patches_dir(evidence_dir=ev_dir, task_id=tid)
                status_obj = patch_gate_set_verdict(evidence_dir=ev_dir, task_id=tid, name=n, verdict=verdict, note=note)
                try:
                    get_task_logger(repo_root=repo_root, task_id=tid).emit(
                        "patch_gate_verdict_set", task_id=tid, data={"name": n, "verdict": verdict, "note": note}
                    )
                except Exception:
                    pass
                return JSONResponse(content={"ok": True, "task_id": tid, "name": n, "verdict": verdict, "patch_gate_status": status_obj})
            except Exception as e:
                return JSONResponse(status_code=400, content={"ok": False, "error": str(e)})

    except Exception:
        # If SCC module is unavailable, keep the core server running.
        pass

    # ATA 鈫?SCC ingestion (use ATA as the task inbox/outbox baseline).
    try:
        from tools.scc.ata_ingestion import ATAIngestionConfig, SCCATAIngestionWorker

        cfg = ATAIngestionConfig(
            enabled=(os.environ.get("SCC_ATA_INGEST_ENABLED", "true").strip().lower() != "false"),
            poll_interval_s=float(os.environ.get("SCC_ATA_POLL_INTERVAL_S", "1.0") or 1.0),
            to_agent=(os.environ.get("SCC_ATA_TO_AGENT", "scc") or "scc").strip(),
            from_agent=(os.environ.get("SCC_ATA_FROM_AGENT", "scc") or "scc").strip(),
            kind=(os.environ.get("SCC_ATA_KIND", "request") or "request").strip(),
            max_batch=int(os.environ.get("SCC_ATA_MAX_BATCH", "5") or 5),
        )

        # Reuse the queue instance if it exists; otherwise create a dedicated one.
        if "task_queue" not in locals():
            from tools.scc.task_queue import SCCTaskQueue

            task_queue = SCCTaskQueue(repo_root=repo_root)

        ata_ingestion = SCCATAIngestionWorker(task_queue=task_queue, repo_root=repo_root, config=cfg)

        @app.post("/scc/ata/start")
        async def scc_ata_start():
            ata_ingestion.start()
            return JSONResponse(content={"ok": True, "status": "started", "health": ata_ingestion.health()})

        @app.post("/scc/ata/stop")
        async def scc_ata_stop():
            ata_ingestion.stop()
            return JSONResponse(content={"ok": True, "status": "stopped", "health": ata_ingestion.health()})

        @app.get("/scc/ata/config")
        async def scc_ata_config():
            return JSONResponse(
                content={
                    "ok": True,
                    "enabled": cfg.enabled,
                    "poll_interval_s": cfg.poll_interval_s,
                    "to_agent": cfg.to_agent,
                    "from_agent": cfg.from_agent,
                    "kind": cfg.kind,
                    "max_batch": cfg.max_batch,
                }
            )

        @app.get("/scc/ata/health")
        async def scc_ata_health():
            return JSONResponse(content=ata_ingestion.health())

        @app.get("/scc/ata/state")
        async def scc_ata_state():
            try:
                return JSONResponse(content=ata_ingestion.engine.state())
            except Exception as exc:
                return JSONResponse(status_code=500, content={"ok": False, "error": str(exc)})

        @app.post("/scc/ata/poll_once")
        async def scc_ata_poll_once():
            try:
                return JSONResponse(content=ata_ingestion.poll_and_process_once())
            except Exception as e:
                return JSONResponse(status_code=500, content={"ok": False, "error": str(e)})

        @app.get("/scc/ata/events")
        async def scc_ata_events(limit: int = 200):
            try:
                p = (repo_root / "artifacts" / "scc_state" / "ata_ingestion_events.jsonl").resolve()
                if not p.exists():
                    return JSONResponse(status_code=404, content={"ok": False, "error": "events_not_found"})
                lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
                lim = max(1, min(5000, int(limit or 200)))
                return JSONResponse(content={"ok": True, "path": str(p), "lines": lines[-lim:]})
            except Exception as e:
                return JSONResponse(status_code=500, content={"ok": False, "error": str(e)})

        # Auto-start on server boot (best-effort).
        ata_ingestion.start()

        # Codex CLI quota & models锛堜粎鏌ヨ锛屼笉鎵ц浠诲姟锛?
        def _codex_cli_exe() -> str:
            env_exe = os.environ.get("CODEX_CLI_EXE", "").strip()
            if env_exe:
                return env_exe
            return "codex"

        def _find_script_exe() -> Optional[str]:
            candidates = [
                "script",  # if available in PATH (e.g., Git bash)
                r"C:\Program Files\Git\usr\bin\script.exe",
                r"C:\Program Files (x86)\Git\usr\bin\script.exe",
                r"C:\msys64\usr\bin\script.exe",
            ]
            for c in candidates:
                if shutil.which(c):
                    return shutil.which(c)
                if Path(c).exists():
                    return c
            return None

        def _tail_jsonl_rate_limits(path: Path) -> Optional[dict]:
            """
            Best-effort: parse the last token_count event from a Codex session jsonl.
            Expected record shape:
              {"type":"event_msg","payload":{"type":"token_count",...,"rate_limits":{...}}}
            """
            try:
                p = Path(path)
                if not p.exists():
                    return None
                # Read last ~1MB and scan backwards for a token_count record.
                max_bytes = 1_000_000
                size = p.stat().st_size
                start = max(0, size - max_bytes)
                with p.open("rb") as f:
                    f.seek(start)
                    chunk = f.read()
                text = chunk.decode("utf-8", errors="replace")
                lines = [ln for ln in text.splitlines() if ln.strip()]
                for ln in reversed(lines[-5000:]):
                    try:
                        obj = json.loads(ln)
                    except Exception:
                        continue
                    if not isinstance(obj, dict):
                        continue
                    if obj.get("type") != "event_msg":
                        continue
                    payload = obj.get("payload")
                    if not isinstance(payload, dict):
                        continue
                    if payload.get("type") != "token_count":
                        continue
                    rl = payload.get("rate_limits")
                    if isinstance(rl, dict):
                        return rl
                return None
            except Exception:
                return None

        def _read_codex_rate_limits_from_logs() -> Optional[dict]:
            """
            Read Codex CLI rate limits from ~/.codex/sessions/*/*.jsonl
            Works without TTY and matches what the VS Code extension shows.
            """
            try:
                home = Path(os.environ.get("USERPROFILE", "") or "").resolve()
                base = (home / ".codex" / "sessions").resolve()
                if not base.exists():
                    return None
                candidates: list[Path] = []
                for p in base.rglob("*.jsonl"):
                    try:
                        if p.is_file():
                            candidates.append(p)
                    except Exception:
                        continue
                if not candidates:
                    return None
                candidates.sort(key=lambda x: x.stat().st_mtime, reverse=True)
                for p in candidates[:20]:
                    rl = _tail_jsonl_rate_limits(p)
                    if rl:
                        return {"rate_limits": rl, "source_file": str(p)}
                return None
            except Exception:
                return None

        def _format_rate_limit_window(item: dict, *, now_ts: float) -> dict:
            used = float(item.get("used_percent") or 0.0)
            resets_at = int(item.get("resets_at") or 0)
            window_minutes = int(item.get("window_minutes") or 0)
            remaining = max(0.0, min(100.0, 100.0 - used))
            remaining_seconds = None
            remaining_days = None
            remaining_days_ceil = None
            if resets_at:
                try:
                    remaining_seconds = max(0, int(resets_at - now_ts))
                    remaining_days = remaining_seconds / 86400.0
                    # For UI "how many days left" we want a conservative ceiling (e.g. 0.2d -> 1d).
                    remaining_days_ceil = int((remaining_seconds + 86399) // 86400)
                except Exception:
                    remaining_seconds = None
                    remaining_days = None
                    remaining_days_ceil = None
            return {
                "used_percent": used,
                "remaining_percent": remaining,
                "window_minutes": window_minutes,
                "resets_at": resets_at,
                "resets_at_iso": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(resets_at)) if resets_at else None,
                "remaining_seconds": remaining_seconds,
                "remaining_days": remaining_days,
                "remaining_days_ceil": remaining_days_ceil,
            }

        def _run_codex(args: list[str]) -> tuple[int, str, str]:
            exe = _codex_cli_exe()
            base_cmd = [exe] + args
            try:
                p = subprocess.run(
                    base_cmd,
                    cwd=str(repo_root),
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=20,
                )
                if p.returncode == 0 or ("stdin is not a terminal" not in (p.stderr or "")):
                    return p.returncode, p.stdout or "", p.stderr or ""
                # retry with pseudo-TTY using script.exe if available
                script_exe = _find_script_exe()
                if script_exe:
                    wrapped = [script_exe, "-q", "-c", " ".join(base_cmd), "NUL"]
                    p2 = subprocess.run(
                        wrapped,
                        cwd=str(repo_root),
                        capture_output=True,
                        text=True,
                        encoding="utf-8",
                        errors="replace",
                        timeout=30,
                    )
                    return p2.returncode, p2.stdout or "", p2.stderr or p.stderr or ""
                return p.returncode, p.stdout or "", p.stderr or ""
            except FileNotFoundError:
                return 127, "", "codex cli not found"
            except subprocess.TimeoutExpired:
                return 124, "", "codex cli timeout"
            except Exception as exc:  # noqa: BLE001
                return 1, "", f"{type(exc).__name__}: {exc}"

        @app.get("/scc/codex/quota")
        async def scc_codex_quota():
            # In-memory + file cache to keep this endpoint fast (UI polls frequently).
            # Cache TTL is short; this is not an authoritative billing API, just UI guidance.
            nonlocal_vars = getattr(scc_codex_quota, "_cache", None)
            if not isinstance(nonlocal_vars, dict):
                nonlocal_vars = {"ts": 0.0, "payload": None}
                setattr(scc_codex_quota, "_cache", nonlocal_vars)
            now_ts = time.time()
            if (now_ts - float(nonlocal_vars.get("ts") or 0.0)) < 10.0 and nonlocal_vars.get("payload"):
                return JSONResponse(content=nonlocal_vars["payload"])

            cache_path = (repo_root / "artifacts" / "scc_state" / "codex_rate_limits_cache.json").resolve()
            try:
                if cache_path.exists():
                    age_s = now_ts - cache_path.stat().st_mtime
                    if age_s < 30.0:
                        cached = json.loads(cache_path.read_text(encoding="utf-8", errors="replace") or "{}")
                        payload = {"ok": True, "data": cached}
                        nonlocal_vars["ts"] = now_ts
                        nonlocal_vars["payload"] = payload
                        return JSONResponse(content=payload)
            except Exception:
                pass

            # Prefer reading local Codex session logs (no TTY required).
            log_info = _read_codex_rate_limits_from_logs()
            if log_info and isinstance(log_info.get("rate_limits"), dict):
                rl = log_info["rate_limits"]
                # Map to UI-friendly keys: 5h + 1w
                primary = _format_rate_limit_window(
                    (rl.get("primary") or {}) if isinstance(rl.get("primary"), dict) else {}, now_ts=now_ts
                )
                secondary = _format_rate_limit_window(
                    (rl.get("secondary") or {}) if isinstance(rl.get("secondary"), dict) else {}, now_ts=now_ts
                )
                out = {
                    "ok": True,
                    "data": {
                        "source": "codex_sessions_jsonl",
                        "source_file": log_info.get("source_file"),
                        "rate_limits": {"short": primary, "week": secondary},
                    },
                }
                try:
                    cache_path.parent.mkdir(parents=True, exist_ok=True)
                    cache_path.write_text(json.dumps(out["data"], ensure_ascii=False, indent=2), encoding="utf-8")
                except Exception:
                    pass
                nonlocal_vars["ts"] = now_ts
                nonlocal_vars["payload"] = out
                return JSONResponse(content=out)

            # Fallback: try codex CLI (may require TTY; best-effort).
            rc, out, err = _run_codex(["status"])
            data: dict[str, Any] = {"raw": out} if out.strip() else {}
            payload = {"ok": False, "error": err or "codex status failed", "data": data}
            nonlocal_vars["ts"] = now_ts
            nonlocal_vars["payload"] = payload
            # UI expects links to always open. Use 200 + structured error instead of 500.
            return JSONResponse(content=payload)

        @app.get("/scc/codex/models")
        async def scc_codex_models():
            # Prefer Codex local cache file (no TTY required).
            try:
                home = Path(os.environ.get("USERPROFILE", "") or "").resolve()
                cache = (home / ".codex" / "models_cache.json").resolve()
                if cache.exists():
                    raw = json.loads(cache.read_text(encoding="utf-8", errors="replace") or "{}")
                    models = raw.get("models") if isinstance(raw, dict) else None
                    items: list[dict] = []
                    if isinstance(models, list):
                        for m in models:
                            if not isinstance(m, dict):
                                continue
                            slug = str(m.get("slug") or m.get("display_name") or "").strip()
                            if not slug:
                                continue
                            items.append(
                                {
                                    "slug": slug,
                                    "display_name": str(m.get("display_name") or slug),
                                    "visibility": str(m.get("visibility") or ""),
                                    "supported_in_api": bool(m.get("supported_in_api")) if "supported_in_api" in m else None,
                                    "priority": m.get("priority"),
                                }
                            )
                    # Write router library (SCC-owned), used by orchestrators for model selection.
                    default_model = str(os.environ.get("SCC_CODEX_DEFAULT_MODEL", "") or "").strip() or "gpt-5.2"
                    allowed_env = str(os.environ.get("SCC_CODEX_ALLOWED_MODELS", "") or "").strip()
                    allowed = [s.strip() for s in allowed_env.split(",") if s.strip()] if allowed_env else [default_model]
                    router_obj = {
                        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                        "source": str(cache),
                        "routing": {"default": default_model, "allowed": allowed},
                        "models": items,
                    }
                    try:
                        router_path = (repo_root / "artifacts" / "scc_state" / "codex_model_routes.json").resolve()
                        router_path.parent.mkdir(parents=True, exist_ok=True)
                        router_path.write_text(json.dumps(router_obj, ensure_ascii=False, indent=2), encoding="utf-8")
                    except Exception:
                        pass
                    return JSONResponse(content={"ok": True, "data": router_obj})
            except Exception:
                pass

            # Fallback: try codex CLI (may require TTY; best-effort).
            rc, out, err = _run_codex(["models"])
            data: dict[str, Any] = {"raw": out} if out.strip() else {}
            # UI expects links to always open. Use 200 + structured error instead of 500.
            return JSONResponse(content={"ok": False, "error": err or "codex models failed", "data": data})

        def _restart_requests_dir() -> Path:
            return (repo_root / "artifacts" / "scc_state" / "restart_requests").resolve()

        def _watchdog_log_path() -> Path:
            # watchdog default: tools/unified_server/logs/watchdog.log
            return (repo_root / "tools" / "unified_server" / "logs" / "watchdog.log").resolve()

        def _watchdog_recently_active(now_ts: float, *, max_age_s: float = 20.0) -> bool:
            try:
                p = _watchdog_log_path()
                if not p.exists():
                    return False
                age = now_ts - p.stat().st_mtime
                return 0.0 <= age <= float(max_age_s)
            except Exception:
                return False

        def _schedule_process_exit(*, exit_code: int, delay_s: float) -> None:
            delay_s = float(delay_s or 0.0)
            if delay_s < 0.05:
                delay_s = 0.05
            if delay_s > 10.0:
                delay_s = 10.0

            def _do():
                try:
                    time.sleep(delay_s)
                finally:
                    os._exit(int(exit_code))

            threading.Thread(target=_do, daemon=True).start()

        @app.post("/scc/admin/restart")
        async def scc_admin_restart(request: Request, payload: dict | None = None):
            """
            Ask the unified server to exit, so an external watchdog can restart it.

            Security:
            - Always requires localhost client IP.
            - Additionally protected by X-Admin-Token when UNIFIED_SERVER_ADMIN_TOKEN is set (middleware).
            """
            try:
                host = (getattr(request.client, "host", "") or "").strip()
                if host not in ("127.0.0.1", "::1", "localhost", "testclient"):
                    return JSONResponse(status_code=403, content={"ok": False, "error": "forbidden_non_localhost"})

                payload = payload or {}
                reason = str(payload.get("reason") or "api_restart").strip()[:500]
                delay_s = float(payload.get("delay_s") or 0.5)
                exit_code = int(payload.get("exit_code") or 66)
                dry_run = bool(payload.get("dry_run")) or (str(os.environ.get("SCC_DISABLE_SELF_RESTART", "")).strip().lower() == "true")

                now_ts = time.time()
                req_dir = _restart_requests_dir()
                req_dir.mkdir(parents=True, exist_ok=True)
                stamp = time.strftime("%Y%m%d-%H%M%S", time.gmtime(now_ts))
                fn = f"{stamp}__pid{os.getpid()}__{exit_code}.json"
                req_path = (req_dir / fn).resolve()
                obj = {
                    "requested_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now_ts)),
                    "pid": os.getpid(),
                    "exit_code": exit_code,
                    "delay_s": delay_s,
                    "reason": reason,
                    "argv": sys.argv,
                    "watchdog_log": str(_watchdog_log_path()),
                    "watchdog_recent": _watchdog_recently_active(now_ts),
                }
                try:
                    req_path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
                except Exception:
                    pass

                if not dry_run:
                    _schedule_process_exit(exit_code=exit_code, delay_s=delay_s)
                return JSONResponse(
                    content={
                        "ok": True,
                        "scheduled": not dry_run,
                        "exit_code": exit_code,
                        "delay_s": delay_s,
                        "request_file": str(req_path),
                        "watchdog_recent": bool(obj["watchdog_recent"]),
                        "note": "If watchdog is running, it should restart the server automatically.",
                    }
                )
            except Exception as e:
                return JSONResponse(status_code=500, content={"ok": False, "error": str(e)})

        @app.get("/scc/admin/restart/requests")
        async def scc_admin_restart_requests(limit: int = 20):
            """
            List recent restart requests (server-side audit trail).
            """
            try:
                n = int(limit or 20)
                if n < 1:
                    n = 1
                if n > 200:
                    n = 200
                d = _restart_requests_dir()
                if not d.exists():
                    return JSONResponse(content={"ok": True, "items": []})
                items: list[dict] = []
                for p in sorted(d.glob("*.json"), reverse=True)[:n]:
                    try:
                        j = json.loads(p.read_text(encoding="utf-8", errors="replace") or "{}")
                    except Exception:
                        j = {}
                    items.append({"name": p.name, "path": str(p), "json": j if isinstance(j, dict) else {}})
                return JSONResponse(content={"ok": True, "items": items})
            except Exception as e:
                return JSONResponse(status_code=500, content={"ok": False, "error": str(e)})

    except Exception:
        pass

    # --- OID Generator (ULID + Postgres registry) ---
    @app.get("/scc/oid/health")
    async def scc_oid_health():
        try:
            from tools.scc.oid.pg_registry import get_oid_pg_dsn

            dsn = get_oid_pg_dsn()
            return {"ok": True, "configured": bool(dsn)}
        except Exception as e:
            return JSONResponse(status_code=500, content={"ok": False, "error": f"oid_health_failed: {e}"})

    @app.post("/scc/oid/new")
    async def scc_oid_new(request: Request):
        body = await request.json()
        if not isinstance(body, dict):
            return JSONResponse(status_code=400, content={"ok": False, "error": "invalid_body"})

        required = ["path", "kind", "layer", "primary_unit"]
        missing = [k for k in required if not str(body.get(k) or "").strip()]
        if missing:
            return JSONResponse(status_code=400, content={"ok": False, "error": "missing_fields", "missing": missing})

        try:
            from tools.scc.oid.pg_registry import get_oid_pg_dsn, issue_new

            dsn = get_oid_pg_dsn()
            oid, issued = issue_new(
                dsn=dsn,
                path=str(body.get("path")),
                kind=str(body.get("kind")),
                layer=str(body.get("layer")),
                primary_unit=str(body.get("primary_unit")),
                tags=list(body.get("tags") or []),
                stable_key=str(body.get("stable_key")).strip() if body.get("stable_key") else None,
                hint=str(body.get("hint")).strip() if body.get("hint") else None,
            )
            return {"ok": True, "oid": oid, "issued": bool(issued)}
        except Exception as e:
            return JSONResponse(status_code=500, content={"ok": False, "error": f"oid_new_failed: {e}"})

    @app.post("/scc/oid/migrate")
    async def scc_oid_migrate(request: Request):
        body = await request.json()
        if not isinstance(body, dict):
            return JSONResponse(status_code=400, content={"ok": False, "error": "invalid_body"})
        oid = str(body.get("oid") or "").strip()
        if not oid:
            return JSONResponse(status_code=400, content={"ok": False, "error": "missing_oid"})
        patch = body.get("patch")
        if not isinstance(patch, dict):
            return JSONResponse(status_code=400, content={"ok": False, "error": "invalid_patch"})
        reason = str(body.get("reason") or "").strip()
        actor = str(body.get("actor") or "").strip() or "agent"
        if not reason:
            return JSONResponse(status_code=400, content={"ok": False, "error": "missing_reason"})
        try:
            from tools.scc.oid.pg_registry import get_oid_pg_dsn, migrate

            dsn = get_oid_pg_dsn()
            migrated = migrate(dsn=dsn, oid=oid, patch=patch, reason=reason, actor=actor)
            return {"ok": True, "oid": oid, "migrated": bool(migrated)}
        except Exception as e:
            return JSONResponse(status_code=500, content={"ok": False, "error": f"oid_migrate_failed: {e}"})

    # Register service initialization task (defined inside create_app).
    services_initialized = False

    async def initialize_services():
        """Initialize all services."""
        nonlocal services_initialized
        if services_initialized:
            logger.info("Services already initialized, skipping")
            return
        logger.info("initialize_services function called")
        # 瀵煎叆鏈嶅姟闆嗘垚妯″潡
        logger.info("Importing register_all_services from tools.unified_server.services")
        from tools.unified_server.services import register_all_services
        
        # 娉ㄥ唽鎵€鏈夋湇鍔?
        logger.info("Starting service registration")
        register_all_services(registry, service_config, repo_root)
        logger.info("Registered all services")
        
        # 鎵撳嵃娉ㄥ唽鐨勬湇鍔?
        services = registry.get_all()
        logger.info(f"Registered services: {list(services.keys())}")
        
        # 鍒濆鍖栨墍鏈夋湇鍔?
        logger.info("Starting service initialization")
        await registry.initialize_all()
        logger.info("Initialized all services")
        
        # 鎵撳嵃鏈嶅姟鐘舵€?
        health_status = registry.get_health_status()
        logger.info(f"Service health status: {health_status}")
        
        # 鎸傝浇鏈嶅姟鍒板簲鐢?
        logger.info("Starting service mounting")
        for name, service in registry.get_all().items():
            if service.enabled and service.is_ready():
                app_path = getattr(service, "path", f"/{name}")
                service_app = service.get_app()
                logger.info(f"Mounting service {name} at {app_path}, app: {service_app}")
                app.mount(app_path, service_app)
                logger.info(f"Mounted service {name} at {app_path}")
                # Stable API aliases (so clients don't depend on internal service paths).
                # NOTE: /api is reserved for the legacy A2A Hub service mount.
                if name == "executor":
                    app.mount("/cp/executor", service_app)
                    logger.info("Mounted service executor at /cp/executor")
                if name == "files":
                    app.mount("/cp/files", service_app)
                    logger.info("Mounted service files at /cp/files")
            else:
                logger.info(f"Skipping service {name}, enabled: {service.enabled}, ready: {service.is_ready()}")
        

        # SPA fallback (register after service mounts so `/health/*`, `/opencode/*`, etc win).
        try:
            ui_dist = (repo_root / "tools" / "scc_ui" / "dist").resolve()
            if not ui_dist.exists():
                ui_dist = (repo_root / "scc-top" / "tools" / "scc_ui" / "dist").resolve()
            index = (ui_dist / "index.html").resolve()
            if index.is_file() and str(index).startswith(str(ui_dist)):
                reserved = (
                    "health",
                    "api",
                    "mcp",
                    "executor",
                    "files",
                    "opencode",
                    "clawdbot",
                    "scc",
                    "viewer",
                    "desktop",
                    "client-config",
                )

                async def _spa_fallback(path: str, request: Request):
                    p = str(path or "").lstrip("/")
                    for r in reserved:
                        if p == r or p.startswith(r + "/"):
                            return JSONResponse(status_code=404, content={"ok": False, "error": "not_found"})
                    return FileResponse(index)

                app.add_api_route("/{path:path}", _spa_fallback, methods=["GET"], include_in_schema=False)
                logger.info(f"Registered SPA fallback route (dist={ui_dist})")
        except Exception as e:
            logger.warning(f"Failed to register SPA fallback route: {e}")

        logger.info("Service initialization and mounting completed")
        services_initialized = True
    
    # 娉ㄥ唽鍚姩浠诲姟
    logger.info("Registering initialize_services to lifecycle")
    lifecycle.register_startup(initialize_services)
    
    # 娉ㄥ唽鏈嶅姟鍏抽棴浠诲姟
    @lifecycle.register_shutdown
    async def shutdown_services():
        """Shutdown all services."""
        await registry.shutdown_all()
    
    return app
