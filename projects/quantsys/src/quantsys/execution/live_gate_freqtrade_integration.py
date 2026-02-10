#!/usr/bin/env python3
"""
LiveGate到Freqtrade的集成模块
实现LiveGate与Freqtrade策略的集成，在下单前强制调用LiveGate决策
"""

import logging
from typing import Any

from freqtrade.strategy import IStrategy
from pandas import DataFrame

from src.quantsys.live_gate import LiveGate

# 配置日志
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class LiveGateFreqtradeIntegration:
    """
    LiveGate到Freqtrade的集成类
    负责在Freqtrade策略下单前强制调用LiveGate决策
    """

    def __init__(self):
        """
        初始化集成类
        """
        # 获取LiveGate实例
        self.live_gate = LiveGate()

        logger.info("LiveGate到Freqtrade集成模块初始化完成")

    def check_live_access_for_entry(
        self, strategy: IStrategy, dataframe: DataFrame, metadata: dict, entry_signal: bool
    ) -> dict[str, Any]:
        """
        检查策略entry信号的LiveGate访问权限

        Args:
            strategy: Freqtrade策略实例
            dataframe: 策略数据
            metadata: 元数据
            entry_signal: 策略生成的entry信号

        Returns:
            Dict[str, Any]: LiveGate检查结果，包含:
                - allow_entry: bool, 是否允许entry
                - reason: str, 决策原因
                - blocking_issues: dict, 完整的阻塞问题对象
        """
        # 如果策略没有生成entry信号，直接返回不允许
        if not entry_signal:
            return {"allow_entry": False, "reason": "策略未生成entry信号", "blocking_issues": None}

        # 调用LiveGate检查访问权限
        is_allowed, blocking_issues = self.live_gate.check_live_access()

        # 记录LiveGate决策结果
        if is_allowed:
            logger.info("LiveGate允许entry: 所有条件均已满足")
            return {
                "allow_entry": True,
                "reason": "LiveGate所有条件均已满足",
                "blocking_issues": blocking_issues,
            }
        else:
            logger.warning(f"LiveGate禁止entry: 存在{len(blocking_issues['issues'])}个阻塞问题")
            return {
                "allow_entry": False,
                "reason": f"LiveGate存在{len(blocking_issues['issues'])}个阻塞问题",
                "blocking_issues": blocking_issues,
            }


# 单例模式
_live_gate_integration = None


def get_live_gate_integration() -> LiveGateFreqtradeIntegration:
    """
    获取LiveGate到Freqtrade集成模块实例（单例模式）

    Returns:
        LiveGateFreqtradeIntegration: 集成模块实例
    """
    global _live_gate_integration

    if _live_gate_integration is None:
        _live_gate_integration = LiveGateFreqtradeIntegration()

    return _live_gate_integration


# 策略包装器基类，用于包装Freqtrade策略，添加LiveGate集成
class LiveGateManagedStrategy(IStrategy):
    """
    LiveGate管理策略包装器
    继承自IStrategy，在entry前添加LiveGate检查
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.live_gate_integration = get_live_gate_integration()

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """
        重写populate_entry_trend方法，添加LiveGate检查
        """
        # 先调用父类的populate_entry_trend生成原始entry信号
        dataframe = super().populate_entry_trend(dataframe, metadata)

        # 遍历数据，检查每个entry信号
        for index, row in dataframe.iterrows():
            # 检查是否有entry信号
            entry_signal = row.get("enter_long", 0) == 1 or row.get("enter_short", 0) == 1

            if entry_signal:
                # 检查LiveGate访问权限
                live_gate_result = self.live_gate_integration.check_live_access_for_entry(
                    strategy=self, dataframe=dataframe, metadata=metadata, entry_signal=entry_signal
                )

                # 根据LiveGate检查结果更新entry信号
                if not live_gate_result["allow_entry"]:
                    logger.info(f"LiveGate禁止entry: {live_gate_result['reason']}, 时间: {index}")
                    dataframe.at[index, "enter_long"] = 0
                    dataframe.at[index, "enter_short"] = 0
                else:
                    logger.info(f"LiveGate允许entry: {live_gate_result['reason']}, 时间: {index}")

        return dataframe


# 用于直接调用LiveGate的工具函数
def check_live_gate_before_entry() -> tuple[bool, dict]:
    """
    直接检查entry前的LiveGate访问权限

    Returns:
        tuple[bool, dict]: (is_allowed, blocking_issues)
    """
    live_gate = LiveGate()
    return live_gate.check_live_access()
