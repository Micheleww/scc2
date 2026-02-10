"""
Shared helper functions extracted from main.py
"""
import hmac
import os
from pathlib import Path
from typing import Any

from fastapi import HTTPException, Request
from fastapi.responses import FileResponse


def create_cached_file_response(file_path: Path, media_type: str = None) -> FileResponse:
    """创建带永久缓存头的文件响应（浏览器永久缓存直到手动清除）"""
    headers = {
        "Cache-Control": "public, max-age=31536000, immutable",  # 1年，不可变，永久缓存
        "X-Content-Type-Options": "nosniff",
    }
    return FileResponse(file_path, media_type=media_type, headers=headers)


def secrets_compare(a: str, b: str) -> bool:
    """constant-time-ish compare"""
    try:
        return hmac.compare_digest(a, b)
    except Exception:
        return a == b


def extract_admin_ctx(req: Request, auth_service=None) -> dict[str, Any]:
    """
    Determine whether the caller is ATA admin (fail-closed for privileged ops).
    Sources:
    - Header: X-ATA-ADMIN-TOKEN must match env ATA_ADMIN_TOKEN
    - Cookie: auth_token (JWT issued by /api/auth/login) with role=admin
    """
    # Import here to avoid circular imports
    if auth_service is None:
        from ..auth import auth_service as _auth_service
        auth_service = _auth_service

    is_admin = False
    reason = "not_authenticated"
    expected = os.getenv("ATA_ADMIN_TOKEN")
    provided = req.headers.get("x-ata-admin-token")
    if expected and provided and secrets_compare(expected, provided):
        return {"is_admin": True, "method": "header", "reason": "ok"}

    token = req.cookies.get("auth_token")
    if token:
        payload = auth_service.verify_token(token)
        if payload and payload.get("role") == "admin":
            return {"is_admin": True, "method": "cookie", "reason": "ok"}
        reason = "invalid_or_non_admin_jwt"
    return {"is_admin": is_admin, "method": None, "reason": reason}


def _format_agent_code(numeric_code: int | None) -> str:
    """Format numeric code as 2-digit string, e.g. 1 -> '01'."""
    if numeric_code is None:
        return "--"
    try:
        return f"{int(numeric_code):02d}"
    except Exception:
        return "--"


def _display_name(agent_id: str, numeric_code: int | None) -> str:
    """Display name for ATA communications: 名字#NN"""
    return f"{agent_id}#{_format_agent_code(numeric_code)}"


def get_repo_root() -> Path:
    """Get repository root path"""
    return Path(os.getenv("REPO_ROOT", "d:\\quantsys")).resolve()


def get_caller(request: Request) -> str:
    """Get caller identification from request"""
    user_agent = request.headers.get("user-agent", "unknown")
    if "ChatGPT" in user_agent:
        return "ChatGPT"
    elif "TRAE" in user_agent:
        return "TRAE"
    return user_agent[:50]


def _resolve_agent_ref(executor, agent_ref: str) -> str:
    """
    Resolve agent_ref to agent_id.
    agent_ref supports:
    - numeric code: "1".."100"
    - agent_id: e.g. "ATA系统"
    """
    if not executor.coordinator:
        raise HTTPException(status_code=503, detail="AgentCoordinator not available")

    ref = (agent_ref or "").strip()
    if not ref:
        raise HTTPException(status_code=400, detail="agent_ref is required")

    # numeric_code
    if ref.isdigit():
        code = int(ref)
        if not (1 <= code <= 100):
            raise HTTPException(status_code=400, detail="numeric_code must be in range 1..100")
        agent = executor.coordinator.registry.get_agent_by_code(code)
        if not agent:
            raise HTTPException(status_code=404, detail=f"Agent not found for numeric_code={code}")
        return agent.agent_id

    # agent_id
    agent = executor.coordinator.registry.get_agent(ref)
    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent not found: {ref}")
    return agent.agent_id
