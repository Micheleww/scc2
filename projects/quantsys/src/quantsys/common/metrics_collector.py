"""
运行时指标收集器，用于收集和报告系统运行状态指标。
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ConnectionMetrics:
    """
    连接状态指标数据类。
    """

    status: str  # DISCONNECTED, CONNECTING, CONNECTED, RECONNECTING, FAILED
    reconnect_count: int  # 重连次数
    last_reconnect_time: int | None = None  # 上次重连时间戳（毫秒）
    connected_since: int | None = None  # 连接建立时间戳（毫秒）
    latency: float = 0.0  # 连接延迟（毫秒）
    heartbeat_latency: float = 0.0  # 心跳延迟（毫秒）


@dataclass(frozen=True)
class RateLimitMetrics:
    """
    速率限制指标数据类。
    """

    limit_count: int  # 限流次数
    total_requests: int  # 总请求次数
    limited_requests: int  # 被限流的请求次数
    limit_ratio: float = 0.0  # 限流比率


@dataclass(frozen=True)
class OrderMetrics:
    """
    订单执行指标数据类。
    """

    total_orders: int  # 总订单数
    successful_orders: int  # 成功订单数
    failed_orders: int  # 失败订单数
    rejected_orders: int  # 被拒绝订单数
    failed_ratio: float = 0.0  # 订单失败率
    rejection_ratio: float = 0.0  # 订单拒绝率
    avg_order_latency: float = 0.0  # 平均订单执行延迟（毫秒）


@dataclass(frozen=True)
class ReconciliationMetrics:
    """
    对账指标数据类。
    """

    drift_count: int  # 对账漂移次数
    total_reconciliations: int  # 总对账次数
    drift_ratio: float = 0.0  # 对账漂移比率
    max_drift_amount: float = 0.0  # 最大漂移金额
    last_drift_time: int | None = None  # 上次漂移时间戳（毫秒）


@dataclass(frozen=True)
class SystemMetrics:
    """
    系统资源指标数据类。
    """

    cpu_usage: float = 0.0  # CPU使用率（%）
    memory_usage: float = 0.0  # 内存使用率（%）
    disk_usage: float = 0.0  # 磁盘使用率（%）
    network_in: float = 0.0  # 网络输入（MB/s）
    network_out: float = 0.0  # 网络输出（MB/s）


@dataclass(frozen=True)
class MetricsReport:
    """
    完整的指标报告数据类。
    """

    # 必需字段（没有默认值）
    timestamp: int  # 报告生成时间戳（毫秒）
    connection: ConnectionMetrics  # 连接指标
    rate_limit: RateLimitMetrics  # 速率限制指标
    order: OrderMetrics  # 订单指标
    reconciliation: ReconciliationMetrics  # 对账指标

    # 可选字段（带有默认值）
    run_id: str | None = None  # 运行ID
    strategy_version: str | None = None  # 策略版本
    factor_version: str | None = None  # 因子版本
    system: SystemMetrics | None = None  # 系统资源指标
    custom: dict[str, Any] | None = None  # 自定义指标

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MetricsReport:
        """从字典创建MetricsReport实例。"""
        connection_data = data.get("connection", {})
        rate_limit_data = data.get("rate_limit", {})
        order_data = data.get("order", {})
        reconciliation_data = data.get("reconciliation", {})
        system_data = data.get("system", {})
        custom_data = data.get("custom", {})

        return cls(
            timestamp=data.get("timestamp", 0),
            run_id=data.get("run_id"),
            strategy_version=data.get("strategy_version"),
            factor_version=data.get("factor_version"),
            connection=ConnectionMetrics(**connection_data),
            rate_limit=RateLimitMetrics(**rate_limit_data),
            order=OrderMetrics(**order_data),
            reconciliation=ReconciliationMetrics(**reconciliation_data),
            system=SystemMetrics(**system_data) if system_data else None,
            custom=custom_data if custom_data else None,
        )


class MetricsCollector:
    """
    运行时指标收集器，用于收集和报告系统运行状态指标。
    """

    def __init__(
        self,
        name: str = "system",
        run_id: str | None = None,
        strategy_version: str | None = None,
        factor_version: str | None = None,
    ):
        """
        初始化指标收集器。

        Args:
            name: 收集器名称，用于区分不同实例
            run_id: 运行ID
            strategy_version: 策略版本
            factor_version: 因子版本
        """
        self.name = name
        self.logger = logging.getLogger(f"metrics.{name}")
        self.run_id = run_id
        self.strategy_version = strategy_version
        self.factor_version = factor_version

        # 指标数据存储
        self.metrics: dict[str, Any] = {
            "connection": {
                "status": "DISCONNECTED",
                "reconnect_count": 0,
                "last_reconnect_time": None,
                "connected_since": None,
                "latency": 0.0,
                "heartbeat_latency": 0.0,
            },
            "rate_limit": {
                "limit_count": 0,
                "total_requests": 0,
                "limited_requests": 0,
                "limit_ratio": 0.0,
            },
            "order": {
                "total_orders": 0,
                "successful_orders": 0,
                "failed_orders": 0,
                "rejected_orders": 0,
                "failed_ratio": 0.0,
                "rejection_ratio": 0.0,
                "avg_order_latency": 0.0,
            },
            "reconciliation": {
                "drift_count": 0,
                "total_reconciliations": 0,
                "drift_ratio": 0.0,
                "max_drift_amount": 0.0,
                "last_drift_time": None,
            },
            "system": {
                "cpu_usage": 0.0,
                "memory_usage": 0.0,
                "disk_usage": 0.0,
                "network_in": 0.0,
                "network_out": 0.0,
            },
            "custom": {},
        }

        # 历史指标存储
        self.history: list[MetricsReport] = []
        self.max_history_size = 1000  # 最大历史记录数

        self.logger.info(f"指标收集器 {name} 初始化完成")

    def update_connection_status(self, status: str) -> None:
        """
        更新连接状态。

        Args:
            status: 连接状态，如 DISCONNECTED, CONNECTING, CONNECTED, RECONNECTING, FAILED
        """
        now = int(datetime.now().timestamp() * 1000)

        if status == "CONNECTED" and self.metrics["connection"]["status"] != "CONNECTED":
            self.metrics["connection"]["connected_since"] = now

        if status == "RECONNECTING" and self.metrics["connection"]["status"] != "RECONNECTING":
            self.metrics["connection"]["reconnect_count"] += 1
            self.metrics["connection"]["last_reconnect_time"] = now

        self.metrics["connection"]["status"] = status
        self.logger.debug(f"连接状态更新: {status}")

    def update_latency(self, latency: float, heartbeat: bool = False) -> None:
        """
        更新连接延迟。

        Args:
            latency: 延迟值（毫秒）
            heartbeat: 是否为心跳延迟
        """
        if heartbeat:
            self.metrics["connection"]["heartbeat_latency"] = latency
        else:
            self.metrics["connection"]["latency"] = latency

    def update_rate_limit(self, limited: bool) -> None:
        """
        更新速率限制指标。

        Args:
            limited: 是否被限流
        """
        self.metrics["rate_limit"]["total_requests"] += 1

        if limited:
            self.metrics["rate_limit"]["limit_count"] += 1
            self.metrics["rate_limit"]["limited_requests"] += 1

        # 更新限流比率
        if self.metrics["rate_limit"]["total_requests"] > 0:
            self.metrics["rate_limit"]["limit_ratio"] = (
                self.metrics["rate_limit"]["limited_requests"]
                / self.metrics["rate_limit"]["total_requests"]
            )

    def update_order_status(
        self, successful: bool, rejected: bool = False, latency: float = 0.0
    ) -> None:
        """
        更新订单状态指标。

        Args:
            successful: 订单是否成功
            rejected: 订单是否被拒绝
            latency: 订单执行延迟（毫秒）
        """
        self.metrics["order"]["total_orders"] += 1

        if successful:
            self.metrics["order"]["successful_orders"] += 1
            # 更新平均订单延迟
            current_total = self.metrics["order"]["avg_order_latency"] * (
                self.metrics["order"]["successful_orders"] - 1
            )
            self.metrics["order"]["avg_order_latency"] = (current_total + latency) / self.metrics[
                "order"
            ]["successful_orders"]
        else:
            self.metrics["order"]["failed_orders"] += 1
            if rejected:
                self.metrics["order"]["rejected_orders"] += 1

        # 更新失败率和拒绝率
        if self.metrics["order"]["total_orders"] > 0:
            self.metrics["order"]["failed_ratio"] = (
                self.metrics["order"]["failed_orders"] / self.metrics["order"]["total_orders"]
            )
            self.metrics["order"]["rejection_ratio"] = (
                self.metrics["order"]["rejected_orders"] / self.metrics["order"]["total_orders"]
            )

    def update_reconciliation(self, drift: bool, drift_amount: float = 0.0) -> None:
        """
        更新对账指标。

        Args:
            drift: 是否检测到漂移
            drift_amount: 漂移金额
        """
        self.metrics["reconciliation"]["total_reconciliations"] += 1

        if drift:
            self.metrics["reconciliation"]["drift_count"] += 1
            self.metrics["reconciliation"]["last_drift_time"] = int(
                datetime.now().timestamp() * 1000
            )

            # 更新最大漂移金额
            if abs(drift_amount) > self.metrics["reconciliation"]["max_drift_amount"]:
                self.metrics["reconciliation"]["max_drift_amount"] = abs(drift_amount)

        # 更新漂移比率
        if self.metrics["reconciliation"]["total_reconciliations"] > 0:
            self.metrics["reconciliation"]["drift_ratio"] = (
                self.metrics["reconciliation"]["drift_count"]
                / self.metrics["reconciliation"]["total_reconciliations"]
            )

    def update_system_metrics(
        self,
        cpu: float,
        memory: float,
        disk: float,
        network_in: float = 0.0,
        network_out: float = 0.0,
    ) -> None:
        """
        更新系统资源指标。

        Args:
            cpu: CPU使用率（%）
            memory: 内存使用率（%）
            disk: 磁盘使用率（%）
            network_in: 网络输入（MB/s）
            network_out: 网络输出（MB/s）
        """
        self.metrics["system"]["cpu_usage"] = cpu
        self.metrics["system"]["memory_usage"] = memory
        self.metrics["system"]["disk_usage"] = disk
        self.metrics["system"]["network_in"] = network_in
        self.metrics["system"]["network_out"] = network_out

    def set_custom_metric(self, name: str, value: Any) -> None:
        """
        设置自定义指标。

        Args:
            name: 指标名称
            value: 指标值
        """
        self.metrics["custom"][name] = value

    def get_metrics(self) -> MetricsReport:
        """
        获取当前指标报告。

        Returns:
            MetricsReport: 当前指标报告
        """
        return MetricsReport.from_dict(
            {
                "timestamp": int(datetime.now().timestamp() * 1000),
                "run_id": self.run_id,
                "strategy_version": self.strategy_version,
                "factor_version": self.factor_version,
                **self.metrics,
            }
        )

    def record_metrics(self) -> None:
        """
        记录当前指标到历史记录。
        """
        metrics_report = self.get_metrics()
        self.history.append(metrics_report)

        # 保持历史记录大小
        if len(self.history) > self.max_history_size:
            self.history = self.history[-self.max_history_size :]

    def generate_report(self) -> dict[str, Any]:
        """
        生成格式化的指标报告。

        Returns:
            Dict[str, Any]: 格式化的指标报告
        """
        report = self.get_metrics()
        self.record_metrics()
        return asdict(report)

    def save_report(self, output_dir: str = "reports") -> Path:
        """
        保存指标报告到文件。

        Args:
            output_dir: 输出目录

        Returns:
            Path: 保存的报告文件路径
        """
        report = self.generate_report()

        # 确保输出目录存在
        output_path = Path(output_dir)
        output_path.mkdir(exist_ok=True)

        # 生成文件名
        timestamp = report["timestamp"]
        filename = f"metrics_report_{timestamp}.json"
        file_path = output_path / filename

        # 保存报告
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, ensure_ascii=False)

        # 同时更新最新报告链接
        latest_link = output_path / "latest_metrics.json"
        if latest_link.exists():
            latest_link.unlink()
        latest_link.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

        self.logger.info(f"指标报告已保存到 {file_path}")
        return file_path

    def save_history(self, output_dir: str = "reports") -> Path:
        """
        保存指标历史记录到文件。

        Args:
            output_dir: 输出目录

        Returns:
            Path: 保存的历史记录文件路径
        """
        # 确保输出目录存在
        output_path = Path(output_dir)
        output_path.mkdir(exist_ok=True)

        # 生成文件名
        timestamp = int(datetime.now().timestamp() * 1000)
        filename = f"metrics_history_{timestamp}.json"
        file_path = output_path / filename

        # 转换历史记录为字典列表
        history_dicts = [asdict(report) for report in self.history]

        # 保存历史记录
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(history_dicts, f, indent=2, ensure_ascii=False)

        self.logger.info(f"指标历史记录已保存到 {file_path}")
        return file_path

    def print_metrics(self) -> None:
        """
        打印当前指标到日志。
        """
        report = self.get_metrics()
        self.logger.info("=" * 60)
        self.logger.info(
            f"{self.name} 指标报告 - {datetime.fromtimestamp(report.timestamp / 1000)}"
        )
        self.logger.info("=" * 60)

        # 连接指标
        self.logger.info(f"连接状态: {report.connection.status}")
        self.logger.info(f"重连次数: {report.connection.reconnect_count}")
        self.logger.info(f"连接延迟: {report.connection.latency:.2f} ms")
        self.logger.info(f"心跳延迟: {report.connection.heartbeat_latency:.2f} ms")

        # 速率限制指标
        self.logger.info(f"总请求数: {report.rate_limit.total_requests}")
        self.logger.info(f"限流次数: {report.rate_limit.limit_count}")
        self.logger.info(f"限流比率: {report.rate_limit.limit_ratio:.2%}")

        # 订单指标
        self.logger.info(f"总订单数: {report.order.total_orders}")
        self.logger.info(f"成功订单: {report.order.successful_orders}")
        self.logger.info(f"失败订单: {report.order.failed_orders}")
        self.logger.info(f"订单失败率: {report.order.failed_ratio:.2%}")
        self.logger.info(f"订单拒绝率: {report.order.rejection_ratio:.2%}")
        self.logger.info(f"平均订单延迟: {report.order.avg_order_latency:.2f} ms")

        # 对账指标
        self.logger.info(f"总对账次数: {report.reconciliation.total_reconciliations}")
        self.logger.info(f"对账漂移次数: {report.reconciliation.drift_count}")
        self.logger.info(f"对账漂移比率: {report.reconciliation.drift_ratio:.2%}")
        self.logger.info(f"最大漂移金额: {report.reconciliation.max_drift_amount:.4f}")

        # 系统指标
        if report.system:
            self.logger.info(f"CPU使用率: {report.system.cpu_usage:.2f}%")
            self.logger.info(f"内存使用率: {report.system.memory_usage:.2f}%")
            self.logger.info(f"磁盘使用率: {report.system.disk_usage:.2f}%")

        self.logger.info("=" * 60)
