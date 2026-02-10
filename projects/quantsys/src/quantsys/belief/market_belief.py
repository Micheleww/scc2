#!/usr/bin/env python3
"""
市场信念层（MarketBelief）
实现三维概率分布结构：Raw Belief 和 Calibrated Belief
"""

from datetime import datetime
from typing import Any


class MarketBeliefRaw:
    """
    原始市场信念数据结构
    模型直接输出的概率分布
    """

    def __init__(self):
        # 方向概率分布：上涨/下跌/横盘
        self.direction: dict[str, float] = {"up": 0.0, "down": 0.0, "flat": 0.0}

        # 幅度概率分布：小/中/大
        self.magnitude: dict[str, float] = {"small": 0.0, "medium": 0.0, "large": 0.0}

        # 时间概率分布：短/中/长
        self.time: dict[str, float] = {"short": 0.0, "medium": 0.0, "long": 0.0}

    def validate(self) -> bool:
        """
        验证概率分布是否合法（各维度概率和为1）
        """
        direction_sum = sum(self.direction.values())
        magnitude_sum = sum(self.magnitude.values())
        time_sum = sum(self.time.values())

        # 允许一定的浮点数误差
        tolerance = 1e-6
        return (
            abs(direction_sum - 1.0) < tolerance
            and abs(magnitude_sum - 1.0) < tolerance
            and abs(time_sum - 1.0) < tolerance
        )


class HealthScore:
    """
    信念健康度评分
    """

    def __init__(self):
        self.direction: float = 0.0  # 方向维度健康度 [0, 1]
        self.magnitude: float = 0.0  # 幅度维度健康度 [0, 1]
        self.time: float = 0.0  # 时间维度健康度 [0, 1]
        self.overall_health: float = 0.0  # 综合健康度 [0, 1]

    def validate(self) -> bool:
        """
        验证健康度评分是否合法
        """
        return (
            0.0 <= self.direction <= 1.0
            and 0.0 <= self.magnitude <= 1.0
            and 0.0 <= self.time <= 1.0
            and 0.0 <= self.overall_health <= 1.0
        )


class CalibrationMeta:
    """
    校准元数据
    """

    def __init__(self):
        self.calibrator_id: str = ""
        self.calibration_window: int = 0  # 校准窗口大小
        self.timestamp: datetime = datetime.now()  # 校准时间戳


class MarketBeliefCalibrated:
    """
    校准后的市场信念数据结构
    包含校准元数据和健康度评分
    """

    def __init__(self):
        self.belief: MarketBeliefRaw = MarketBeliefRaw()  # 原始信念
        self.calibration_meta: CalibrationMeta = CalibrationMeta()  # 校准元数据
        self.health_score: HealthScore = HealthScore()  # 健康度评分

    def validate(self) -> bool:
        """
        验证校准后的信念是否合法
        """
        return self.belief.validate() and self.health_score.validate()


class StateLabel:
    """
    状态标签枚举
    """

    RANGE = "RANGE"
    TRANSITION = "TRANSITION"
    TREND = "TREND"
    SHOCK = "SHOCK"


def compute_raw_belief(features: dict[str, Any]) -> MarketBeliefRaw:
    """
    基于特征生成原始市场信念

    Args:
        features: 标准化特征

    Returns:
        MarketBeliefRaw: 原始三维概率分布
    """
    belief = MarketBeliefRaw()

    # 基于特征数据计算方向概率分布
    direction_score = 0.0
    total_weight = 0.0
    
    # 计算方向得分（综合考虑所有因子）
    for factor_name, factor_value in features.items():
        # 跳过非数值因子
        if isinstance(factor_value, (int, float)):
            direction_score += factor_value
            total_weight += 1.0
    
    # 归一化方向得分到[-1, 1]范围
    if total_weight > 0:
        normalized_score = direction_score / total_weight
        normalized_score = max(-1.0, min(1.0, normalized_score))
    else:
        normalized_score = 0.0
    
    # 基于归一化得分计算方向概率
    up_prob = (normalized_score + 1.0) / 3.0
    down_prob = (1.0 - normalized_score) / 3.0
    flat_prob = 1.0 - up_prob - down_prob
    
    # 确保概率和为1.0
    total_dir_prob = up_prob + down_prob + flat_prob
    belief.direction = {
        "up": up_prob / total_dir_prob,
        "down": down_prob / total_dir_prob,
        "flat": flat_prob / total_dir_prob
    }

    # 基于方向得分计算幅度概率分布
    magnitude_score = abs(normalized_score)
    belief.magnitude = {
        "small": max(0.1, 1.0 - magnitude_score * 2),
        "medium": max(0.0, magnitude_score * 2 - 0.5),
        "large": max(0.0, magnitude_score * 2 - 1.5)
    }
    
    # 归一化幅度概率
    total_mag_prob = sum(belief.magnitude.values())
    for key in belief.magnitude:
        belief.magnitude[key] /= total_mag_prob

    # 基于因子数量计算时间概率分布
    factor_count = len(features)
    if factor_count < 5:
        # 因子数量少，短期概率高
        belief.time = {"short": 0.6, "medium": 0.3, "long": 0.1}
    elif factor_count < 10:
        # 因子数量中等，中期概率高
        belief.time = {"short": 0.3, "medium": 0.6, "long": 0.1}
    else:
        # 因子数量多，长期概率高
        belief.time = {"short": 0.1, "medium": 0.3, "long": 0.6}

    return belief


def generate_belief_from_factors(factors: dict[str, Any]) -> MarketBeliefRaw:
    """
    从因子数据生成原始市场信念

    Args:
        factors: 因子数据

    Returns:
        MarketBeliefRaw: 原始三维概率分布
    """
    # 调用核心信念计算函数
    return compute_raw_belief(factors)


def compress_belief_to_weight(belief: MarketBeliefRaw) -> float:
    """
    将市场信念压缩为连续权重 w ∈ [0, 1]
    用于风险预算计算和策略生成

    Args:
        belief: 原始三维概率分布

    Returns:
        float: 连续权重值
    """
    # 方向权重：上涨和下跌的差值，转换为 [0, 1] 范围
    direction_weight = abs(belief.direction["up"] - belief.direction["down"])
    
    # 幅度权重：大中小幅度的加权平均，转换为 [0, 1] 范围
    magnitude_weight = (
        belief.magnitude["small"] * 0.3 + 
        belief.magnitude["medium"] * 0.5 + 
        belief.magnitude["large"] * 0.8
    )
    
    # 时间权重：短中长期的加权平均，转换为 [0, 1] 范围
    time_weight = (
        belief.time["short"] * 0.3 + 
        belief.time["medium"] * 0.5 + 
        belief.time["long"] * 0.8
    )
    
    # 综合权重：三个维度的加权平均，确保在 [0, 1] 范围内
    combined_weight = (direction_weight * 0.5 + magnitude_weight * 0.3 + time_weight * 0.2)
    
    # 应用非线性转换，增强置信度高的信念
    compressed_weight = combined_weight ** 2
    
    # 确保最终权重在 [0, 1] 范围内
    return max(0.0, min(1.0, compressed_weight))
