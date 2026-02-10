"""
AWS Gateway - FastAPI 端点
提供 HTTP API 供 AWS Web Console 调用
"""

import logging
from pathlib import Path
from typing import Any, Optional

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from .aws_bridge import AWSBridge
from .aws_protocol_mapper import AWSProtocolMapper
from .integration_service import IntegrationService

logger = logging.getLogger(__name__)

# 创建 FastAPI 应用（可作为独立服务或集成到 main.py）
aws_gateway_app = FastAPI(title="AWS Unified Intake Gateway", version="0.1.0")

# CORS 配置（允许 AWS Web Console 访问）
aws_gateway_app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 生产环境应限制为特定域名
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 全局服务实例（在启动时初始化）
_aws_bridge: Optional[AWSBridge] = None
_integration_service: Optional[IntegrationService] = None


def init_aws_gateway(repo_root: Path) -> None:
    """初始化 AWS Gateway（在应用启动时调用）"""
    global _aws_bridge, _integration_service
    
    _integration_service = IntegrationService(repo_root)
    _aws_bridge = AWSBridge(repo_root, _integration_service)


# ==================== 请求模型 ====================

class AWSTaskCreateRequest(BaseModel):
    """AWS 任务创建请求"""
    aws_task_id: Optional[str] = None  # 如果 AWS 已生成
    aws_task_code: Optional[str] = None
    task_type: str
    goal: Optional[str] = None
    instructions: Optional[str] = None
    prompt: Optional[str] = None
    area: Optional[str] = None
    constraints: Optional[dict[str, Any]] = None
    acceptance: Optional[list[str]] = None
    expected: Optional[list[str]] = None
    created_by: Optional[str] = None
    user_id: Optional[str] = None
    priority: str = "normal"


class AWSLogAppendRequest(BaseModel):
    """AWS 日志追加请求"""
    aws_task_id: str
    log_data: dict[str, Any]


class AWSStatusUpdateRequest(BaseModel):
    """AWS 状态更新请求"""
    aws_task_id: str
    status: str
    status_data: Optional[dict[str, Any]] = None


# ==================== 鉴权 ====================

def verify_user_token(authorization: Optional[str] = Header(None)) -> dict[str, Any]:
    """验证 Web 用户 token"""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")
    
    token = authorization[7:]
    # 简化实现：实际应该验证 JWT token
    # 这里仅做格式检查，生产环境需要完整验证
    return {"user_id": "user_from_token", "token": token}


def verify_device_token(x_device_token: Optional[str] = Header(None)) -> Optional[dict[str, Any]]:
    """验证设备 token（可选）"""
    if not x_device_token:
        return None
    
    # 简化实现：实际应该验证设备 token
    return {"device_id": "device_from_token", "token": x_device_token}


# ==================== API 端点 ====================

@aws_gateway_app.post("/api/aws/task/create")
async def aws_create_task(
    request: AWSTaskCreateRequest,
    user: dict[str, Any] = Depends(verify_user_token),
    device: Optional[dict[str, Any]] = Depends(verify_device_token),
):
    """
    AWS 任务创建端点
    
    将 AWS 任务创建请求转换为 T1 Event 并发布
    """
    if not _aws_bridge:
        raise HTTPException(status_code=500, detail="AWS Bridge not initialized")
    
    # 转换为字典
    aws_payload = request.model_dump(exclude_none=True)
    
    # 处理任务创建
    result = _aws_bridge.handle_aws_task_create(
        aws_task_id=request.aws_task_id or f"aws-{request.aws_task_code or 'unknown'}",
        aws_task_code=request.aws_task_code,
        aws_payload=aws_payload,
        user_token=user.get("token", ""),
        device_token=device.get("token") if device else None,
    )
    
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error"))
    
    return {
        "success": True,
        "task_id": result["t1_task_id"],
        "aws_task_id": result["aws_task_id"],
        "task_code": result["task_code"],
        "event_id": result["event_id"],
    }


@aws_gateway_app.post("/api/aws/task/log")
async def aws_append_log(
    request: AWSLogAppendRequest,
    user: dict[str, Any] = Depends(verify_user_token),
):
    """
    AWS 日志追加端点
    
    将 AWS 日志转换为 T1 Event
    """
    if not _aws_bridge:
        raise HTTPException(status_code=500, detail="AWS Bridge not initialized")
    
    result = _aws_bridge.handle_aws_log_append(
        aws_task_id=request.aws_task_id,
        log_data=request.log_data,
    )
    
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error"))
    
    return {
        "success": True,
        "t1_task_id": result["t1_task_id"],
        "event_id": result["event_id"],
    }


@aws_gateway_app.post("/api/aws/task/status")
async def aws_update_status(
    request: AWSStatusUpdateRequest,
    user: dict[str, Any] = Depends(verify_user_token),
):
    """
    AWS 状态更新端点
    
    将 AWS 状态更新转换为 T1 Event
    """
    if not _aws_bridge:
        raise HTTPException(status_code=500, detail="AWS Bridge not initialized")
    
    result = _aws_bridge.handle_aws_status_update(
        aws_task_id=request.aws_task_id,
        status=request.status,
        status_data=request.status_data or {},
    )
    
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error"))
    
    return {
        "success": True,
        "t1_task_id": result["t1_task_id"],
        "event_id": result["event_id"],
    }


@aws_gateway_app.get("/api/aws/events/{task_id}")
async def aws_get_events(
    task_id: str,
    user: dict[str, Any] = Depends(verify_user_token),
    limit: int = 100,
):
    """
    获取任务事件流（供 Web Console 展示）
    
    返回 T1 事件（已转换为 AWS 格式）
    """
    if not _aws_bridge:
        raise HTTPException(status_code=500, detail="AWS Bridge not initialized")
    
    # 获取 T1 task_id（如果有 AWS task_id 映射）
    t1_task_id = _aws_bridge._get_t1_task_id_from_aws(task_id)
    if not t1_task_id:
        # 尝试作为 T1 task_id 使用
        t1_task_id = task_id
    
    # 从事件目录读取事件
    events_dir = _aws_bridge.repo_root / "docs" / "REPORT" / "ata" / "events"
    events = []
    
    if events_dir.exists():
        # 读取所有事件文件，过滤出相关任务的事件
        for event_file in sorted(events_dir.glob("*.json"), reverse=True)[:limit]:
            try:
                import json
                with open(event_file, encoding="utf-8") as f:
                    event_data = json.load(f)
                    if event_data.get("correlation_id") == t1_task_id:
                        # 转换为 AWS 格式
                        from .models import Event
                        event = Event(**event_data)
                        aws_event = AWSProtocolMapper.convert_t1_event_to_aws(
                            event,
                            aws_task_id=task_id if task_id != t1_task_id else None,
                        )
                        events.append(aws_event)
            except Exception:
                continue
    
    return {
        "success": True,
        "task_id": task_id,
        "t1_task_id": t1_task_id,
        "events": events,
        "count": len(events),
    }


@aws_gateway_app.get("/api/aws/task/{task_id}/status")
async def aws_get_task_status(
    task_id: str,
    user: dict[str, Any] = Depends(verify_user_token),
):
    """
    获取任务状态（供 Web Console 展示）
    
    从 T1 orchestrator 获取任务状态
    """
    if not _aws_bridge or not _integration_service:
        raise HTTPException(status_code=500, detail="Services not initialized")
    
    # 获取 T1 task_id
    t1_task_id = _aws_bridge._get_t1_task_id_from_aws(task_id)
    if not t1_task_id:
        t1_task_id = task_id
    
    # 从 orchestrator 获取状态
    task_status = _integration_service.orchestrator.get_task_status(t1_task_id, include_subtasks=True)
    
    if not task_status.get("success"):
        raise HTTPException(status_code=404, detail="Task not found")
    
    return {
        "success": True,
        "task_id": task_id,
        "t1_task_id": t1_task_id,
        "status": task_status.get("status"),
        "subtasks": task_status.get("subtasks", []),
        "progress": task_status.get("progress", {}),
    }


@aws_gateway_app.get("/api/aws/health")
async def aws_health():
    """健康检查端点"""
    return {
        "status": "ok",
        "service": "aws_gateway",
        "version": "0.1.0",
    }
