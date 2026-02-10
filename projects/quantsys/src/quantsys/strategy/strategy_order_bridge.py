#!/usr/bin/env python3
"""
策略输出到订单意图桥接层
实现策略输出到组合/下单意图的转换，处理风险控制和资金管理
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
class ActionIntent:
    """
    策略行为意图数据类（V1.6 constitution 要求）
    """

    action_type: str  # 行为类型: enter/exit/hold
    entry_type: str  # 入场类型: breakout/pullback/mean/etc
    exit_logic: dict[str, Any]  # 出场逻辑: {type: time/price/condition, parameters: {...}}
    strategy_id: str = "default"  # 策略ID
    timestamp: str = None  # 生成时间戳
    confidence: float = 0.5  # 置信度

    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now().isoformat()


@dataclass
class OrderIntent:
    """
    标准化订单意图数据类
    """

    symbol: str  # 交易对
    side: str  # 买卖方向: buy/sell
    order_type: str  # 订单类型: market/limit
    amount: float  # 交易数量
    price: float | None = None  # 交易价格（市价单可为None）
    leverage: float = 1.0  # 杠杆倍数
    strategy_id: str = "default"  # 策略ID
    client_order_id: str | None = None  # 客户端订单ID
    is_reduce_only: bool = False  # 是否为减仓订单
    is_blocked: bool = False  # 是否被风控阻止
    blocked_reasons: list[str] = None  # 被阻止的原因列表

    def __post_init__(self):
        if self.blocked_reasons is None:
            self.blocked_reasons = []


class StrategyOrderBridge:
    """
    策略行为意图到订单意图桥接器
    处理策略行为意图到订单意图的转换，严格遵循V1.6 constitution要求
    """

    def __init__(self, config: dict[str, Any]):
        """
        初始化策略订单桥接器

        Args:
            config: 配置信息
        """
        self.config = config

        # 初始化风险管理器
        self.risk_manager = RiskManager(config.get("risk_params", {}))

        # 初始化状态（仅用于风险检查，不用于仓位计算）
        self.current_positions: dict[str, float] = {}  # 当前持仓量
        self.current_balance: float = config.get("initial_balance", 10000.0)  # 当前可用余额
        self.current_equity: float = config.get("initial_equity", 10000.0)  # 当前账户权益

        logger.info("策略订单桥接器初始化完成")

    def update_current_state(self, positions: dict[str, float], balance: float, equity: float):
        """
        更新当前状态（仅用于风险检查）

        Args:
            positions: 当前持仓量字典
            balance: 当前可用余额
            equity: 当前账户权益
        """
        self.current_positions = positions
        self.current_balance = balance
        self.current_equity = equity

        logger.info(f"当前状态已更新: 持仓={positions}, 余额={balance}, 权益={equity}")

    def _generate_client_order_id(self, action_intent: ActionIntent, order_type: str) -> str:
        """
        生成客户端订单ID

        Args:
            action_intent: 策略行为意图
            order_type: 订单类型

        Returns:
            str: 客户端订单ID
        """
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S%f")[:-3]
        return f"{action_intent.strategy_id}_{order_type}_{timestamp}"

    def convert_action_intents_to_order_intents(
        self,
        action_intents: list[ActionIntent],
        position_size: float,
        symbol: str,
        current_price: float,
    ) -> list[OrderIntent]:
        """
        将策略行为意图转换为标准化订单意图
        严格遵循V1.6 constitution：策略只生成行为请求，不决定仓位大小

        Args:
            action_intents: 策略行为意图列表
            position_size: 由Position Sizing模块计算的仓位大小
            symbol: 交易对
            current_price: 当前价格

        Returns:
            List[OrderIntent]: 标准化订单意图列表
        """
        order_intents = []

        for action_intent in action_intents:
            # 根据行为类型生成订单意图
            if action_intent.action_type == "hold":
                logger.info(f"执行持有策略：{symbol}")
                continue  # 持有状态不生成订单

            # 确定订单方向
            if action_intent.action_type == "enter":
                side = "buy"
            elif action_intent.action_type == "exit":
                side = "sell"
                # 卖出时，订单金额不能超过当前持仓
                current_position = self.current_positions.get(symbol, 0.0)
                if current_position <= 0:
                    logger.info(f"当前无持仓，跳过卖出订单：{symbol}")
                    continue
            else:
                logger.warning(f"未知的行为类型：{action_intent.action_type}")
                continue

            # 订单大小由position_size决定，策略不能修改
            order_size = position_size

            # 检查风险 - 仅用于验证，不影响订单生成
            risk_verdict = self.risk_manager.get_risk_verdict(
                symbol=symbol,
                side=side,
                amount=order_size,
                price=current_price,
                balance=self.current_balance,
                current_position=self.current_positions.get(symbol, 0.0),
                total_position=sum(self.current_positions.values()),
                equity=self.current_equity,
                leverage=1.0,  # 杠杆由risk系统决定，策略不能指定
                is_contract=False,
                contract_amount=0.0,
            )

            # 检查是否允许交易
            is_allowed = False
            if side == "buy":
                is_allowed = risk_verdict.allow_open
            else:
                is_allowed = risk_verdict.allow_reduce

            # 生成客户端订单ID
            client_order_id = self._generate_client_order_id(action_intent, "market")

            # 创建订单意图
            order_intent = OrderIntent(
                symbol=symbol,
                side=side,
                order_type="market",  # 默认为市价单
                amount=order_size,
                price=current_price if side == "buy" else None,  # 限价单需要价格
                leverage=1.0,  # 杠杆由risk系统决定，策略不能指定
                strategy_id=action_intent.strategy_id,
                client_order_id=client_order_id,
                is_reduce_only=side == "sell" and not risk_verdict.allow_open,
                is_blocked=not is_allowed,
                blocked_reasons=risk_verdict.blocked_reason,
            )

            # 记录日志
            if not is_allowed:
                logger.warning(
                    f"订单被风控阻止：{symbol} {side} {order_size} {current_price}，原因：{', '.join(risk_verdict.blocked_reason)}"
                )
            else:
                logger.info(f"生成订单意图：{symbol} {side} {order_size} {current_price}")

            order_intents.append(order_intent)

        return order_intents

    def filter_valid_order_intents(self, order_intents: list[OrderIntent]) -> list[OrderIntent]:
        """
        过滤有效的订单意图

        Args:
            order_intents: 订单意图列表

        Returns:
            List[OrderIntent]: 有效的订单意图列表
        """
        valid_intents = []

        for intent in order_intents:
            if not intent.is_blocked:
                valid_intents.append(intent)

        logger.info(f"过滤后有效订单意图数量：{len(valid_intents)}/{len(order_intents)}")
        return valid_intents

    def process_action_intents(
        self,
        action_intents: list[ActionIntent],
        position_size: float,
        symbol: str,
        current_price: float,
        positions: dict[str, float] | None = None,
        balance: float | None = None,
        equity: float | None = None,
    ) -> list[OrderIntent]:
        """
        处理策略行为意图，生成有效的订单意图

        Args:
            action_intents: 策略行为意图列表
            position_size: 由Position Sizing模块计算的仓位大小
            symbol: 交易对
            current_price: 当前价格
            positions: 当前持仓量字典（可选）
            balance: 当前可用余额（可选）
            equity: 当前账户权益（可选）

        Returns:
            List[OrderIntent]: 有效的订单意图列表
        """
        # 更新当前状态（如果提供了新的状态）
        if positions is not None:
            self.current_positions = positions
        if balance is not None:
            self.current_balance = balance
        if equity is not None:
            self.current_equity = equity

        # 转换行为意图为订单意图
        order_intents = self.convert_action_intents_to_order_intents(
            action_intents, position_size, symbol, current_price
        )

        # 过滤有效的订单意图
        valid_intents = self.filter_valid_order_intents(order_intents)

        return valid_intents

    def validate_order_intents(self, order_intents: list[OrderIntent]) -> dict[str, Any]:
        """
        验证订单意图

        Args:
            order_intents: 订单意图列表

        Returns:
            Dict[str, Any]: 验证结果
        """
        validation_results = {
            "total_intents": len(order_intents),
            "valid_intents": 0,
            "blocked_intents": 0,
            "risk_violations": [],
            "timestamp": datetime.now().isoformat(),
        }

        for intent in order_intents:
            if not intent.is_blocked:
                validation_results["valid_intents"] += 1
            else:
                validation_results["blocked_intents"] += 1
                validation_results["risk_violations"].extend(intent.blocked_reasons)

        # 去重风险违规原因
        validation_results["risk_violations"] = list(set(validation_results["risk_violations"]))

        return validation_results

    def get_stats(self) -> dict[str, Any]:
        """
        获取桥接器统计信息

        Returns:
            Dict[str, Any]: 统计信息
        """
        return {
            "current_positions": self.current_positions,
            "current_balance": self.current_balance,
            "current_equity": self.current_equity,
            "risk_params": self.risk_manager.risk_params,
            "timestamp": datetime.now().isoformat(),
        }
