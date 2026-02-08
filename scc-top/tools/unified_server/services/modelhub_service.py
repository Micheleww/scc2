"""
ModelHub proxy service

Local interface for remote Apple compute "model library" (OpenAI-compatible direction).
This service is intentionally minimal:
- only enabled when MODELHUB_ENABLED=true
- access restricted by client IP allowlist + admin token header
- forwards to remote MODELHUB_BASE_URL with API key + HMAC signing (via tools/modelhub_client.py)
"""

import logging
import os
from pathlib import Path
from typing import Any, Dict, Optional

from tools.unified_server.core.service_registry import Service

logger = logging.getLogger(__name__)


class ModelHubService(Service):
    def __init__(
        self,
        name: str,
        enabled: bool = True,
        repo_root: Optional[Path] = None,
        path: str = "/modelhub",
    ):
        super().__init__(name, enabled, auto_allocate_port=False)
        self.path = path
        self.repo_root = repo_root or Path(__file__).parent.parent.parent.parent
        self._app: Any = None

        self.allowed_ips = [
            s.strip()
            for s in os.environ.get("MODELHUB_ALLOWED_IPS", "127.0.0.1,::1").split(",")
            if s.strip()
        ]
        # Prefer the unified server token if set, so the whole stack has one admin token.
        self.admin_token = (
            os.environ.get("UNIFIED_SERVER_ADMIN_TOKEN", "").strip()
            or os.environ.get("MODELHUB_ADMIN_TOKEN", "").strip()
        )

    async def initialize(self) -> None:
        from fastapi import FastAPI, HTTPException, Request
        from fastapi.responses import JSONResponse

        from tools.modelhub_client import ModelHubClient, load_modelhub_config_from_env

        cfg = load_modelhub_config_from_env()
        if not cfg.base_url:
            raise RuntimeError("MODELHUB_BASE_URL is required when MODELHUB_ENABLED=true")

        client = ModelHubClient(cfg)
        app = FastAPI(title="ModelHub Proxy", version="0.1.0")

        def _check_access(req: Request) -> None:
            ip = getattr(req.client, "host", "") if req.client else ""
            if self.allowed_ips and ip and ip not in self.allowed_ips:
                raise HTTPException(status_code=403, detail=f"forbidden ip: {ip}")
            if self.admin_token:
                tok = (req.headers.get("x-admin-token") or "").strip()
                if not tok:
                    tok = (req.headers.get("x-modelhub-admin-token") or "").strip()
                if not tok:
                    tok = (req.cookies.get("admin_token") or "").strip()
                if tok != self.admin_token:
                    raise HTTPException(status_code=401, detail="invalid admin token")

        @app.get("/health")
        async def health(req: Request):
            _check_access(req)
            try:
                data = client.health()
                return JSONResponse(content={"ok": True, "upstream": data})
            except Exception as e:
                return JSONResponse(content={"ok": False, "error": str(e)}, status_code=502)

        @app.get("/models")
        async def models(req: Request):
            _check_access(req)
            try:
                return JSONResponse(content=client.list_models())
            except Exception as e:
                raise HTTPException(status_code=502, detail=str(e))

        @app.post("/chat/completions")
        async def chat(req: Request, payload: Dict[str, Any]):
            _check_access(req)
            try:
                model = str(payload.get("model") or "")
                messages = payload.get("messages") or []
                if not model or not isinstance(messages, list):
                    raise HTTPException(status_code=400, detail="model and messages required")
                rest = {k: v for k, v in payload.items() if k not in {"model", "messages"}}
                out = client.chat_completions(model=model, messages=messages, **rest)
                return JSONResponse(content=out)
            except HTTPException:
                raise
            except Exception as e:
                raise HTTPException(status_code=502, detail=str(e))

        self._app = app
        self.status = "ready"

    def get_app(self):
        return self._app
