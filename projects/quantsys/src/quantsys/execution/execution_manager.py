#!/usr/bin/env python3
"""
执行管理器
协调各个组件，提供统一的订单执行接口
"""

import logging
from typing import Any

from src.quantsys.common.black_swan_mode import BlackSwanModeManager
from src.quantsys.common.risk_manager import RiskManager
from src.quantsys.execution.readiness import ExecutionReadiness
from src.quantsys.risk import RiskEngine

from .account_service import AccountService
from .exchange_adapter import ExchangeAdapterFactory
from .execution_context import ExecutionContext
from .guards.risk_guard import RiskGuard
from .order_executor import OrderExecutor
from .order_ids import OrderIdManager
from .order_splitter import OrderSplitter
from .order_validator import OrderValidator
from .risk_gate import RiskGate

# 配置日志
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class ExecutionManager:
    """
    执行管理器
    协调各个组件，提供统一的订单执行接口
    """

    def __init__(
        self,
        config: dict[str, Any],
        readiness: ExecutionReadiness | None = None,
        risk_engine: RiskEngine | None = None,
    ):
        """
        初始化执行管理器

        Args:
            config: 配置信息
            readiness: Execution Readiness manager instance
            risk_engine: Risk Engine instance
        """
        self.config = config
        self.exchange = config.get("exchange", "okx")
        self.trading_mode = config.get("trading_mode", "drill")
        self.readiness = readiness
        self.risk_engine = risk_engine

        # 从环境变量读取API密钥
        import os

        exchange_prefix = self.exchange.upper()
        api_key = os.environ.get(f"{exchange_prefix}_API_KEY", "")
        secret_key = os.environ.get(f"{exchange_prefix}_API_SECRET", "")
        passphrase = os.environ.get(f"{exchange_prefix}_PASSPHRASE", "")

        # 创建交易所适配器
        self.exchange_adapter = ExchangeAdapterFactory.create(
            exchange=self.exchange,
            api_key=api_key,
            secret_key=secret_key,
            passphrase=passphrase,
            trading_mode=self.trading_mode,
        )

        # 创建订单ID管理器
        self.order_id_manager = OrderIdManager()

        # 创建订单验证器
        self.order_validator = OrderValidator(config.get("order_validator", {}))

        # 创建订单执行器
        self.order_executor = OrderExecutor(
            exchange_adapter=self.exchange_adapter,
            order_id_manager=self.order_id_manager,
            order_validator=self.order_validator,
        )

        # 创建风险管理器
        self.risk_manager = RiskManager(config.get("risk_params", {}))

        # 创建账户服务
        self.account_service = AccountService(
            exchange=self.exchange, trading_mode=self.trading_mode
        )

        # 创建风险门禁
        self.risk_gate = RiskGate(
            risk_manager=self.risk_manager, account_service=self.account_service
        )

        # 创建订单分拆管理器
        self.order_splitter = OrderSplitter(config.get("order_splitter", {}))

        # 创建黑天鹅模式管理器
        self.black_swan_manager = BlackSwanModeManager(config.get("black_swan", {}))

        # 创建Runtime Guard
        risk_guard_config = config.get("risk_guard", {})
        risk_guard_enabled = risk_guard_config.get("enabled", True)
        self.risk_guard = RiskGuard(enabled=risk_guard_enabled)

        # 事件流日志
        self.event_log = []

        # 真单开关配置
        self.real_order_switch = config.get("real_order", {}).get("enabled", False)
        self.real_order_config = config.get("real_order", {})

        # 真单限制参数
        self.real_order_limits = {
            "single_order_max_usdt": self.real_order_config.get("single_order_max_usdt", 3.3),
            "total_budget_max_usdt": self.real_order_config.get("total_budget_max_usdt", 10.0),
            "max_positions": self.real_order_config.get("max_positions", 1),
        }

        # 止损配置
        self.stop_loss_config = {
            "enabled": self.real_order_config.get("stop_loss_enabled", True),
            "stop_loss_ratio": self.real_order_config.get("stop_loss_ratio", 0.01),
        }

        logger.info("ExecutionManager initialized")

    def place_order(
        self,
        symbol: str,
        side: str,
        order_type: str,
        amount: float,
        price: float | None = None,
        params: dict[str, Any] = None,
        context: ExecutionContext | None = None,
    ) -> dict[str, Any]:
        """
        下单（统一入口）

        Args:
            symbol: 交易对
            side: 买卖方向
            order_type: 订单类型
            amount: 交易数量
            price: 交易价格（限价单需要）
            params: 其他参数
            context: 执行上下文

        Returns:
            result: 订单创建结果
        """
        # 1. 检查执行就绪状态
        if self.readiness and self.readiness.is_blocked():
            reasons = self.readiness.get_blocked_reasons()
            error_msg = f"系统处于 BLOCKED 状态，禁止下单: {'; '.join(reasons)}"
            logger.error(error_msg)
            raise RuntimeError(error_msg)

        # 2. 检查黑天鹅模式
        if self.black_swan_manager.is_reduce_only() or self.black_swan_manager.is_liquidate():
            if side != "sell":
                error_msg = f"黑天鹅模式 ({self.black_swan_manager.get_current_status_value()}) 下不允许买入操作"
                logger.error(error_msg)
                raise RuntimeError(error_msg)
            logger.warning(
                f"黑天鹅模式 ({self.black_swan_manager.get_current_status_value()}) 下执行卖出操作"
            )

        # 3. 风险检查（使用统一风险门禁）
        verdict = self.risk_gate.check_order(
            symbol=symbol, side=side, amount=amount, price=price or 0.0
        )

        if not self.risk_gate.is_order_allowed(symbol, side, amount, price or 0.0):
            error_msg = f"风险检查失败，禁止下单: {'; '.join(verdict.blocked_reason)}"
            logger.error(error_msg)
            raise RuntimeError(error_msg)

        # 4. 检查是否需要分拆订单
        params = params or {}
        if amount > self.order_splitter.config.max_single_order_amount:
            logger.info(f"订单数量 {amount} 超过最大单笔订单数量，开始分拆")
            # 使用订单分拆管理器执行分拆订单
            split_result = self.order_splitter.split_and_execute(
                self.order_executor, symbol, side, order_type, amount, price, params
            )
            return {
                "code": "0" if split_result.status == "success" else "1",
                "msg": f"Order split and executed, status: {split_result.status}",
                "data": [
                    {
                        "original_order_id": split_result.original_order_id,
                        "status": split_result.status,
                        "split_count": len(split_result.split_orders),
                    }
                ],
            }

        # 5. 执行订单
        return self.order_executor.execute_order(
            symbol=symbol,
            side=side,
            order_type=order_type,
            amount=amount,
            price=price,
            params=params,
        )

    def cancel_order(self, symbol: str, order_id: str) -> dict[str, Any]:
        """
        撤单

        Args:
            symbol: 交易对
            order_id: 订单ID

        Returns:
            result: 撤单结果
        """
        return self.order_executor.cancel_order(symbol, order_id)

    def get_order(self, symbol: str, order_id: str) -> dict[str, Any]:
        """
        查询订单

        Args:
            symbol: 交易对
            order_id: 订单ID

        Returns:
            result: 订单状态
        """
        return self.order_executor.get_order_status(symbol, order_id)

    def get_balance(self) -> dict[str, Any]:
        """
        查询余额

        Returns:
            result: 账户余额信息
        """
        return self.exchange_adapter.get_balance()

    def get_positions(self, symbol: str | None = None) -> dict[str, Any]:
        """
        查询持仓

        Args:
            symbol: 交易对（可选）

        Returns:
            result: 持仓信息
        """
        return self.exchange_adapter.get_positions(symbol)
