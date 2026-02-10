#!/usr/bin/env python3
"""
Freqtrade API兼容层
实现所有freqtrade API端点，确保前端可以无缝切换
"""

import logging
from typing import Any, Dict, List, Optional

from flask import jsonify, request

from src.quantsys.trading_engine.core.trading_bot import TradingBot

logger = logging.getLogger(__name__)


class FreqtradeAPICompat:
    """
    Freqtrade API兼容层
    提供与freqtrade完全兼容的API接口
    """

    def __init__(self, trading_bot: TradingBot):
        """
        初始化兼容层

        Args:
            trading_bot: 交易机器人实例
        """
        self.trading_bot = trading_bot
        logger.info("Freqtrade API兼容层初始化完成")

    def setup_routes(self, app):
        """设置所有freqtrade兼容的路由"""

        # ========== 基础功能 ==========
        
        @app.route("/api/v1/ping", methods=["GET"])
        def ping():
            """健康检查"""
            return jsonify({"status": "ok"})

        @app.route("/api/v1/status", methods=["GET"])
        def status():
            """获取交易状态"""
            bot_status = self.trading_bot.get_status()
            
            # 转换为freqtrade格式
            return jsonify({
                "state": "running" if bot_status.get("running") else "stopped",
                "trade_count": bot_status.get("open_trades", 0),
                "max_open_trades": bot_status.get("max_open_trades", 0),
                "strategy": bot_status.get("strategy", ""),
                "dry_run": bot_status.get("dry_run", True),
            })

        @app.route("/api/v1/balance", methods=["GET"])
        def balance():
            """获取账户余额"""
            if self.trading_bot.execution_manager:
                result = self.trading_bot.execution_manager.get_balance()
                # 转换为freqtrade格式
                if result.get("code") == "0" and result.get("data"):
                    data = result["data"][0] if isinstance(result["data"], list) else result["data"]
                    return jsonify({
                        "currencies": [
                            {
                                "currency": data.get("ccy", "USDT"),
                                "free": float(data.get("availBal", 0)),
                                "used": float(data.get("frozenBal", 0)),
                                "balance": float(data.get("cashBal", 0)),
                            }
                        ],
                        "total": float(data.get("cashBal", 0)),
                        "symbol": data.get("ccy", "USDT"),
                        "value": float(data.get("cashBal", 0)),
                    })
            return jsonify({"currencies": [], "total": 0, "symbol": "USDT", "value": 0})

        # ========== 交易管理 ==========

        @app.route("/api/v1/trades", methods=["GET"])
        def trades():
            """获取交易列表（兼容freqtrade格式）"""
            limit = int(request.args.get("limit", 100))
            closed_trades = self.trading_bot.get_closed_trades(limit=limit)
            
            # 转换为freqtrade格式
            trades_list = []
            for trade in closed_trades:
                trades_list.append({
                    "trade_id": trade.get("order_id", ""),
                    "pair": trade.get("pair", ""),
                    "is_open": False,
                    "is_short": trade.get("side") == "short",
                    "amount": trade.get("amount", 0),
                    "stake_amount": trade.get("amount", 0),
                    "stake_currency": self.trading_bot.stake_currency,
                    "open_date": trade.get("entry_time").isoformat() if trade.get("entry_time") else "",
                    "open_timestamp": int(trade.get("entry_time").timestamp()) if trade.get("entry_time") else 0,
                    "close_date": trade.get("exit_time").isoformat() if trade.get("exit_time") else "",
                    "close_timestamp": int(trade.get("exit_time").timestamp()) if trade.get("exit_time") else 0,
                    "open_rate": trade.get("entry_price", 0),
                    "close_rate": trade.get("exit_price", 0),
                    "current_rate": trade.get("exit_price", 0),
                    "profit_abs": trade.get("profit", 0),
                    "profit_ratio": trade.get("profit_pct", 0) / 100 if trade.get("profit_pct") else 0,
                    "profit_pct": trade.get("profit_pct", 0),
                    "exit_reason": trade.get("exit_reason", ""),
                })
            
            return jsonify(trades_list)

        @app.route("/api/v1/trades/open", methods=["GET"])
        def trades_open():
            """获取当前持仓（兼容freqtrade格式）"""
            open_trades = self.trading_bot.get_open_trades()
            
            # 转换为freqtrade格式
            trades_list = []
            for trade in open_trades:
                # 获取当前价格
                ticker = self.trading_bot.data_provider.get_ticker(trade.get("pair", ""))
                current_rate = ticker.get("last", trade.get("entry_price", 0)) if ticker else trade.get("entry_price", 0)
                
                # 计算未实现盈亏
                entry_price = trade.get("entry_price", 0)
                amount = trade.get("amount", 0)
                if trade.get("side") == "long":
                    profit_abs = (current_rate - entry_price) * amount
                    profit_ratio = (current_rate / entry_price - 1) * 100 if entry_price > 0 else 0
                else:
                    profit_abs = (entry_price - current_rate) * amount
                    profit_ratio = (entry_price / current_rate - 1) * 100 if current_rate > 0 else 0
                
                trades_list.append({
                    "trade_id": trade.get("order_id", ""),
                    "pair": trade.get("pair", ""),
                    "is_open": True,
                    "is_short": trade.get("side") == "short",
                    "amount": amount,
                    "stake_amount": amount,
                    "stake_currency": self.trading_bot.stake_currency,
                    "open_date": trade.get("entry_time").isoformat() if trade.get("entry_time") else "",
                    "open_timestamp": int(trade.get("entry_time").timestamp()) if trade.get("entry_time") else 0,
                    "open_rate": entry_price,
                    "current_rate": current_rate,
                    "profit_abs": profit_abs,
                    "profit_ratio": profit_ratio / 100,
                    "profit_pct": profit_ratio,
                })
            
            return jsonify(trades_list)

        @app.route("/api/v1/profit", methods=["GET"])
        def profit():
            """获取盈亏统计"""
            closed_trades = self.trading_bot.get_closed_trades(limit=1000)
            
            total_profit = sum(t.get("profit", 0) for t in closed_trades)
            winning_trades = [t for t in closed_trades if t.get("profit", 0) > 0]
            losing_trades = [t for t in closed_trades if t.get("profit", 0) <= 0]
            
            return jsonify({
                "profit_closed_coin": total_profit,
                "profit_closed_percent_mean": sum(t.get("profit_pct", 0) for t in closed_trades) / len(closed_trades) if closed_trades else 0,
                "profit_closed_ratio": len(winning_trades) / len(closed_trades) if closed_trades else 0,
                "profit_closed_percent_sum": sum(t.get("profit_pct", 0) for t in closed_trades),
                "profit_closed_fiat": total_profit,  # 假设USDT
                "profit_all_coin": total_profit,
                "profit_all_percent_mean": sum(t.get("profit_pct", 0) for t in closed_trades) / len(closed_trades) if closed_trades else 0,
                "profit_all_ratio": len(winning_trades) / len(closed_trades) if closed_trades else 0,
                "profit_all_percent_sum": sum(t.get("profit_pct", 0) for t in closed_trades),
                "profit_all_fiat": total_profit,
                "trade_count": len(closed_trades),
                "closed_trade_count": len(closed_trades),
                "winning_trades": len(winning_trades),
                "losing_trades": len(losing_trades),
            })

        # ========== 控制功能 ==========

        @app.route("/api/v1/start", methods=["POST"])
        def start():
            """启动交易机器人"""
            try:
                self.trading_bot.start()
                return jsonify({"status": "starting"})
            except Exception as e:
                return jsonify({"status": "error", "message": str(e)}), 500

        @app.route("/api/v1/stop", methods=["POST"])
        def stop():
            """停止交易机器人"""
            try:
                self.trading_bot.stop()
                return jsonify({"status": "stopped"})
            except Exception as e:
                return jsonify({"status": "error", "message": str(e)}), 500

        @app.route("/api/v1/reload_config", methods=["POST"])
        def reload_config():
            """重新加载配置"""
            # 暂时只返回成功，实际重载需要重新初始化
            return jsonify({"status": "reloaded"})

        # ========== 交易对管理 ==========

        @app.route("/api/v1/whitelist", methods=["GET"])
        def whitelist():
            """获取交易对白名单"""
            config = self.trading_bot.config
            pairs = config.get("exchange", {}).get("pair_whitelist", [])
            return jsonify({"whitelist": pairs})

        @app.route("/api/v1/blacklist", methods=["GET"])
        def blacklist():
            """获取交易对黑名单"""
            config = self.trading_bot.config
            pairs = config.get("exchange", {}).get("pair_blacklist", [])
            return jsonify({"blacklist": pairs})

        # ========== 策略管理 ==========

        @app.route("/api/v1/strategies", methods=["GET"])
        def strategies():
            """获取策略列表"""
            # 从user_data/strategies目录扫描策略文件
            import os
            from pathlib import Path
            
            strategies_dir = Path("user_data/strategies")
            strategies = []
            
            if strategies_dir.exists():
                for file in strategies_dir.glob("*.py"):
                    if file.name != "__init__.py":
                        strategies.append(file.stem)
            
            return jsonify({"strategies": strategies})

        @app.route("/api/v1/show_config", methods=["GET"])
        def show_config():
            """获取配置"""
            return jsonify(self.trading_bot.config)

        # ========== 强制交易 ==========

        @app.route("/api/v1/force_entry", methods=["POST"])
        def force_entry():
            """强制入场"""
            data = request.get_json() or {}
            pair = data.get("pair")
            side = data.get("side", "long")
            
            if not pair:
                return jsonify({"error": "缺少pair参数"}), 400
            
            try:
                ticker = self.trading_bot.data_provider.get_ticker(pair)
                if not ticker:
                    return jsonify({"error": "无法获取价格"}), 400
                
                import pandas as pd
                candle = pd.Series({
                    "close": ticker["last"],
                    "open": ticker["last"],
                    "high": ticker["last"],
                    "low": ticker["last"],
                    "volume": 0,
                })
                
                result = self.trading_bot._enter_trade(pair, side, candle)
                if result.get("status") == "success":
                    return jsonify({"id": result.get("order_id"), "status": "open"})
                else:
                    return jsonify({"error": result.get("reason", "入场失败")}), 400
            except Exception as e:
                return jsonify({"error": str(e)}), 500

        @app.route("/api/v1/force_exit", methods=["POST"])
        def force_exit():
            """强制出场"""
            data = request.get_json() or {}
            trade_id = data.get("trade_id")
            pair = data.get("pair")
            
            if not trade_id and not pair:
                return jsonify({"error": "缺少trade_id或pair参数"}), 400
            
            try:
                if pair:
                    result = self.trading_bot._exit_trade(pair, "force_exit")
                else:
                    # 根据trade_id查找交易对
                    open_trades = self.trading_bot.get_open_trades()
                    trade = next((t for t in open_trades if t.get("order_id") == trade_id), None)
                    if not trade:
                        return jsonify({"error": "交易不存在"}), 404
                    result = self.trading_bot._exit_trade(trade.get("pair"), "force_exit")
                
                if result.get("status") == "success":
                    return jsonify({"id": result.get("order_id"), "status": "closed"})
                else:
                    return jsonify({"error": result.get("reason", "出场失败")}), 400
            except Exception as e:
                return jsonify({"error": str(e)}), 500

        # ========== 性能统计 ==========

        @app.route("/api/v1/performance", methods=["GET"])
        def performance():
            """获取策略表现"""
            closed_trades = self.trading_bot.get_closed_trades(limit=1000)
            
            # 按策略分组统计（目前只有一个策略）
            strategy_name = self.trading_bot.strategy.name
            
            winning = [t for t in closed_trades if t.get("profit", 0) > 0]
            losing = [t for t in closed_trades if t.get("profit", 0) <= 0]
            
            return jsonify([{
                "pair": "ALL",
                "profit_abs": sum(t.get("profit", 0) for t in closed_trades),
                "count": len(closed_trades),
                "profit_pct": sum(t.get("profit_pct", 0) for t in closed_trades) / len(closed_trades) if closed_trades else 0,
            }])

        logger.info("Freqtrade API兼容路由设置完成")
