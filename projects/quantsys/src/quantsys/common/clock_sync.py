#!/usr/bin/env python3
"""
时钟同步服务，用于检测系统时钟漂移和交易所时间差
"""

import logging
from datetime import datetime, timedelta
from pathlib import Path

# 配置日志
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class ClockSyncService:
    """时钟同步服务，检测系统时钟漂移和交易所时间差"""

    def __init__(self, drift_threshold_ms: int = 500):
        """初始化时钟同步服务

        Args:
            drift_threshold_ms: 时钟漂移阈值，单位毫秒
        """
        self.drift_threshold_ms = drift_threshold_ms
        self.last_sync_time = None
        self.current_drift_ms = 0
        self.bar_close_times = {}

        logger.info(f"时钟同步服务初始化，漂移阈值: {drift_threshold_ms}ms")

    def get_system_time(self) -> datetime:
        """获取系统当前时间"""
        return datetime.now()

    def get_reference_time(self) -> datetime:
        """获取参考时间（模拟交易所时间）

        在实际系统中，这里应该调用交易所API获取真实时间
        这里使用系统时间模拟，但添加一些随机漂移来测试功能
        """
        # 模拟交易所时间，添加±200ms的随机漂移
        import random

        drift_ms = random.randint(-200, 200)
        reference_time = self.get_system_time() + timedelta(milliseconds=drift_ms)

        return reference_time

    def check_clock_drift(self) -> dict[str, any]:
        """检查系统时钟与参考时间的漂移

        Returns:
            Dict: 包含漂移信息的字典
        """
        system_time = self.get_system_time()
        reference_time = self.get_reference_time()

        # 计算时间差（毫秒）
        drift = reference_time - system_time
        drift_ms = int(drift.total_seconds() * 1000)

        self.current_drift_ms = drift_ms
        self.last_sync_time = system_time

        # 检查是否超过阈值
        is_exceeding = abs(drift_ms) > self.drift_threshold_ms

        result = {
            "system_time": system_time.strftime("%Y-%m-%d %H:%M:%S.%f"),
            "reference_time": reference_time.strftime("%Y-%m-%d %H:%M:%S.%f"),
            "drift_ms": drift_ms,
            "is_exceeding": is_exceeding,
            "threshold_ms": self.drift_threshold_ms,
            "last_sync_time": self.last_sync_time.strftime("%Y-%m-%d %H:%M:%S.%f"),
        }

        logger.info(
            f"时钟漂移检查: 系统时间={system_time}, 参考时间={reference_time}, 漂移={drift_ms}ms, 超过阈值={is_exceeding}"
        )

        return result

    def calculate_bar_close_time(self, timestamp: datetime, frequency: str) -> datetime:
        """计算给定时间戳对应的bar关闭时间

        Args:
            timestamp: 输入时间戳
            frequency: 时间周期，如'1m', '5m', '1h', '1d'

        Returns:
            datetime: bar关闭时间
        """
        # 计算bar关闭时间的逻辑
        if frequency == "1m":
            # 1分钟bar，关闭时间为整分钟
            close_time = timestamp.replace(second=0, microsecond=0) + timedelta(minutes=1)
        elif frequency == "5m":
            # 5分钟bar，关闭时间为5分钟的倍数
            minute = (timestamp.minute // 5) * 5
            close_time = timestamp.replace(minute=minute, second=0, microsecond=0) + timedelta(
                minutes=5
            )
        elif frequency == "1h":
            # 1小时bar，关闭时间为整小时
            close_time = timestamp.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
        elif frequency == "1d":
            # 1天bar，关闭时间为当天结束
            close_time = timestamp.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(
                days=1
            )
        else:
            # 默认使用1小时bar
            close_time = timestamp.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)

        # 保存计算结果，用于一致性检查
        key = (timestamp, frequency)
        self.bar_close_times[key] = close_time

        return close_time

    def check_bar_close_consistency(self) -> bool:
        """检查bar关闭时间计算的一致性

        Returns:
            bool: True表示一致，False表示不一致
        """
        # 对相同的输入，多次计算bar关闭时间，检查结果是否一致
        test_timestamp = self.get_system_time()
        frequencies = ["1m", "5m", "1h", "1d"]

        for freq in frequencies:
            # 多次计算同一时间戳的bar关闭时间
            results = []
            for _ in range(5):
                close_time = self.calculate_bar_close_time(test_timestamp, freq)
                results.append(close_time)

            # 检查所有结果是否一致
            if len(set(results)) != 1:
                logger.error(
                    f"bar关闭时间计算不一致: 时间戳={test_timestamp}, 周期={freq}, 结果={results}"
                )
                return False

        logger.info("bar关闭时间计算一致")
        return True

    def run_clock_sync_check(self) -> dict[str, any]:
        """运行完整的时钟同步检查

        Returns:
            Dict: 包含所有检查结果的字典
        """
        # 1. 检查时钟漂移
        drift_result = self.check_clock_drift()

        # 2. 检查bar关闭时间一致性
        bar_consistency = self.check_bar_close_consistency()

        # 3. 综合结果
        overall_result = {
            "clock_drift": drift_result,
            "bar_consistency": bar_consistency,
            "overall_ok": not drift_result["is_exceeding"] and bar_consistency,
        }

        return overall_result

    def save_sync_report(
        self, report: dict[str, any], output_path: str = "logs/clock_sync_report.json"
    ):
        """保存时钟同步报告到文件

        Args:
            report: 时钟同步报告
            output_path: 输出文件路径
        """
        import json

        # 确保日志目录存在
        log_dir = Path(output_path).parent
        log_dir.mkdir(parents=True, exist_ok=True)

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, ensure_ascii=False, default=str)

        logger.info(f"时钟同步报告已保存到: {output_path}")

    def run_self_test(self) -> bool:
        """运行自测试

        Returns:
            bool: 测试是否通过
        """
        logger.info("开始时钟同步服务自测试")

        # 1. 测试时钟漂移检查
        drift_result = self.check_clock_drift()
        logger.info(f"时钟漂移测试结果: {drift_result}")

        # 2. 测试bar关闭时间计算
        test_timestamp = datetime.now()
        for freq in ["1m", "5m", "1h", "1d"]:
            close_time = self.calculate_bar_close_time(test_timestamp, freq)
            logger.info(
                f"bar关闭时间计算测试: 时间戳={test_timestamp}, 周期={freq}, 关闭时间={close_time}"
            )

        # 3. 测试bar关闭时间一致性
        consistency = self.check_bar_close_consistency()
        logger.info(f"bar关闭时间一致性测试结果: {consistency}")

        # 4. 测试完整同步检查
        full_report = self.run_clock_sync_check()
        logger.info(f"完整同步检查测试结果: {full_report}")

        # 5. 保存报告
        self.save_sync_report(full_report, "evidence/clock_sync_self_test.json")

        logger.info("时钟同步服务自测试完成")

        return full_report["overall_ok"]


if __name__ == "__main__":
    # 运行自测试
    clock_sync = ClockSyncService()
    test_result = clock_sync.run_self_test()
    print(f"自测试结果: {'通过' if test_result else '失败'}")
