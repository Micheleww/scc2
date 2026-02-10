#!/usr/bin/env python3
"""
交易机器人核心类
协调策略、数据、执行等模块，实现完整的交易流程
"""

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import pandas as pd

from src.quantsys.execution.execution_manager import ExecutionManager
from src.quantsys.trading_engine.core.data_provider import DataProvider
from src.quantsys.trading_engine.core.strategy_base import StrategyBase

logger = logging.getLogger(__name__)


class TradingBot:
    """
    交易机器人
    核心交易执行引擎，替代freqtrade功能
    """

    def __init__(
        self,
        strategy: StrategyBase,
        config: Dict[str, Any],
        data_provider: Optional[DataProvider] = None,
        execution_manager: Optional[ExecutionManager] = None,
    ):
        """
        初始化交易机器人

        Args:
            strategy: 交易策略实例
            config: 配置字典
            data_provider: 数据提供者（可选）
            execution_manager: 执行管理器（可选）
        """
        self.strategy = strategy
        self.config = config
        self.dry_run = config.get("dry_run", True)
        self.max_open_trades = config.get("max_open_trades", 3)
        self.stake_amount = config.get("stake_amount", 0.01)
        self.stake_currency = config.get("stake_currency", "USDT")
        
        # 初始化组件
        self.data_provider = data_provider or DataProvider(config.get("data", {}))
        self.execution_manager = execution_manager
        
        # 交易状态
        self.open_trades: Dict[str, Dict] = {}
        self.closed_trades: List[Dict] = []
        self.orders: Dict[str, Dict] = {}
        
        # 运行状态
        self.running = False
        self.last_update = None
        
        logger.info(f"交易机器人初始化完成 (dry_run={self.dry_run})")

    def start(self) -> None:
        """启动交易机器人"""
        if self.running:
            logger.warning("交易机器人已在运行")
            return
        
        self.running = True
        self.strategy.bot_start()
        logger.info("交易机器人已启动")

    def stop(self) -> None:
        """停止交易机器人"""
        if not self.running:
            return
        
        self.running = False
        self.strategy.bot_stop()
        logger.info("交易机器人已停止")

    def process(self, pair: str) -> Dict[str, Any]:
        """
        处理单个交易对

        Args:
            pair: 交易对

        Returns:
            处理结果
        """
        if not self.running:
            return {"status": "stopped", "message": "交易机器人未运行"}
        
        try:
            # 获取数据
            dataframe = self.data_provider.get_ohlcv(
                pair=pair,
                timeframe=self.strategy.timeframe,
                limit=500
            )
            
            if dataframe.empty:
                return {"status": "error", "message": f"无法获取 {pair} 的数据"}
            
            metadata = {"pair": pair}
            
            # 执行策略
            dataframe = self.strategy.populate_indicators(dataframe, metadata)
            dataframe = self.strategy.populate_entry_trend(dataframe, metadata)
            dataframe = self.strategy.populate_exit_trend(dataframe, metadata)
            
            # 检查入场信号
            latest = dataframe.iloc[-1]
            has_entry_long = latest.get("enter_long", 0) == 1
            has_entry_short = latest.get("enter_short", 0) == 1
            has_exit_long = latest.get("exit_long", 0) == 1
            has_exit_short = latest.get("exit_short", 0) == 1
            
            result = {
                "status": "success",
                "pair": pair,
                "timestamp": latest.name.isoformat() if hasattr(latest.name, "isoformat") else str(latest.name),
                "signals": {
                    "enter_long": has_entry_long,
                    "enter_short": has_entry_short,
                    "exit_long": has_exit_long,
                    "exit_short": has_exit_short,
                },
                "actions": [],
            }
            
            # 处理出场信号
            if pair in self.open_trades:
                trade = self.open_trades[pair]
                if (trade["side"] == "long" and has_exit_long) or \
                   (trade["side"] == "short" and has_exit_short):
                    exit_result = self._exit_trade(pair, "strategy_signal")
                    result["actions"].append(exit_result)
            
            # 处理入场信号
            if pair not in self.open_trades and len(self.open_trades) < self.max_open_trades:
                if has_entry_long:
                    entry_result = self._enter_trade(pair, "long", latest)
                    result["actions"].append(entry_result)
                elif has_entry_short:
                    entry_result = self._enter_trade(pair, "short", latest)
                    result["actions"].append(entry_result)
            
            self.last_update = datetime.now()
            return result
            
        except Exception as e:
            logger.error(f"处理交易对 {pair} 时出错: {e}", exc_info=True)
            return {"status": "error", "message": str(e)}

    def _enter_trade(self, pair: str, side: str, candle: pd.Series) -> Dict[str, Any]:
        """
        入场交易

        Args:
            pair: 交易对
            side: 方向 (long/short)
            candle: K线数据

        Returns:
            入场结果
        """
        try:
            # 确认入场
            if not self.strategy.confirm_trade_entry(
                pair=pair,
                order_type="market",
                amount=self.stake_amount,
                rate=float(candle["close"]),
                time_in_force="GTC",
                current_time=datetime.now(),
                entry_tag=None,
                side=side,
            ):
                return {"action": "enter", "status": "rejected", "reason": "策略拒绝入场"}
            
            # 执行下单
            if self.execution_manager and not self.dry_run:
                order_result = self.execution_manager.place_order(
                    symbol=pair.replace("/", "-"),
                    side="buy" if side == "long" else "sell",
                    order_type="market",
                    amount=self.stake_amount,
                )
                
                if order_result.get("code") != "0":
                    return {"action": "enter", "status": "failed", "reason": order_result.get("msg")}
                
                order_id = order_result.get("data", [{}])[0].get("ordId")
            else:
                # Dry-run模式
                order_id = f"dry_run_{int(datetime.now().timestamp())}"
            
            # 记录交易
            trade = {
                "pair": pair,
                "side": side,
                "entry_time": datetime.now(),
                "entry_price": float(candle["close"]),
                "amount": self.stake_amount,
                "order_id": order_id,
                "status": "open",
            }
            
            self.open_trades[pair] = trade
            
            logger.info(f"入场交易: {pair} {side} @ {trade['entry_price']}")
            
            return {
                "action": "enter",
                "status": "success",
                "pair": pair,
                "side": side,
                "order_id": order_id,
            }
            
        except Exception as e:
            logger.error(f"入场交易失败: {e}", exc_info=True)
            return {"action": "enter", "status": "error", "reason": str(e)}

    def _exit_trade(self, pair: str, reason: str) -> Dict[str, Any]:
        """
        出场交易

        Args:
            pair: 交易对
            reason: 出场原因

        Returns:
            出场结果
        """
        if pair not in self.open_trades:
            return {"action": "exit", "status": "error", "reason": "交易不存在"}
        
        try:
            trade = self.open_trades[pair]
            
            # 获取当前价格
            ticker = self.data_provider.get_ticker(pair)
            current_price = ticker.get("last", trade["entry_price"])
            
            # 确认出场
            if not self.strategy.confirm_trade_exit(
                pair=pair,
                trade=trade,
                order_type="market",
                amount=trade["amount"],
                rate=current_price,
                time_in_force="GTC",
                exit_reason=reason,
                current_time=datetime.now(),
            ):
                return {"action": "exit", "status": "rejected", "reason": "策略拒绝出场"}
            
            # 执行平仓
            if self.execution_manager and not self.dry_run:
                order_result = self.execution_manager.place_order(
                    symbol=pair.replace("/", "-"),
                    side="sell" if trade["side"] == "long" else "buy",
                    order_type="market",
                    amount=trade["amount"],
                )
                
                if order_result.get("code") != "0":
                    return {"action": "exit", "status": "failed", "reason": order_result.get("msg")}
                
                order_id = order_result.get("data", [{}])[0].get("ordId")
            else:
                order_id = f"dry_run_{int(datetime.now().timestamp())}"
            
            # 计算盈亏
            profit = (current_price - trade["entry_price"]) * trade["amount"]
            if trade["side"] == "short":
                profit = -profit
            
            profit_pct = (current_price / trade["entry_price"] - 1) * 100
            if trade["side"] == "short":
                profit_pct = -profit_pct
            
            # 记录已关闭交易
            closed_trade = {
                **trade,
                "exit_time": datetime.now(),
                "exit_price": current_price,
                "exit_reason": reason,
                "profit": profit,
                "profit_pct": profit_pct,
                "order_id": order_id,
                "status": "closed",
            }
            
            self.closed_trades.append(closed_trade)
            del self.open_trades[pair]
            
            logger.info(f"出场交易: {pair} @ {current_price}, 盈亏: {profit_pct:.2f}%")
            
            return {
                "action": "exit",
                "status": "success",
                "pair": pair,
                "profit": profit,
                "profit_pct": profit_pct,
                "order_id": order_id,
            }
            
        except Exception as e:
            logger.error(f"出场交易失败: {e}", exc_info=True)
            return {"action": "exit", "status": "error", "reason": str(e)}

    def get_status(self) -> Dict[str, Any]:
        """
        获取机器人状态

        Returns:
            状态字典
        """
        return {
            "running": self.running,
            "dry_run": self.dry_run,
            "strategy": self.strategy.name,
            "open_trades": len(self.open_trades),
            "max_open_trades": self.max_open_trades,
            "closed_trades": len(self.closed_trades),
            "last_update": self.last_update.isoformat() if self.last_update else None,
        }

    def get_open_trades(self) -> List[Dict]:
        """获取当前持仓"""
        return list(self.open_trades.values())

    def get_closed_trades(self, limit: int = 100) -> List[Dict]:
        """获取已关闭交易"""
        return self.closed_trades[-limit:]
