"""
System and health check routes
"""
import os
from datetime import datetime
from fastapi import APIRouter

from ..monitoring import monitoring_service
from ..cache_service import cached

router = APIRouter()

# A2A Hub configuration
A2A_HUB_ENABLED = os.getenv("A2A_HUB_ENABLED", "false").lower() == "true"


def _check_service_health(service: str) -> bool | None:
    """Check if a service is healthy"""
    # This is a placeholder - actual implementation would check service health
    return True


@router.get("/health")
async def health():
    """Health check endpoint"""
    a2a_status = None
    if A2A_HUB_ENABLED:
        a2a_status = {"enabled": True, "healthy": _check_service_health("a2a")}
    else:
        a2a_status = {"enabled": False}

    return {
        "ok": True,
        "ts": datetime.now().isoformat(),
        "status": "healthy",
        "version": "0.1.0",
        "a2a": a2a_status,
    }


@router.get("/api/langsmith/status")
async def get_langsmith_status():
    """LangSmith tracing configuration/status (safe, no secrets)."""
    try:
        from tools.langsmith.fastapi_middleware import langsmith_status

        payload = langsmith_status()
        payload["middleware_attached"] = bool(os.getenv("LANGSMITH_MIDDLEWARE_ATTACHED", False))
        payload["available"] = True
        return payload
    except Exception as e:
        return {
            "available": False,
            "configured": False,
            "middleware_attached": False,
            "error": str(e),
        }


@router.get("/api/monitoring/status")
@cached(prefix="monitoring", ttl=5)  # 缓存5秒
async def get_monitoring_status():
    """获取所有服务状态"""
    return monitoring_service.get_status_summary()


@router.get("/api/monitoring/metrics")
@cached(prefix="monitoring", ttl=5)  # 缓存5秒
async def get_monitoring_metrics():
    """获取系统指标"""
    metrics = (
        monitoring_service.metrics_history[-100:] if monitoring_service.metrics_history else []
    )
    return {
        "metrics": [
            {
                "timestamp": m.timestamp.isoformat(),
                "cpu_percent": m.cpu_percent,
                "memory_percent": m.memory_percent,
                "memory_used_mb": m.memory_used_mb,
                "memory_total_mb": m.memory_total_mb,
                "disk_percent": m.disk_percent,
                "disk_used_gb": m.disk_used_gb,
                "disk_total_gb": m.disk_total_gb,
                "network_sent_mb": m.network_sent_mb,
                "network_recv_mb": m.network_recv_mb,
            }
            for m in metrics
        ]
    }


@router.get("/api/monitoring/alerts")
async def get_monitoring_alerts(resolved: bool = False):
    """获取告警列表"""
    alerts = monitoring_service.alerts
    if not resolved:
        alerts = [a for a in alerts if not a.resolved]

    return {
        "alerts": [
            {
                "id": a.id,
                "level": a.level,
                "service": a.service,
                "message": a.message,
                "timestamp": a.timestamp.isoformat(),
                "resolved": a.resolved,
            }
            for a in alerts[-50:]  # 最近50条
        ]
    }


@router.post("/api/monitoring/alerts/{alert_id}/resolve")
async def resolve_alert(alert_id: str):
    """解决告警"""
    await monitoring_service.resolve_alert(alert_id)
    return {"success": True, "alert_id": alert_id}
