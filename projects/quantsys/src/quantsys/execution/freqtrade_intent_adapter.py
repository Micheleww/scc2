#!/usr/bin/env python3
"""
Freqtrade策略Intent适配器
实现Intent幂等与去重功能，确保同一intent_id只允许一次entry，已有持仓时禁止新intent entry
"""

import logging

from freqtrade.strategy import IStrategy
from pandas import DataFrame

from src.quantsys.execution.intent_manager import IntentManager, get_intent_manager

# 配置日志
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class FreqtradeIntentAdapter:
    """
    Freqtrade策略Intent适配器
    负责在Freqtrade策略中实现Intent幂等与去重功能
    """

    def __init__(self, intent_manager: IntentManager | None = None):
        """
        初始化Freqtrade Intent适配器

        Args:
            intent_manager: IntentManager实例，如果为None则使用默认实例
        """
        self.intent_manager = intent_manager or get_intent_manager()
        self.strategy_name: str | None = None

        logger.info("Freqtrade Intent适配器初始化完成")

    def initialize_strategy(self, strategy: IStrategy):
        """
        初始化策略，获取策略名称

        Args:
            strategy: Freqtrade策略实例
        """
        self.strategy_name = strategy.__class__.__name__
        logger.info(f"Freqtrade策略已初始化: {self.strategy_name}")

    def generate_intent_id(self, strategy_id: str, bar_time: str, symbol: str) -> str:
        """
        生成统一的intent_id

        Args:
            strategy_id: 策略ID
            bar_time: K线时间
            symbol: 交易对

        Returns:
            str: 生成的intent_id
        """
        return self.intent_manager.generate_intent_id(strategy_id, bar_time, symbol)

    def check_intent_allowed(
        self, intent_id: str, strategy_id: str, symbol: str, side: str, has_position: bool = False
    ) -> tuple[bool, str]:
        """
        检查intent是否允许entry

        Args:
            intent_id: 统一的intent_id
            strategy_id: 策略ID
            symbol: 交易对
            side: 买卖方向
            has_position: 是否已有持仓

        Returns:
            tuple[bool, str]: (是否允许entry, 原因)
        """
        return self.intent_manager.check_intent_allowed(
            intent_id=intent_id,
            strategy_id=strategy_id,
            symbol=symbol,
            side=side,
            has_position=has_position,
        )

    def consume_intent(
        self,
        intent_id: str,
        strategy_id: str,
        symbol: str,
        side: str,
        bar_time: str,
        status: str = "CONSUMED",
        reason: str | None = None,
    ) -> bool:
        """
        消费intent，记录到journal

        Args:
            intent_id: 统一的intent_id
            strategy_id: 策略ID
            symbol: 交易对
            side: 买卖方向
            bar_time: K线时间
            status: 消费状态
            reason: 消费原因

        Returns:
            bool: 消费是否成功
        """
        return self.intent_manager.consume_intent(
            intent_id=intent_id,
            strategy_id=strategy_id,
            symbol=symbol,
            side=side,
            bar_time=bar_time,
            status=status,
            reason=reason,
        )

    def update_position_status(self, symbol: str, has_position: bool) -> None:
        """
        更新持仓状态

        Args:
            symbol: 交易对
            has_position: 是否有持仓
        """
        self.intent_manager.update_position_status(symbol, has_position)

    def should_enter_trade(
        self,
        strategy: IStrategy,
        dataframe: DataFrame,
        metadata: dict,
        entry_signal: bool,
        has_position: bool = False,
    ) -> tuple[bool, str]:
        """
        检查是否应该进入交易

        Args:
            strategy: Freqtrade策略实例
            dataframe: 策略数据
            metadata: 元数据
            entry_signal: 策略生成的entry信号
            has_position: 是否已有持仓

        Returns:
            tuple[bool, str]: (是否允许entry, 原因)
        """
        # 如果没有entry信号，直接返回不允许
        if not entry_signal:
            return False, "策略未生成entry信号"

        # 获取策略ID和交易对
        strategy_id = strategy.__class__.__name__
        symbol = metadata.get("pair", "")

        # 获取最新的bar时间
        bar_time = dataframe.index[-1].isoformat() if not dataframe.empty else "unknown"

        # 生成intent_id
        intent_id = self.generate_intent_id(strategy_id, bar_time, symbol)

        # 检查intent是否允许entry
        allowed, reason = self.check_intent_allowed(
            intent_id=intent_id,
            strategy_id=strategy_id,
            symbol=symbol,
            side="buy",  # 默认buy，实际应根据策略信号确定
            has_position=has_position,
        )

        if allowed:
            # 消费intent
            consumed = self.consume_intent(
                intent_id=intent_id,
                strategy_id=strategy_id,
                symbol=symbol,
                side="buy",  # 默认buy，实际应根据策略信号确定
                bar_time=bar_time,
            )
            if consumed:
                logger.info(f"允许entry: {intent_id}, 策略: {strategy_id}, 交易对: {symbol}")
                return True, reason
            else:
                logger.warning(
                    f"允许entry但消费失败: {intent_id}, 策略: {strategy_id}, 交易对: {symbol}"
                )
                return False, "Intent消费失败"
        else:
            logger.warning(f"禁止entry: {reason}, 策略: {strategy_id}, 交易对: {symbol}")
            return False, reason


# IntentManager集成的Freqtrade策略基类
class IntentManagedStrategy(IStrategy):
    """
    Intent管理的Freqtrade策略基类
    继承自IStrategy，自动实现Intent幂等与去重功能
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # 初始化Intent适配器
        self.intent_adapter = FreqtradeIntentAdapter()
        self.intent_adapter.initialize_strategy(self)

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """
        重写populate_entry_trend方法，添加Intent检查

        :param dataframe: DataFrame with data from the exchange
        :param metadata: Additional information, like the currently traded pair
        :return: DataFrame with entry columns populated
        """
        # 先调用父类的populate_entry_trend生成原始entry信号
        dataframe = super().populate_entry_trend(dataframe, metadata)

        # 遍历数据，添加Intent检查
        for index, row in dataframe.iterrows():
            # 检查是否有entry信号
            entry_signal = row.get("enter_long", 0) == 1 or row.get("enter_short", 0) == 1

            if entry_signal:
                # 获取交易方向
                side = "buy" if row.get("enter_long", 0) == 1 else "sell"

                # 检查是否已有持仓（这里简化处理，实际应从策略中获取）
                has_position = False

                # 生成intent_id
                strategy_id = self.__class__.__name__
                symbol = metadata.get("pair", "")
                bar_time = index.isoformat()
                intent_id = self.intent_adapter.generate_intent_id(strategy_id, bar_time, symbol)

                # 检查intent是否允许entry
                allowed, reason = self.intent_adapter.check_intent_allowed(
                    intent_id=intent_id,
                    strategy_id=strategy_id,
                    symbol=symbol,
                    side=side,
                    has_position=has_position,
                )

                # 根据Intent检查结果更新entry信号
                if not allowed:
                    logger.info(
                        f"Intent禁止entry: {reason}, 时间: {index}, 策略: {strategy_id}, 交易对: {symbol}"
                    )
                    dataframe.at[index, "enter_long"] = 0
                    dataframe.at[index, "enter_short"] = 0
                else:
                    # 消费intent
                    self.intent_adapter.consume_intent(
                        intent_id=intent_id,
                        strategy_id=strategy_id,
                        symbol=symbol,
                        side=side,
                        bar_time=bar_time,
                    )
                    logger.info(
                        f"Intent允许entry: {reason}, 时间: {index}, 策略: {strategy_id}, 交易对: {symbol}"
                    )

        return dataframe


# 单例模式
_freqtrade_intent_adapter = None


def get_freqtrade_intent_adapter(
    intent_manager: IntentManager | None = None,
) -> FreqtradeIntentAdapter:
    """
    获取Freqtrade Intent适配器实例（单例模式）

    Args:
        intent_manager: IntentManager实例，如果为None则使用默认实例

    Returns:
        FreqtradeIntentAdapter: Freqtrade Intent适配器实例
    """
    global _freqtrade_intent_adapter

    if _freqtrade_intent_adapter is None:
        _freqtrade_intent_adapter = FreqtradeIntentAdapter(intent_manager)

    return _freqtrade_intent_adapter
