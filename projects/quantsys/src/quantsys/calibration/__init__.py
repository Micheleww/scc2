#!/usr/bin/env python3

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class MarketBeliefRaw:
    """
    原始市场信念数据结构
    - direction: 信念方向（如上涨/下跌）
    - magnitude: 信念强度（如概率值）
    - time: 信念生成时间
    """

    direction: float
    magnitude: float
    time: datetime
    additional_info: dict[str, Any] = field(default_factory=dict)


@dataclass
class CalibrationMeta:
    """
    校准元数据
    """

    calibrator_version: str
    calibration_time: datetime
    update_frequency: str  # 如 'daily', 'hourly', 'minute'
    fit_timestamp: datetime | None = None
    params: dict[str, Any] = field(default_factory=dict)


@dataclass
class MarketBeliefCalibrated:
    """
    校准后的市场信念数据结构
    """

    direction: float
    magnitude: float
    time: datetime
    calibration_meta: CalibrationMeta
    additional_info: dict[str, Any] = field(default_factory=dict)


@dataclass
class HealthScore:
    """
    健康评分输出结构
    - overall_health: 整体健康度，范围 [0, 1]
    - component_scores: 各组件评分
    - update_frequency: 更新频率
    """

    overall_health: float
    component_scores: dict[str, float]
    update_frequency: str
    timestamp: datetime
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        """
        确保overall_health在[0, 1]范围内
        """
        if not 0 <= self.overall_health <= 1:
            logger.warning(
                f"Overall health score {self.overall_health} out of range [0, 1], clamping to valid range"
            )
            self.overall_health = max(0, min(1, self.overall_health))


class BeliefCalibrator:
    """
    市场信念校准器
    """

    def __init__(self, update_frequency: str = "daily", calibrator_version: str = "v1"):
        """
        初始化校准器

        Args:
            update_frequency: 校准更新频率
            calibrator_version: 校准器版本
        """
        self.update_frequency = update_frequency
        self.calibrator_version = calibrator_version
        self.is_fitted = False
        self._is_realtime_mode = False
        self.calibration_params: dict[str, Any] = {}

    def set_realtime_mode(self, mode: bool):
        """
        设置是否为实时模式

        Args:
            mode: True表示实时模式，False表示回测/训练模式
        """
        self._is_realtime_mode = mode

    def fit(self, beliefs: list[MarketBeliefRaw], labels: list[Any]) -> None:
        """
        训练校准模型 - 不允许在实时路径调用

        Args:
            beliefs: 历史原始信念列表
            labels: 对应的真实结果列表

        Raises:
            RuntimeError: 如果在实时模式下调用
        """
        if self._is_realtime_mode:
            raise RuntimeError("fit() is not allowed to be called in real-time path")

        logger.info(f"Fitting belief calibrator with {len(beliefs)} samples")
        # 最小逻辑实现：仅标记为已拟合
        self.is_fitted = True
        self.calibration_params = {"fit_samples": len(beliefs), "fit_time": datetime.now()}

    def calibrate(self, belief: MarketBeliefRaw) -> MarketBeliefCalibrated:
        """
        校准单个市场信念 - 不得访问未来结果

        Args:
            belief: 原始市场信念

        Returns:
            校准后的市场信念
        """
        if not self.is_fitted:
            logger.warning("Calibrator not fitted, using default calibration")

        # 最小逻辑实现：返回校准后的信念（当前仅添加元数据）
        calibration_meta = CalibrationMeta(
            calibrator_version=self.calibrator_version,
            calibration_time=datetime.now(),
            update_frequency=self.update_frequency,
            fit_timestamp=self.calibration_params.get("fit_time"),
            params=self.calibration_params,
        )

        return MarketBeliefCalibrated(
            direction=belief.direction,
            magnitude=belief.magnitude,
            time=belief.time,
            calibration_meta=calibration_meta,
            additional_info=belief.additional_info.copy(),
        )


class BeliefScorer:
    """
    市场信念评分器
    """

    def __init__(self, update_frequency: str = "hourly"):
        """
        初始化评分器

        Args:
            update_frequency: 评分更新频率
        """
        self.update_frequency = update_frequency

    def score(self, belief: MarketBeliefCalibrated) -> HealthScore:
        """
        评估信念的可信度
        - 只评估可信度，不输出交易信号
        - 结果只能影响 risk budget / w cap，不得直接触发交易

        Args:
            belief: 校准后的市场信念

        Returns:
            健康评分
        """
        # 最小逻辑实现：基于magnitude生成健康评分
        # 假设magnitude在[0, 1]范围内
        magnitude = belief.magnitude
        component_scores = {
            "magnitude_consistency": max(0, min(1, magnitude)),
            "calibration_quality": 1.0 if belief.calibration_meta.calibrator_version else 0.5,
        }

        # 简单加权平均计算整体健康度
        overall_health = sum(component_scores.values()) / len(component_scores)

        return HealthScore(
            overall_health=overall_health,
            component_scores=component_scores,
            update_frequency=self.update_frequency,
            timestamp=datetime.now(),
            metadata={
                "belief_time": belief.time,
                "calibrator_version": belief.calibration_meta.calibrator_version,
            },
        )
