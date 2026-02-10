"""
AWS API Gateway
提供 HTTP API 接口供 AWS Relay 调用，接入 T1 协作闭环
"""

import logging
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Header, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, Field

from .aws_bridge import AWSBridge
from .aws_protocol_mapper import AWSProtocolMapper
from .integration_service import IntegrationService

logger = logging.getLogger(__name__)

# 安全方案
security = HTTPBearer()

router = APIRouter(prefix="/api/aws", tags=["aws"])


# ==================== 请求模型 ====================

class AWSTaskCreateRequest(BaseModel):
    """AWS 任务创建请求"""
    aws_task_id: Optional[str] = Field(None, description="AWS 生成的任务ID（可选）")
    aws_task_code: Optional[str] = Field(None, description="AWS 任务代码（可选）")
    task_type: str = Field(..., description="任务类型（必须在白名单中）")
    goal: Optional[str] = Field(None, description="任务目标")
    instructions: Optional[str] = Field(None, description="任务指令（兼容字段）")
    prompt: Optional[str] = Field(None, description="提示词（兼容字段）")
    area: Optional[str] = Field(None, description="任务区域（用于生成 task_id）")
    constraints: Optional[dict[str, Any]] = Field(None, description="约束条件")
    acceptance: Optional[list[str]] = Field(None, description="验收标准")
    expected: Optional[list[str]] = Field(None, description="期望结果（兼容字段）")
    created_by: Optional[str] = Field(None, description="创建者")
    user_id: Optional[str] = Field(None, description="用户ID（兼容字段）")
    priority: str = Field(default="normal", description="优先级")


class AWSLogAppendRequest(BaseModel):
    """AWS 日志追加请求"""
    aws_task_id: str = Field(..., description="AWS 任务ID")
    log_data: dict[str, Any] = Field(..., description="日志数据")


class AWSStatusUpdateRequest(BaseModel):
    """AWS 状态更新请求"""
    aws_task_id: str = Field(..., description="AWS 任务ID")
    status: str = Field(..., description="状态值")
    status_data: Optional[dict[str, Any]] = Field(None, description="状态数据")


# ==================== 鉴权 ====================

def verify_user_token(credentials: HTTPAuthorizationCredentials = Depends(security)) -> dict[str, Any]:
    """验证 Web 用户 token"""
    token = credentials.credentials
    # TODO: 实现 JWT 验证或 token 验证
    # 这里简化处理，实际应该验证 token 并返回用户信息
    return {"user_id": "aws_user", "role": "user"}


def verify_device_token(x_device_token: Optional[str] = Header(None)) -> Optional[dict[str, Any]]:
    """验证设备 token（可选，用于设备级鉴权）"""
    if not x_device_token:
        return None
    # TODO: 实现设备 token 验证
    return {"device_id": "device_001"}


# ==================== API 端点 ====================

@router.post("/task/create")
async def aws_create_task(
    request: AWSTaskCreateRequest,
    user_info: dict = Depends(verify_user_token),
    device_info: Optional[dict] = None,
):
    """
    AWS 任务创建接口
    
    将 AWS 任务创建请求转换为 T1 Event 并发布
    """
    import os
    from pathlib import Path
    
    repo_root = Path(os.getenv("REPO_ROOT", ".")).resolve()
    integration_service = IntegrationService(repo_root)
    aws_bridge = AWSBridge(repo_root, integration_service)
    
    # 验证任务负载
    is_valid, error_msg = AWSProtocolMapper.validate_aws_task_payload(request.model_dump())
    if not is_valid:
        raise HTTPException(status_code=400, detail=error_msg)
    
    # 处理任务创建
    result = aws_bridge.handle_aws_task_create(
        aws_task_id=request.aws_task_id or f"aws-{request.aws_task_code or 'task'}-{request.task_type}",
        aws_task_code=request.aws_task_code,
        aws_payload=request.model_dump(),
        user_token=user_info.get("user_id", "aws_user"),
        device_token=device_info.get("device_id") if device_info else None,
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


@router.post("/task/log")
async def aws_append_log(
    request: AWSLogAppendRequest,
    user_info: dict = Depends(verify_user_token),
):
    """AWS 日志追加接口"""
    import os
    from pathlib import Path
    
    repo_root = Path(os.getenv("REPO_ROOT", ".")).resolve()
    integration_service = IntegrationService(repo_root)
    aws_bridge = AWSBridge(repo_root, integration_service)
    
    result = aws_bridge.handle_aws_log_append(
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


@router.post("/task/status")
async def aws_update_status(
    request: AWSStatusUpdateRequest,
    user_info: dict = Depends(verify_user_token),
):
    """AWS 状态更新接口"""
    import os
    from pathlib import Path
    
    repo_root = Path(os.getenv("REPO_ROOT", ".")).resolve()
    integration_service = IntegrationService(repo_root)
    aws_bridge = AWSBridge(repo_root, integration_service)
    
    result = aws_bridge.handle_aws_status_update(
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


@router.get("/events/{task_id}")
async def aws_get_events(
    task_id: str,
    user_info: dict = Depends(verify_user_token),
    limit: int = 100,
):
    """
    获取任务事件流（供 Web Console 展示）
    
    返回 T1 事件转换为 AWS 格式的事件列表
    """
    import os
    from pathlib import Path
    
    repo_root = Path(os.getenv("REPO_ROOT", ".")).resolve()
    integration_service = IntegrationService(repo_root)
    aws_bridge = AWSBridge(repo_root, integration_service)
    
    # 获取 T1 task_id（如果有 AWS task_id 映射）
    t1_task_id = aws_bridge._get_t1_task_id_from_aws(task_id) or task_id
    
    # 从事件目录读取事件
    events_dir = repo_root / "docs" / "REPORT" / "ata" / "events"
    events = []
    
    if events_dir.exists():
        for event_file in sorted(events_dir.glob("*.json"), reverse=True)[:limit]:
            try:
                import json
                with open(event_file, encoding="utf-8") as f:
                    event_data = json.load(f)
                    if event_data.get("correlation_id") == t1_task_id:
                        # 转换为 AWS 格式
                        from .models import Event
                        t1_event = Event(**event_data)
                        aws_event = AWSProtocolMapper.convert_t1_event_to_aws(
                            t1_event,
                            aws_task_id=task_id if task_id != t1_task_id else None,
                        )
                        events.append(aws_event)
            except Exception as e:
                logger.error(f"Failed to read event file {event_file}: {e}")
    
    return {
        "success": True,
        "task_id": task_id,
        "t1_task_id": t1_task_id,
        "events": events,
        "count": len(events),
    }


@router.get("/task/{task_id}/status")
async def aws_get_task_status(
    task_id: str,
    user_info: dict = Depends(verify_user_token),
):
    """获取任务状态（聚合视图）"""
    import os
    from pathlib import Path
    
    repo_root = Path(os.getenv("REPO_ROOT", ".")).resolve()
    integration_service = IntegrationService(repo_root)
    aws_bridge = AWSBridge(repo_root, integration_service)
    
    # 获取 T1 task_id
    t1_task_id = aws_bridge._get_t1_task_id_from_aws(task_id) or task_id
    
    # 获取任务状态
    task_status = integration_service.orchestrator.get_task_status(t1_task_id, include_subtasks=True)
    
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
