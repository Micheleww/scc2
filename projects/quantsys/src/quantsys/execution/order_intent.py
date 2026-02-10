#!/usr/bin/env python3
"""
订单意图模块
实现策略输出到订单意图的桥接层，处理净敞口、杠杆、单品种上限等风险控制
"""

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from src.quantsys.common.risk_manager import RiskManager

# 配置日志
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


@dataclass
class OrderIntent:
    """
    标准化订单意图数据结构
    """

    strategy_id: str  # 策略ID
    symbol: str  # 交易对
    side: str  # 买卖方向 (buy/sell)
    order_type: str  # 订单类型 (market/limit)
    amount: float  # 交易数量
    price: float | None = None  # 交易价格（限价单需要）
    timestamp: str = datetime.now().isoformat()  # 生成时间
    meta: dict[str, Any] | None = None  # 其他元数据


@dataclass
class PortfolioState:
    """
    组合状态数据结构
    """

    balance: float  # 可用余额
    equity: float  # 账户权益
    positions: dict[str, float]  # 持仓情况 {symbol: notional_value}
    total_position: float  # 总持仓金额
    current_leverage: float  # 当前使用杠杆


class StrategyToOrderIntentBridge:
    """
    策略输出到订单意图的桥接层
    处理净敞口、杠杆、单品种上限等风险控制
    """

    def __init__(self, config: dict[str, Any]):
        """
        初始化桥接层

        Args:
            config: 配置信息
        """
        self.config = config

        # 初始化风险管理器
        self.risk_manager = RiskManager(config.get("risk_params", {}))

        # 默认配置
        self.defaults = {
            "max_net_exposure": 0.5,  # 最大净敞口比例
            "max_leverage": 10.0,  # 最大杠杆
            "max_single_position_ratio": 0.2,  # 单品种最大仓位比例
            "min_order_amount": 10.0,  # 最小订单金额
        }

        # 合并配置
        self.params = {**self.defaults, **config.get("bridge_params", {})}

        logger.info("策略到订单意图桥接层初始化完成")

    def generate_order_intents(
        self, strategy_output: list[dict[str, Any]], portfolio_state: PortfolioState
    ) -> list[OrderIntent]:
        """
        生成标准化订单意图列表

        Args:
            strategy_output: 策略输出列表
            portfolio_state: 组合状态

        Returns:
            List[OrderIntent]: 标准化订单意图列表
        """
        order_intents = []

        # 遍历策略输出，生成订单意图
        for strategy_signal in strategy_output:
            intent = self._convert_strategy_signal_to_intent(strategy_signal, portfolio_state)
            if intent:
                order_intents.append(intent)

        # 应用风险控制，过滤和调整订单意图
        filtered_intents = self._apply_risk_control(order_intents, portfolio_state)

        # 应用净敞口、杠杆和单品种上限控制
        adjusted_intents = self._adjust_for_exposure_and_leverage(filtered_intents, portfolio_state)

        logger.info(
            f"生成订单意图: 策略输出 {len(strategy_output)}, 过滤后 {len(filtered_intents)}, 调整后 {len(adjusted_intents)}"
        )

        return adjusted_intents

    def _convert_strategy_signal_to_intent(
        self, signal: dict[str, Any], portfolio_state: PortfolioState
    ) -> OrderIntent | None:
        """
        将策略信号转换为订单意图

        Args:
            signal: 策略信号
            portfolio_state: 组合状态

        Returns:
            Optional[OrderIntent]: 订单意图，如果转换失败则返回None
        """
        try:
            # 提取策略信号中的关键信息
            strategy_id = signal.get("strategy_id", "default")
            symbol = signal["symbol"]
            side = signal["side"]
            order_type = signal.get("order_type", "market")
            amount = signal["amount"]
            price = signal.get("price")
            meta = signal.get("meta", {})

            # 创建订单意图
            intent = OrderIntent(
                strategy_id=strategy_id,
                symbol=symbol,
                side=side,
                order_type=order_type,
                amount=amount,
                price=price,
                meta=meta,
            )

            return intent
        except KeyError as e:
            logger.error(f"策略信号转换失败，缺少关键字段: {e}, 信号: {signal}")
            return None

    def _apply_risk_control(
        self, intents: list[OrderIntent], portfolio_state: PortfolioState
    ) -> list[OrderIntent]:
        """
        应用风险控制，过滤不符合风险规则的订单意图

        Args:
            intents: 订单意图列表
            portfolio_state: 组合状态

        Returns:
            List[OrderIntent]: 过滤后的订单意图列表
        """
        filtered_intents = []

        for intent in intents:
            # 检查当前品种的持仓
            current_position = portfolio_state.positions.get(intent.symbol, 0.0)

            # 获取风险评估结果
            verdict = self.risk_manager.get_risk_verdict(
                symbol=intent.symbol,
                side=intent.side,
                amount=intent.amount,
                price=intent.price or 0.0,
                balance=portfolio_state.balance,
                current_position=current_position,
                total_position=portfolio_state.total_position,
                equity=portfolio_state.equity,
                leverage=portfolio_state.current_leverage,
            )

            # 检查风险评估结果
            if verdict.is_blocked:
                # 检查是否允许减仓
                if intent.side == "sell" and verdict.allow_reduce:
                    logger.warning(
                        f"风控触发，允许减仓操作: {'; '.join(verdict.blocked_reason)}, 订单: {intent}"
                    )
                    filtered_intents.append(intent)
                else:
                    logger.error(
                        f"风控阻止订单: {'; '.join(verdict.blocked_reason)}, 订单: {intent}"
                    )
            else:
                # 风险检查通过
                filtered_intents.append(intent)

        return filtered_intents

    def _adjust_for_exposure_and_leverage(
        self, intents: list[OrderIntent], portfolio_state: PortfolioState
    ) -> list[OrderIntent]:
        """
        应用净敞口、杠杆和单品种上限控制，调整订单意图

        Args:
            intents: 订单意图列表
            portfolio_state: 组合状态

        Returns:
            List[OrderIntent]: 调整后的订单意图列表
        """
        adjusted_intents = []

        # 计算当前净敞口和可用额度
        current_net_exposure = portfolio_state.total_position / portfolio_state.equity
        max_allowed_exposure = self.params["max_net_exposure"] * portfolio_state.equity

        # 计算每个订单的预期影响，并调整
        for intent in intents:
            # 计算订单金额
            order_amount = intent.amount * (intent.price or 0.0) if intent.price else intent.amount

            # 检查最小订单金额
            if order_amount < self.params["min_order_amount"]:
                logger.warning(f"订单金额小于最小限制，跳过: {intent}")
                continue

            # 获取当前品种持仓
            current_position = portfolio_state.positions.get(intent.symbol, 0.0)

            # 计算调整后的订单金额，考虑单品种上限
            max_single_position = self.params["max_single_position_ratio"] * portfolio_state.equity

            if intent.side == "buy":
                # 买入时检查单品种上限
                new_position = current_position + order_amount
                if new_position > max_single_position:
                    # 调整订单金额
                    adjusted_amount = (max_single_position - current_position) / (
                        intent.price or 1.0
                    )
                    if adjusted_amount < self.params["min_order_amount"] / (intent.price or 1.0):
                        logger.warning(f"调整后订单金额小于最小限制，跳过: {intent}")
                        continue

                    logger.info(
                        f"调整买入订单金额，单品种上限限制: 原金额 {intent.amount}, 调整后 {adjusted_amount}, 品种: {intent.symbol}"
                    )
                    intent.amount = adjusted_amount
            else:
                # 卖出时检查是否超过当前持仓
                if order_amount > current_position:
                    # 调整订单金额为当前持仓
                    adjusted_amount = current_position / (intent.price or 1.0)
                    logger.info(
                        f"调整卖出订单金额，超过当前持仓: 原金额 {intent.amount}, 调整后 {adjusted_amount}, 品种: {intent.symbol}"
                    )
                    intent.amount = adjusted_amount

            # 检查总敞口和杠杆
            adjusted_order_amount = (
                intent.amount * (intent.price or 0.0) if intent.price else intent.amount
            )
            new_total_position = (
                portfolio_state.total_position + adjusted_order_amount
                if intent.side == "buy"
                else portfolio_state.total_position - adjusted_order_amount
            )

            new_leverage = (
                new_total_position / portfolio_state.equity if portfolio_state.equity > 0 else 0.0
            )

            if (
                new_leverage <= self.params["max_leverage"]
                and new_total_position <= max_allowed_exposure
            ):
                adjusted_intents.append(intent)
            else:
                logger.warning(
                    f"订单超过杠杆或敞口限制，跳过: {intent}, 新杠杆: {new_leverage}, 新敞口: {new_total_position}"
                )

        return adjusted_intents

    def validate_order_intents(
        self, intents: list[OrderIntent], portfolio_state: PortfolioState
    ) -> dict[str, Any]:
        """
        验证订单意图是否符合风险规则

        Args:
            intents: 订单意图列表
            portfolio_state: 组合状态

        Returns:
            Dict[str, Any]: 验证结果
        """
        validation_result = {
            "valid": True,
            "errors": [],
            "warnings": [],
            "stats": {
                "total_intents": len(intents),
                "total_order_amount": 0.0,
                "average_order_amount": 0.0,
            },
        }

        if not intents:
            validation_result["warnings"].append("没有生成订单意图")
            return validation_result

        # 计算统计信息
        total_amount = sum(intent.amount * (intent.price or 1.0) for intent in intents)
        validation_result["stats"]["total_order_amount"] = total_amount
        validation_result["stats"]["average_order_amount"] = total_amount / len(intents)

        # 验证每个订单意图
        for intent in intents:
            # 检查最小订单金额
            order_amount = intent.amount * (intent.price or 1.0)
            if order_amount < self.params["min_order_amount"]:
                validation_result["valid"] = False
                validation_result["errors"].append(f"订单金额小于最小限制: {intent}")

            # 检查风险规则
            verdict = self.risk_manager.get_risk_verdict(
                symbol=intent.symbol,
                side=intent.side,
                amount=intent.amount,
                price=intent.price or 0.0,
                balance=portfolio_state.balance,
                current_position=portfolio_state.positions.get(intent.symbol, 0.0),
                total_position=portfolio_state.total_position,
                equity=portfolio_state.equity,
                leverage=portfolio_state.current_leverage,
            )

            if verdict.is_blocked:
                if not (intent.side == "sell" and verdict.allow_reduce):
                    validation_result["valid"] = False
                    validation_result["errors"].append(
                        f"风控阻止订单: {'; '.join(verdict.blocked_reason)}, 订单: {intent}"
                    )

        return validation_result
