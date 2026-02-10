#!/usr/bin/env python3
"""
信号执行器
监听信号总线，将信号转换为订单并执行
实现策略层与执行层的解耦
"""

import logging

from src.quantsys.strategy.signal_bus import Signal, SignalBus, SignalType

from .order_execution import OrderExecution
from .risk_gate import RiskGate

# 配置日志
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class SignalExecutor:
    """
    信号执行器
    监听信号总线，将信号转换为订单并执行
    """

    def __init__(
        self,
        order_executor: OrderExecution,
        risk_gate: RiskGate,
        signal_bus: SignalBus | None = None,
    ):
        """
        初始化信号执行器

        Args:
            order_executor: 订单执行器
            risk_gate: 风险门禁
            signal_bus: 信号总线（可选，默认使用全局实例）
        """
        self.order_executor = order_executor
        self.risk_gate = risk_gate

        # 使用提供的signal_bus或全局实例
        if signal_bus is None:
            from src.quantsys.strategy.signal_bus import get_signal_bus

            self.signal_bus = get_signal_bus()
        else:
            self.signal_bus = signal_bus

        # 订阅信号
        self._subscribe_signals()

        logger.info("SignalExecutor initialized")

    def _subscribe_signals(self):
        """订阅信号总线"""
        # 订阅入场信号
        self.signal_bus.subscribe(SignalType.ENTER, self._handle_enter_signal)

        # 订阅出场信号
        self.signal_bus.subscribe(SignalType.EXIT, self._handle_exit_signal)

        # 订阅调整信号
        self.signal_bus.subscribe(SignalType.ADJUST, self._handle_adjust_signal)

        logger.info("Subscribed to signal bus")

    def _handle_enter_signal(self, signal: Signal):
        """
        处理入场信号

        Args:
            signal: 交易信号
        """
        logger.info(f"Received enter signal: {signal.signal_id} for {signal.symbol}")

        # 计算订单数量（根据信号强度）
        # 这里简化处理，实际应该根据策略和风险参数计算
        base_amount = signal.metadata.get("base_amount", 100.0)
        amount = base_amount * signal.strength

        # 风险检查
        # 注意：这里需要获取当前价格，简化处理使用metadata中的价格
        current_price = signal.metadata.get("current_price", 0.0)
        if current_price <= 0:
            logger.error(f"无法获取当前价格，跳过信号: {signal.signal_id}")
            return

        # 使用风险门禁检查
        verdict = self.risk_gate.check_order(
            symbol=signal.symbol, side=signal.side, amount=amount, price=current_price
        )

        if not self.risk_gate.is_order_allowed(
            symbol=signal.symbol, side=signal.side, amount=amount, price=current_price
        ):
            logger.warning(
                f"风险检查未通过，跳过信号: {signal.signal_id}, 原因: {verdict.blocked_reason}"
            )
            return

        # 执行订单
        try:
            result = self.order_executor.place_order(
                symbol=signal.symbol,
                side=signal.side,
                order_type="market",
                amount=amount,
                price=None,  # 市价单
                params={
                    "strategy_id": signal.strategy_id,
                    "strategy_version": signal.strategy_version,
                    "signal_id": signal.signal_id,
                    "stop_loss": signal.stop_loss,
                    "take_profit": signal.take_profit,
                },
            )

            if result.get("code") == "0":
                logger.info(
                    f"订单执行成功: {signal.signal_id}, 订单ID: {result.get('data', [{}])[0].get('ordId')}"
                )
            else:
                logger.error(f"订单执行失败: {signal.signal_id}, 原因: {result.get('msg')}")

        except Exception as e:
            logger.error(f"执行信号时出错: {signal.signal_id}, 错误: {e}", exc_info=True)

    def _handle_exit_signal(self, signal: Signal):
        """
        处理出场信号

        Args:
            signal: 交易信号
        """
        logger.info(f"Received exit signal: {signal.signal_id} for {signal.symbol}")

        # 出场信号处理逻辑（简化）
        # 实际应该根据当前持仓计算平仓数量
        current_price = signal.metadata.get("current_price", 0.0)
        if current_price <= 0:
            logger.error(f"无法获取当前价格，跳过信号: {signal.signal_id}")
            return

        # 风险检查（出场通常是减仓，允许通过）
        # 执行平仓订单
        try:
            # 这里简化处理，实际应该查询当前持仓
            result = self.order_executor.place_order(
                symbol=signal.symbol,
                side=signal.side,
                order_type="market",
                amount=0.0,  # 实际应该使用当前持仓数量
                price=None,
                params={
                    "strategy_id": signal.strategy_id,
                    "strategy_version": signal.strategy_version,
                    "signal_id": signal.signal_id,
                    "reduce_only": True,
                },
            )

            if result.get("code") == "0":
                logger.info(f"平仓订单执行成功: {signal.signal_id}")
            else:
                logger.error(f"平仓订单执行失败: {signal.signal_id}, 原因: {result.get('msg')}")

        except Exception as e:
            logger.error(f"执行出场信号时出错: {signal.signal_id}, 错误: {e}", exc_info=True)

    def _handle_adjust_signal(self, signal: Signal):
        """
        处理调整信号

        Args:
            signal: 交易信号
        """
        logger.info(f"Received adjust signal: {signal.signal_id} for {signal.symbol}")
        # 调整信号处理逻辑（待实现）
        pass
