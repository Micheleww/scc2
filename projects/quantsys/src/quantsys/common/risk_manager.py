#!/usr/bin/env python3

"""
风险控制模块
实现实盘交易的风险控制机制，升级为全局风控总闸
"""

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any

# 配置日志
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


@dataclass
class RiskVerdict:
    """
    风险评估结果
    """

    allow_open: bool  # 是否允许开新仓
    allow_reduce: bool  # 是否允许减仓/平仓
    blocked_reason: list[str]  # 风控触发原因列表
    is_blocked: bool  # 是否被风控阻止


class RiskManager:
    """
    风险管理器，实现各种风险控制机制
    升级为全局风控总闸，支持多种风险规则
    """

    def __init__(self, config: dict[str, Any]):
        """
        初始化风险管理器

        Args:
            config: 风险控制配置
        """
        self.config = config

        # 风险参数默认值
        self.defaults = {
            # 单笔订单风险
            "max_single_order_amount": 1000.0,  # 单笔订单最大金额（USDT）
            "max_single_order_ratio": 0.1,  # 单笔订单最大比例（相对于总资金）
            # 每日风险
            "max_daily_loss": 1000.0,  # 每日最大亏损（USDT）
            "max_daily_loss_ratio": 0.05,  # 每日最大亏损比例（相对于总资金）
            "max_daily_trades": 50,  # 每日最大交易次数
            # 连续亏损控制
            "max_consecutive_losses": 5,  # 最大连续亏损次数
            # 仓位控制
            "max_position_ratio": 0.2,  # 单一品种最大仓位比例
            "max_total_position_ratio": 0.5,  # 总仓位最大比例
            "max_position_size": 0.0,  # 单一品种最大绝对仓位大小（适用于小仓限制）
            # 其他风险
            "min_order_amount": 10.0,  # 最小订单金额（USDT）
            "max_slippage": 0.01,  # 最大滑点容忍度（1%）
            # 仓位与杠杆
            "risk_per_trade": 0.008,  # 单笔风险占权益比例
            "max_leverage": 10,  # 最大杠杆
            "min_lot_size": 0.0,  # 最小下单量（单位: 合约张或现货数量）
            # 新增风险规则
            "max_drawdown": 0.1,  # 最大回撤比例（10%）
            # 组合级风险控制（新增）
            "max_net_exposure": 0.3,  # 最大净敞口比例（30%）
            "max_correlation_concentration": 0.5,  # 最大相关性集中度（50%）
            "max_sector_concentration": 0.4,  # 最大行业集中度（40%）
            # 容量限制（新增）
            "max_strategies": 20,  # 最大策略数量
            "max_symbols": 20,  # 最大品种数量
            # 总暴露限制（新增）
            "total_exposure_limit": 10.0,  # 总暴露限制（10 USDT）
        }

        # 合并配置
        self.risk_params = {**self.defaults, **config}

        # 使用max_total_usdt作为总风险预算
        if "max_total_usdt" in self.config:
            # 使用配置中的max_total_usdt作为总暴露限制
            self.risk_params["total_exposure_limit"] = self.config["max_total_usdt"]
            logger.info(
                f"使用配置中的max_total_usdt={self.config['max_total_usdt']}，总暴露限制={self.risk_params['total_exposure_limit']} USDT"
            )
        else:
            # 默认总风险预算为1000 USDT
            self.risk_params["total_exposure_limit"] = 1000.0
            logger.info(
                f"未配置max_total_usdt，使用默认总暴露限制={self.risk_params['total_exposure_limit']} USDT"
            )

        # 添加锁机制防止竞态条件（必须在任何使用锁的初始化之前）
        import threading

        self._lock = threading.Lock()

        # 初始化风险统计数据（使用私有变量防止外部修改）
        self._daily_stats = None
        self.reset_daily_stats()

        # 初始化最大回撤相关数据
        self.initial_equity = 0.0  # 初始权益
        self.high_watermark = 0.0  # 权益最高点

        # 初始化订单时间窗口跟踪器（防止订单拆分攻击）
        from .order_window_tracker import OrderWindowTracker

        window_seconds = self.risk_params.get("order_window_seconds", 60)  # 默认60秒窗口
        max_window_amount = self.risk_params.get(
            "max_window_amount", self.risk_params["max_single_order_amount"] * 2
        )  # 默认2倍单笔限制
        self.order_window_tracker = OrderWindowTracker(
            window_seconds=window_seconds, max_window_amount=max_window_amount
        )

        # 初始化Pending订单跟踪器（准确跟踪pending订单）
        from .pending_order_tracker import PendingOrderTracker

        self.pending_order_tracker = PendingOrderTracker()

        logger.info("风险控制模块初始化完成")

    def clamp_leverage(self, leverage: float) -> float:
        """
        限制杠杆在允许范围内
        """
        if leverage <= 0:
            return 1.0
        return float(min(leverage, self.risk_params["max_leverage"]))

    def calculate_position_size_by_stop(
        self, equity: float, stop_distance: float, price: float, leverage: float = 1.0
    ) -> dict[str, float]:
        """
        基于止损距离计算仓位大小（符合单笔风险）

        Args:
            equity: 账户权益（USDT）
            stop_distance: 止损距离（USDT）
            price: 当前价格（USDT）
            leverage: 目标杠杆

        Returns:
            dict: position_size, notional, margin, leverage
        """
        if equity <= 0 or stop_distance <= 0 or price <= 0:
            logger.error("无法计算仓位：输入参数无效")
            return {"position_size": 0.0, "notional": 0.0, "margin": 0.0, "leverage": 0.0}

        leverage = self.clamp_leverage(leverage)
        risk_amount = equity * self.risk_params["risk_per_trade"]

        position_size = risk_amount / stop_distance
        notional = position_size * price
        margin = notional / leverage

        max_position_value = equity * self.risk_params["max_position_ratio"] * leverage
        if notional > max_position_value:
            notional = max_position_value
            position_size = notional / price
            margin = notional / leverage
            logger.info("仓位超过上限，已按仓位比例限制调整")

        if notional < self.risk_params["min_order_amount"]:
            logger.warning("计算得到的仓位低于最小订单金额，返回0")
            return {"position_size": 0.0, "notional": 0.0, "margin": 0.0, "leverage": leverage}

        min_lot_size = self.risk_params.get("min_lot_size", 0.0)
        if min_lot_size and min_lot_size > 0:
            position_size = round(position_size / min_lot_size) * min_lot_size
            notional = position_size * price
            margin = notional / leverage

        return {
            "position_size": position_size,
            "notional": notional,
            "margin": margin,
            "leverage": leverage,
        }

    def reset_daily_stats(self):
        """
        重置每日风险统计数据
        """
        with self._lock:  # 使用锁保护状态更新
            self._daily_stats = {
                "date": datetime.now().date(),
                "total_trades": 0,
                "total_pnl": 0.0,
                "consecutive_losses": 0,
                "last_order_time": None,
            }

        logger.info("每日风险统计数据已重置")

    @property
    def daily_stats(self) -> dict[str, Any]:
        """
        获取每日统计数据（只读）
        SECURITY: 返回副本防止外部修改
        """
        with self._lock:
            return self._daily_stats.copy() if self._daily_stats else None

    def check_daily_reset(self):
        """
        检查是否需要重置每日统计数据
        SECURITY: 使用锁保护状态检查
        """
        if not self._daily_stats:
            self.reset_daily_stats()
            return

        current_date = datetime.now().date()
        if current_date != self._daily_stats["date"]:
            self.reset_daily_stats()

    def calculate_drawdown(self, current_equity: float) -> float:
        """
        计算当前回撤比例

        Args:
            current_equity: 当前权益

        Returns:
            float: 回撤比例（0-1）
        """
        # 初始化权益和最高点
        if self.initial_equity == 0:
            self.initial_equity = current_equity
            self.high_watermark = current_equity
            return 0.0

        # 更新最高点
        if current_equity > self.high_watermark:
            self.high_watermark = current_equity

        # 计算回撤
        if self.high_watermark == 0:
            return 0.0

        drawdown = (self.high_watermark - current_equity) / self.high_watermark
        return drawdown

    def calculate_net_exposure(
        self, long_exposure: float, short_exposure: float, equity: float
    ) -> float:
        """
        计算净敞口比例

        Args:
            long_exposure: 多头敞口金额
            short_exposure: 空头敞口金额
            equity: 账户权益

        Returns:
            float: 净敞口比例（0-1）
        """
        if equity <= 0:
            return 0.0

        net_exposure = abs(long_exposure - short_exposure) / equity
        return net_exposure

    def calculate_correlation_concentration(self, positions: list[dict[str, Any]]) -> float:
        """
        计算相关性集中度（简化版，使用最大持仓占比作为近似）

        Args:
            positions: 持仓列表，每个持仓包含'symbol'和'value'字段

        Returns:
            float: 相关性集中度（0-1）
        """
        if not positions:
            return 0.0

        total_value = sum(pos["value"] for pos in positions)
        if total_value <= 0:
            return 0.0

        # 简化计算：使用最大持仓占比作为相关性集中度的近似
        max_position = max(pos["value"] for pos in positions)
        concentration = max_position / total_value
        return concentration

    def calculate_sector_concentration(self, positions: list[dict[str, Any]]) -> float:
        """
        计算行业集中度（简化版，使用主要行业占比作为近似）

        Args:
            positions: 持仓列表，每个持仓包含'symbol'和'value'字段

        Returns:
            float: 行业集中度（0-1）
        """
        if not positions:
            return 0.0

        total_value = sum(pos["value"] for pos in positions)
        if total_value <= 0:
            return 0.0

        # 简化计算：假设BTC和ETH代表主要行业，计算它们的总占比
        major_sector_value = sum(
            pos["value"]
            for pos in positions
            if pos["symbol"].startswith("BTC") or pos["symbol"].startswith("ETH")
        )
        concentration = major_sector_value / total_value
        return concentration

    def get_portfolio_risk_verdict(
        self,
        long_exposure: float,
        short_exposure: float,
        total_exposure: float,
        equity: float,
        leverage: float,
        positions: list[dict[str, Any]],
        simplified: bool = False,
    ) -> RiskVerdict:
        """
        获取组合级风险评估结果

        Args:
            long_exposure: 多头敞口金额
            short_exposure: 空头敞口金额
            total_exposure: 总敞口金额
            equity: 账户权益
            leverage: 当前使用杠杆
            positions: 持仓列表，每个持仓包含'symbol'和'value'字段
            simplified: 是否为简化模式（用于单一订单风险检查时跳过某些检查）

        Returns:
            RiskVerdict: 组合级风险评估结果
        """
        blocked_reasons = []

        logger.info(
            f"检查组合风险: 多头敞口={long_exposure}, 空头敞口={short_exposure}, 总敞口={total_exposure}, 权益={equity}, 杠杆={leverage}"
        )

        # 1. 检查净敞口限制
        net_exposure = self.calculate_net_exposure(long_exposure, short_exposure, equity)
        if net_exposure > self.risk_params["max_net_exposure"]:
            blocked_reasons.append(
                f"净敞口比例 {net_exposure:.4f} 超过限制 {self.risk_params['max_net_exposure']}"
            )

        # 2. 检查杠杆限制
        if leverage > self.risk_params["max_leverage"]:
            blocked_reasons.append(f"杠杆 {leverage} 超过限制 {self.risk_params['max_leverage']}")

        # 3. 检查相关性集中度限制（简化模式下跳过）
        if not simplified:
            correlation_concentration = self.calculate_correlation_concentration(positions)
            if correlation_concentration > self.risk_params["max_correlation_concentration"]:
                blocked_reasons.append(
                    f"相关性集中度 {correlation_concentration:.4f} 超过限制 {self.risk_params['max_correlation_concentration']}"
                )

        # 4. 检查行业集中度限制（简化模式下跳过）
        if not simplified:
            sector_concentration = self.calculate_sector_concentration(positions)
            if sector_concentration > self.risk_params["max_sector_concentration"]:
                blocked_reasons.append(
                    f"行业集中度 {sector_concentration:.4f} 超过限制 {self.risk_params['max_sector_concentration']}"
                )

        # 5. 检查最大回撤限制
        drawdown = self.calculate_drawdown(equity)
        if drawdown >= self.risk_params["max_drawdown"]:
            blocked_reasons.append(
                f"回撤 {drawdown:.4f} 超过限制 {self.risk_params['max_drawdown']}"
            )

        # 决定是否允许开新仓和减仓
        allow_open = len(blocked_reasons) == 0
        allow_reduce = True  # 始终允许减仓/平仓

        # 记录风险评估结果
        logger.info(
            f"组合风险评估结果: 允许开新仓={allow_open}, 允许减仓={allow_reduce}, 阻塞原因={blocked_reasons}"
        )

        return RiskVerdict(
            allow_open=allow_open,
            allow_reduce=allow_reduce,
            blocked_reason=blocked_reasons,
            is_blocked=len(blocked_reasons) > 0,
        )

    def calculate_total_exposure(
        self,
        current_total_position: float,
        pending_orders: float,
        new_order_amount: float,
        side: str,
    ) -> float:
        """
        计算总暴露，汇总当前持仓估值+未成交委托占用+新订单占用

        Args:
            current_total_position: 当前总持仓金额
            pending_orders: 未成交委托总占用金额
            new_order_amount: 新订单金额
            side: 买卖方向

        Returns:
            float: 总暴露金额
        """
        # 计算新增订单后的总暴露
        if side == "buy":
            total_exposure = current_total_position + pending_orders + new_order_amount
        else:
            total_exposure = current_total_position + pending_orders  # 卖单不增加总暴露

        logger.info(
            f"计算总暴露: 当前总持仓={current_total_position}, 未成交委托={pending_orders}, 新订单={new_order_amount}, 总暴露={total_exposure}"
        )
        return total_exposure

    def get_risk_verdict(
        self,
        symbol: str,
        side: str,
        amount: float,
        price: float,
        balance: float,
        current_position: float,
        total_position: float,
        equity: float,
        leverage: float,
        is_contract: bool = False,
        contract_amount: float = 0.0,
        pending_orders: float = 0.0,
        order_id: str | None = None,
    ) -> RiskVerdict:
        """
        获取风险评估结果

        Args:
            symbol: 交易对
            side: 买卖方向
            amount: 交易数量
            price: 交易价格
            balance: 当前可用余额
            current_position: 当前品种持仓金额
            total_position: 总持仓金额
            equity: 当前账户权益
            leverage: 当前使用杠杆
            is_contract: 是否为合约交易
            contract_amount: 合约交易的实际保证金金额（USDT）
            pending_orders: 未成交委托总占用金额（USDT）

        Returns:
            RiskVerdict: 风险评估结果
        """
        # SECURITY: 输入验证
        import math

        if symbol is None or not isinstance(symbol, str) or len(symbol) == 0:
            return RiskVerdict(
                allow_open=False,
                allow_reduce=True,
                blocked_reason=["无效的交易对"],
                is_blocked=True,
            )
        if side not in ["buy", "sell"]:
            return RiskVerdict(
                allow_open=False,
                allow_reduce=True,
                blocked_reason=[f"无效的买卖方向: {side}"],
                is_blocked=True,
            )
        if amount is None or not math.isfinite(amount) or amount <= 0:
            return RiskVerdict(
                allow_open=False,
                allow_reduce=True,
                blocked_reason=[f"无效的交易数量: {amount}"],
                is_blocked=True,
            )
        if price is None or not math.isfinite(price) or price <= 0:
            return RiskVerdict(
                allow_open=False,
                allow_reduce=True,
                blocked_reason=[f"无效的交易价格: {price}"],
                is_blocked=True,
            )
        if balance is None or not math.isfinite(balance) or balance < 0:
            return RiskVerdict(
                allow_open=False,
                allow_reduce=True,
                blocked_reason=[f"无效的余额: {balance}"],
                is_blocked=True,
            )

        # 使用锁保护整个检查过程，防止竞态条件
        with self._lock:
            self.check_daily_reset()
            stats = self._daily_stats.copy() if self._daily_stats else None
            blocked_reasons = []

            # 对于合约交易，使用实际保证金金额进行风险检查
            if is_contract:
                order_amount = contract_amount
            else:
                order_amount = amount * price

            # 验证order_amount有效性
            if not math.isfinite(order_amount) or order_amount < 0:
                return RiskVerdict(
                    allow_open=False,
                    allow_reduce=True,
                    blocked_reason=[f"无效的订单金额: {order_amount}"],
                    is_blocked=True,
                )

            logger.info(f"检查订单风险: {symbol} {side} {amount} @ {price} = {order_amount} USDT")
            logger.info(
                f"当前余额: {balance} USDT, 当前持仓: {current_position} USDT, 总持仓: {total_position} USDT, 未成交委托: {pending_orders} USDT"
            )
            if stats:
                logger.info(
                    f"每日统计: 交易次数={stats['total_trades']}, PnL={stats['total_pnl']}, 连续亏损={stats['consecutive_losses']}"
                )

            # 1. 检查单笔订单金额限制
            if order_amount > self.risk_params["max_single_order_amount"]:
                blocked_reasons.append(
                    f"单笔订单金额 {order_amount} 超过限制 {self.risk_params['max_single_order_amount']}"
                )

            # 1.5. 检查时间窗口累计金额限制（防止订单拆分攻击）
            window_allowed, window_total = self.order_window_tracker.add_order(
                order_amount, symbol, side
            )
            if not window_allowed:
                blocked_reasons.append(
                    f"时间窗口内累计金额 {window_total:.2f} USDT 超过限制 {self.order_window_tracker.max_window_amount} USDT"
                )

            # 2. 检查单笔订单比例限制
            if balance > 0 and order_amount > balance * self.risk_params["max_single_order_ratio"]:
                blocked_reasons.append(
                    f"单笔订单比例 {order_amount / balance:.4f} 超过限制 {self.risk_params['max_single_order_ratio']}"
                )

            # 3. 检查每日交易次数限制
            if stats and stats["total_trades"] >= self.risk_params["max_daily_trades"]:
                blocked_reasons.append(
                    f"每日交易次数 {stats['total_trades']} 超过限制 {self.risk_params['max_daily_trades']}"
                )

            # 4. 检查连续亏损限制
            if stats and stats["consecutive_losses"] >= self.risk_params["max_consecutive_losses"]:
                blocked_reasons.append(
                    f"连续亏损次数 {stats['consecutive_losses']} 超过限制 {self.risk_params['max_consecutive_losses']}"
                )

        # 5. 检查最小订单金额限制
        if order_amount < self.risk_params["min_order_amount"]:
            blocked_reasons.append(
                f"订单金额 {order_amount} 低于最小限制 {self.risk_params['min_order_amount']}"
            )

        # 6. 检查单一品种仓位限制（仅当开新仓时）
        new_position = (
            current_position + order_amount if side == "buy" else current_position - order_amount
        )
        if side == "buy":
            # 检查比例限制
            if new_position > balance * self.risk_params["max_position_ratio"]:
                blocked_reasons.append(
                    f"单一品种仓位 {new_position / balance:.4f} 超过限制 {self.risk_params['max_position_ratio']}"
                )

            # 检查绝对大小限制（小仓限制）
            if (
                self.risk_params["max_position_size"] > 0
                and amount > self.risk_params["max_position_size"]
            ):
                blocked_reasons.append(
                    f"单一品种仓位大小 {amount} 超过限制 {self.risk_params['max_position_size']}"
                )

            # 7. 检查总仓位限制（仅当开新仓时）
            new_total_position = (
                total_position + order_amount if side == "buy" else total_position - order_amount
            )
            if (
                side == "buy"
                and new_total_position > balance * self.risk_params["max_total_position_ratio"]
            ):
                blocked_reasons.append(
                    f"总仓位 {new_total_position / balance:.4f} 超过限制 {self.risk_params['max_total_position_ratio']}"
                )

            # 8. 检查总暴露限制 - TotalExposureLimiter
            # SECURITY: 使用PendingOrderTracker获取准确的pending金额
            accurate_pending = self.pending_order_tracker.get_total_pending_amount(
                side="buy" if side == "buy" else None
            )
            # 如果提供了pending_orders参数，使用两者中的较大值（更保守）
            effective_pending = max(pending_orders, accurate_pending)

            total_exposure = self.calculate_total_exposure(
                total_position, effective_pending, order_amount, side
            )
            if total_exposure > self.risk_params["total_exposure_limit"]:
                blocked_reasons.append(
                    f"总暴露 {total_exposure:.2f} USDT 超过限制 {self.risk_params['total_exposure_limit']} USDT"
                )
                logger.error(
                    f"总暴露超限: 当前总持仓={total_position}, 未成交委托={effective_pending} "
                    f"(参数={pending_orders}, 跟踪器={accurate_pending}), 新订单={order_amount}, "
                    f"总暴露={total_exposure}, 限制={self.risk_params['total_exposure_limit']}"
                )

            # 9. 检查每日亏损限制
            if stats and stats["total_pnl"] <= -self.risk_params["max_daily_loss"]:
                blocked_reasons.append(
                    f"每日亏损 {stats['total_pnl']} 超过限制 {-self.risk_params['max_daily_loss']}"
                )

            # 10. 检查每日亏损比例限制
            if (
                stats
                and balance > 0
                and stats["total_pnl"] <= -balance * self.risk_params["max_daily_loss_ratio"]
            ):
                blocked_reasons.append(
                    f"每日亏损比例 {stats['total_pnl'] / balance:.4f} 超过限制 {-self.risk_params['max_daily_loss_ratio']}"
                )

            # 11. 检查最大回撤限制
            drawdown = self.calculate_drawdown(equity)
            if drawdown >= self.risk_params["max_drawdown"]:
                blocked_reasons.append(
                    f"回撤 {drawdown:.4f} 超过限制 {self.risk_params['max_drawdown']}"
                )

            # 12. 检查杠杆限制
            if leverage > self.risk_params["max_leverage"]:
                blocked_reasons.append(
                    f"杠杆 {leverage} 超过限制 {self.risk_params['max_leverage']}"
                )

            # 13. 检查组合级风险（简化版，使用总持仓作为多头敞口）
            # 注意：这里使用简化的组合风险检查，实际应用中需要传入完整的持仓列表
            mock_positions = [
                {
                    "symbol": symbol,
                    "value": current_position + order_amount if side == "buy" else current_position,
                }
            ]
            portfolio_verdict = self.get_portfolio_risk_verdict(
                long_exposure=total_position + order_amount if side == "buy" else total_position,
                short_exposure=0.0,  # 简化：假设只有多头
                total_exposure=total_position + order_amount if side == "buy" else total_position,
                equity=equity,
                leverage=leverage,
                positions=mock_positions,
                simplified=True,  # 简化模式，跳过集中度检查
            )

            if portfolio_verdict.is_blocked:
                blocked_reasons.extend(portfolio_verdict.blocked_reason)

            # 决定是否允许开新仓和减仓
            allow_open = len(blocked_reasons) == 0
            allow_reduce = True  # 始终允许减仓/平仓

            # 如果允许开仓且提供了order_id，将订单添加到pending跟踪器
            if allow_open and order_id and side == "buy":
                self.pending_order_tracker.add_order(
                    order_id=order_id, symbol=symbol, side=side, amount=order_amount, price=price
                )

            # 记录风险评估结果
            logger.info(
                f"风险评估结果: 允许开新仓={allow_open}, 允许减仓={allow_reduce}, 阻塞原因={blocked_reasons}"
            )

            return RiskVerdict(
                allow_open=allow_open,
                allow_reduce=allow_reduce,
                blocked_reason=blocked_reasons,
                is_blocked=len(blocked_reasons) > 0,
            )

    def check_order_risk(
        self,
        symbol: str,
        side: str,
        amount: float,
        price: float,
        balance: float,
        current_position: float,
        total_position: float,
        equity: float,
        leverage: float,
        is_contract: bool = False,
        contract_amount: float = 0.0,
        pending_orders: float = 0.0,
    ) -> bool:
        """
        检查订单风险（兼容旧接口）

        Args:
            symbol: 交易对
            side: 买卖方向
            amount: 交易数量
            price: 交易价格
            balance: 当前可用余额
            current_position: 当前品种持仓金额
            total_position: 总持仓金额
            equity: 当前账户权益
            leverage: 当前使用杠杆
            is_contract: 是否为合约交易
            contract_amount: 合约交易的实际保证金金额（USDT）
            pending_orders: 未成交委托总占用金额（USDT）

        Returns:
            bool: 是否允许下单
        """
        verdict = self.get_risk_verdict(
            symbol,
            side,
            amount,
            price,
            balance,
            current_position,
            total_position,
            equity,
            leverage,
            is_contract,
            contract_amount,
            pending_orders,
        )
        return verdict.allow_open

    def update_trade_stats(self, pnl: float):
        """
        更新交易统计数据
        SECURITY: 使用锁保护状态更新，防止竞态条件

        Args:
            pnl: 交易盈亏
        """
        with self._lock:  # 使用锁保护状态更新
            self.check_daily_reset()

            if not self._daily_stats:
                self.reset_daily_stats()

            # 更新交易次数
            self._daily_stats["total_trades"] += 1

            # 更新总盈亏
            self._daily_stats["total_pnl"] += pnl

            # 更新连续亏损次数
            if pnl < 0:
                self._daily_stats["consecutive_losses"] += 1
            else:
                self._daily_stats["consecutive_losses"] = 0

            # 更新最后订单时间
            self._daily_stats["last_order_time"] = datetime.now()

            logger.info(
                f"交易统计数据已更新: PnL={pnl:.4f}, 总PnL={self._daily_stats['total_pnl']:.4f}, "
                f"交易次数={self._daily_stats['total_trades']}, 连续亏损={self._daily_stats['consecutive_losses']}"
            )

    def check_slippage(self, expected_price: float, actual_price: float) -> bool:
        """
        检查滑点是否超过容忍度

        Args:
            expected_price: 预期价格
            actual_price: 实际成交价格

        Returns:
            bool: 是否允许成交
        """
        slippage = abs(actual_price - expected_price) / expected_price
        if slippage > self.risk_params["max_slippage"]:
            logger.error(f"滑点 {slippage:.4f} 超过限制 {self.risk_params['max_slippage']}")
            return False

        logger.info(f"滑点检查通过: {slippage:.4f}")
        return True

    def get_adjusted_order_amount(
        self,
        symbol: str,
        side: str,
        amount: float,
        price: float,
        balance: float,
        current_position: float,
        total_position: float,
    ) -> float:
        """
        获取调整后的订单金额

        Args:
            symbol: 交易对
            side: 买卖方向
            amount: 请求的交易数量
            price: 交易价格
            balance: 当前可用余额
            current_position: 当前品种持仓金额
            total_position: 总持仓金额

        Returns:
            float: 调整后的交易数量
        """
        order_amount = amount * price

        # 计算各种限制下的最大允许金额
        max_amount_by_single = self.risk_params["max_single_order_amount"]
        max_amount_by_ratio = balance * self.risk_params["max_single_order_ratio"]

        # 单一品种仓位限制
        if side == "buy":
            max_position = balance * self.risk_params["max_position_ratio"]
            max_amount_by_position = max_position - current_position
        else:
            max_amount_by_position = current_position

        # 总仓位限制
        if side == "buy":
            max_total_position = balance * self.risk_params["max_total_position_ratio"]
            max_amount_by_total = max_total_position - total_position
        else:
            max_amount_by_total = total_position

        # 取最小值
        max_allowed_amount = min(
            max_amount_by_single,
            max_amount_by_ratio,
            max_amount_by_position,
            max_amount_by_total,
            balance,  # 不能超过可用余额
        )

        # 确保不低于最小订单金额
        max_allowed_amount = max(max_allowed_amount, self.risk_params["min_order_amount"])

        # 如果请求金额超过限制，调整数量
        if order_amount > max_allowed_amount:
            adjusted_amount = max_allowed_amount / price
            logger.info(
                f"订单金额已调整: 原金额={order_amount:.2f} USDT, 调整后={max_allowed_amount:.2f} USDT, "
                f"原数量={amount:.6f}, 调整后={adjusted_amount:.6f}"
            )
            return adjusted_amount

        return amount

    def is_trading_allowed(self, balance: float, equity: float = 0.0) -> bool:
        """
        检查当前是否允许交易
        SECURITY: 使用锁保护状态读取

        Args:
            balance: 当前可用余额
            equity: 当前账户权益

        Returns:
            bool: 是否允许交易
        """
        with self._lock:
            self.check_daily_reset()
            stats = self._daily_stats.copy() if self._daily_stats else None
            blocked_reasons = []

            if not stats:
                return True

            # 检查每日亏损限制
            if stats["total_pnl"] <= -self.risk_params["max_daily_loss"]:
                blocked_reasons.append(
                    f"达到每日亏损限制: {stats['total_pnl']:.2f} <= {-self.risk_params['max_daily_loss']:.2f}"
                )

            # 检查每日亏损比例限制
            if (
                balance > 0
                and stats["total_pnl"] <= -balance * self.risk_params["max_daily_loss_ratio"]
            ):
                blocked_reasons.append(
                    f"达到每日亏损比例限制: {stats['total_pnl'] / balance:.4f} <= {-self.risk_params['max_daily_loss_ratio']:.4f}"
                )

            # 检查连续亏损限制
            if stats["consecutive_losses"] >= self.risk_params["max_consecutive_losses"]:
                blocked_reasons.append(
                    f"达到连续亏损限制: {stats['consecutive_losses']} >= {self.risk_params['max_consecutive_losses']}"
                )

            # 检查每日交易次数限制
            if stats["total_trades"] >= self.risk_params["max_daily_trades"]:
                blocked_reasons.append(
                    f"达到每日交易次数限制: {stats['total_trades']} >= {self.risk_params['max_daily_trades']}"
                )

            # 检查最大回撤限制
            if equity > 0:
                drawdown = self.calculate_drawdown(equity)
                if drawdown > self.risk_params["max_drawdown"]:
                    blocked_reasons.append(
                        f"达到最大回撤限制: {drawdown:.4f} > {self.risk_params['max_drawdown']:.4f}"
                    )

            if blocked_reasons:
                logger.error(f"交易被禁止: {', '.join(blocked_reasons)}")
                return False

        logger.info("当前允许交易")
        return True

    def get_risk_status(self) -> dict[str, Any]:
        """
        获取当前风险状态
        SECURITY: 返回只读副本

        Returns:
            dict: 风险状态信息
        """
        with self._lock:
            self.check_daily_reset()
            stats = self._daily_stats.copy() if self._daily_stats else None

        return {
            "risk_params": self.risk_params.copy(),  # 返回副本
            "daily_stats": stats,  # 已经是副本
            "timestamp": datetime.now().isoformat(),
        }

    def update_capacity_limits(self, limits: dict[str, Any]) -> None:
        """
        更新容量限制

        Args:
            limits: 容量限制字典，包含max_strategies和max_symbols
        """
        logger.info(f"更新容量限制: {limits}")

        # 更新风险参数中的容量限制
        if "max_strategies" in limits:
            self.risk_params["max_strategies"] = limits["max_strategies"]

        if "max_symbols" in limits:
            self.risk_params["max_symbols"] = limits["max_symbols"]

        logger.info(
            f"容量限制已更新: 最大策略数={self.risk_params['max_strategies']}, 最大品种数={self.risk_params['max_symbols']}"
        )
