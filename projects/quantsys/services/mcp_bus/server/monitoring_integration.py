#!/usr/bin/env python3
"""
监控服务深度集成模块
"""

import logging
from typing import Any

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from .monitoring import monitoring_service

logger = logging.getLogger(__name__)

# 创建监控服务API路由
monitoring_router = APIRouter(
    prefix="/api/monitoring",
    tags=["监控服务"],
    responses={404: {"description": "Not found"}},
)


@monitoring_router.get("/status")
async def get_monitoring_status() -> dict[str, Any]:
    """获取监控服务状态"""
    return {
        "running": monitoring_service.running,
        "check_interval": monitoring_service.check_interval,
        "metrics_history_size": monitoring_service.metrics_history_size
    }


@monitoring_router.get("/services")
async def get_services_status() -> dict[str, Any]:
    """获取所有服务状态"""
    return {
        "services": {
            name: {
                "name": service.name,
                "status": service.status.value,
                "response_time_ms": service.response_time_ms,
                "last_check": service.last_check.isoformat() if service.last_check else None,
                "error": service.error,
                "uptime_percent": service.uptime_percent
            }
            for name, service in monitoring_service.services.items()
        }
    }


@monitoring_router.get("/services/{service_name}")
async def get_service_status(service_name: str) -> dict[str, Any]:
    """获取单个服务状态"""
    service = monitoring_service.services.get(service_name)
    if not service:
        return JSONResponse(status_code=404, content={"error": f"服务 {service_name} 不存在"})
    
    return {
        "name": service.name,
        "status": service.status.value,
        "response_time_ms": service.response_time_ms,
        "last_check": service.last_check.isoformat() if service.last_check else None,
        "error": service.error,
        "uptime_percent": service.uptime_percent
    }


@monitoring_router.get("/metrics")
async def get_system_metrics() -> dict[str, Any]:
    """获取最新系统指标"""
    metrics = await monitoring_service.get_system_metrics()
    return {
        "timestamp": metrics.timestamp.isoformat(),
        "cpu_percent": metrics.cpu_percent,
        "memory_percent": metrics.memory_percent,
        "memory_used_mb": metrics.memory_used_mb,
        "memory_total_mb": metrics.memory_total_mb,
        "disk_percent": metrics.disk_percent,
        "disk_used_gb": metrics.disk_used_gb,
        "disk_total_gb": metrics.disk_total_gb,
        "network_sent_mb": metrics.network_sent_mb,
        "network_recv_mb": metrics.network_recv_mb
    }


@monitoring_router.get("/metrics/history")
async def get_metrics_history(limit: int = 100) -> dict[str, Any]:
    """获取系统指标历史"""
    history = monitoring_service.metrics_history[-limit:]
    return {
        "metrics": [
            {
                "timestamp": metrics.timestamp.isoformat(),
                "cpu_percent": metrics.cpu_percent,
                "memory_percent": metrics.memory_percent,
                "memory_used_mb": metrics.memory_used_mb,
                "memory_total_mb": metrics.memory_total_mb,
                "disk_percent": metrics.disk_percent,
                "disk_used_gb": metrics.disk_used_gb,
                "disk_total_gb": metrics.disk_total_gb,
                "network_sent_mb": metrics.network_sent_mb,
                "network_recv_mb": metrics.network_recv_mb
            }
            for metrics in history
        ],
        "total": len(history),
        "limit": limit
    }


@monitoring_router.get("/alerts")
async def get_alerts(resolved: bool = False) -> dict[str, Any]:
    """获取告警信息"""
    alerts = [
        alert for alert in monitoring_service.alerts 
        if alert.resolved == resolved
    ][-100:]  # 只返回最近100条
    
    return {
        "alerts": [
            {
                "id": alert.id,
                "level": alert.level,
                "service": alert.service,
                "message": alert.message,
                "timestamp": alert.timestamp.isoformat(),
                "resolved": alert.resolved
            }
            for alert in alerts
        ],
        "total": len(alerts)
    }


@monitoring_router.put("/alerts/{alert_id}/resolve")
async def resolve_alert(alert_id: str) -> dict[str, Any]:
    """解决告警"""
    await monitoring_service.resolve_alert(alert_id)
    return {"message": f"告警 {alert_id} 已解决"}


@monitoring_router.get("/summary")
async def get_status_summary() -> dict[str, Any]:
    """获取状态摘要"""
    return monitoring_service.get_status_summary()


@monitoring_router.post("/start")
async def start_monitoring() -> dict[str, Any]:
    """启动监控服务"""
    monitoring_service.start()
    return {"message": "监控服务已启动"}


@monitoring_router.post("/stop")
async def stop_monitoring() -> dict[str, Any]:
    """停止监控服务"""
    monitoring_service.stop()
    return {"message": "监控服务已停止"}


@monitoring_router.post("/check/services")
async def check_all_services() -> dict[str, Any]:
    """立即检查所有服务状态"""
    await monitoring_service.check_all_services()
    return {"message": "服务检查完成"}


def init_monitoring_integration(app):
    """初始化监控服务集成"""
    # 将监控路由添加到应用
    app.include_router(monitoring_router)
    
    # 使用 FastAPI 生命周期事件处理器来启动和停止监控服务
    @app.on_event("startup")
    async def startup_event():
        """应用启动时启动监控服务"""
        monitoring_service.start()
        logger.info("监控服务已通过生命周期事件启动")
    
    @app.on_event("shutdown")
    async def shutdown_event():
        """应用关闭时停止监控服务"""
        monitoring_service.stop()
        logger.info("监控服务已通过生命周期事件停止")
    
    logger.info("监控服务深度集成完成")
    return app
