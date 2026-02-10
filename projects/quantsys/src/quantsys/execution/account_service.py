#!/usr/bin/env python3
"""
账户服务模块
统一账户数据访问接口，从交易所API获取真实账户数据
"""

import logging
import os
from dataclasses import dataclass

from .check_balance import OKXBalanceChecker

# 配置日志
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


@dataclass
class AccountState:
    """账户状态数据类"""

    balance: float  # 可用余额（USDT）
    equity: float  # 账户权益（USDT）
    positions: dict[str, float]  # 持仓情况 {symbol: notional_value}
    total_position: float  # 总持仓金额（USDT）
    leverage: float  # 当前使用杠杆


class AccountService:
    """
    账户服务类
    统一账户数据访问接口，从交易所API获取真实账户数据
    """

    def __init__(self, exchange: str = "okx", trading_mode: str = "drill"):
        """
        初始化账户服务

        Args:
            exchange: 交易所名称，默认'okx'
            trading_mode: 交易模式，'live'/'dry_run'/'paper'/'drill'/'test'
        """
        self.exchange = exchange
        self.trading_mode = trading_mode

        # 初始化交易所客户端
        if exchange == "okx":
            # 从环境变量读取API密钥
            exchange_prefix = exchange.upper()
            api_key = os.environ.get(f"{exchange_prefix}_API_KEY", "")
            secret_key = os.environ.get(f"{exchange_prefix}_API_SECRET", "")
            passphrase = os.environ.get(f"{exchange_prefix}_PASSPHRASE", "")

            # 只有在live模式下才需要真实密钥
            if trading_mode == "live" and not all([api_key, secret_key, passphrase]):
                logger.warning("Live模式但缺少API密钥，将使用模拟数据")
                self.balance_checker = None
            else:
                self.balance_checker = (
                    OKXBalanceChecker(api_key, secret_key, passphrase) if api_key else None
                )
        else:
            logger.warning(f"不支持的交易所: {exchange}，将使用模拟数据")
            self.balance_checker = None

    def get_account_state(self, symbol: str | None = None) -> AccountState:
        """
        获取账户状态

        Args:
            symbol: 交易对（可选），用于获取特定品种持仓

        Returns:
            AccountState: 账户状态
        """
        # 如果是测试模式或没有balance_checker，返回模拟数据
        if (
            self.trading_mode in ["test", "drill", "dry_run", "paper"]
            or self.balance_checker is None
        ):
            logger.debug(f"{self.trading_mode}模式：返回模拟账户数据")
            return AccountState(
                balance=10000.0, equity=10000.0, positions={}, total_position=0.0, leverage=1.0
            )

        # Live模式：从交易所API获取真实数据
        try:
            # 获取余额
            balance_data = self.balance_checker.get_balance()
            if balance_data is None:
                logger.warning("无法获取账户余额，使用默认值")
                return self._get_default_state()

            # 解析余额数据
            equity = float(balance_data.get("totalEq", "0"))
            balance = float(balance_data.get("availEq", "0"))

            # 获取持仓
            positions_data = self.balance_checker.get_position()
            positions = {}
            total_position = 0.0

            if positions_data:
                for pos in positions_data:
                    pos_symbol = pos.get("instId", "")
                    if symbol and pos_symbol != symbol:
                        continue

                    notional_usd = float(pos.get("notionalUsd", "0"))
                    if abs(notional_usd) > 0.01:  # 忽略微小持仓
                        positions[pos_symbol] = notional_usd
                        total_position += abs(notional_usd)

            # 计算平均杠杆（简化处理）
            leverage = 1.0
            if total_position > 0 and equity > 0:
                leverage = total_position / equity

            return AccountState(
                balance=balance,
                equity=equity,
                positions=positions,
                total_position=total_position,
                leverage=leverage,
            )

        except Exception as e:
            logger.error(f"获取账户状态失败: {e}，使用默认值")
            return self._get_default_state()

    def get_balance(self) -> float:
        """
        获取可用余额

        Returns:
            float: 可用余额（USDT）
        """
        account_state = self.get_account_state()
        return account_state.balance

    def get_equity(self) -> float:
        """
        获取账户权益

        Returns:
            float: 账户权益（USDT）
        """
        account_state = self.get_account_state()
        return account_state.equity

    def get_position(self, symbol: str) -> float:
        """
        获取指定交易对的持仓金额

        Args:
            symbol: 交易对

        Returns:
            float: 持仓金额（USDT），正数表示多头，负数表示空头
        """
        account_state = self.get_account_state(symbol=symbol)
        return account_state.positions.get(symbol, 0.0)

    def get_total_position(self) -> float:
        """
        获取总持仓金额

        Returns:
            float: 总持仓金额（USDT）
        """
        account_state = self.get_account_state()
        return account_state.total_position

    def get_leverage(self) -> float:
        """
        获取当前杠杆

        Returns:
            float: 当前杠杆倍数
        """
        account_state = self.get_account_state()
        return account_state.leverage

    def _get_default_state(self) -> AccountState:
        """
        获取默认账户状态（用于错误情况）

        Returns:
            AccountState: 默认账户状态
        """
        return AccountState(
            balance=10000.0, equity=10000.0, positions={}, total_position=0.0, leverage=1.0
        )
