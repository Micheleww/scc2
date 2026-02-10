#!/usr/bin/env python3
"""
仓位平滑与换手控制模块
实现目标仓位平滑、换手上限控制和换手率报告
"""

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


@dataclass
class PositionSmootherConfig:
    """仓位平滑配置"""

    smoothing_factor: float = 0.3  # 平滑因子 (0-1)，越大越快调整
    max_turnover_ratio: float = 0.5  # 最大换手率 (0-1)
    max_turnover_amount: float = 10000.0  # 最大换手金额 (USDT)
    min_trade_amount: float = 10.0  # 最小交易金额 (USDT)
    max_position_ratio: float = 0.2  # 单一品种最大仓位比例
    window_size: int = 20  # 换手率计算窗口 (交易次数)


@dataclass
class TurnoverRecord:
    """换手记录"""

    timestamp: datetime
    symbol: str
    old_position: float
    new_position: float
    trade_amount: float
    trade_value: float


@dataclass
class TurnoverReport:
    """换手率报告"""

    start_time: datetime
    end_time: datetime
    total_trades: int
    total_turnover: float
    avg_turnover_per_trade: float
    max_turnover_per_trade: float
    turnover_by_symbol: dict[str, float]
    turnover_records: list[TurnoverRecord] = field(default_factory=list)


class PositionSmoother:
    """
    仓位平滑与换手控制器

    功能：
    1. 对target_position进行平滑调整
    2. 控制换手上限
    3. 生成换手率报告
    4. 与组合/风控门禁兼容
    """

    def __init__(self, config: PositionSmootherConfig):
        """
        初始化仓位平滑器

        Args:
            config: 仓位平滑配置
        """
        self.config = config

        # 当前持仓
        self.current_positions: dict[str, float] = {}

        # 目标持仓
        self.target_positions: dict[str, float] = {}

        # 换手记录
        self.turnover_records: list[TurnoverRecord] = []

        # 换手窗口
        self.turnover_window: list[float] = []

        # 总资金（用于计算仓位比例）
        self.total_equity: float = 100000.0

        logger.info("仓位平滑器初始化完成")
        logger.info(
            f"配置: 平滑因子={config.smoothing_factor}, 最大换手率={config.max_turnover_ratio}"
        )

    def set_total_equity(self, equity: float):
        """
        设置总资金

        Args:
            equity: 总资金金额 (USDT)
        """
        self.total_equity = equity
        logger.info(f"总资金已更新: {equity} USDT")

    def update_target_position(self, symbol: str, target_position: float):
        """
        更新目标仓位

        Args:
            symbol: 交易对
            target_position: 目标仓位 (USDT)
        """
        self.target_positions[symbol] = target_position
        logger.info(f"目标仓位已更新: {symbol} = {target_position} USDT")

    def get_smoothed_position(
        self, symbol: str, current_position: float, target_position: float
    ) -> float:
        """
        获取平滑后的仓位

        Args:
            symbol: 交易对
            current_position: 当前仓位 (USDT)
            target_position: 目标仓位 (USDT)

        Returns:
            float: 平滑后的仓位 (USDT)
        """
        # 计算仓位差
        position_diff = target_position - current_position

        # 应用平滑因子
        smoothed_diff = position_diff * self.config.smoothing_factor

        # 计算平滑后的仓位
        smoothed_position = current_position + smoothed_diff

        # 确保不超过最大仓位比例
        max_position = self.total_equity * self.config.max_position_ratio
        if abs(smoothed_position) > max_position:
            smoothed_position = max_position if smoothed_position > 0 else -max_position
            logger.info(f"仓位已限制在最大比例: {symbol} = {smoothed_position} USDT")

        logger.info(
            f"仓位平滑: {symbol} 当前={current_position:.2f}, 目标={target_position:.2f}, "
            f"平滑后={smoothed_position:.2f}, 调整量={smoothed_diff:.2f}"
        )

        return smoothed_position

    def check_turnover_limit(self, trade_value: float) -> bool:
        """
        检查换手上限

        Args:
            trade_value: 交易金额 (USDT)

        Returns:
            bool: 是否允许交易
        """
        # 计算当前换手率
        if len(self.turnover_window) == 0:
            current_turnover = 0.0
        else:
            current_turnover = sum(self.turnover_window)

        # 计算交易后的换手率
        new_turnover = current_turnover + trade_value

        # 检查最大换手率
        max_turnover_by_ratio = self.total_equity * self.config.max_turnover_ratio
        if new_turnover > max_turnover_by_ratio:
            logger.warning(f"换手率超过上限: {new_turnover:.2f} > {max_turnover_by_ratio:.2f}")
            return False

        # 检查最大换手金额
        if trade_value > self.config.max_turnover_amount:
            logger.warning(
                f"单笔换手金额超过上限: {trade_value:.2f} > {self.config.max_turnover_amount:.2f}"
            )
            return False

        # 检查最小交易金额
        if trade_value < self.config.min_trade_amount:
            logger.warning(
                f"交易金额低于最小值: {trade_value:.2f} < {self.config.min_trade_amount:.2f}"
            )
            return False

        return True

    def execute_trade(
        self, symbol: str, current_position: float, target_position: float, price: float
    ) -> dict[str, Any] | None:
        """
        执行交易（考虑平滑和换手限制）

        Args:
            symbol: 交易对
            current_position: 当前仓位 (USDT)
            target_position: 目标仓位 (USDT)
            price: 当前价格

        Returns:
            dict: 交易信息，如果被阻止则返回None
        """
        # 获取平滑后的仓位
        smoothed_position = self.get_smoothed_position(symbol, current_position, target_position)

        # 计算交易量
        trade_amount = smoothed_position - current_position
        trade_value = abs(trade_amount)

        # 如果交易量很小，不执行交易
        if trade_value < self.config.min_trade_amount:
            logger.info(
                f"交易量太小，不执行交易: {trade_value:.2f} < {self.config.min_trade_amount:.2f}"
            )
            return None

        # 检查换手上限
        if not self.check_turnover_limit(trade_value):
            logger.warning(f"换手上限阻止交易: {symbol} {trade_value:.2f} USDT")
            return None

        # 记录换手
        turnover_record = TurnoverRecord(
            timestamp=datetime.now(),
            symbol=symbol,
            old_position=current_position,
            new_position=smoothed_position,
            trade_amount=trade_amount,
            trade_value=trade_value,
        )
        self.turnover_records.append(turnover_record)

        # 更新换手窗口
        self.turnover_window.append(trade_value)
        if len(self.turnover_window) > self.config.window_size:
            self.turnover_window.pop(0)

        # 更新当前持仓
        self.current_positions[symbol] = smoothed_position

        logger.info(
            f"交易执行成功: {symbol} {trade_amount:+.2f} @ {price:.2f} = {trade_value:.2f} USDT"
        )

        return {
            "symbol": symbol,
            "side": "buy" if trade_amount > 0 else "sell",
            "amount": abs(trade_amount / price),
            "price": price,
            "value": trade_value,
            "old_position": current_position,
            "new_position": smoothed_position,
            "timestamp": datetime.now().isoformat(),
        }

    def get_turnover_report(
        self, start_time: datetime | None = None, end_time: datetime | None = None
    ) -> TurnoverReport:
        """
        获取换手率报告

        Args:
            start_time: 开始时间
            end_time: 结束时间

        Returns:
            TurnoverReport: 换手率报告
        """
        # 筛选时间范围内的记录
        if start_time is None:
            start_time = min((r.timestamp for r in self.turnover_records), default=datetime.now())
        if end_time is None:
            end_time = max((r.timestamp for r in self.turnover_records), default=datetime.now())

        filtered_records = [
            r for r in self.turnover_records if start_time <= r.timestamp <= end_time
        ]

        # 计算总换手
        total_turnover = sum(r.trade_value for r in filtered_records)
        total_trades = len(filtered_records)

        # 计算平均换手
        avg_turnover = total_turnover / total_trades if total_trades > 0 else 0.0

        # 计算最大换手
        max_turnover = max((r.trade_value for r in filtered_records), default=0.0)

        # 按品种统计换手
        turnover_by_symbol: dict[str, float] = {}
        for record in filtered_records:
            if record.symbol not in turnover_by_symbol:
                turnover_by_symbol[record.symbol] = 0.0
            turnover_by_symbol[record.symbol] += record.trade_value

        return TurnoverReport(
            start_time=start_time,
            end_time=end_time,
            total_trades=total_trades,
            total_turnover=total_turnover,
            avg_turnover_per_trade=avg_turnover,
            max_turnover_per_trade=max_turnover,
            turnover_by_symbol=turnover_by_symbol,
            turnover_records=filtered_records,
        )

    def save_turnover_report(
        self, report: TurnoverReport, output_dir: str = "reports/position_smoother"
    ) -> list[str]:
        """
        保存换手率报告

        Args:
            report: 换手率报告
            output_dir: 输出目录

        Returns:
            list: 保存的文件路径列表
        """
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        # 保存JSON报告
        json_path = output_path / "turnover_report.json"
        report_data = {
            "start_time": report.start_time.isoformat(),
            "end_time": report.end_time.isoformat(),
            "total_trades": report.total_trades,
            "total_turnover": report.total_turnover,
            "avg_turnover_per_trade": report.avg_turnover_per_trade,
            "max_turnover_per_trade": report.max_turnover_per_trade,
            "turnover_by_symbol": report.turnover_by_symbol,
            "turnover_records": [
                {
                    "timestamp": r.timestamp.isoformat(),
                    "symbol": r.symbol,
                    "old_position": r.old_position,
                    "new_position": r.new_position,
                    "trade_amount": r.trade_amount,
                    "trade_value": r.trade_value,
                }
                for r in report.turnover_records
            ],
        }
        json_path.write_text(
            json.dumps(report_data, indent=2, ensure_ascii=False), encoding="utf-8"
        )

        # 保存Markdown报告
        md_path = output_path / "turnover_report.md"
        md_lines = [
            "# 换手率报告",
            "",
            f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f"统计时间: {report.start_time.strftime('%Y-%m-%d %H:%M:%S')} - {report.end_time.strftime('%Y-%m-%d %H:%M:%S')}",
            "",
            "## 概览",
            f"- 总交易次数: {report.total_trades}",
            f"- 总换手金额: {report.total_turnover:.2f} USDT",
            f"- 平均换手: {report.avg_turnover_per_trade:.2f} USDT",
            f"- 最大换手: {report.max_turnover_per_trade:.2f} USDT",
            "",
            "## 按品种统计",
            "",
        ]

        for symbol, turnover in report.turnover_by_symbol.items():
            md_lines.append(f"- {symbol}: {turnover:.2f} USDT")

        md_lines.extend(
            [
                "",
                "## 配置",
                f"- 平滑因子: {self.config.smoothing_factor}",
                f"- 最大换手率: {self.config.max_turnover_ratio}",
                f"- 最大换手金额: {self.config.max_turnover_amount} USDT",
                f"- 最小交易金额: {self.config.min_trade_amount} USDT",
                f"- 最大仓位比例: {self.config.max_position_ratio}",
                f"- 换手窗口大小: {self.config.window_size}",
            ]
        )

        md_path.write_text("\n".join(md_lines), encoding="utf-8")

        logger.info(f"换手率报告已保存: {json_path}, {md_path}")

        return [str(json_path), str(md_path)]

    def reset(self):
        """
        重置状态
        """
        self.current_positions.clear()
        self.target_positions.clear()
        self.turnover_records.clear()
        self.turnover_window.clear()
        logger.info("仓位平滑器状态已重置")

    def get_status(self) -> dict[str, Any]:
        """
        获取当前状态

        Returns:
            dict: 状态信息
        """
        current_turnover = sum(self.turnover_window)

        return {
            "current_positions": self.current_positions,
            "target_positions": self.target_positions,
            "current_turnover": current_turnover,
            "turnover_ratio": current_turnover / self.total_equity
            if self.total_equity > 0
            else 0.0,
            "total_trades": len(self.turnover_records),
            "config": {
                "smoothing_factor": self.config.smoothing_factor,
                "max_turnover_ratio": self.config.max_turnover_ratio,
                "max_turnover_amount": self.config.max_turnover_amount,
                "min_trade_amount": self.config.min_trade_amount,
                "max_position_ratio": self.config.max_position_ratio,
                "window_size": self.config.window_size,
            },
            "timestamp": datetime.now().isoformat(),
        }
