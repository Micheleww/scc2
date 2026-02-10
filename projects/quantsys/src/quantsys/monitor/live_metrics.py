#!/usr/bin/env python3
"""
Live Metrics and Risk Control Module

This module implements the LiveMetrics class which tracks real-time performance
and risk metrics, including max drawdown monitoring with an 8% threshold that
will trigger BLOCKED state and SAFE_STOP.
"""

import datetime
import json
import os
from typing import Any


class LiveMetrics:
    """
    Live Metrics and Risk Control Class

    Tracks real-time performance metrics and enforces risk controls:
    - Real-time equity curve
    - Daily/Weekly PnL
    - Max drawdown monitoring (≥8% triggers BLOCKED state)
    - Weekly trade count monitoring (1-3 trades/week, warning if exceeded)
    """

    def __init__(self, data_dir: str = "data", metrics_dir: str = "data"):
        """
        Initialize LiveMetrics

        Args:
            data_dir: Directory to read data files from
            metrics_dir: Directory to write metrics files to
        """
        self.data_dir = data_dir
        self.metrics_dir = metrics_dir

        # Risk parameters
        self.MAX_DRAWDOWN_THRESHOLD = 0.08  # 8%
        self.MIN_TRADES_PER_WEEK = 1
        self.MAX_TRADES_PER_WEEK = 3

        # Metrics storage
        self.equity_curve = []
        self.trades = []
        self.metrics = {
            "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
            "current_equity": 0.0,
            "initial_equity": 0.0,
            "daily_pnl": 0.0,
            "weekly_pnl": 0.0,
            "max_drawdown": 0.0,
            "current_drawdown": 0.0,
            "weekly_trade_count": 0,
            "status": "NORMAL",  # NORMAL, WARNING, BLOCKED
            "status_reason": "",
            "last_update": datetime.datetime.utcnow().isoformat() + "Z",
        }

        # Load initial state if exists
        self._load_initial_state()

    def _load_initial_state(self):
        """
        Load initial state from existing files
        """
        # Load trade ledger to get initial trades
        trade_ledger_path = os.path.join(self.data_dir, "trade_ledger.json")
        if os.path.exists(trade_ledger_path):
            try:
                with open(trade_ledger_path, encoding="utf-8") as f:
                    self.trades = json.load(f)
            except (OSError, json.JSONDecodeError):
                pass

    def update_metrics(self, portfolio_snapshot: dict[str, Any]) -> dict[str, Any]:
        """
        Update metrics based on portfolio snapshot

        Args:
            portfolio_snapshot: Portfolio snapshot data

        Returns:
            dict: Updated metrics
        """
        # Get current timestamp
        now = datetime.datetime.utcnow()
        timestamp_str = now.isoformat() + "Z"

        # Extract equity from balance
        balance = portfolio_snapshot.get("balance", {})
        current_equity = balance.get("total", 0.0)

        # Update equity curve
        self.equity_curve.append({"timestamp": timestamp_str, "equity": current_equity})

        # Set initial equity if not set
        if self.metrics["initial_equity"] == 0.0:
            self.metrics["initial_equity"] = current_equity

        # Update current equity
        self.metrics["current_equity"] = current_equity

        # Calculate daily PnL
        self.metrics["daily_pnl"] = self._calculate_daily_pnl()

        # Calculate weekly PnL
        self.metrics["weekly_pnl"] = self._calculate_weekly_pnl()

        # Calculate drawdowns
        self.metrics["current_drawdown"] = self._calculate_current_drawdown()
        self.metrics["max_drawdown"] = self._calculate_max_drawdown()

        # Update weekly trade count
        self.metrics["weekly_trade_count"] = self._count_weekly_trades()

        # Update status
        self._update_status()

        # Update timestamps
        self.metrics["timestamp"] = timestamp_str
        self.metrics["last_update"] = timestamp_str

        # Save metrics
        self._save_metrics()

        return self.metrics

    def _calculate_daily_pnl(self) -> float:
        """
        Calculate daily PnL

        Returns:
            float: Daily PnL in USDT
        """
        if not self.equity_curve:
            return 0.0

        # Get today's start (UTC)
        today = datetime.datetime.utcnow().date()

        # Find first equity point of today
        today_start_equity = None
        for point in self.equity_curve:
            point_date = datetime.datetime.fromisoformat(point["timestamp"].rstrip("Z")).date()
            if point_date == today:
                today_start_equity = point["equity"]
                break

        if today_start_equity is None:
            today_start_equity = self.metrics["current_equity"]

        return self.metrics["current_equity"] - today_start_equity

    def _calculate_weekly_pnl(self) -> float:
        """
        Calculate weekly PnL

        Returns:
            float: Weekly PnL in USDT
        """
        if not self.equity_curve:
            return 0.0

        # Get current week start (Monday UTC)
        now = datetime.datetime.utcnow()
        week_start = now - datetime.timedelta(days=now.weekday())
        week_start = week_start.replace(hour=0, minute=0, second=0, microsecond=0)

        # Find first equity point of the week
        week_start_equity = None
        for point in self.equity_curve:
            point_time = datetime.datetime.fromisoformat(point["timestamp"].rstrip("Z"))
            if point_time >= week_start:
                week_start_equity = point["equity"]
                break

        if week_start_equity is None:
            week_start_equity = self.metrics["current_equity"]

        return self.metrics["current_equity"] - week_start_equity

    def _calculate_current_drawdown(self) -> float:
        """
        Calculate current drawdown

        Returns:
            float: Current drawdown ratio (0.0 to 1.0)
        """
        if not self.equity_curve or len(self.equity_curve) < 2:
            return 0.0

        max_equity = max(point["equity"] for point in self.equity_curve)
        if max_equity == 0.0:
            return 0.0

        current_equity = self.metrics["current_equity"]
        return max(0.0, (max_equity - current_equity) / max_equity)

    def _calculate_max_drawdown(self) -> float:
        """
        Calculate maximum drawdown

        Returns:
            float: Maximum drawdown ratio (0.0 to 1.0)
        """
        if not self.equity_curve or len(self.equity_curve) < 2:
            return 0.0

        max_drawdown = 0.0
        current_max = self.equity_curve[0]["equity"]

        for point in self.equity_curve[1:]:
            equity = point["equity"]
            current_max = max(current_max, equity)
            drawdown = max(0.0, (current_max - equity) / current_max)
            max_drawdown = max(max_drawdown, drawdown)

        return max_drawdown

    def _count_weekly_trades(self) -> int:
        """
        Count trades in the current week

        Returns:
            int: Number of trades this week
        """
        if not self.trades:
            return 0

        # Get current week start (Monday UTC)
        now = datetime.datetime.utcnow()
        week_start = now - datetime.timedelta(days=now.weekday())
        week_start = week_start.replace(hour=0, minute=0, second=0, microsecond=0)

        # Count trades from this week
        weekly_count = 0
        for trade in self.trades:
            if isinstance(trade, dict):
                trade_time_str = trade.get("timestamp")
                if trade_time_str:
                    try:
                        trade_time = datetime.datetime.fromisoformat(trade_time_str.rstrip("Z"))
                        if trade_time >= week_start:
                            weekly_count += 1
                    except ValueError:
                        continue

        return weekly_count

    def _update_status(self):
        """
        Update status based on metrics
        """
        # Check max drawdown first (highest priority)
        if self.metrics["max_drawdown"] >= self.MAX_DRAWDOWN_THRESHOLD:
            self.metrics["status"] = "BLOCKED"
            self.metrics["status_reason"] = (
                f"Max drawdown ({self.metrics['max_drawdown']:.2%}) exceeds threshold ({self.MAX_DRAWDOWN_THRESHOLD:.2%})"
            )
            self._execute_safe_stop()
            return

        # Check trade count
        trade_count = self.metrics["weekly_trade_count"]
        if trade_count > self.MAX_TRADES_PER_WEEK:
            self.metrics["status"] = "WARNING"
            self.metrics["status_reason"] = (
                f"Weekly trade count ({trade_count}) exceeds maximum ({self.MAX_TRADES_PER_WEEK})"
            )
            return

        # Normal status
        self.metrics["status"] = "NORMAL"
        self.metrics["status_reason"] = "All metrics within acceptable ranges"

    def _execute_safe_stop(self):
        """
        Execute safe stop by writing to blocking_issues.json
        """
        blocking_issue = {
            "timestamp": datetime.datetime.utcnow().isoformat(),
            "issues": [
                {
                    "issue_id": "max_drawdown_exceeded",
                    "issue_type": "risk",
                    "status": "blocked",
                    "message": f"Max drawdown ({self.metrics['max_drawdown']:.2%}) exceeded threshold ({self.MAX_DRAWDOWN_THRESHOLD:.2%}). SAFE_STOP triggered.",
                }
            ],
        }

        # Write blocking issues
        blocking_path = os.path.join(self.data_dir, "blocking_issues.json")

        try:
            # Read existing issues if file exists
            existing_issues = {"timestamp": datetime.datetime.utcnow().isoformat(), "issues": []}

            if os.path.exists(blocking_path):
                with open(blocking_path, encoding="utf-8") as f:
                    existing_issues = json.load(f)

            # Add new issue, avoiding duplicates
            existing_issue_ids = {issue["issue_id"] for issue in existing_issues["issues"]}
            if "max_drawdown_exceeded" not in existing_issue_ids:
                existing_issues["issues"].extend(blocking_issue["issues"])

            # Update timestamp
            existing_issues["timestamp"] = datetime.datetime.utcnow().isoformat()

            # Write back to file
            with open(blocking_path, "w", encoding="utf-8") as f:
                json.dump(existing_issues, f, indent=2, ensure_ascii=False)
        except (OSError, json.JSONDecodeError):
            pass

    def _save_metrics(self):
        """
        Save metrics to JSON and generate Markdown report
        """
        # Save to live_metrics.json
        metrics_path = os.path.join(self.metrics_dir, "live_metrics.json")
        try:
            with open(metrics_path, "w", encoding="utf-8") as f:
                json.dump(self.metrics, f, indent=2, ensure_ascii=False)
        except (OSError, json.JSONDecodeError):
            pass

        # Generate Markdown report
        self._generate_markdown_report()

    def _generate_markdown_report(self):
        """
        Generate Markdown report
        """
        report_path = os.path.join(self.metrics_dir, "live_metrics.md")

        try:
            with open(report_path, "w", encoding="utf-8") as f:
                f.write("# 实盘绩效与风控指标\n\n")
                f.write(
                    f"**生成时间**: {datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}\n\n"
                )
                f.write("## 核心指标\n\n")
                f.write("| 指标 | 当前值 | 状态 |\n")
                f.write("|------|--------|------|\n")
                f.write(
                    f"| 当前权益 | ${self.metrics['current_equity']:.2f} | {'✅' if self.metrics['status'] != 'BLOCKED' else '❌'} |\n"
                )
                f.write(
                    f"| 初始权益 | ${self.metrics['initial_equity']:.2f} | {'✅' if self.metrics['status'] != 'BLOCKED' else '❌'} |\n"
                )
                f.write(
                    f"| 当日盈亏 | ${self.metrics['daily_pnl']:.2f} | {'✅' if self.metrics['status'] != 'BLOCKED' else '❌'} |\n"
                )
                f.write(
                    f"| 当周盈亏 | ${self.metrics['weekly_pnl']:.2f} | {'✅' if self.metrics['status'] != 'BLOCKED' else '❌'} |\n"
                )
                f.write(
                    f"| 当前回撤 | {self.metrics['current_drawdown']:.2%} | {'✅' if self.metrics['status'] != 'BLOCKED' else '❌'} |\n"
                )
                f.write(
                    f"| 最大回撤 | {self.metrics['max_drawdown']:.2%} | {'✅' if self.metrics['max_drawdown'] < self.MAX_DRAWDOWN_THRESHOLD else '❌'} |\n"
                )
                f.write(
                    f"| 当周交易次数 | {self.metrics['weekly_trade_count']} | {'✅' if self.metrics['status'] == 'NORMAL' else '⚠️'} |\n"
                )
                f.write(
                    f"| 系统状态 | {self.metrics['status']} | {'✅' if self.metrics['status'] == 'NORMAL' else '⚠️' if self.metrics['status'] == 'WARNING' else '❌'} |\n"
                )
                f.write(f"| 状态原因 | {self.metrics['status_reason']} | |\n\n")

                f.write("## 风险参数\n\n")
                f.write(f"- 最大回撤阈值: {self.MAX_DRAWDOWN_THRESHOLD:.2%}\n")
                f.write(
                    f"- 每周交易次数范围: {self.MIN_TRADES_PER_WEEK} - {self.MAX_TRADES_PER_WEEK}次\n\n"
                )

                f.write("## 权益曲线\n\n")
                f.write("| 时间 | 权益 |\n")
                f.write("|------|------|\n")
                # Show last 10 equity points
                for point in self.equity_curve[-10:]:
                    time_str = datetime.datetime.fromisoformat(
                        point["timestamp"].rstrip("Z")
                    ).strftime("%Y-%m-%d %H:%M:%S")
                    f.write(f"| {time_str} | ${point['equity']:.2f} |\n")
        except OSError:
            pass

    def add_trade(self, trade: dict[str, Any]):
        """
        Add a trade to the metrics

        Args:
            trade: Trade data
        """
        self.trades.append(trade)
        # Update metrics immediately
        self.update_metrics({"balance": {"total": self.metrics["current_equity"]}})

    def get_metrics(self) -> dict[str, Any]:
        """
        Get current metrics

        Returns:
            dict: Current metrics
        """
        return self.metrics

    def reset_weekly_metrics(self):
        """
        Reset weekly metrics
        """
        self.metrics["weekly_pnl"] = 0.0
        self.metrics["weekly_trade_count"] = 0
        self._save_metrics()
