#!/usr/bin/env python3
"""
性能监控模块
为系统组件添加性能预算基准，测试CPU/内存/延迟开销与阈值
"""

import json
import logging
import threading
import time
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import psutil

# 配置日志
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class PerformanceMonitor:
    """
    性能监控器，用于测试单个组件的性能预算
    """

    def __init__(self, config: dict[str, Any]):
        """
        初始化性能监控器

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

        # 组件配置
        self.component_configs = {
            "0502": {
                "name": "Order Execution",
                "description": "订单执行组件",
                "cpu_threshold": 30.0,  # CPU使用率阈值(%)
                "memory_threshold": 20.0,  # 内存使用率阈值(%)
                "latency_threshold": 100.0,  # 延迟阈值(ms)
            },
            "0504": {
                "name": "Reconciliation",
                "description": "对账组件",
                "cpu_threshold": 25.0,
                "memory_threshold": 15.0,
                "latency_threshold": 150.0,
            },
            "0505": {
                "name": "Execution Readiness",
                "description": "执行就绪组件",
                "cpu_threshold": 20.0,
                "memory_threshold": 10.0,
                "latency_threshold": 50.0,
            },
        }

        # 测试配置
        self.test_config = {
            "monitor_interval": config.get("monitor_interval", 0.5),  # 监控间隔（秒）
            "test_duration": config.get("test_duration", 60),  # 每个组件测试时长（秒）
            "warmup_duration": config.get("warmup_duration", 5),  # 预热时长（秒）
        }

        # 当前测试组件
        self.current_component = None
        self.current_test = {
            "component_id": None,
            "start_time": None,
            "end_time": None,
            "latency_samples": [],
        }

        # 性能测试结果
        self.perf_results = []

        logger.info(f"性能监控模块初始化完成，测试配置: {self.test_config}")

    def start_monitoring(self):
        """
        开始监控系统资源
        """
        if not self.is_running:
            self.is_running = True
            self.monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
            self.monitor_thread.start()
            logger.info("性能监控已启动")

    def stop_monitoring(self):
        """
        停止监控系统资源
        """
        if self.is_running:
            self.is_running = False
            if self.monitor_thread:
                self.monitor_thread.join(timeout=5.0)
            logger.info("性能监控已停止")

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
            dict: 包含CPU、内存等指标的字典
        """
        try:
            # CPU使用率
            cpu_percent = psutil.cpu_percent(interval=None)

            # 内存使用情况
            memory = psutil.virtual_memory()

            # 当前进程内存使用
            current_process = psutil.Process()
            process_memory = current_process.memory_percent()

            metrics = {
                "timestamp": datetime.now(),
                "component": self.current_test["component_id"],
                "cpu": {"system_percent": cpu_percent, "process_percent": process_memory},
                "memory": {
                    "system_percent": memory.percent,
                    "system_used": memory.used,
                    "system_total": memory.total,
                    "process_percent": process_memory,
                },
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
            "component": self.current_test["component_id"],
        }
        self.events.append(event)
        logger.info(f"事件记录: [{severity.upper()}] {event_type} - {description}")

    def record_latency(self, latency_ms: float):
        """
        记录组件延迟

        Args:
            latency_ms: 延迟时间（毫秒）
        """
        self.current_test["latency_samples"].append(
            {"timestamp": datetime.now(), "latency_ms": latency_ms}
        )

    def start_component_test(self, component_id: str):
        """
        开始测试单个组件

        Args:
            component_id: 组件ID (0502, 0504, 0505)
        """
        # 结束当前测试
        if self.current_test["component_id"]:
            self.end_component_test()

        # 检查组件ID是否有效
        if component_id not in self.component_configs:
            logger.error(f"无效的组件ID: {component_id}")
            return False

        # 记录当前测试
        self.current_test = {
            "component_id": component_id,
            "start_time": datetime.now(),
            "end_time": None,
            "latency_samples": [],
        }

        # 记录测试开始事件
        component_name = self.component_configs[component_id]["name"]
        self.record_event(
            event_type="test_start",
            description=f"开始测试组件: {component_id} - {component_name}",
            severity="info",
        )

        logger.info(f"开始测试组件: {component_id} - {component_name}")
        return True

    def end_component_test(self):
        """
        结束当前组件测试
        """
        if not self.current_test["component_id"]:
            return

        # 记录当前测试结束时间
        self.current_test["end_time"] = datetime.now()

        # 保存当前组件的测试结果
        self._save_component_results()

        # 记录测试结束事件
        component_name = self.component_configs[self.current_test["component_id"]]["name"]
        self.record_event(
            event_type="test_end",
            description=f"结束测试组件: {self.current_test['component_id']} - {component_name}",
            severity="info",
        )

        logger.info(f"结束测试组件: {self.current_test['component_id']} - {component_name}")

        # 重置当前测试
        self.current_test = {
            "component_id": None,
            "start_time": None,
            "end_time": None,
            "latency_samples": [],
        }

    def _save_component_results(self):
        """
        保存当前组件的测试结果
        """
        if not self.current_test["start_time"] or not self.current_test["end_time"]:
            return

        component_id = self.current_test["component_id"]
        component_config = self.component_configs[component_id]

        # 筛选当前组件测试期间的指标
        start_time = self.current_test["start_time"]
        end_time = self.current_test["end_time"]

        # 排除预热期的数据
        warmup_end_time = start_time + pd.Timedelta(seconds=self.test_config["warmup_duration"])

        component_metrics = [
            m
            for m in self.metrics_history
            if m["component"] == component_id and warmup_end_time <= m["timestamp"] <= end_time
        ]

        if not component_metrics:
            return

        # 计算CPU统计指标
        cpu_system_percents = [m["cpu"]["system_percent"] for m in component_metrics]
        cpu_process_percents = [m["cpu"]["process_percent"] for m in component_metrics]

        # 计算内存统计指标
        memory_system_percents = [m["memory"]["system_percent"] for m in component_metrics]
        memory_process_percents = [m["memory"]["process_percent"] for m in component_metrics]

        # 计算延迟统计指标
        latency_samples = [
            sample["latency_ms"]
            for sample in self.current_test["latency_samples"]
            if warmup_end_time <= sample["timestamp"] <= end_time
        ]

        # 计算统计指标
        def calculate_stats(data):
            if not data:
                return {"avg": 0, "max": 0, "p95": 0}
            return {"avg": np.mean(data), "max": np.max(data), "p95": np.percentile(data, 95)}

        # 计算是否超过阈值
        cpu_threshold = component_config["cpu_threshold"]
        memory_threshold = component_config["memory_threshold"]
        latency_threshold = component_config["latency_threshold"]

        cpu_exceeded = any(p > cpu_threshold for p in cpu_process_percents)
        memory_exceeded = any(p > memory_threshold for p in memory_process_percents)
        latency_exceeded = any(l > latency_threshold for l in latency_samples)

        # 生成优化建议
        recommendations = []
        if cpu_exceeded:
            recommendations.append("考虑优化算法复杂度或增加异步处理")
        if memory_exceeded:
            recommendations.append("考虑优化内存使用或增加资源限制")
        if latency_exceeded:
            recommendations.append("考虑优化代码路径或减少网络调用")

        if not recommendations:
            recommendations.append("组件性能符合预期，无需优化")

        # 保存测试结果
        component_result = {
            "component_id": component_id,
            "component_name": component_config["name"],
            "description": component_config["description"],
            "test_duration": (end_time - start_time).total_seconds(),
            "start_time": start_time,
            "end_time": end_time,
            "cpu": {
                "system": calculate_stats(cpu_system_percents),
                "process": calculate_stats(cpu_process_percents),
                "threshold": cpu_threshold,
                "exceeded": cpu_exceeded,
            },
            "memory": {
                "system": calculate_stats(memory_system_percents),
                "process": calculate_stats(memory_process_percents),
                "threshold": memory_threshold,
                "exceeded": memory_exceeded,
            },
            "latency": {
                "samples": latency_samples,
                "stats": calculate_stats(latency_samples),
                "threshold": latency_threshold,
                "exceeded": latency_exceeded,
            },
            "recommendations": recommendations,
        }

        self.perf_results.append(component_result)
        logger.info(f"组件测试完成: {json.dumps(component_result, default=str, indent=2)}")

    def run_perf_test(self, test_func: Callable, component_id: str):
        """
        运行组件性能测试

        Args:
            test_func: 测试函数，用于执行组件操作并返回延迟数据
            component_id: 组件ID
        """
        if not self.start_component_test(component_id):
            return

        try:
            # 预热期
            logger.info(f"组件 {component_id} 测试预热中...")
            warmup_end = time.time() + self.test_config["warmup_duration"]
            while time.time() < warmup_end:
                test_func()

            # 测试期
            logger.info(f"开始组件 {component_id} 正式测试...")
            test_end = time.time() + self.test_config["test_duration"]
            while time.time() < test_end:
                start_time = time.perf_counter()
                test_func()
                end_time = time.perf_counter()
                latency_ms = (end_time - start_time) * 1000
                self.record_latency(latency_ms)
        finally:
            self.end_component_test()

    def generate_perf_report(self) -> dict[str, Any]:
        """
        生成性能报告

        Returns:
            dict: 性能报告
        """
        # 生成总体性能摘要
        summary = {
            "total_components_tested": len(self.perf_results),
            "components_exceeding_thresholds": sum(
                1
                for r in self.perf_results
                if r["cpu"]["exceeded"] or r["memory"]["exceeded"] or r["latency"]["exceeded"]
            ),
            "generated_at": datetime.now(),
        }

        # 生成性能报告
        report = {
            "summary": summary,
            "test_config": self.test_config,
            "component_configs": self.component_configs,
            "perf_results": self.perf_results,
            "events": self.events,
        }

        return report

    def save_report(self, output_dir: str = "reports") -> dict[str, str]:
        """
        保存性能报告到文件

        Args:
            output_dir: 输出目录

        Returns:
            dict: 保存的报告文件路径
        """
        # 生成性能报告
        report = self.generate_perf_report()

        # 确保输出目录存在
        Path(output_dir).mkdir(exist_ok=True)

        # 生成文件名
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        # 保存JSON报告
        json_path = Path(output_dir) / f"perf_report_{timestamp}.json"
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(report, f, default=str, indent=2, ensure_ascii=False)

        # 生成并保存Markdown报告
        md_path = Path(output_dir) / f"perf_report_{timestamp}.md"
        self._generate_markdown_report(report, md_path)

        logger.info(f"性能报告已保存到 {json_path} 和 {md_path}")

        return {"json_report": str(json_path), "md_report": str(md_path)}

    def _generate_markdown_report(self, report: dict[str, Any], file_path: Path):
        """
        生成Markdown格式的性能报告

        Args:
            report: 性能报告
            file_path: 输出文件路径
        """
        lines = [
            "# 组件性能预算测试报告",
            f"\n生成时间: {report['summary']['generated_at']}",
            "\n## 测试摘要",
            "| 项目 | 值 |",
            "|------|-----|",
            f"| 测试组件数量 | {report['summary']['total_components_tested']} |",
            f"| 超过阈值组件数量 | {report['summary']['components_exceeding_thresholds']} |",
            f"| 监控间隔 | {report['test_config']['monitor_interval']}秒 |",
            f"| 测试时长 | {report['test_config']['test_duration']}秒/组件 |",
            f"| 预热时长 | {report['test_config']['warmup_duration']}秒 |",
        ]

        # 添加每个组件的测试结果
        lines.extend(
            [
                "\n## 组件性能详情",
                "| 组件ID | 组件名称 | 测试时长(秒) | 平均CPU(%) | CPU阈值(%) | 平均内存(%) | 内存阈值(%) | 平均延迟(ms) | 延迟阈值(ms) | 状态 |",
                "|--------|----------|--------------|------------|------------|-------------|-------------|--------------|--------------|------|",
            ]
        )

        for result in report["perf_results"]:
            cpu_avg = result["cpu"]["process"]["avg"]
            cpu_threshold = result["cpu"]["threshold"]
            memory_avg = result["memory"]["process"]["avg"]
            memory_threshold = result["memory"]["threshold"]
            latency_avg = result["latency"]["stats"]["avg"]
            latency_threshold = result["latency"]["threshold"]

            status = (
                "超出阈值"
                if result["cpu"]["exceeded"]
                or result["memory"]["exceeded"]
                or result["latency"]["exceeded"]
                else "正常"
            )

            lines.append(
                f"| {result['component_id']} | {result['component_name']} | {result['test_duration']:.2f} | {cpu_avg:.2f} | {cpu_threshold} | {memory_avg:.2f} | {memory_threshold} | {latency_avg:.2f} | {latency_threshold} | {status} |"
            )

        # 添加详细的组件报告
        for result in report["perf_results"]:
            lines.extend(
                [
                    f"\n### {result['component_id']} - {result['component_name']}",
                    f"**描述**: {result['description']}",
                    f"**测试时长**: {result['test_duration']:.2f}秒",
                    "\n#### CPU性能",
                    "| 指标 | 系统 | 进程 | 阈值 | 状态 |",
                    "|------|------|------|------|------|",
                    f"| 平均值 | {result['cpu']['system']['avg']:.2f}% | {result['cpu']['process']['avg']:.2f}% | {result['cpu']['threshold']}% | {'超出' if result['cpu']['exceeded'] else '正常'} |",
                    f"| 最大值 | {result['cpu']['system']['max']:.2f}% | {result['cpu']['process']['max']:.2f}% | {result['cpu']['threshold']}% | {'超出' if result['cpu']['exceeded'] else '正常'} |",
                    f"| 95分位 | {result['cpu']['system']['p95']:.2f}% | {result['cpu']['process']['p95']:.2f}% | {result['cpu']['threshold']}% | {'超出' if result['cpu']['exceeded'] else '正常'} |",
                    "\n#### 内存性能",
                    "| 指标 | 系统 | 进程 | 阈值 | 状态 |",
                    "|------|------|------|------|------|",
                    f"| 平均值 | {result['memory']['system']['avg']:.2f}% | {result['memory']['process']['avg']:.2f}% | {result['memory']['threshold']}% | {'超出' if result['memory']['exceeded'] else '正常'} |",
                    f"| 最大值 | {result['memory']['system']['max']:.2f}% | {result['memory']['process']['max']:.2f}% | {result['memory']['threshold']}% | {'超出' if result['memory']['exceeded'] else '正常'} |",
                    f"| 95分位 | {result['memory']['system']['p95']:.2f}% | {result['memory']['process']['p95']:.2f}% | {result['memory']['threshold']}% | {'超出' if result['memory']['exceeded'] else '正常'} |",
                    "\n#### 延迟性能",
                    "| 指标 | 平均值 | 最大值 | 95分位 | 阈值 | 状态 |",
                    "|------|--------|--------|--------|------|------|",
                    f"| 延迟(ms) | {result['latency']['stats']['avg']:.2f} | {result['latency']['stats']['max']:.2f} | {result['latency']['stats']['p95']:.2f} | {result['latency']['threshold']}ms | {'超出' if result['latency']['exceeded'] else '正常'} |",
                    "\n#### 优化建议",
                ]
            )

            for rec in result["recommendations"]:
                lines.append(f"- {rec}")

        # 添加事件记录
        if report["events"]:
            lines.extend(
                [
                    "\n## 事件记录",
                    "| 时间 | 组件 | 事件类型 | 严重程度 | 描述 |",
                    "|------|------|----------|----------|------|",
                ]
            )

            for event in report["events"]:
                lines.append(
                    f"| {event['timestamp']} | {event['component']} | {event['event_type']} | {event['severity']} | {event['description']} |"
                )

        # 写入文件
        with open(file_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))

    def get_perf_results(self) -> list[dict[str, Any]]:
        """
        获取性能测试结果

        Returns:
            list: 性能测试结果
        """
        return self.perf_results.copy()


# 测试代码
if __name__ == "__main__":
    # 测试性能监控器
    config = {"monitor_interval": 0.5, "test_duration": 10, "warmup_duration": 2}

    monitor = PerformanceMonitor(config)
    monitor.start_monitoring()

    try:
        # 模拟组件测试函数
        def mock_component_test():
            time.sleep(0.01)  # 模拟组件执行时间

        # 测试所有组件
        for component_id in ["0502", "0504", "0505"]:
            monitor.run_perf_test(mock_component_test, component_id)
            time.sleep(2)  # 组件间间隔
    finally:
        monitor.stop_monitoring()
        monitor.save_report()
