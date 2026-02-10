#!/usr/bin/env python3
"""
RiskEngine到Freqtrade的集成模块
实现RiskEngine与Freqtrade策略的集成，在下单前强制调用RiskEngine决策
"""

import logging
from typing import Any

from freqtrade.strategy import IStrategy
from pandas import DataFrame

from src.quantsys.domain.risk_engine import RiskDecision, RiskEngine
from src.quantsys.execution.signal_freeze import get_signal_freeze_manager

# 配置日志
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class RiskEngineFreqtradeIntegration:
    """
    RiskEngine到Freqtrade的集成类
    负责在Freqtrade策略下单前强制调用RiskEngine决策
    """

    def __init__(self):
        """
        初始化集成类
        """
        # 获取RiskEngine实例
        self.risk_engine = RiskEngine()

        # 获取信号冻结管理器
        self.signal_freeze_manager = get_signal_freeze_manager()

        logger.info("RiskEngine到Freqtrade集成模块初始化完成")

    def evaluate_risk_for_entry(
        self,
        strategy: IStrategy,
        dataframe: DataFrame,
        metadata: dict,
        entry_signal: bool,
        amount: float,
        price: float,
        stop_distance: float | None = None,
    ) -> dict[str, Any]:
        """
        评估策略entry信号的风险

        Args:
            strategy: Freqtrade策略实例
            dataframe: 策略数据
            metadata: 元数据
            entry_signal: 策略生成的entry信号
            amount: 交易数量
            price: 交易价格
            stop_distance: 止损距离

        Returns:
            Dict[str, Any]: 风险评估结果，包含:
                - allow_entry: bool, 是否允许entry
                - reason: str, 决策原因
                - stake_amount: float, 建议的stake金额
                - leverage: float, 建议的杠杆
                - stoploss: float, 建议的止损
                - risk_decision: RiskDecision, 完整的风险决策对象
        """
        # 如果策略没有生成entry信号，直接返回不允许
        if not entry_signal:
            return {
                "allow_entry": False,
                "reason": "策略未生成entry信号",
                "stake_amount": 0.0,
                "leverage": 1.0,
                "stoploss": 0.0,
                "risk_decision": None,
            }

        # 如果没有止损距离，直接BLOCKED
        if stop_distance is None:
            logger.warning("无止损距离，直接BLOCKED")
            return {
                "allow_entry": False,
                "reason": "无止损距离，直接BLOCKED",
                "stake_amount": 0.0,
                "leverage": 1.0,
                "stoploss": 0.0,
                "risk_decision": None,
            }

        # 检查是否已触发安全停止
        if self.risk_engine.risk_state["safe_stop_triggered"]:
            logger.warning("已触发安全停止，禁止所有开仓")
            return {
                "allow_entry": False,
                "reason": "已触发安全停止，禁止所有开仓",
                "stake_amount": 0.0,
                "leverage": 1.0,
                "stoploss": 0.0,
                "risk_decision": None,
            }

        # 获取交易对信息
        symbol = metadata.get("pair", "ETH-USDT")

        # 调用RiskEngine评估风险
        risk_decision = self.risk_engine.evaluate_risk(
            symbol=symbol, side="buy", amount=amount, price=price, stop_distance=stop_distance
        )

        # 记录风险决策结果
        logger.info(f"RiskEngine决策结果: {risk_decision.decision}, 原因: {risk_decision.reason}")

        # 如果风险决策不允许，返回禁止entry
        if risk_decision.decision != "ALLOW":
            return {
                "allow_entry": False,
                "reason": risk_decision.reason,
                "stake_amount": 0.0,
                "leverage": 1.0,
                "stoploss": 0.0,
                "risk_decision": risk_decision,
            }

        # 计算建议的stake金额
        # 单笔最大名义金额为3.3u，所以stake金额为3.3u
        stake_amount = min(
            self.risk_engine.risk_params["single_trade_notional"],
            self.risk_engine.risk_state["current_equity"] * 0.33,  # 最多使用当前权益的33%
        )

        # 计算建议的杠杆
        # 总预算10u，单笔3.3u，所以杠杆约为3.3/10 = 0.33x
        leverage = min(
            stake_amount / self.risk_engine.risk_state["current_equity"],
            1.0,  # 最大杠杆为1x（无杠杆）
        )

        # 计算建议的止损
        # 基于stop_distance和当前价格
        stoploss = -stop_distance / price  # 转换为相对止损比例

        # 冻结信号，保存到intent_freeze.json
        idempotency_key = self.signal_freeze_manager.generate_idempotency_key(
            strategy_id=strategy.__class__.__name__,
            bar_time=dataframe.index[-1].isoformat() if not dataframe.empty else "unknown",
            symbol=symbol,
        )

        self.signal_freeze_manager.freeze_signal(
            idempotency_key=idempotency_key,
            strategy_id=strategy.__class__.__name__,
            strategy_name=strategy.__class__.__name__,
            strategy_params={},
            factor_version="v1.0.0",
            bar_time=dataframe.index[-1].isoformat() if not dataframe.empty else "unknown",
            trigger_reason="策略生成entry信号",
            symbol=symbol,
            side="buy",
            order_type="market",
            planned_entry_price=price,
            planned_stop_loss=price * (1 + stoploss),
            planned_take_profit=None,
        )

        # 返回允许entry的结果
        return {
            "allow_entry": True,
            "reason": risk_decision.reason,
            "stake_amount": stake_amount,
            "leverage": leverage,
            "stoploss": stoploss,
            "risk_decision": risk_decision,
        }

    def update_equity(self, equity: float):
        """
        更新RiskEngine的权益

        Args:
            equity: 新的权益值
        """
        self.risk_engine.update_equity(equity)

    def close_position(self, notional: float):
        """
        通知RiskEngine平仓操作

        Args:
            notional: 平仓名义金额
        """
        self.risk_engine.close_position(notional)

    def get_current_risk_state(self) -> dict[str, Any]:
        """
        获取当前风险状态

        Returns:
            Dict[str, Any]: 当前风险状态
        """
        return self.risk_engine.risk_state.copy()


# 单例模式
_risk_engine_integration = None


def get_risk_engine_integration() -> RiskEngineFreqtradeIntegration:
    """
    获取RiskEngine到Freqtrade集成模块实例（单例模式）

    Returns:
        RiskEngineFreqtradeIntegration: 集成模块实例
    """
    global _risk_engine_integration

    if _risk_engine_integration is None:
        _risk_engine_integration = RiskEngineFreqtradeIntegration()

    return _risk_engine_integration


# 策略包装器基类，用于包装Freqtrade策略，添加RiskEngine集成
class RiskManagedStrategy(IStrategy):
    """
    风险管理策略包装器
    继承自IStrategy，在entry前添加RiskEngine评估
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.risk_integration = get_risk_engine_integration()

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """
        重写populate_entry_trend方法，添加RiskEngine评估
        """
        # 先调用父类的populate_entry_trend生成原始entry信号
        dataframe = super().populate_entry_trend(dataframe, metadata)

        # 遍历数据，评估每个entry信号
        for index, row in dataframe.iterrows():
            # 检查是否有entry信号
            entry_signal = row.get("enter_long", 0) == 1 or row.get("enter_short", 0) == 1

            if entry_signal:
                # 计算止损距离（这里需要根据策略的stoploss计算，或者从dataframe中获取）
                # 简化处理，使用策略的默认stoploss
                stoploss = abs(self.stoploss) if hasattr(self, "stoploss") else 0.01
                stop_distance = stoploss * row["close"]

                # 评估风险
                risk_result = self.risk_integration.evaluate_risk_for_entry(
                    strategy=self,
                    dataframe=dataframe,
                    metadata=metadata,
                    entry_signal=entry_signal,
                    amount=0.1,  # 示例金额，实际应根据策略计算
                    price=row["close"],
                    stop_distance=stop_distance,
                )

                # 根据风险评估结果更新entry信号
                if not risk_result["allow_entry"]:
                    logger.info(f"RiskEngine禁止entry: {risk_result['reason']}, 时间: {index}")
                    dataframe.at[index, "enter_long"] = 0
                    dataframe.at[index, "enter_short"] = 0
                else:
                    logger.info(f"RiskEngine允许entry: {risk_result['reason']}, 时间: {index}")

        return dataframe


# 用于直接调用RiskEngine的工具函数
def check_risk_before_entry(
    symbol: str, side: str, amount: float, price: float, stop_distance: float
) -> RiskDecision:
    """
    直接检查entry前的风险

    Args:
        symbol: 交易对
        side: 买卖方向
        amount: 交易数量
        price: 交易价格
        stop_distance: 止损距离

    Returns:
        RiskDecision: 风险决策结果
    """
    risk_engine = RiskEngine()
    return risk_engine.evaluate_risk(symbol, side, amount, price, stop_distance)
