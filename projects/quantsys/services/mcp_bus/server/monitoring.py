#!/usr/bin/env python3
"""
实时监控与告警系统
"""

import asyncio
import logging
import time
from dataclasses import asdict, dataclass
from datetime import datetime
from enum import Enum
from typing import Any

import httpx
import psutil

logger = logging.getLogger(__name__)


class ServiceStatus(Enum):
    """服务状态枚举"""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    DOWN = "down"
    UNKNOWN = "unknown"


@dataclass
class ServiceHealth:
    """服务健康状态"""

    name: str
    status: ServiceStatus
    url: str
    response_time_ms: float | None = None
    last_check: datetime | None = None
    error: str | None = None
    uptime_percent: float | None = None


@dataclass
class SystemMetrics:
    """系统指标"""

    timestamp: datetime
    cpu_percent: float
    memory_percent: float
    memory_used_mb: float
    memory_total_mb: float
    disk_percent: float
    disk_used_gb: float
    disk_total_gb: float
    network_sent_mb: float
    network_recv_mb: float


@dataclass
class Alert:
    """告警信息"""

    id: str
    level: str  # critical, warning, info
    service: str
    message: str
    timestamp: datetime
    resolved: bool = False


class MonitoringService:
    """监控服务"""

    def __init__(self):
        self.services: dict[str, ServiceHealth] = {}
        self.metrics_history: list[SystemMetrics] = []
        self.alerts: list[Alert] = []
        self.check_interval = 10  # 秒
        self.metrics_history_size = 1000
        self.running = False
        self._task: asyncio.Task | None = None

        # 初始化服务列表
        self._init_services()

    def _init_services(self):
        """初始化服务列表"""
        self.services = {
            "mcp_server": ServiceHealth(
                name="总服务器", status=ServiceStatus.UNKNOWN, url="http://127.0.0.1:18788/mcp/health"
            ),

            "freqtrade": ServiceHealth(
                name="Freqtrade服务",
                status=ServiceStatus.UNKNOWN,
                url="http://127.0.0.1:18788/api/v1/ping",
            ),
            "a2a_hub": ServiceHealth(
                name="A2A Hub", status=ServiceStatus.UNKNOWN, url="http://127.0.0.1:18788/api/health"
            ),
            "dashboard": ServiceHealth(
                name="Dashboard", status=ServiceStatus.UNKNOWN, url="http://127.0.0.1:8051"
            ),
            "langgraph": ServiceHealth(
                name="LangGraph", status=ServiceStatus.UNKNOWN, url="http://127.0.0.1:2024/health"
            ),
        }

    async def check_service(self, service_name: str, service: ServiceHealth) -> ServiceHealth:
        """检查单个服务状态"""
        
        # 特殊处理：检查本地freqtrade进程状态
        if service_name == "freqtrade":
            try:
                from .freqtrade_service import freqtrade_service

                status = freqtrade_service.get_status()
                webserver_status = status["webserver"]

                if webserver_status["running"]:
                    # 进程运行中，检查API是否响应
                    start_time = time.time()
                    try:
                        async with httpx.AsyncClient(timeout=5.0) as client:
                            response = await client.get(service.url)
                            response_time = (time.time() - start_time) * 1000

                            if response.status_code == 200:
                                service.status = ServiceStatus.HEALTHY
                                service.response_time_ms = response_time
                                service.error = None
                            else:
                                service.status = ServiceStatus.DEGRADED
                                service.error = f"HTTP {response.status_code}"
                    except Exception as e:
                        # 进程运行但API不可用
                        service.status = ServiceStatus.DEGRADED
                        service.error = f"API不可用: {str(e)}"
                else:
                    # 进程未运行
                    service.status = ServiceStatus.DOWN
                    service.error = "WebServer进程未运行"

                service.last_check = datetime.now()
                return service
            except ImportError:
                # freqtrade_service未导入，使用默认HTTP检查
                pass

        # 默认HTTP检查
        start_time = time.time()
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(service.url)
                response_time = (time.time() - start_time) * 1000

                if response.status_code == 200:
                    service.status = ServiceStatus.HEALTHY
                    service.response_time_ms = response_time
                    service.error = None
                elif response.status_code >= 500:
                    service.status = ServiceStatus.DOWN
                    service.error = f"HTTP {response.status_code}"
                else:
                    service.status = ServiceStatus.DEGRADED
                    service.error = f"HTTP {response.status_code}"

                service.last_check = datetime.now()

        except httpx.TimeoutException:
            service.status = ServiceStatus.DOWN
            service.response_time_ms = None
            service.error = "Timeout"
            service.last_check = datetime.now()
            await self._create_alert(
                level="warning", service=service_name, message=f"服务超时: {service.name}"
            )
        except Exception as e:
            service.status = ServiceStatus.DOWN
            service.response_time_ms = None
            service.error = str(e)
            service.last_check = datetime.now()
            await self._create_alert(
                level="critical",
                service=service_name,
                message=f"服务异常: {service.name} - {str(e)}",
            )

        return service

    async def check_all_services(self):
        """检查所有服务状态"""
        tasks = [self.check_service(name, service) for name, service in self.services.items()]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for i, (name, service) in enumerate(self.services.items()):
            if not isinstance(results[i], Exception):
                self.services[name] = results[i]

    async def get_system_metrics(self) -> SystemMetrics:
        """获取系统指标"""
        cpu_percent = psutil.cpu_percent(interval=0.1)
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage("/")
        network = psutil.net_io_counters()

        metrics = SystemMetrics(
            timestamp=datetime.now(),
            cpu_percent=cpu_percent,
            memory_percent=memory.percent,
            memory_used_mb=memory.used / (1024 * 1024),
            memory_total_mb=memory.total / (1024 * 1024),
            disk_percent=disk.percent,
            disk_used_gb=disk.used / (1024 * 1024 * 1024),
            disk_total_gb=disk.total / (1024 * 1024 * 1024),
            network_sent_mb=network.bytes_sent / (1024 * 1024),
            network_recv_mb=network.bytes_recv / (1024 * 1024),
        )

        # 保存到历史记录
        self.metrics_history.append(metrics)
        if len(self.metrics_history) > self.metrics_history_size:
            self.metrics_history.pop(0)

        return metrics

    async def _create_alert(self, level: str, service: str, message: str):
        """创建告警"""
        alert = Alert(
            id=f"{service}_{int(time.time())}",
            level=level,
            service=service,
            message=message,
            timestamp=datetime.now(),
        )

        # 检查是否已有相同告警
        existing = [
            a
            for a in self.alerts
            if a.service == service and a.message == message and not a.resolved
        ]
        if not existing:
            self.alerts.append(alert)
            logger.warning(f"Alert [{level}] {service}: {message}")

            # 只保留最近100条告警
            if len(self.alerts) > 100:
                self.alerts = self.alerts[-100:]

    async def resolve_alert(self, alert_id: str):
        """解决告警"""
        for alert in self.alerts:
            if alert.id == alert_id:
                alert.resolved = True
                break

    async def monitoring_loop(self):
        """监控循环"""
        while self.running:
            try:
                # 检查服务状态
                await self.check_all_services()

                # 获取系统指标
                await self.get_system_metrics()

                # 检查告警条件
                await self._check_alert_conditions()

            except Exception as e:
                logger.error(f"监控循环错误: {e}")

            await asyncio.sleep(self.check_interval)

    async def _check_alert_conditions(self):
        """检查告警条件"""
        metrics = self.metrics_history[-1] if self.metrics_history else None

        if metrics:
            # CPU告警
            if metrics.cpu_percent > 90:
                await self._create_alert(
                    level="warning",
                    service="system",
                    message=f"CPU使用率过高: {metrics.cpu_percent:.1f}%",
                )

            # 内存告警
            if metrics.memory_percent > 90:
                await self._create_alert(
                    level="critical",
                    service="system",
                    message=f"内存使用率过高: {metrics.memory_percent:.1f}%",
                )

            # 磁盘告警
            if metrics.disk_percent > 90:
                await self._create_alert(
                    level="warning",
                    service="system",
                    message=f"磁盘使用率过高: {metrics.disk_percent:.1f}%",
                )

    def start(self):
        """启动监控服务"""
        if not self.running:
            self.running = True
            self._task = asyncio.create_task(self.monitoring_loop())
            logger.info("监控服务已启动")

    def stop(self):
        """停止监控服务"""
        if self.running:
            self.running = False
            if self._task:
                self._task.cancel()
            logger.info("监控服务已停止")

    def get_status_summary(self) -> dict[str, Any]:
        """获取状态摘要"""
        healthy_count = sum(1 for s in self.services.values() if s.status == ServiceStatus.HEALTHY)
        total_count = len(self.services)

        recent_alerts = [a for a in self.alerts if not a.resolved][-10:]

        latest_metrics = self.metrics_history[-1] if self.metrics_history else None

        return {
            "services": {
                name: {
                    "name": service.name,
                    "status": service.status.value,
                    "response_time_ms": service.response_time_ms,
                    "last_check": service.last_check.isoformat() if service.last_check else None,
                    "error": service.error,
                }
                for name, service in self.services.items()
            },
            "summary": {
                "healthy": healthy_count,
                "total": total_count,
                "uptime_percent": (healthy_count / total_count * 100) if total_count > 0 else 0,
            },
            "metrics": asdict(latest_metrics) if latest_metrics else None,
            "alerts": [
                {
                    "id": a.id,
                    "level": a.level,
                    "service": a.service,
                    "message": a.message,
                    "timestamp": a.timestamp.isoformat(),
                    "resolved": a.resolved,
                }
                for a in recent_alerts
            ],
        }


# 全局监控服务实例
monitoring_service = MonitoringService()
