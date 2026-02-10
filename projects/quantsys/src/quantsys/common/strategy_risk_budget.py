#!/usr/bin/env python3
"""
策略级风险预算引擎

为每个策略提供独立的风险额度、单日最大亏损、最大仓位限制
当策略触发风险限制时，禁用该策略但不影响系统其他部分
"""

import json
import logging
from dataclasses import asdict, dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

# 配置日志
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


@dataclass
class StrategyRiskParams:
    """
    策略级风险参数
    """

    # 策略基本信息
    strategy_id: str
    strategy_code: str

    # 风险额度
    max_risk_amount: float = 1000.0  # 策略最大风险额度（USDT）
    max_risk_ratio: float = 0.1  # 策略最大风险比例（相对于总资金）

    # 单日最大亏损
    max_daily_loss: float = 500.0  # 策略单日最大亏损（USDT）
    max_daily_loss_ratio: float = 0.05  # 策略单日最大亏损比例

    # 最大仓位
    max_position_ratio: float = 0.2  # 策略最大仓位比例
    max_total_position: float = 10000.0  # 策略最大总仓位（USDT）

    # 其他风险参数
    max_daily_trades: int = 20  # 策略单日最大交易次数
    max_consecutive_losses: int = 5  # 策略最大连续亏损次数
    active: bool = True  # 策略是否激活


@dataclass
class StrategyRiskStats:
    """
    策略风险统计数据
    """

    strategy_id: str
    strategy_code: str
    date: date
    total_trades: int = 0
    total_pnl: float = 0.0
    consecutive_losses: int = 0
    current_risk_amount: float = 0.0
    current_position: float = 0.0
    last_trade_time: datetime | None = None


class StrategyRiskBudgetEngine:
    """
    策略级风险预算引擎
    """

    def __init__(self, config: dict[str, Any] = None):
        """
        初始化策略级风险预算引擎

        Args:
            config: 配置字典
        """
        self.config = config or {}

        # 数据存储路径
        self.data_path = Path(self.config.get("data_path", "data/strategy_risk"))
        self.data_path.mkdir(parents=True, exist_ok=True)

        # 策略风险参数和统计数据
        self.strategy_risk_params: dict[str, StrategyRiskParams] = {}
        self.strategy_risk_stats: dict[str, StrategyRiskStats] = {}

        # 禁用策略列表
        self.disabled_strategies: set[str] = set()

        # 加载策略风险参数和统计数据
        self._load_strategy_risk_params()
        self._load_disabled_strategies()

        logger.info(
            f"策略级风险预算引擎初始化完成，当前管理 {len(self.strategy_risk_params)} 个策略"
        )

    def _load_strategy_risk_params(self):
        """
        从文件加载策略风险参数
        """
        params_file = self.data_path / "strategy_risk_params.json"
        if params_file.exists():
            with open(params_file, encoding="utf-8") as f:
                params_data = json.load(f)

            for strategy_id, params_dict in params_data.items():
                self.strategy_risk_params[strategy_id] = StrategyRiskParams(**params_dict)

            logger.info(f"已加载 {len(self.strategy_risk_params)} 个策略的风险参数")

    def _save_strategy_risk_params(self):
        """
        保存策略风险参数到文件
        """
        params_file = self.data_path / "strategy_risk_params.json"
        params_data = {}

        for strategy_id, params in self.strategy_risk_params.items():
            params_data[strategy_id] = asdict(params)

        with open(params_file, "w", encoding="utf-8") as f:
            json.dump(params_data, f, indent=2, ensure_ascii=False, default=str)

        logger.info(f"已保存 {len(self.strategy_risk_params)} 个策略的风险参数")

    def _load_disabled_strategies(self):
        """
        从文件加载禁用策略列表
        """
        disabled_file = self.data_path / "disabled_strategies.json"
        if disabled_file.exists():
            with open(disabled_file, encoding="utf-8") as f:
                self.disabled_strategies = set(json.load(f))

            logger.info(f"已加载 {len(self.disabled_strategies)} 个禁用策略")

    def _save_disabled_strategies(self):
        """
        保存禁用策略列表到文件
        """
        disabled_file = self.data_path / "disabled_strategies.json"

        with open(disabled_file, "w", encoding="utf-8") as f:
            json.dump(list(self.disabled_strategies), f, indent=2, ensure_ascii=False)

        logger.info(f"已保存 {len(self.disabled_strategies)} 个禁用策略")

    def _get_strategy_stats(self, strategy_id: str, strategy_code: str) -> StrategyRiskStats:
        """
        获取策略风险统计数据，如果不存在则创建

        Args:
            strategy_id: 策略ID
            strategy_code: 策略代码

        Returns:
            StrategyRiskStats: 策略风险统计数据
        """
        current_date = date.today()
        stats_key = f"{strategy_id}_{current_date}"

        if (
            stats_key not in self.strategy_risk_stats
            or self.strategy_risk_stats[stats_key].date != current_date
        ):
            self.strategy_risk_stats[stats_key] = StrategyRiskStats(
                strategy_id=strategy_id, strategy_code=strategy_code, date=current_date
            )

        return self.strategy_risk_stats[stats_key]

    def add_strategy(
        self, strategy_id: str, strategy_code: str, params: dict[str, Any] = None
    ) -> StrategyRiskParams:
        """
        添加策略到风险预算引擎

        Args:
            strategy_id: 策略ID
            strategy_code: 策略代码
            params: 策略风险参数

        Returns:
            StrategyRiskParams: 策略风险参数
        """
        # 创建策略风险参数
        if params:
            risk_params = StrategyRiskParams(
                strategy_id=strategy_id, strategy_code=strategy_code, **params
            )
        else:
            risk_params = StrategyRiskParams(strategy_id=strategy_id, strategy_code=strategy_code)

        # 添加到策略列表
        self.strategy_risk_params[strategy_id] = risk_params

        # 保存到文件
        self._save_strategy_risk_params()

        logger.info(f"已添加策略到风险预算引擎: {strategy_id} ({strategy_code})")
        return risk_params

    def remove_strategy(self, strategy_id: str):
        """
        从风险预算引擎中移除策略

        Args:
            strategy_id: 策略ID
        """
        if strategy_id in self.strategy_risk_params:
            del self.strategy_risk_params[strategy_id]
            self._save_strategy_risk_params()
            logger.info(f"已从风险预算引擎中移除策略: {strategy_id}")

    def update_strategy_params(self, strategy_id: str, params: dict[str, Any]):
        """
        更新策略风险参数

        Args:
            strategy_id: 策略ID
            params: 要更新的风险参数
        """
        if strategy_id in self.strategy_risk_params:
            for key, value in params.items():
                if hasattr(self.strategy_risk_params[strategy_id], key):
                    setattr(self.strategy_risk_params[strategy_id], key, value)

            self._save_strategy_risk_params()
            logger.info(f"已更新策略风险参数: {strategy_id}")

    def check_strategy_risk(
        self, strategy_id: str, strategy_code: str, order_amount: float, pnl: float = 0.0
    ) -> bool:
        """
        检查策略风险

        Args:
            strategy_id: 策略ID
            strategy_code: 策略代码
            order_amount: 订单金额（USDT）
            pnl: 本次交易盈亏（USDT）

        Returns:
            bool: 策略是否允许交易
        """
        # 检查策略是否被禁用
        if strategy_id in self.disabled_strategies:
            logger.warning(f"策略已被禁用，禁止交易: {strategy_id} ({strategy_code})")
            return False

        # 检查策略是否在风险参数列表中，不在则添加
        if strategy_id not in self.strategy_risk_params:
            self.add_strategy(strategy_id, strategy_code)

        # 获取策略风险参数和统计数据
        risk_params = self.strategy_risk_params[strategy_id]
        risk_stats = self._get_strategy_stats(strategy_id, strategy_code)

        # 检查策略是否激活
        if not risk_params.active:
            logger.warning(f"策略未激活，禁止交易: {strategy_id} ({strategy_code})")
            return False

        # 1. 检查策略风险额度
        if risk_stats.current_risk_amount + order_amount > risk_params.max_risk_amount:
            logger.error(
                f"策略风险额度超限: {strategy_id} ({strategy_code}) - 当前风险: {risk_stats.current_risk_amount + order_amount}, 限制: {risk_params.max_risk_amount}"
            )
            self.disable_strategy(strategy_id, strategy_code, reason="风险额度超限")
            return False

        # 2. 检查单日最大亏损
        if risk_stats.total_pnl + pnl < -risk_params.max_daily_loss:
            logger.error(
                f"策略单日亏损超限: {strategy_id} ({strategy_code}) - 当前亏损: {risk_stats.total_pnl + pnl}, 限制: {-risk_params.max_daily_loss}"
            )
            self.disable_strategy(strategy_id, strategy_code, reason="单日亏损超限")
            return False

        # 3. 检查最大仓位
        if risk_stats.current_position + order_amount > risk_params.max_total_position:
            logger.error(
                f"策略仓位超限: {strategy_id} ({strategy_code}) - 当前仓位: {risk_stats.current_position + order_amount}, 限制: {risk_params.max_total_position}"
            )
            return False

        # 4. 检查单日最大交易次数
        if risk_stats.total_trades >= risk_params.max_daily_trades:
            logger.error(
                f"策略单日交易次数超限: {strategy_id} ({strategy_code}) - 当前次数: {risk_stats.total_trades}, 限制: {risk_params.max_daily_trades}"
            )
            return False

        # 5. 检查最大连续亏损次数
        if risk_stats.consecutive_losses >= risk_params.max_consecutive_losses:
            logger.error(
                f"策略连续亏损次数超限: {strategy_id} ({strategy_code}) - 当前次数: {risk_stats.consecutive_losses}, 限制: {risk_params.max_consecutive_losses}"
            )
            self.disable_strategy(strategy_id, strategy_code, reason="连续亏损次数超限")
            return False

        return True

    def update_strategy_stats(
        self, strategy_id: str, strategy_code: str, order_amount: float, pnl: float
    ):
        """
        更新策略风险统计数据

        Args:
            strategy_id: 策略ID
            strategy_code: 策略代码
            order_amount: 订单金额（USDT）
            pnl: 交易盈亏（USDT）
        """
        # 获取策略风险统计数据
        risk_stats = self._get_strategy_stats(strategy_id, strategy_code)

        # 更新交易次数
        risk_stats.total_trades += 1

        # 更新总盈亏
        risk_stats.total_pnl += pnl

        # 更新连续亏损次数
        if pnl < 0:
            risk_stats.consecutive_losses += 1
        else:
            risk_stats.consecutive_losses = 0

        # 更新当前风险额度和仓位
        risk_stats.current_risk_amount += order_amount
        risk_stats.current_position += order_amount

        # 更新最后交易时间
        risk_stats.last_trade_time = datetime.now()

        logger.info(
            f"已更新策略风险统计数据: {strategy_id} ({strategy_code}) - 交易次数: {risk_stats.total_trades}, PnL: {risk_stats.total_pnl:.2f}, 连续亏损: {risk_stats.consecutive_losses}"
        )

    def disable_strategy(self, strategy_id: str, strategy_code: str, reason: str):
        """
        禁用策略

        Args:
            strategy_id: 策略ID
            strategy_code: 策略代码
            reason: 禁用原因
        """
        # 添加到禁用列表
        self.disabled_strategies.add(strategy_id)

        # 保存到文件
        self._save_disabled_strategies()

        logger.info(f"已禁用策略: {strategy_id} ({strategy_code}) - 原因: {reason}")

    def enable_strategy(self, strategy_id: str, strategy_code: str):
        """
        启用策略

        Args:
            strategy_id: 策略ID
            strategy_code: 策略代码
        """
        # 从禁用列表中移除
        if strategy_id in self.disabled_strategies:
            self.disabled_strategies.remove(strategy_id)

            # 保存到文件
            self._save_disabled_strategies()

            logger.info(f"已启用策略: {strategy_id} ({strategy_code})")

    def _save_disabled_strategies(self):
        """
        保存禁用策略列表到文件
        """
        disabled_file = self.data_path / "disabled_strategies.json"

        with open(disabled_file, "w", encoding="utf-8") as f:
            json.dump(list(self.disabled_strategies), f, indent=2, ensure_ascii=False)

        # 同时保存到last_run目录，用于证据落盘
        last_run_dir = Path("last_run")
        last_run_dir.mkdir(exist_ok=True)
        last_disabled_file = last_run_dir / "disabled_strategies.json"
        with open(last_disabled_file, "w", encoding="utf-8") as f:
            json.dump(list(self.disabled_strategies), f, indent=2, ensure_ascii=False)

    def get_disabled_strategies(self) -> set[str]:
        """
        获取禁用策略列表

        Returns:
            Set[str]: 禁用策略列表
        """
        return self.disabled_strategies.copy()

    def is_strategy_enabled(self, strategy_id: str) -> bool:
        """
        检查策略是否启用

        Args:
            strategy_id: 策略ID

        Returns:
            bool: 策略是否启用
        """
        return strategy_id not in self.disabled_strategies

    def get_strategy_risk_status(self, strategy_id: str) -> dict[str, Any]:
        """
        获取策略风险状态

        Args:
            strategy_id: 策略ID

        Returns:
            Dict[str, Any]: 策略风险状态
        """
        if strategy_id not in self.strategy_risk_params:
            return {"strategy_id": strategy_id, "status": "not_found"}

        risk_params = self.strategy_risk_params[strategy_id]
        risk_stats = self._get_strategy_stats(strategy_id, risk_params.strategy_code)

        return {
            "strategy_id": strategy_id,
            "strategy_code": risk_params.strategy_code,
            "enabled": self.is_strategy_enabled(strategy_id),
            "risk_params": asdict(risk_params),
            "risk_stats": asdict(risk_stats),
            "timestamp": datetime.now().isoformat(),
        }

    def get_all_strategy_risk_status(self) -> dict[str, Any]:
        """
        获取所有策略风险状态

        Returns:
            Dict[str, Any]: 所有策略风险状态
        """
        status = {
            "strategies": [],
            "disabled_count": len(self.disabled_strategies),
            "total_count": len(self.strategy_risk_params),
            "timestamp": datetime.now().isoformat(),
        }

        for strategy_id in self.strategy_risk_params:
            status["strategies"].append(self.get_strategy_risk_status(strategy_id))

        return status

    def reset_daily_stats(self, strategy_id: str = None):
        """
        重置策略每日统计数据

        Args:
            strategy_id: 策略ID， None表示重置所有策略
        """
        if strategy_id:
            # 重置单个策略
            current_date = date.today()
            stats_key = f"{strategy_id}_{current_date}"
            if stats_key in self.strategy_risk_stats:
                del self.strategy_risk_stats[stats_key]
                logger.info(f"已重置策略每日统计数据: {strategy_id}")
        else:
            # 重置所有策略
            self.strategy_risk_stats.clear()
            logger.info("已重置所有策略每日统计数据")


# 创建默认实例
default_strategy_risk_budget = StrategyRiskBudgetEngine()
