"""
健康检查模块

提供健康检查、就绪检查和存活检查端点
"""

import logging
import os
import shutil
import time
from pathlib import Path
from typing import Dict, Any, List
from fastapi import APIRouter, status
from fastapi.responses import JSONResponse

from .service_registry import get_service_registry
from .port_allocator import get_port_allocator

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/health", tags=["health"])


def _repo_root() -> Path:
    rr = str(os.environ.get("REPO_ROOT", "") or "").strip()
    if rr:
        return Path(rr).resolve()
    # tools/unified_server/core/health.py -> <repo_root>
    return Path(__file__).resolve().parents[4]


def _get_env_int(name: str, default: int) -> int:
    raw = str(os.environ.get(name, "") or "").strip()
    if not raw:
        return default
    try:
        return int(raw, 10)
    except Exception:
        return default


def _writable_probe(dir_path: Path) -> Dict[str, Any]:
    dir_path.mkdir(parents=True, exist_ok=True)
    ts = int(time.time() * 1000)
    probe = dir_path / f".healthcheck_write_{os.getpid()}_{ts}.tmp"
    try:
        probe.write_bytes(b"ok")
        probe.unlink(missing_ok=True)  # py3.8+ in stdlib backport? (safe: try/except below)
        return {"path": str(dir_path), "ok": True}
    except TypeError:
        try:
            if probe.exists():
                probe.unlink()
        except OSError:
            pass
        return {"path": str(dir_path), "ok": True}
    except Exception as e:
        try:
            if probe.exists():
                probe.unlink()
        except OSError:
            pass
        return {"path": str(dir_path), "ok": False, "error": str(e)}


def _disk_status(path: Path) -> Dict[str, Any]:
    try:
        usage = shutil.disk_usage(str(path))
        return {"path": str(path), "total": usage.total, "used": usage.used, "free": usage.free}
    except Exception as e:
        return {"path": str(path), "error": str(e)}


@router.get("", status_code=status.HTTP_200_OK)
async def health_check() -> Dict[str, Any]:
    """基本健康检查 - 检查服务器是否运行"""
    return {
        "status": "healthy",
        "service": "unified_server"
    }


@router.get("/ready", status_code=status.HTTP_200_OK)
async def readiness_check() -> Dict[str, Any]:
    """就绪检查 - 检查所有服务是否就绪"""
    registry = get_service_registry()
    services_status = registry.get_health_status()

    repo_root = _repo_root()
    min_free_mb = _get_env_int("PERSISTENCE_MIN_FREE_MB", 1024)
    min_free_bytes = int(min_free_mb) * 1024 * 1024

    persistence_dirs: List[Path] = [
        (repo_root / "artifacts").resolve(),
        (repo_root / "data").resolve(),
        (repo_root / "logs").resolve(),
        (repo_root / "tools" / "unified_server" / "state").resolve(),
        (repo_root / "tools" / "unified_server" / "logs").resolve(),
        (repo_root / "tools" / "mcp_bus" / "_state").resolve(),
    ]

    persistence_checks = [_writable_probe(p) for p in persistence_dirs]
    all_persist_ok = all(bool(x.get("ok")) for x in persistence_checks)

    disk = _disk_status(repo_root)
    disk_ok = True
    if "free" in disk:
        disk_ok = int(disk["free"]) >= min_free_bytes
    
    # 检查所有启用的服务是否就绪
    all_ready = all(
        status_info["ready"] or not status_info["enabled"]
        for status_info in services_status.values()
    )
    
    if all_ready and all_persist_ok and disk_ok:
        return {
            "status": "ready",
            "services": services_status,
            "persistence": {
                "repo_root": str(repo_root),
                "checks": persistence_checks,
                "disk": disk,
                "min_free_mb": min_free_mb,
            },
        }
    else:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={
                "status": "not_ready",
                "services": services_status,
                "persistence": {
                    "repo_root": str(repo_root),
                    "checks": persistence_checks,
                    "disk": disk,
                    "min_free_mb": min_free_mb,
                },
            }
        )


@router.get("/live", status_code=status.HTTP_200_OK)
async def liveness_check() -> Dict[str, Any]:
    """存活检查 - 检查进程是否存活"""
    return {
        "status": "alive",
        "service": "unified_server"
    }


@router.get("/ports", status_code=status.HTTP_200_OK)
async def port_allocations() -> Dict[str, Any]:
    """获取端口分配信息"""
    registry = get_service_registry()
    allocator = get_port_allocator()
    
    return {
        "allocated_ports": registry.get_port_allocations(),
        "statistics": allocator.get_statistics(),
        "all_allocations": allocator.list_allocated_ports()
    }
