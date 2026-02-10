#!/usr/bin/env python3
"""
ETH永续专属风险守护模块
实现资金费率和强平风险监控
"""

import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any

from ..models.liquidation_model import LiquidationModel
from ..models.margin_model import MarginModel, MarginState

# 配置日志
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


@dataclass
class PerpRiskGuardConfig:
    """
    永续风险守护配置
    """

    # 资金费率相关配置
    max_absolute_funding_rate: float = 0.0015  # 最大绝对资金费率 (0.15%)
    max_long_funding_rate: float = 0.001  # 多头最大资金费率 (0.1%)
    max_short_funding_rate: float = -0.001  # 空头最大资金费率 (-0.1%)
    block_new_positions_on_high_funding: bool = True  # 高资金费率时是否禁止新开仓
    reduce_positions_on_high_funding: bool = False  # 高资金费率时是否降低仓位

    # 强平价格距离相关配置
    safe_distance_threshold: float = 0.05  # 安全距离阈值 (5%)
    emergency_distance_threshold: float = 0.02  # 紧急距离阈值 (2%)
    safe_stop_on_emergency: bool = True  # 紧急距离时是否执行SAFE_STOP
    block_new_positions_on_close_liquidation: bool = True  # 强平价格过近时是否禁止新开仓
    block_add_positions_on_close_liquidation: bool = True  # 强平价格过近时是否禁止加仓

    # 输出配置
    output_path: str = "perp_risk_guard.json"
    check_interval_seconds: int = 60  # 检查间隔（秒）


@dataclass
class PerpRiskGuardResult:
    """
    永续风险守护结果
    """

    # 基本信息
    timestamp: float = field(default_factory=time.time)
    symbol: str = "ETH-USDT"

    # 资金费率信息
    current_funding_rate: float = 0.0
    funding_rate_block_new: bool = False
    funding_rate_reduce: bool = False

    # 强平价格信息
    current_price: float = 0.0
    liquidation_price: float = 0.0
    distance_to_liquidation: float = 0.0
    distance_ratio: float = 0.0
    safe_stop_triggered: bool = False
    block_new_positions: bool = False
    block_add_positions: bool = False

    # 决策结果
    allow_open: bool = True
    allow_add: bool = True
    allow_reduce: bool = True
    recommended_action: str = ""

    def to_dict(self) -> dict[str, Any]:
        """转换为字典格式"""
        return {
            "timestamp": self.timestamp,
            "symbol": self.symbol,
            "current_funding_rate": self.current_funding_rate,
            "funding_rate_block_new": self.funding_rate_block_new,
            "funding_rate_reduce": self.funding_rate_reduce,
            "current_price": self.current_price,
            "liquidation_price": self.liquidation_price,
            "distance_to_liquidation": self.distance_to_liquidation,
            "distance_ratio": self.distance_ratio,
            "safe_stop_triggered": self.safe_stop_triggered,
            "block_new_positions": self.block_new_positions,
            "block_add_positions": self.block_add_positions,
            "allow_open": self.allow_open,
            "allow_add": self.allow_add,
            "allow_reduce": self.allow_reduce,
            "recommended_action": self.recommended_action,
        }


class PerpRiskGuard:
    """
    ETH永续专属风险守护
    监控资金费率和强平风险
    """

    def __init__(self, config: dict[str, Any] | None = None):
        """
        初始化永续风险守护

        Args:
            config: 配置字典
        """
        # 合并配置
        self.config = PerpRiskGuardConfig(**(config or {}))

        # 初始化模型
        self.margin_model = MarginModel()
        self.liquidation_model = LiquidationModel()

        # 风险检查结果历史
        self.risk_results: list[PerpRiskGuardResult] = []

        logger.info("ETH永续风险守护模块初始化完成")
        logger.info(f"配置: {self.config.__dict__}")

    def get_current_funding_rate(self) -> float:
        """
        获取当前资金费率

        Returns:
            float: 当前资金费率
        """
        # TODO: 实现从交易所API获取实时资金费率
        # 目前返回模拟数据
        return 0.0005  # 0.05%

    def calculate_liquidation_distance(self, margin_state: MarginState) -> tuple[float, float]:
        """
        计算当前价格到强平价格的距离

        Args:
            margin_state: 保证金状态

        Returns:
            tuple[float, float]: (距离绝对值, 距离比例)
        """
        if margin_state.position_qty == 0:
            return 0.0, 0.0

        # 直接计算强平价格，不依赖check_liquidation的结果
        liquidation_price = self.liquidation_model.calculate_liquidation_price(margin_state)

        if liquidation_price <= 0:
            return 0.0, 0.0

        # 计算距离
        current_price = margin_state.current_price
        distance = abs(current_price - liquidation_price)
        distance_ratio = distance / current_price

        return distance, distance_ratio

    def check_funding_rate_risk(self, funding_rate: float) -> tuple[bool, bool]:
        """
        检查资金费率风险

        Args:
            funding_rate: 当前资金费率

        Returns:
            tuple[bool, bool]: (是否禁止新开仓, 是否需要降低仓位)
        """
        block_new = False
        reduce = False

        # 检查绝对资金费率
        if abs(funding_rate) > self.config.max_absolute_funding_rate:
            block_new = self.config.block_new_positions_on_high_funding
            reduce = self.config.reduce_positions_on_high_funding
        else:
            # 检查多头资金费率（当资金费率为正，多头需支付费用）
            if (
                funding_rate > self.config.max_long_funding_rate
                or funding_rate < self.config.max_short_funding_rate
            ):
                block_new = self.config.block_new_positions_on_high_funding
                reduce = self.config.reduce_positions_on_high_funding

        return block_new, reduce

    def check_liquidation_risk(self, distance_ratio: float) -> tuple[bool, bool, bool]:
        """
        检查强平风险

        Args:
            distance_ratio: 当前价格到强平价格的距离比例

        Returns:
            tuple[bool, bool, bool]: (是否触发SAFE_STOP, 是否禁止新开仓, 是否禁止加仓)
        """
        safe_stop = False
        block_new = False
        block_add = False

        # 检查紧急距离
        if distance_ratio < self.config.emergency_distance_threshold:
            safe_stop = self.config.safe_stop_on_emergency
            block_new = self.config.block_new_positions_on_close_liquidation
            block_add = self.config.block_add_positions_on_close_liquidation
        # 检查安全距离
        elif distance_ratio < self.config.safe_distance_threshold:
            block_new = self.config.block_new_positions_on_close_liquidation
            block_add = self.config.block_add_positions_on_close_liquidation

        return safe_stop, block_new, block_add

    def check_risk(self, margin_state: MarginState | None = None) -> PerpRiskGuardResult:
        """
        执行风险检查

        Args:
            margin_state: 保证金状态

        Returns:
            PerpRiskGuardResult: 风险检查结果
        """
        result = PerpRiskGuardResult()

        # 获取当前资金费率
        funding_rate = self.get_current_funding_rate()
        result.current_funding_rate = funding_rate

        # 检查资金费率风险
        funding_block_new, funding_reduce = self.check_funding_rate_risk(funding_rate)
        result.funding_rate_block_new = funding_block_new
        result.funding_rate_reduce = funding_reduce

        # 检查强平价格风险
        if margin_state and margin_state.position_qty != 0:
            result.current_price = margin_state.current_price

            # 计算强平价格和距离
            is_liquidated, liquidation_price = self.liquidation_model.check_liquidation(
                margin_state
            )
            result.liquidation_price = liquidation_price

            distance, distance_ratio = self.calculate_liquidation_distance(margin_state)
            result.distance_to_liquidation = distance
            result.distance_ratio = distance_ratio

            # 检查强平风险
            safe_stop, block_new, block_add = self.check_liquidation_risk(distance_ratio)
            result.safe_stop_triggered = safe_stop
            result.block_new_positions = block_new
            result.block_add_positions = block_add

        # 综合决策
        result.allow_open = not (result.funding_rate_block_new or result.block_new_positions)
        result.allow_add = not (result.funding_rate_block_new or result.block_add_positions)
        result.allow_reduce = True  # 始终允许减仓

        # 生成推荐操作
        if result.safe_stop_triggered:
            result.recommended_action = "SAFE_STOP: 强平价格过近，建议立即平仓"
        elif result.funding_rate_reduce:
            result.recommended_action = "REDUCE_POSITION: 资金费率过高，建议降低仓位"
        elif not result.allow_open:
            result.recommended_action = "BLOCK_NEW: 风险较高，禁止新开仓"
        elif not result.allow_add:
            result.recommended_action = "BLOCK_ADD: 风险较高，禁止加仓"
        else:
            result.recommended_action = "SAFE: 当前风险可控"

        # 保存结果
        self.risk_results.append(result)
        self.save_results()

        logger.info(f"风险检查结果: {result.recommended_action}")
        return result

    def save_results(self) -> None:
        """
        保存风险检查结果到文件
        """
        # 准备输出数据
        output_data = {
            "config": self.config.__dict__,
            "latest_result": self.risk_results[-1].to_dict() if self.risk_results else {},
            "results": [result.to_dict() for result in self.risk_results[-20:]],  # 保存最近20条结果
        }

        # 保存到文件
        try:
            with open(self.config.output_path, "w") as f:
                json.dump(output_data, f, indent=2, ensure_ascii=False)
            logger.info(f"风险守护结果已保存到: {self.config.output_path}")
        except Exception as e:
            logger.error(f"保存风险守护结果失败: {e}")

    def run_continuous_check(self, margin_state: MarginState) -> None:
        """
        运行连续风险检查

        Args:
            margin_state: 保证金状态
        """
        logger.info(f"开始连续风险检查，间隔 {self.config.check_interval_seconds} 秒")

        try:
            while True:
                self.check_risk(margin_state)
                time.sleep(self.config.check_interval_seconds)
        except KeyboardInterrupt:
            logger.info("连续风险检查已停止")


# 示例使用
if __name__ == "__main__":
    # 配置
    config = {
        "max_absolute_funding_rate": 0.0015,
        "safe_distance_threshold": 0.05,
        "emergency_distance_threshold": 0.02,
    }

    # 创建风险守护实例
    risk_guard = PerpRiskGuard(config)

    # 创建模拟保证金状态
    from ..models.margin_model import MarginState

    margin_state = MarginState(
        initial_capital=10000.0,
        balance=10000.0,
        position_qty=5.0,
        position_side=1,  # 多头
        entry_price=2000.0,
        current_price=2100.0,
        margin_used=1000.0,
        available_balance=9000.0,
        equity=10500.0,
        notional_value=10500.0,
        leverage=10.5,
        maintenance_margin=210.0,
        margin_ratio=50.0,
    )

    # 执行风险检查
    result = risk_guard.check_risk(margin_state)
    print(f"风险检查结果: {result.recommended_action}")
    print(f"允许新开仓: {result.allow_open}")
    print(f"允许加仓: {result.allow_add}")
    print(f"安全停止: {result.safe_stop_triggered}")
