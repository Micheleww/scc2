#!/usr/bin/env python3
"""
因子调度器，按frequency/lag刷新特征，确保策略只使用当期可用数据
"""

import logging
from datetime import datetime, timedelta

import numpy as np
import pandas as pd

from src.quantsys.data.availability import DataAvailability
from src.quantsys.factors.factor_registry import FactorRegistry

# 配置日志
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class FactorRefreshStatus:
    """
    因子刷新状态
    """

    def __init__(
        self, factor_code: str, last_refreshed: datetime, is_available: bool, lag_status: str
    ):
        self.factor_code = factor_code
        self.last_refreshed = last_refreshed
        self.is_available = is_available
        self.lag_status = lag_status  # current, delayed, missing
        self.refresh_count = 0
        self.error_count = 0


class FactorScheduler:
    """
    因子调度器，管理因子的刷新和可用性
    """

    def __init__(self, registry_path: str = None):
        """
        初始化因子调度器

        Args:
            registry_path: 因子注册表路径
        """
        self.registry = FactorRegistry(registry_path)
        self.data_availability = DataAvailability()
        self.refresh_status: dict[str, FactorRefreshStatus] = {}
        self.factor_data: dict[str, pd.DataFrame] = {}
        self.current_timestamp: datetime | None = None

        # 检查注册表是否为空，如果为空则添加默认因子
        if len(self.registry.list_registered()) == 0:
            self._add_default_factors()

        # 初始化刷新状态
        self._initialize_refresh_status()

        logger.info("因子调度器初始化完成")

    def _add_default_factors(self):
        """
        添加默认因子到注册表
        """
        default_factors = [
            {
                "code": "ma",
                "name": "移动平均线",
                "version": "1.0.0",
                "type": "price",
                "description": "简单移动平均线",
                "dependencies": [],
                "frequency": "1h",
                "window": "20",
                "lag": 0,
                "availability_lag": 0,
                "output_columns": ["value"],
                "missing_strategy": "fill",
                "standardized": False,
                "availability": True,
                "input_fields": ["close"],
                "output_range": "[-inf, inf]",
            },
            {
                "code": "rsi",
                "name": "相对强弱指标",
                "version": "1.0.0",
                "type": "momentum",
                "description": "相对强弱指标",
                "dependencies": [],
                "frequency": "1h",
                "window": "14",
                "lag": 0,
                "availability_lag": 0,
                "output_columns": ["value"],
                "missing_strategy": "fill",
                "standardized": False,
                "availability": True,
                "input_fields": ["close"],
                "output_range": "[0, 100]",
            },
            {
                "code": "macd",
                "name": "移动平均收敛发散",
                "version": "1.0.0",
                "type": "momentum",
                "description": "移动平均收敛发散指标",
                "dependencies": [],
                "frequency": "1h",
                "window": "26",
                "lag": 0,
                "availability_lag": 0,
                "output_columns": ["macd", "signal", "histogram"],
                "missing_strategy": "fill",
                "standardized": False,
                "availability": True,
                "input_fields": ["close"],
                "output_range": "[-inf, inf]",
            },
        ]

        for factor_data in default_factors:
            try:
                self.registry.register_factor(factor_data)
                logger.info(f"添加默认因子: {factor_data['code']}")
            except Exception as e:
                logger.error(f"添加默认因子 {factor_data['code']} 失败: {e}")

    def _initialize_refresh_status(self):
        """
        初始化因子刷新状态
        """
        for factor_code in self.registry.list_registered():
            try:
                spec = self.registry.get_spec(factor_code)
                self.refresh_status[factor_code] = FactorRefreshStatus(
                    factor_code=factor_code,
                    last_refreshed=datetime.now() - timedelta(days=1),  # 初始化为昨天
                    is_available=False,
                    lag_status="missing",
                )
            except Exception as e:
                logger.error(f"初始化因子 {factor_code} 状态失败: {e}")

    def set_current_timestamp(self, timestamp: datetime):
        """
        设置当前时间戳

        Args:
            timestamp: 当前时间戳
        """
        self.current_timestamp = timestamp
        logger.info(f"当前时间戳设置为: {timestamp}")

    def get_frequency_timedelta(self, frequency: str) -> timedelta:
        """
        将频率字符串转换为timedelta

        Args:
            frequency: 频率字符串，如'1m', '5m', '1h', '1d'

        Returns:
            timedelta: 对应的时间差
        """
        frequency_map = {
            "1m": timedelta(minutes=1),
            "5m": timedelta(minutes=5),
            "15m": timedelta(minutes=15),
            "30m": timedelta(minutes=30),
            "1h": timedelta(hours=1),
            "4h": timedelta(hours=4),
            "1d": timedelta(days=1),
            "1w": timedelta(weeks=1),
        }

        return frequency_map.get(frequency, timedelta(hours=1))  # 默认1小时

    def should_refresh_factor(self, factor_code: str) -> bool:
        """
        判断因子是否需要刷新

        Args:
            factor_code: 因子代码

        Returns:
            bool: 是否需要刷新
        """
        if factor_code not in self.refresh_status:
            return False

        try:
            spec = self.registry.get_spec(factor_code)
            status = self.refresh_status[factor_code]

            # 计算下次刷新时间
            freq_delta = self.get_frequency_timedelta(spec.frequency)
            next_refresh_time = status.last_refreshed + freq_delta

            # 如果当前时间超过下次刷新时间，需要刷新
            return self.current_timestamp >= next_refresh_time
        except Exception as e:
            logger.error(f"判断因子 {factor_code} 是否需要刷新失败: {e}")
            return False

    def refresh_factor(self, factor_code: str) -> bool:
        """
        刷新单个因子

        Args:
            factor_code: 因子代码

        Returns:
            bool: 刷新是否成功
        """
        if not self.current_timestamp:
            logger.error("当前时间戳未设置，无法刷新因子")
            return False

        try:
            spec = self.registry.get_spec(factor_code)
            status = self.refresh_status[factor_code]

            logger.info(f"刷新因子: {factor_code}, 当前时间: {self.current_timestamp}")

            # 检查依赖项是否需要刷新
            for dep_code in spec.dependencies:
                if (
                    dep_code not in self.refresh_status
                    or not self.refresh_status[dep_code].is_available
                ):
                    logger.warning(f"因子 {factor_code} 的依赖 {dep_code} 不可用，跳过刷新")
                    return False

            # 模拟因子计算（实际实现中应调用因子计算引擎）
            # 生成模拟数据
            np.random.seed(42)
            dates = pd.date_range(end=self.current_timestamp, periods=100, freq=spec.frequency)
            data = pd.DataFrame({"value": np.random.randn(100), "timestamp": dates}).set_index(
                "timestamp"
            )

            # 保存因子数据
            self.factor_data[factor_code] = data

            # 更新刷新状态
            status.last_refreshed = self.current_timestamp
            status.refresh_count += 1

            # 检查因子是否在滞后范围内
            lag_delta = self.get_frequency_timedelta(spec.frequency) * spec.lag
            cutoff_time = self.current_timestamp - lag_delta

            if data.index.max() <= cutoff_time:
                status.is_available = True
                status.lag_status = "current"
            else:
                status.is_available = True
                status.lag_status = "delayed"

            logger.info(f"因子 {factor_code} 刷新成功，状态: {status.lag_status}")
            return True

        except Exception as e:
            logger.error(f"刷新因子 {factor_code} 失败: {e}")
            if factor_code in self.refresh_status:
                self.refresh_status[factor_code].error_count += 1
                self.refresh_status[factor_code].is_available = False
                self.refresh_status[factor_code].lag_status = "missing"
            return False

    def refresh_all_factors(self):
        """
        刷新所有需要刷新的因子
        """
        if not self.current_timestamp:
            logger.error("当前时间戳未设置，无法刷新因子")
            return

        logger.info("开始刷新所有需要刷新的因子")

        for factor_code in self.registry.list_registered():
            if self.should_refresh_factor(factor_code):
                self.refresh_factor(factor_code)

        logger.info("因子刷新完成")

    def get_available_factors(self) -> list[str]:
        """
        获取当前可用的因子列表

        Returns:
            List[str]: 可用因子列表
        """
        return [code for code, status in self.refresh_status.items() if status.is_available]

    def get_factor_data(
        self, factor_code: str, check_availability: bool = True
    ) -> pd.DataFrame | None:
        """
        获取因子数据，可选检查可用性

        Args:
            factor_code: 因子代码
            check_availability: 是否检查可用性

        Returns:
            Optional[pd.DataFrame]: 因子数据，如果不可用则返回None
        """
        if check_availability:
            if (
                factor_code not in self.refresh_status
                or not self.refresh_status[factor_code].is_available
            ):
                logger.warning(f"因子 {factor_code} 不可用，返回None")
                return None

        return self.factor_data.get(factor_code)

    def create_availability_mask_for_strategy(self, factor_codes: list[str]) -> pd.Series:
        """
        为策略创建因子可用性掩码

        Args:
            factor_codes: 策略使用的因子列表

        Returns:
            pd.Series: 可用性掩码，True表示所有因子都可用
        """
        if not factor_codes:
            return pd.Series([True])

        # 获取所有因子的最新数据时间戳
        all_timestamps = []
        for factor_code in factor_codes:
            data = self.get_factor_data(factor_code, check_availability=False)
            if data is not None and not data.empty:
                all_timestamps.append(data.index)

        if not all_timestamps:
            return pd.Series([False])

        # 合并所有时间戳
        combined_timestamps = (
            pd.concat([pd.Series(ts) for ts in all_timestamps]).sort_values().drop_duplicates()
        )

        # 检查每个因子在每个时间点的可用性
        masks = []
        for factor_code in factor_codes:
            data = self.get_factor_data(factor_code, check_availability=False)
            if data is not None and not data.empty:
                spec = self.registry.get_spec(factor_code)
                # 计算滞后时间
                lag_delta = self.get_frequency_timedelta(spec.frequency) * spec.lag

                # 创建因子的可用性掩码
                mask = pd.Series(False, index=combined_timestamps)
                for ts in combined_timestamps:
                    # 检查该时间点的数据是否在滞后范围内
                    cutoff_time = ts - lag_delta
                    if not data[data.index <= cutoff_time].empty:
                        mask.loc[ts] = True
                masks.append(mask)

        if not masks:
            return pd.Series([False])

        # 合并所有掩码，只有所有因子都可用才为True
        unified_mask = masks[0]
        for mask in masks[1:]:
            unified_mask = unified_mask & mask

        return unified_mask

    def filter_strategy_data(
        self, strategy_factors: list[str], include_unavailable: bool = False
    ) -> dict[str, pd.DataFrame]:
        """
        为策略过滤可用的因子数据

        Args:
            strategy_factors: 策略使用的因子列表
            include_unavailable: 是否包含不可用因子

        Returns:
            Dict[str, pd.DataFrame]: 过滤后的因子数据
        """
        filtered_data = {}

        for factor_code in strategy_factors:
            if include_unavailable:
                data = self.get_factor_data(factor_code, check_availability=False)
                if data is not None:
                    filtered_data[factor_code] = data
            else:
                data = self.get_factor_data(factor_code, check_availability=True)
                if data is not None:
                    filtered_data[factor_code] = data

        # 检查是否所有因子都可用
        if len(filtered_data) != len(strategy_factors):
            missing_factors = set(strategy_factors) - set(filtered_data.keys())
            logger.warning(f"策略所需因子 {missing_factors} 不可用")

        return filtered_data

    def get_refresh_status_report(self) -> pd.DataFrame:
        """
        获取刷新状态报告

        Returns:
            pd.DataFrame: 刷新状态报告
        """
        report_data = []

        for factor_code, status in self.refresh_status.items():
            try:
                spec = self.registry.get_spec(factor_code)
                report_data.append(
                    {
                        "factor_code": factor_code,
                        "frequency": spec.frequency,
                        "lag": spec.lag,
                        "last_refreshed": status.last_refreshed,
                        "is_available": status.is_available,
                        "lag_status": status.lag_status,
                        "refresh_count": status.refresh_count,
                        "error_count": status.error_count,
                    }
                )
            except Exception as e:
                logger.error(f"生成因子 {factor_code} 状态报告失败: {e}")

        return pd.DataFrame(report_data)

    def validate_strategy_factors(self, strategy_factors: list[str]) -> tuple[bool, list[str]]:
        """
        验证策略使用的因子是否可用

        Args:
            strategy_factors: 策略使用的因子列表

        Returns:
            Tuple[bool, List[str]]: (是否所有因子都可用, 不可用因子列表)
        """
        unavailable_factors = []

        for factor_code in strategy_factors:
            if (
                factor_code not in self.refresh_status
                or not self.refresh_status[factor_code].is_available
            ):
                unavailable_factors.append(factor_code)

        return len(unavailable_factors) == 0, unavailable_factors

    def handle_missing_data(
        self, strategy_factors: list[str], action: str = "block"
    ) -> dict[str, pd.DataFrame]:
        """
        处理缺失数据

        Args:
            strategy_factors: 策略使用的因子列表
            action: 处理方式，"block"或"downgrade"

        Returns:
            Dict[str, pd.DataFrame]: 处理后的因子数据
        """
        if action == "block":
            # 阻断策略执行，只返回可用因子
            return self.filter_strategy_data(strategy_factors, include_unavailable=False)
        elif action == "downgrade":
            # 降级处理，返回所有可用因子，即使部分缺失
            return self.filter_strategy_data(strategy_factors, include_unavailable=True)
        else:
            logger.error(f"未知的缺失数据处理方式: {action}")
            return {}


class StrategyScheduler:
    """
    策略调度器，管理策略的因子使用
    """

    def __init__(self, factor_scheduler: FactorScheduler):
        """
        初始化策略调度器

        Args:
            factor_scheduler: 因子调度器实例
        """
        self.factor_scheduler = factor_scheduler
        self.strategy_factors: dict[str, list[str]] = {}  # 策略名称到因子列表的映射

        logger.info("策略调度器初始化完成")

    def register_strategy(self, strategy_name: str, factors: list[str]):
        """
        注册策略及其使用的因子

        Args:
            strategy_name: 策略名称
            factors: 策略使用的因子列表
        """
        self.strategy_factors[strategy_name] = factors
        logger.info(f"策略 {strategy_name} 注册完成，使用因子: {factors}")

    def get_strategy_available_factors(self, strategy_name: str) -> list[str]:
        """
        获取策略可用的因子列表

        Args:
            strategy_name: 策略名称

        Returns:
            List[str]: 可用因子列表
        """
        if strategy_name not in self.strategy_factors:
            logger.error(f"策略 {strategy_name} 未注册")
            return []

        factors = self.strategy_factors[strategy_name]
        available_factors = [
            f
            for f in factors
            if f in self.factor_scheduler.refresh_status
            and self.factor_scheduler.refresh_status[f].is_available
        ]

        return available_factors

    def get_strategy_data(
        self, strategy_name: str, missing_action: str = "block"
    ) -> dict[str, pd.DataFrame]:
        """
        获取策略可用的因子数据

        Args:
            strategy_name: 策略名称
            missing_action: 缺失数据处理方式，"block"或"downgrade"

        Returns:
            Dict[str, pd.DataFrame]: 可用的因子数据
        """
        if strategy_name not in self.strategy_factors:
            logger.error(f"策略 {strategy_name} 未注册")
            return {}

        factors = self.strategy_factors[strategy_name]

        # 检查因子是否都可用
        all_available, unavailable = self.factor_scheduler.validate_strategy_factors(factors)

        if not all_available:
            logger.warning(f"策略 {strategy_name} 的因子 {unavailable} 不可用")

            if missing_action == "block":
                logger.info(f"阻断策略 {strategy_name} 执行")
                return {}
            elif missing_action == "downgrade":
                logger.info(f"降级策略 {strategy_name} 执行，使用可用因子")

        return self.factor_scheduler.handle_missing_data(factors, action=missing_action)

    def run_strategy_cycle(self, strategy_name: str, missing_action: str = "block") -> bool:
        """
        运行策略周期

        Args:
            strategy_name: 策略名称
            missing_action: 缺失数据处理方式

        Returns:
            bool: 策略是否成功执行
        """
        logger.info(f"开始策略 {strategy_name} 周期")

        # 1. 刷新所有因子
        self.factor_scheduler.refresh_all_factors()

        # 2. 获取策略可用数据
        strategy_data = self.get_strategy_data(strategy_name, missing_action=missing_action)

        if not strategy_data:
            logger.error(f"策略 {strategy_name} 无可可用因子数据，执行失败")
            return False

        # 3. 检查数据可用性掩码
        factors = self.strategy_factors[strategy_name]
        availability_mask = self.factor_scheduler.create_availability_mask_for_strategy(factors)

        if not availability_mask.any():
            logger.error(f"策略 {strategy_name} 无可用数据时间点，执行失败")
            return False

        # 4. 模拟策略执行
        logger.info(f"策略 {strategy_name} 执行成功，使用因子: {list(strategy_data.keys())}")
        logger.info(f"可用数据时间点数量: {availability_mask.sum()}")

        return True

    def get_strategy_status_report(self) -> pd.DataFrame:
        """
        获取策略状态报告

        Returns:
            pd.DataFrame: 策略状态报告
        """
        report_data = []

        for strategy_name, factors in self.strategy_factors.items():
            available_factors = self.get_strategy_available_factors(strategy_name)
            all_available, unavailable = self.factor_scheduler.validate_strategy_factors(factors)

            report_data.append(
                {
                    "strategy_name": strategy_name,
                    "total_factors": len(factors),
                    "available_factors": len(available_factors),
                    "unavailable_factors": len(unavailable),
                    "status": "available" if all_available else "unavailable",
                }
            )

        return pd.DataFrame(report_data)
