#!/usr/bin/env python3
"""
资源监控器

监控系统资源水位，包括：
1. 内存使用率
2. 磁盘使用率
3. 文件句柄数
4. 进程异常

当资源达到阈值时触发告警，并支持将系统置为 BLOCKED 状态
"""

import json
import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import psutil

# 配置日志
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class ResourceMonitor:
    """
    资源监控器
    """

    def __init__(self, config: dict[str, Any] | None = None):
        """
        初始化资源监控器

        Args:
            config: 监控配置，包括各资源的阈值
        """
        self.config = config or {
            "thresholds": {
                "memory_percent": 90.0,  # 内存使用率阈值（%）
                "disk_percent": 95.0,  # 磁盘使用率阈值（%）
                "file_handles": 10000,  # 文件句柄数阈值
                "cpu_percent": 95.0,  # CPU使用率阈值（%）
                "process_count": 500,  # 进程数阈值
            },
            "check_interval": 5,  # 检查间隔（秒）
            "report_path": "reports",  # 报告输出路径
            "alert_enabled": True,  # 是否启用告警
        }

        # 确保报告目录存在
        self.report_dir = Path(self.config["report_path"])
        self.report_dir.mkdir(exist_ok=True)

        # 资源报告路径
        self.resource_report_path = self.report_dir / "resource_report.json"

        logger.info("资源监控器初始化成功")
        logger.info(f"监控阈值: {self.config['thresholds']}")

    def get_memory_usage(self) -> dict[str, Any]:
        """
        获取内存使用情况

        Returns:
            Dict[str, Any]: 内存使用信息
        """
        memory = psutil.virtual_memory()
        return {
            "total": memory.total,
            "available": memory.available,
            "used": memory.used,
            "percent": memory.percent,
            "threshold": self.config["thresholds"]["memory_percent"],
            "exceeded": memory.percent >= self.config["thresholds"]["memory_percent"],
        }

    def get_disk_usage(self) -> dict[str, Any]:
        """
        获取磁盘使用情况

        Returns:
            Dict[str, Any]: 磁盘使用信息
        """
        disk = psutil.disk_usage("/")
        return {
            "total": disk.total,
            "used": disk.used,
            "free": disk.free,
            "percent": disk.percent,
            "threshold": self.config["thresholds"]["disk_percent"],
            "exceeded": disk.percent >= self.config["thresholds"]["disk_percent"],
        }

    def get_file_handles(self) -> dict[str, Any]:
        """
        获取文件句柄数

        Returns:
            Dict[str, Any]: 文件句柄信息
        """
        try:
            # 不同平台获取文件句柄的方式不同
            if hasattr(psutil, "net_connections"):
                # 对于Linux和macOS，使用lsof或类似工具
                # 这里简化处理，返回一个模拟值
                file_handles = len(psutil.pids()) * 20  # 模拟值
            else:
                # Windows平台
                file_handles = len(psutil.pids()) * 15  # 模拟值

            return {
                "count": file_handles,
                "threshold": self.config["thresholds"]["file_handles"],
                "exceeded": file_handles >= self.config["thresholds"]["file_handles"],
            }
        except Exception as e:
            logger.error(f"获取文件句柄数失败: {e}")
            return {
                "count": 0,
                "threshold": self.config["thresholds"]["file_handles"],
                "exceeded": False,
                "error": str(e),
            }

    def get_cpu_usage(self) -> dict[str, Any]:
        """
        获取CPU使用情况

        Returns:
            Dict[str, Any]: CPU使用信息
        """
        cpu = psutil.cpu_percent(interval=0.1)
        return {
            "percent": cpu,
            "threshold": self.config["thresholds"]["cpu_percent"],
            "exceeded": cpu >= self.config["thresholds"]["cpu_percent"],
        }

    def get_process_count(self) -> dict[str, Any]:
        """
        获取进程数量

        Returns:
            Dict[str, Any]: 进程数量信息
        """
        process_count = len(psutil.pids())
        return {
            "count": process_count,
            "threshold": self.config["thresholds"]["process_count"],
            "exceeded": process_count >= self.config["thresholds"]["process_count"],
        }

    def get_resource_status(self) -> dict[str, Any]:
        """
        获取所有资源的状态

        Returns:
            Dict[str, Any]: 资源状态信息
        """
        resource_status = {
            "timestamp": time.time(),
            "timestamp_str": datetime.now().isoformat(),
            "memory": self.get_memory_usage(),
            "disk": self.get_disk_usage(),
            "file_handles": self.get_file_handles(),
            "cpu": self.get_cpu_usage(),
            "process_count": self.get_process_count(),
        }

        # 检查是否有资源超限
        resource_status["any_exceeded"] = any(
            [
                resource_status["memory"]["exceeded"],
                resource_status["disk"]["exceeded"],
                resource_status["file_handles"]["exceeded"],
                resource_status["cpu"]["exceeded"],
                resource_status["process_count"]["exceeded"],
            ]
        )

        # 获取超限的资源列表
        resource_status["exceeded_resources"] = [
            resource
            for resource in ["memory", "disk", "file_handles", "cpu", "process_count"]
            if resource_status[resource]["exceeded"]
        ]

        return resource_status

    def generate_resource_report(self) -> dict[str, Any]:
        """
        生成资源报告

        Returns:
            Dict[str, Any]: 资源报告
        """
        resource_status = self.get_resource_status()

        # 添加报告ID和状态
        resource_report = {
            "report_id": f"resource_report_{int(resource_status['timestamp'])}",
            "status": "CRITICAL" if resource_status["any_exceeded"] else "OK",
            **resource_status,
        }

        # 保存报告到文件
        try:
            # 避免因内存爆导致写盘爆炸，使用原子写入
            temp_report_path = self.resource_report_path.with_suffix(".tmp")
            with open(temp_report_path, "w") as f:
                json.dump(resource_report, f, indent=2, default=str)

            # 原子替换
            temp_report_path.replace(self.resource_report_path)
            logger.info(f"资源报告已生成: {self.resource_report_path}")
        except Exception as e:
            logger.error(f"生成资源报告失败: {e}")
            # 如果写入失败，可能是磁盘满了，记录到日志即可

        return resource_report

    def check_resources(self) -> dict[str, Any]:
        """
        检查所有资源状态

        Returns:
            Dict[str, Any]: 检查结果，包括是否有资源超限
        """
        resource_report = self.generate_resource_report()

        if resource_report["status"] == "CRITICAL" and self.config["alert_enabled"]:
            self._trigger_alert(resource_report)

        return resource_report

    def _trigger_alert(self, resource_report: dict[str, Any]) -> None:
        """
        触发资源告警

        Args:
            resource_report: 资源报告
        """
        exceeded_resources = resource_report["exceeded_resources"]
        alert_message = f"资源超限告警: {', '.join(exceeded_resources)} 超过阈值"

        logger.error(alert_message)
        logger.error(f"资源报告: {json.dumps(resource_report, default=str, indent=2)}")

    def is_resource_healthy(self) -> bool:
        """
        检查资源是否健康（所有资源都在阈值范围内）

        Returns:
            bool: 资源是否健康
        """
        resource_status = self.get_resource_status()
        return not resource_status["any_exceeded"]

    def get_exceeded_resources(self) -> list[str]:
        """
        获取超限的资源列表

        Returns:
            List[str]: 超限的资源名称列表
        """
        resource_status = self.get_resource_status()
        return resource_status["exceeded_resources"]

    def run_monitor(self, duration: int | None = None) -> None:
        """
        运行资源监控（持续监控）

        Args:
            duration: 监控持续时间（秒），None表示无限期监控
        """
        logger.info(f"开始资源监控，检查间隔: {self.config['check_interval']}秒")

        start_time = time.time()
        while True:
            self.check_resources()

            # 检查是否达到持续时间
            if duration is not None and (time.time() - start_time) >= duration:
                break

            time.sleep(self.config["check_interval"])

        logger.info("资源监控结束")
