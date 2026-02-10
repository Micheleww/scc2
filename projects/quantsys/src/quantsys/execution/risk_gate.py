#!/usr/bin/env python3
"""
统一风险检查入口
RiskGate类作为所有风险检查的统一入口，确保所有订单都经过统一的风险检查
"""

import logging
from dataclasses import dataclass

from src.quantsys.common.risk_manager import RiskManager, RiskVerdict

from .account_service import AccountService

# 配置日志
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


@dataclass
class TradingContext:
    """交易上下文数据类"""

    symbol: str
    side: str
    amount: float
    price: float
    balance: float
    equity: float
    current_position: float
    total_position: float
    leverage: float
    is_contract: bool = False
    contract_amount: float = 0.0
    pending_orders: float = 0.0


class RiskGate:
    """
    统一风险检查入口
    所有订单必须通过此门禁检查才能执行
    """

    def __init__(self, risk_manager: RiskManager, account_service: AccountService):
        """
        初始化风险门禁

        Args:
            risk_manager: 风险管理器实例
            account_service: 账户服务实例
        """
        self.risk_manager = risk_manager
        self.account_service = account_service
        logger.info("RiskGate initialized")

    def check_order(
        self,
        symbol: str,
        side: str,
        amount: float,
        price: float,
        is_contract: bool = False,
        contract_amount: float = 0.0,
        pending_orders: float = 0.0,
    ) -> RiskVerdict:
        """
        统一的风险检查入口

        Args:
            symbol: 交易对
            side: 买卖方向
            amount: 交易数量
            price: 交易价格
            is_contract: 是否为合约交易
            contract_amount: 合约交易的实际保证金金额（USDT）
            pending_orders: 未成交委托总占用金额（USDT）

        Returns:
            RiskVerdict: 风险评估结果
        """
        # 从账户服务获取真实账户数据
        account_state = self.account_service.get_account_state(symbol=symbol)

        # 构建交易上下文
        context = TradingContext(
            symbol=symbol,
            side=side,
            amount=amount,
            price=price,
            balance=account_state.balance,
            equity=account_state.equity,
            current_position=account_state.positions.get(symbol, 0.0),
            total_position=account_state.total_position,
            leverage=account_state.leverage,
            is_contract=is_contract,
            contract_amount=contract_amount,
            pending_orders=pending_orders,
        )

        logger.debug(f"风险检查上下文: {context}")

        # 调用风险管理器进行风险评估
        verdict = self.risk_manager.get_risk_verdict(
            symbol=context.symbol,
            side=context.side,
            amount=context.amount,
            price=context.price,
            balance=context.balance,
            current_position=context.current_position,
            total_position=context.total_position,
            equity=context.equity,
            leverage=context.leverage,
            is_contract=context.is_contract,
            contract_amount=context.contract_amount,
            pending_orders=context.pending_orders,
        )

        # 记录风险检查结果
        if verdict.is_blocked:
            logger.warning(
                f"风险检查阻止订单: {symbol} {side} {amount} @ {price}, 原因: {verdict.blocked_reason}"
            )
        else:
            logger.info(f"风险检查通过: {symbol} {side} {amount} @ {price}")

        return verdict

    def is_order_allowed(
        self,
        symbol: str,
        side: str,
        amount: float,
        price: float,
        is_contract: bool = False,
        contract_amount: float = 0.0,
        pending_orders: float = 0.0,
    ) -> bool:
        """
        检查订单是否允许执行（简化接口）

        Args:
            symbol: 交易对
            side: 买卖方向
            amount: 交易数量
            price: 交易价格
            is_contract: 是否为合约交易
            contract_amount: 合约交易的实际保证金金额（USDT）
            pending_orders: 未成交委托总占用金额（USDT）

        Returns:
            bool: True表示允许，False表示阻止
        """
        verdict = self.check_order(
            symbol=symbol,
            side=side,
            amount=amount,
            price=price,
            is_contract=is_contract,
            contract_amount=contract_amount,
            pending_orders=pending_orders,
        )

        # 对于买入操作，检查allow_open
        # 对于卖出操作，检查allow_reduce（减仓）或allow_open（开空）
        if side == "buy":
            return verdict.allow_open
        else:  # sell
            # 卖出可能是减仓或开空，优先检查减仓
            return verdict.allow_reduce or verdict.allow_open
