"""
Files service (artifacts access)

Purpose: support "server-first" separation:
- client submits tasks via HTTP
- server runs tools and writes evidence under repo_root/artifacts
- client lists/downloads artifacts via HTTP (no direct filesystem access)

Security:
- relies on unified_server AccessControlMiddleware when enabled (X-Admin-Token / IP allowlist)
- additionally restricts paths to repo_root/artifacts only
"""

import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from tools.unified_server.core.service_registry import Service, ServiceStatus

logger = logging.getLogger(__name__)


class FilesService(Service):
    def __init__(
        self,
        name: str,
        enabled: bool = True,
        repo_root: Optional[Path] = None,
        path: str = "/files",
    ):
        super().__init__(name, enabled, auto_allocate_port=False)
        self.path = path
        self.repo_root = repo_root or Path(__file__).parent.parent.parent.parent
        self.artifacts_root = (self.repo_root / "artifacts").resolve()
        self._app: Any = None

    def _resolve_under_artifacts(self, rel: str) -> Path:
        rel = (rel or "").replace("\\", "/").lstrip("/")
        p = (self.artifacts_root / rel).resolve()
        if not str(p).startswith(str(self.artifacts_root)):
            raise ValueError("path outside artifacts root")
        return p

    async def initialize(self) -> None:
        from fastapi import FastAPI, HTTPException, Query
        from fastapi.responses import FileResponse, JSONResponse

        app = FastAPI(title="Files Service", version="0.1.0")

        @app.get("/health")
        async def health():
            return {"ok": True, "root": str(self.artifacts_root)}

        @app.get("/list")
        async def list_files(
            prefix: str = Query(default="", description="path relative to artifacts/"),
            recursive: bool = Query(default=False),
            max_items: int = Query(default=2000, ge=1, le=20000),
        ):
            try:
                base = self._resolve_under_artifacts(prefix)
            except Exception as e:
                raise HTTPException(status_code=400, detail=str(e))

            if not base.exists():
                return JSONResponse(content={"ok": True, "items": [], "base": str(base)})

            items: List[Dict[str, Any]] = []

            def _add(path: Path):
                try:
                    st = path.stat()
                    relp = str(path.relative_to(self.artifacts_root)).replace("\\", "/")
                    items.append(
                        {
                            "path": relp,
                            "name": path.name,
                            "is_dir": path.is_dir(),
                            "size": int(st.st_size) if path.is_file() else 0,
                            "mtime": float(st.st_mtime),
                        }
                    )
                except Exception:
                    pass

            if base.is_file():
                _add(base)
            else:
                if recursive:
                    for p in base.rglob("*"):
                        if len(items) >= int(max_items):
                            break
                        if p.is_dir() or p.is_file():
                            _add(p)
                else:
                    for p in base.iterdir():
                        if len(items) >= int(max_items):
                            break
                        _add(p)

            return JSONResponse(content={"ok": True, "base": str(base), "items": items})

        @app.get("/download")
        async def download(
            path: str = Query(..., description="path relative to artifacts/"),
            inline: bool = Query(default=False, description="render inline instead of attachment"),
        ):
            try:
                p = self._resolve_under_artifacts(path)
            except Exception as e:
                raise HTTPException(status_code=400, detail=str(e))
            if not p.exists() or not p.is_file():
                raise HTTPException(status_code=404, detail="file not found")
            if inline:
                # FileResponse uses `attachment` when `filename` is set; override for in-app viewing.
                headers = {"Content-Disposition": f'inline; filename="{p.name}"'}
                return FileResponse(str(p), headers=headers)
            return FileResponse(str(p), filename=p.name)

        self._app = app

    def get_app(self):
        return self._app

    async def shutdown(self) -> None:
        self.status = ServiceStatus.SHUTTING_DOWN
        self._app = None
        self.status = ServiceStatus.SHUTDOWN
