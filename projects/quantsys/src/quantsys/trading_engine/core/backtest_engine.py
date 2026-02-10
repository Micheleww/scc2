#!/usr/bin/env python3
"""
回测引擎
支持历史数据回测，计算性能指标
"""

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import pandas as pd

from src.quantsys.trading_engine.core.data_provider import DataProvider
from src.quantsys.trading_engine.core.strategy_base import StrategyBase

logger = logging.getLogger(__name__)


class BacktestEngine:
    """
    回测引擎
    执行策略回测，计算性能指标
    """

    def __init__(
        self,
        strategy: StrategyBase,
        data_provider: DataProvider,
        config: Dict[str, Any] = None,
    ):
        """
        初始化回测引擎

        Args:
            strategy: 交易策略
            data_provider: 数据提供者
            config: 回测配置
        """
        self.strategy = strategy
        self.data_provider = data_provider
        self.config = config or {}
        
        self.initial_balance = self.config.get("starting_balance", 1000.0)
        self.stake_amount = self.config.get("stake_amount", 0.01)
        self.max_open_trades = self.config.get("max_open_trades", 3)
        
        logger.info(f"回测引擎初始化完成，初始资金: {self.initial_balance}")

    def run(
        self,
        pairs: List[str],
        timerange: Optional[tuple] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        运行回测

        Args:
            pairs: 交易对列表
            timerange: 时间范围 (start, end) 或 (start_str, end_str)
            **kwargs: 其他参数

        Returns:
            回测结果
        """
        logger.info(f"开始回测: {pairs}, timerange: {timerange}")
        
        # 初始化回测状态
        balance = self.initial_balance
        open_trades: Dict[str, Dict] = {}
        closed_trades: List[Dict] = []
        equity_curve: List[Dict] = []
        
        # 解析时间范围
        start_date, end_date = self._parse_timerange(timerange)
        
        # 获取所有数据
        all_data = {}
        for pair in pairs:
            df = self.data_provider.get_ohlcv(
                pair=pair,
                timeframe=self.strategy.timeframe,
                since=start_date,
            )
            if not df.empty:
                all_data[pair] = df
        
        if not all_data:
            return {"error": "无法获取回测数据"}
        
        # 合并所有时间戳
        all_timestamps = set()
        for df in all_data.values():
            all_timestamps.update(df.index)
        all_timestamps = sorted(all_timestamps)
        
        # 过滤时间范围
        if start_date:
            all_timestamps = [t for t in all_timestamps if t >= start_date]
        if end_date:
            all_timestamps = [t for t in all_timestamps if t <= end_date]
        
        # 遍历每个时间点
        for timestamp in all_timestamps:
            # 处理每个交易对
            for pair, dataframe in all_data.items():
                # 获取到当前时间的数据
                current_data = dataframe[dataframe.index <= timestamp]
                if len(current_data) < 10:  # 至少需要10根K线
                    continue
                
                # 确保数据按时间排序
                current_data = current_data.sort_index()
                
                # 确保当前时间点有数据
                if timestamp not in dataframe.index:
                    continue
                
                metadata = {"pair": pair}
                
                # 执行策略
                try:
                    current_data = self.strategy.populate_indicators(current_data, metadata)
                    current_data = self.strategy.populate_entry_trend(current_data, metadata)
                    current_data = self.strategy.populate_exit_trend(current_data, metadata)
                except Exception as e:
                    logger.warning(f"策略执行出错: {e}")
                    continue
                
                if current_data.empty:
                    continue
                
                latest = current_data.iloc[-1]
                current_price = float(latest["close"])
                
                # 检查出场信号
                if pair in open_trades:
                    trade = open_trades[pair]
                    should_exit = False
                    exit_reason = None
                    
                    if trade["side"] == "long" and latest.get("exit_long", 0) == 1:
                        should_exit = True
                        exit_reason = "exit_signal"
                    elif trade["side"] == "short" and latest.get("exit_short", 0) == 1:
                        should_exit = True
                        exit_reason = "exit_signal"
                    
                    # 检查止损
                    if not should_exit:
                        stoploss = self.strategy.custom_stoploss(
                            pair=pair,
                            trade=trade,
                            current_time=timestamp,
                            current_rate=current_price,
                            current_profit=0,
                        )
                        if stoploss < 0:
                            if trade["side"] == "long":
                                stop_price = trade["entry_price"] * (1 + stoploss)
                                if current_price <= stop_price:
                                    should_exit = True
                                    exit_reason = "stoploss"
                            else:
                                stop_price = trade["entry_price"] * (1 - stoploss)
                                if current_price >= stop_price:
                                    should_exit = True
                                    exit_reason = "stoploss"
                    
                    if should_exit:
                        # 平仓
                        profit = (current_price - trade["entry_price"]) * trade["amount"]
                        if trade["side"] == "short":
                            profit = -profit
                        
                        profit_pct = (current_price / trade["entry_price"] - 1) * 100
                        if trade["side"] == "short":
                            profit_pct = -profit_pct
                        
                        balance += profit
                        
                        closed_trade = {
                            **trade,
                            "exit_time": timestamp,
                            "exit_price": current_price,
                            "exit_reason": exit_reason,
                            "profit": profit,
                            "profit_pct": profit_pct,
                        }
                        closed_trades.append(closed_trade)
                        del open_trades[pair]
                
                # 检查入场信号
                if pair not in open_trades and len(open_trades) < self.max_open_trades:
                    has_entry_long = latest.get("enter_long", 0) == 1
                    has_entry_short = latest.get("enter_short", 0) == 1
                    
                    if has_entry_long and balance >= self.stake_amount:
                        # 开多
                        open_trades[pair] = {
                            "pair": pair,
                            "side": "long",
                            "entry_time": timestamp,
                            "entry_price": current_price,
                            "amount": self.stake_amount,
                        }
                        balance -= self.stake_amount
                    elif has_entry_short and balance >= self.stake_amount:
                        # 开空
                        open_trades[pair] = {
                            "pair": pair,
                            "side": "short",
                            "entry_time": timestamp,
                            "entry_price": current_price,
                            "amount": self.stake_amount,
                        }
                        balance -= self.stake_amount
            
            # 记录权益曲线
            current_equity = balance
            for trade in open_trades.values():
                # 计算未实现盈亏
                pair = trade["pair"]
                if pair in all_data:
                    try:
                        pair_data = all_data[pair]
                        if timestamp in pair_data.index:
                            current_price = float(pair_data.loc[timestamp, "close"])
                            unrealized = (current_price - trade["entry_price"]) * trade["amount"]
                            if trade["side"] == "short":
                                unrealized = -unrealized
                            current_equity += unrealized
                    except (KeyError, IndexError):
                        # 如果该时间点没有数据，使用入场价格
                        pass
            
            equity_curve.append({
                "timestamp": timestamp,
                "balance": balance,
                "equity": current_equity,
                "open_trades": len(open_trades),
            })
        
        # 计算性能指标
        results = self._calculate_metrics(
            initial_balance=self.initial_balance,
            final_balance=balance,
            closed_trades=closed_trades,
            equity_curve=equity_curve,
        )
        
        logger.info(f"回测完成: 总盈亏 {results['total_profit_pct']:.2f}%")
        
        return results

    def _parse_timerange(self, timerange: Optional[tuple]) -> tuple:
        """解析时间范围"""
        if not timerange:
            return None, None
        
        start, end = timerange
        
        if isinstance(start, str):
            # 支持相对时间，如 "30d", "1w"
            if start.endswith("d"):
                days = int(start[:-1])
                start = datetime.now() - timedelta(days=days)
            elif start.endswith("w"):
                weeks = int(start[:-1])
                start = datetime.now() - timedelta(weeks=weeks)
            elif start.endswith("h"):
                hours = int(start[:-1])
                start = datetime.now() - timedelta(hours=hours)
            else:
                try:
                    # 尝试解析ISO格式
                    start = datetime.fromisoformat(start.replace("Z", "+00:00"))
                except:
                    # 尝试解析其他格式
                    try:
                        start = datetime.strptime(start, "%Y%m%d")
                    except:
                        logger.warning(f"无法解析时间范围: {start}, 使用None")
                        start = None
        
        if isinstance(end, str):
            try:
                end = datetime.fromisoformat(end.replace("Z", "+00:00"))
            except:
                try:
                    end = datetime.strptime(end, "%Y%m%d")
                except:
                    logger.warning(f"无法解析时间范围: {end}, 使用None")
                    end = None
        
        return start, end

    def _calculate_metrics(
        self,
        initial_balance: float,
        final_balance: float,
        closed_trades: List[Dict],
        equity_curve: List[Dict],
    ) -> Dict[str, Any]:
        """计算性能指标"""
        total_profit = final_balance - initial_balance
        total_profit_pct = (final_balance / initial_balance - 1) * 100
        
        winning_trades = [t for t in closed_trades if t.get("profit", 0) > 0]
        losing_trades = [t for t in closed_trades if t.get("profit", 0) <= 0]
        
        win_rate = len(winning_trades) / len(closed_trades) * 100 if closed_trades else 0
        
        avg_win = sum(t.get("profit", 0) for t in winning_trades) / len(winning_trades) if winning_trades else 0
        avg_loss = sum(t.get("profit", 0) for t in losing_trades) / len(losing_trades) if losing_trades else 0
        
        profit_factor = abs(avg_win / avg_loss) if avg_loss != 0 else 0
        
        # 计算最大回撤
        max_equity = initial_balance
        max_drawdown = 0
        max_drawdown_pct = 0
        
        for point in equity_curve:
            equity = point["equity"]
            if equity > max_equity:
                max_equity = equity
            drawdown = max_equity - equity
            drawdown_pct = (drawdown / max_equity) * 100 if max_equity > 0 else 0
            
            if drawdown > max_drawdown:
                max_drawdown = drawdown
                max_drawdown_pct = drawdown_pct
        
        return {
            "initial_balance": initial_balance,
            "final_balance": final_balance,
            "total_profit": total_profit,
            "total_profit_pct": total_profit_pct,
            "total_trades": len(closed_trades),
            "winning_trades": len(winning_trades),
            "losing_trades": len(losing_trades),
            "win_rate": win_rate,
            "avg_win": avg_win,
            "avg_loss": avg_loss,
            "profit_factor": profit_factor,
            "max_drawdown": max_drawdown,
            "max_drawdown_pct": max_drawdown_pct,
            "closed_trades": closed_trades,
            "equity_curve": equity_curve,
        }
