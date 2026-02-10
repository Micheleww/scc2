#!/usr/bin/env python3
"""
容量监控模块
实现系统容量基准测试，包括资源监控、负载生成、容量报告生成
"""

import json
import logging
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import psutil

# 配置日志
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class CapacityMonitor:
    """
    容量监控器，用于监控系统资源使用情况和生成容量报告
    """

    def __init__(self, config: dict[str, Any]):
        """
        初始化容量监控器

        Args:
            config: 监控配置
        """
        self.config = config
        self.is_running = False
        self.monitor_thread = None

        # 监控数据
        self.metrics_history = []

        # 系统事件记录
        self.events = []

        # 测试配置
        self.test_config = {
            "base_strategy_count": config.get("base_strategy_count", 1),
            "base_symbol_count": config.get("base_symbol_count", 1),
            "increment_step": config.get("increment_step", 1),
            "max_strategies": config.get("max_strategies", 20),
            "max_symbols": config.get("max_symbols", 20),
            "monitor_interval": config.get("monitor_interval", 1.0),  # 监控间隔（秒）
            "test_duration": config.get("test_duration", 300),  # 每个负载级别测试时长（秒）
        }

        # 当前负载
        self.current_load = {
            "strategy_count": self.test_config["base_strategy_count"],
            "symbol_count": self.test_config["base_symbol_count"],
            "start_time": None,
            "end_time": None,
        }

        # 容量测试结果
        self.capacity_results = []

        logger.info(f"容量监控模块初始化完成，测试配置: {self.test_config}")

    def start_monitoring(self):
        """
        开始监控系统资源
        """
        if not self.is_running:
            self.is_running = True
            self.monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
            self.monitor_thread.start()
            logger.info("容量监控已启动")

    def stop_monitoring(self):
        """
        停止监控系统资源
        """
        if self.is_running:
            self.is_running = False
            if self.monitor_thread:
                self.monitor_thread.join(timeout=5.0)
            logger.info("容量监控已停止")

    def _monitor_loop(self):
        """
        监控循环，定期收集系统资源指标
        """
        while self.is_running:
            metrics = self._collect_metrics()
            self.metrics_history.append(metrics)
            time.sleep(self.test_config["monitor_interval"])

    def _collect_metrics(self) -> dict[str, Any]:
        """
        收集系统资源指标

        Returns:
            dict: 包含CPU、内存、网络等指标的字典
        """
        try:
            # CPU使用率
            cpu_percent = psutil.cpu_percent(interval=None)
            cpu_stats = psutil.cpu_stats()

            # 内存使用情况
            memory = psutil.virtual_memory()

            # 磁盘使用情况
            disk = psutil.disk_usage("/")

            # 网络IO
            net_io = psutil.net_io_counters()

            # 进程数
            process_count = len(psutil.pids())

            # 线程数
            thread_count = 0
            for pid in psutil.pids()[:50]:  # 只统计前50个进程，避免性能问题
                try:
                    process = psutil.Process(pid)
                    thread_count += process.num_threads()
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue

            metrics = {
                "timestamp": datetime.now(),
                "load": self.current_load.copy(),
                "cpu": {
                    "percent": cpu_percent,
                    "ctx_switches": cpu_stats.ctx_switches,
                    "interrupts": cpu_stats.interrupts,
                    "soft_interrupts": cpu_stats.soft_interrupts,
                    "syscalls": cpu_stats.syscalls,
                },
                "memory": {
                    "total": memory.total,
                    "available": memory.available,
                    "percent": memory.percent,
                    "used": memory.used,
                    "free": memory.free,
                },
                "disk": {
                    "total": disk.total,
                    "used": disk.used,
                    "free": disk.free,
                    "percent": disk.percent,
                },
                "network": {
                    "bytes_sent": net_io.bytes_sent,
                    "bytes_recv": net_io.bytes_recv,
                    "packets_sent": net_io.packets_sent,
                    "packets_recv": net_io.packets_recv,
                    "errin": net_io.errin,
                    "errout": net_io.errout,
                    "dropin": net_io.dropin,
                    "dropout": net_io.dropout,
                },
                "processes": {"total": process_count, "threads": thread_count},
            }

            return metrics
        except Exception as e:
            logger.error(f"收集资源指标失败: {e}")
            return {"timestamp": datetime.now(), "error": str(e)}

    def record_event(self, event_type: str, description: str, severity: str = "info"):
        """
        记录系统事件

        Args:
            event_type: 事件类型
            description: 事件描述
            severity: 事件严重性 (info, warning, error, critical)
        """
        event = {
            "timestamp": datetime.now(),
            "event_type": event_type,
            "description": description,
            "severity": severity,
            "load": self.current_load.copy(),
        }
        self.events.append(event)
        logger.info(f"事件记录: [{severity.upper()}] {event_type} - {description}")

    def start_load_level(self, strategy_count: int, symbol_count: int):
        """
        开始新的负载级别测试

        Args:
            strategy_count: 策略数量
            symbol_count: 品种数量
        """
        # 记录当前负载结束时间
        if self.current_load["start_time"]:
            self.current_load["end_time"] = datetime.now()
            # 保存当前负载级别的结果
            self._save_load_level_results()

        # 更新当前负载
        self.current_load = {
            "strategy_count": strategy_count,
            "symbol_count": symbol_count,
            "start_time": datetime.now(),
            "end_time": None,
        }

        # 记录负载变化事件
        self.record_event(
            event_type="load_change",
            description=f"开始负载级别: {strategy_count}个策略, {symbol_count}个品种",
            severity="info",
        )

        logger.info(f"开始负载级别测试: {strategy_count}个策略, {symbol_count}个品种")

    def _save_load_level_results(self):
        """
        保存当前负载级别的测试结果
        """
        if not self.current_load["start_time"] or not self.current_load["end_time"]:
            return

        # 筛选当前负载期间的指标
        start_time = self.current_load["start_time"]
        end_time = self.current_load["end_time"]

        load_metrics = [m for m in self.metrics_history if start_time <= m["timestamp"] <= end_time]

        if not load_metrics:
            return

        # 计算统计指标
        cpu_percents = [m["cpu"]["percent"] for m in load_metrics if "cpu" in m]
        memory_percents = [m["memory"]["percent"] for m in load_metrics if "memory" in m]
        network_bytes = [
            m["network"]["bytes_sent"] + m["network"]["bytes_recv"]
            for m in load_metrics
            if "network" in m
        ]

        # 计算网络IO速率
        network_rates = []
        for i in range(1, len(network_bytes)):
            time_diff = (
                load_metrics[i]["timestamp"] - load_metrics[i - 1]["timestamp"]
            ).total_seconds()
            if time_diff > 0:
                rate = (network_bytes[i] - network_bytes[i - 1]) / time_diff
                network_rates.append(rate)

        # 计算平均、最大、95分位数
        def calculate_stats(data):
            if not data:
                return {"avg": 0, "max": 0, "p95": 0}
            return {"avg": np.mean(data), "max": np.max(data), "p95": np.percentile(data, 95)}

        load_result = {
            "load": self.current_load.copy(),
            "duration": (end_time - start_time).total_seconds(),
            "cpu": calculate_stats(cpu_percents),
            "memory": calculate_stats(memory_percents),
            "network": {
                "total_bytes": network_bytes[-1] - network_bytes[0]
                if len(network_bytes) > 1
                else 0,
                "rate": calculate_stats(network_rates),
            },
            "event_count": len(
                [e for e in self.events if start_time <= e["timestamp"] <= end_time]
            ),
        }

        self.capacity_results.append(load_result)
        logger.info(f"负载级别测试完成: {json.dumps(load_result, default=str, indent=2)}")

    def record_system_issues(self, issues: dict[str, Any]):
        """
        记录系统问题

        Args:
            issues: 系统问题字典，包含断连、限流、对账漂移等信息
        """
        for issue_type, issue_details in issues.items():
            if issue_details.get("occurred", False):
                self.record_event(
                    event_type=issue_type,
                    description=f"{issue_type}问题: {issue_details.get('description', '')}",
                    severity="error",
                )

    def generate_capacity_report(self) -> dict[str, Any]:
        """
        生成容量报告

        Returns:
            dict: 容量报告
        """
        # 确保保存最后一个负载级别的结果
        if self.current_load["start_time"] and not self.current_load["end_time"]:
            self.current_load["end_time"] = datetime.now()
            self._save_load_level_results()

        # 分析容量测试结果，找出安全上限
        safe_limits = self._calculate_safe_limits()

        report = {
            "generated_at": datetime.now(),
            "test_config": self.test_config,
            "total_test_duration": (
                datetime.now() - self.metrics_history[0]["timestamp"]
            ).total_seconds()
            if self.metrics_history
            else 0,
            "metrics_history": self.metrics_history,
            "events": self.events,
            "capacity_results": self.capacity_results,
            "safe_limits": safe_limits,
            "conclusions": self._generate_conclusions(safe_limits),
        }

        return report

    def _calculate_safe_limits(self) -> dict[str, Any]:
        """
        计算系统安全上限

        Returns:
            dict: 安全上限配置
        """
        # 定义性能阈值
        thresholds = {
            "cpu_percent": 80.0,  # CPU使用率阈值
            "memory_percent": 85.0,  # 内存使用率阈值
            "network_rate_p95": 1000000,  # 网络IO速率阈值 (bytes/s)
            "max_events_per_minute": 100,  # 每分钟最大事件数阈值
        }

        # 初始安全上限
        safe_strategy_count = self.test_config["max_strategies"]
        safe_symbol_count = self.test_config["max_symbols"]

        # 分析每个负载级别的结果
        for result in self.capacity_results:
            # 检查CPU使用率
            if (
                result["cpu"]["avg"] > thresholds["cpu_percent"]
                or result["cpu"]["p95"] > thresholds["cpu_percent"]
            ):
                safe_strategy_count = min(safe_strategy_count, result["load"]["strategy_count"] - 1)
                safe_symbol_count = min(safe_symbol_count, result["load"]["symbol_count"] - 1)
                continue

            # 检查内存使用率
            if (
                result["memory"]["avg"] > thresholds["memory_percent"]
                or result["memory"]["p95"] > thresholds["memory_percent"]
            ):
                safe_strategy_count = min(safe_strategy_count, result["load"]["strategy_count"] - 1)
                safe_symbol_count = min(safe_symbol_count, result["load"]["symbol_count"] - 1)
                continue

            # 检查网络IO速率
            if result["network"]["rate"]["p95"] > thresholds["network_rate_p95"]:
                safe_strategy_count = min(safe_strategy_count, result["load"]["strategy_count"] - 1)
                safe_symbol_count = min(safe_symbol_count, result["load"]["symbol_count"] - 1)
                continue

            # 检查事件频率
            events_per_minute = result["event_count"] / (result["duration"] / 60)
            if events_per_minute > thresholds["max_events_per_minute"]:
                safe_strategy_count = min(safe_strategy_count, result["load"]["strategy_count"] - 1)
                safe_symbol_count = min(safe_symbol_count, result["load"]["symbol_count"] - 1)
                continue

        # 确保安全上限不小于基础值
        safe_strategy_count = max(safe_strategy_count, self.test_config["base_strategy_count"])
        safe_symbol_count = max(safe_symbol_count, self.test_config["base_symbol_count"])

        return {
            "safe_strategy_count": safe_strategy_count,
            "safe_symbol_count": safe_symbol_count,
            "thresholds": thresholds,
        }

    def _generate_conclusions(self, safe_limits: dict[str, Any]) -> list[str]:
        """
        生成容量测试结论

        Args:
            safe_limits: 安全上限配置

        Returns:
            list: 结论列表
        """
        conclusions = [
            f"系统容量测试完成，共测试了 {len(self.capacity_results)} 个负载级别",
            f"建议的安全上限: {safe_limits['safe_strategy_count']} 个策略, {safe_limits['safe_symbol_count']} 个品种",
            f"CPU使用率阈值: {safe_limits['thresholds']['cpu_percent']}%",
            f"内存使用率阈值: {safe_limits['thresholds']['memory_percent']}%",
            f"网络IO速率阈值: {safe_limits['thresholds']['network_rate_p95']} bytes/s",
            f"事件频率阈值: {safe_limits['thresholds']['max_events_per_minute']} 事件/分钟",
        ]

        # 检查是否达到了最大负载
        if safe_limits["safe_strategy_count"] >= self.test_config["max_strategies"]:
            conclusions.append(
                "注意: 系统未达到性能瓶颈，建议增加测试的最大负载级别以获得更准确的安全上限"
            )

        # 检查是否有系统事件
        error_events = [e for e in self.events if e["severity"] in ["error", "critical"]]
        if error_events:
            conclusions.append(f"测试过程中发生 {len(error_events)} 个错误事件，建议检查系统稳定性")

        return conclusions

    def save_report(self, output_dir: str = "reports") -> dict[str, str]:
        """
        保存容量报告到文件

        Args:
            output_dir: 输出目录

        Returns:
            dict: 保存的报告文件路径
        """
        # 生成容量报告
        report = self.generate_capacity_report()

        # 确保输出目录存在
        Path(output_dir).mkdir(exist_ok=True)

        # 生成文件名
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        # 保存JSON报告
        json_path = Path(output_dir) / f"capacity_report_{timestamp}.json"
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(report, f, default=str, indent=2, ensure_ascii=False)

        # 生成并保存Markdown报告
        md_path = Path(output_dir) / f"capacity_report_{timestamp}.md"
        self._generate_markdown_report(report, md_path)

        logger.info(f"容量报告已保存到 {json_path} 和 {md_path}")

        return {"json_report": str(json_path), "md_report": str(md_path)}

    def _generate_markdown_report(self, report: dict[str, Any], file_path: Path):
        """
        生成Markdown格式的容量报告

        Args:
            report: 容量报告
            file_path: 输出文件路径
        """
        lines = [
            "# 系统容量测试报告",
            f"\n生成时间: {report['generated_at']}",
            "\n## 测试配置",
            "| 配置项 | 值 |",
            "|--------|-----|",
            f"| 基础策略数量 | {report['test_config']['base_strategy_count']} |",
            f"| 基础品种数量 | {report['test_config']['base_symbol_count']} |",
            f"| 增量步长 | {report['test_config']['increment_step']} |",
            f"| 最大策略数量 | {report['test_config']['max_strategies']} |",
            f"| 最大品种数量 | {report['test_config']['max_symbols']} |",
            f"| 监控间隔 | {report['test_config']['monitor_interval']}秒 |",
            f"| 每个负载级别测试时长 | {report['test_config']['test_duration']}秒 |",
            f"| 总测试时长 | {report['total_test_duration']:.2f}秒 |",
            "\n## 安全上限建议",
            "| 资源类型 | 安全上限 | 阈值 |",
            "|----------|----------|------|",
            f"| 策略数量 | {report['safe_limits']['safe_strategy_count']} | CPU < {report['safe_limits']['thresholds']['cpu_percent']}%, 内存 < {report['safe_limits']['thresholds']['memory_percent']}% |",
            f"| 品种数量 | {report['safe_limits']['safe_symbol_count']} | CPU < {report['safe_limits']['thresholds']['cpu_percent']}%, 内存 < {report['safe_limits']['thresholds']['memory_percent']}% |",
            "\n## 测试结果详情",
            "| 策略数量 | 品种数量 | 测试时长(秒) | 平均CPU(%) | 平均内存(%) | 95% CPU(%) | 95%内存(%) | 网络IO速率(字节/秒) | 事件数 |",
            "|----------|----------|--------------|------------|------------|------------|------------|-------------------|--------|",
        ]

        # 添加每个负载级别的测试结果
        for result in report["capacity_results"]:
            lines.append(
                f"| {result['load']['strategy_count']} | {result['load']['symbol_count']} | {result['duration']:.2f} | {result['cpu']['avg']:.2f} | {result['memory']['avg']:.2f} | {result['cpu']['p95']:.2f} | {result['memory']['p95']:.2f} | {result['network']['rate']['p95']:.0f} | {result['event_count']} |"
            )

        # 添加事件记录
        if report["events"]:
            lines.extend(
                [
                    "\n## 系统事件记录",
                    "| 时间 | 事件类型 | 严重程度 | 描述 |",
                    "|------|----------|----------|------|",
                ]
            )

            for event in report["events"]:
                lines.append(
                    f"| {event['timestamp']} | {event['event_type']} | {event['severity']} | {event['description']} |"
                )

        # 添加结论
        lines.extend(
            [
                "\n## 结论",
            ]
        )

        for conclusion in report["conclusions"]:
            lines.append(f"- {conclusion}")

        # 写入文件
        with open(file_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))

    def get_current_metrics(self) -> dict[str, Any] | None:
        """
        获取当前系统资源指标

        Returns:
            dict: 当前资源指标，或None如果没有数据
        """
        if self.metrics_history:
            return self.metrics_history[-1]
        return None

    def get_metrics_history(self) -> list[dict[str, Any]]:
        """
        获取完整的指标历史记录

        Returns:
            list: 指标历史记录
        """
        return self.metrics_history.copy()

    def get_events(self) -> list[dict[str, Any]]:
        """
        获取事件记录

        Returns:
            list: 事件记录
        """
        return self.events.copy()

    def get_capacity_results(self) -> list[dict[str, Any]]:
        """
        获取容量测试结果

        Returns:
            list: 容量测试结果
        """
        return self.capacity_results.copy()


if __name__ == "__main__":
    # 测试容量监控器
    config = {
        "base_strategy_count": 1,
        "base_symbol_count": 1,
        "increment_step": 1,
        "max_strategies": 10,
        "max_symbols": 10,
        "monitor_interval": 1.0,
        "test_duration": 60,
    }

    monitor = CapacityMonitor(config)
    monitor.start_monitoring()

    try:
        # 模拟不同负载级别的测试
        for i in range(1, 6):
            monitor.start_load_level(i, i)
            time.sleep(5)  # 实际测试中应使用更长时间
    finally:
        monitor.stop_monitoring()
        monitor.save_report()
