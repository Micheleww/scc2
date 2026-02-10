#!/usr/bin/env python3
"""
状态评估与权重压缩模块
将校准后的信念压缩为风险强度旋钮 w
"""

from ..belief.market_belief import MarketBeliefCalibrated, StateLabel


class WeightEstimator:
    """
    权重估计器
    将校准后的信念压缩为风险强度 w
    """

    def __init__(self, w_min: float = 0.1, hysteresis_threshold: float = 0.05):
        """
        初始化权重估计器

        Args:
            w_min: 参与交易的最小 w 值
            hysteresis_threshold: 状态切换的迟滞阈值
        """
        self.w_min = w_min
        self.hysteresis_threshold = hysteresis_threshold
        self.previous_state = StateLabel.RANGE

    def compute_w(self, calibrated_belief: MarketBeliefCalibrated) -> float:
        """
        基于校准后的信念计算风险强度 w

        Args:
            calibrated_belief: 校准后的信念

        Returns:
            float: 风险强度 w ∈ [0, 1]
        """
        if not calibrated_belief.validate():
            raise ValueError("Invalid MarketBeliefCalibrated: Validation failed")

        # 1. 从校准后的信念中提取三维概率分布
        belief = calibrated_belief.belief
        health_score = calibrated_belief.health_score

        # 2. 计算方向强度：(up - down) 范围 [-1, 1]
        direction_strength = belief.direction["up"] - belief.direction["down"]

        # 3. 计算幅度强度：(large + 0.5*medium) 范围 [0, 1]
        magnitude_strength = belief.magnitude["large"] + 0.5 * belief.magnitude["medium"]

        # 4. 计算时间强度：(long + 0.5*medium) 范围 [0, 1]
        time_strength = belief.time["long"] + 0.5 * belief.time["medium"]

        # 5. 综合强度，考虑置信度和健康度
        raw_strength = abs(direction_strength) * magnitude_strength * time_strength

        # 6. 应用健康度评分进行风险调整
        # 健康度只能降低风险，不能放大
        adjusted_strength = raw_strength * health_score.overall_health

        # 7. 归一化到 [0, 1] 范围
        w = max(0.0, min(1.0, adjusted_strength))

        return w

    def label_from_w(self, w: float) -> str:
        """
        基于 w 值生成解释性状态标签，包含迟滞效应

        Args:
            w: 风险强度

        Returns:
            str: 状态标签（RANGE/TRANSITION/TREND/SHOCK）
        """
        current_label = self.previous_state

        # 应用迟滞效应的状态转换逻辑
        if self.previous_state == StateLabel.RANGE:
            if w > 0.6 + self.hysteresis_threshold:
                current_label = StateLabel.TREND
            elif w > 0.4:
                current_label = StateLabel.TRANSITION
        elif self.previous_state == StateLabel.TRANSITION:
            if w > 0.6 + self.hysteresis_threshold:
                current_label = StateLabel.TREND
            elif w < 0.4 - self.hysteresis_threshold:
                current_label = StateLabel.RANGE
        elif self.previous_state == StateLabel.TREND:
            if w < 0.6 - self.hysteresis_threshold:
                current_label = StateLabel.TRANSITION
            elif w < 0.4 - self.hysteresis_threshold:
                current_label = StateLabel.RANGE

        # 更新前一状态
        self.previous_state = current_label

        return current_label

    def should_participate(self, w: float) -> bool:
        """
        决定是否参与交易

        Args:
            w: 风险强度

        Returns:
            bool: 是否参与交易
        """
        return w >= self.w_min


def compute_state_and_weight(
    calibrated_belief: MarketBeliefCalibrated, weight_estimator: WeightEstimator
) -> tuple[float, str, bool]:
    """
    计算状态和权重的统一接口

    Args:
        calibrated_belief: 校准后的信念
        weight_estimator: 权重估计器实例

    Returns:
        Tuple[float, str, bool]: (w, state_label, should_participate)
    """
    # 1. 计算 w
    w = weight_estimator.compute_w(calibrated_belief)

    # 2. 生成状态标签
    state_label = weight_estimator.label_from_w(w)

    # 3. 决定是否参与
    participate = weight_estimator.should_participate(w)

    return w, state_label, participate


def create_weight_estimator() -> WeightEstimator:
    """
    创建权重估计器实例

    Returns:
        WeightEstimator: 权重估计器实例
    """
    return WeightEstimator(w_min=0.1, hysteresis_threshold=0.05)
