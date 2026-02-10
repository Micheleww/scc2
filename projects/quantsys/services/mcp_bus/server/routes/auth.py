"""
Authentication routes
"""
from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.responses import JSONResponse

from ..auth import auth_service

router = APIRouter()


@router.post("/api/auth/login")
async def login(request: Request):
    """用户登录"""
    try:
        body = await request.json()
        username = body.get("username")
        password = body.get("password")

        if not username or not password:
            raise HTTPException(status_code=400, detail="Username and password required")

        token = auth_service.authenticate(username, password)
        if not token:
            raise HTTPException(status_code=401, detail="Invalid credentials")

        # 记录审计日志
        user = auth_service.get_user_by_username(username)
        auth_service.log_audit(
            user_id=user.id if user else None,
            action="login",
            ip_address=request.client.host if request.client else None,
        )

        response = JSONResponse(
            {
                "success": True,
                "token": token,
                "user": {"id": user.id, "username": user.username, "role": user.role.value},
            }
        )

        # 设置cookie
        response.set_cookie(
            key="auth_token",
            value=token,
            max_age=86400,  # 24小时
            httponly=True,
            secure=False,  # 开发环境，生产环境应设为True
            samesite="lax",
        )

        return response
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail="Login failed")


@router.post("/api/auth/logout")
async def logout(request: Request, authorization: str | None = Header(None)):
    """用户登出"""
    token = None

    if authorization and authorization.startswith("Bearer "):
        token = authorization[7:]
    else:
        token = request.cookies.get("auth_token")

    if token:
        auth_service.logout(token)

        # 记录审计日志
        payload = auth_service.verify_token(token)
        if payload:
            auth_service.log_audit(
                user_id=payload.get("user_id"),
                action="logout",
                ip_address=request.client.host if request.client else None,
            )

    response = JSONResponse({"success": True})
    response.delete_cookie("auth_token")
    return response


@router.get("/api/auth/me")
async def get_current_user(request: Request, authorization: str | None = Header(None)):
    """获取当前用户信息"""
    token = None

    if authorization and authorization.startswith("Bearer "):
        token = authorization[7:]
    else:
        token = request.cookies.get("auth_token")

    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")

    payload = auth_service.verify_token(token)

    if not payload:
        raise HTTPException(status_code=401, detail="Invalid token")

    user = auth_service.get_user_by_id(payload["user_id"])
    if not user or not user.active:
        raise HTTPException(status_code=401, detail="User not found or inactive")

    return {
        "id": user.id,
        "username": user.username,
        "role": user.role.value,
        "last_login": user.last_login.isoformat() if user.last_login else None,
    }


@router.get("/api/auth/permissions")
async def get_permissions(request: Request, authorization: str | None = Header(None)):
    """获取用户权限"""
    token = None

    if authorization and authorization.startswith("Bearer "):
        token = authorization[7:]
    else:
        token = request.cookies.get("auth_token")

    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")

    payload = auth_service.verify_token(token)

    if not payload:
        raise HTTPException(status_code=401, detail="Invalid token")

    role = payload.get("role", "viewer")

    # 定义权限
    permissions = {
        "admin": [
            "read",
            "write",
            "delete",
            "manage_users",
            "manage_config",
            "view_logs",
            "view_monitoring",
            "manage_alerts",
        ],
        "operator": ["read", "write", "view_logs", "view_monitoring", "manage_alerts"],
        "viewer": ["read", "view_logs", "view_monitoring"],
    }

    return {"role": role, "permissions": permissions.get(role, [])}
