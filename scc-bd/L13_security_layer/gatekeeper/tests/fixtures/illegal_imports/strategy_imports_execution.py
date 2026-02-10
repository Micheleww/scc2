"""
负例样本：策略层非法导入执行层实现

此文件用于验证 gatekeeper 规则 D01、D07 是否能正确检测到违规导入。
策略层禁止直接访问执行层（包括 broker 执行实现）。

预期：gatekeeper import-scan 应该检测到违规并失败。
"""

from src.quantsys.execution.order_execution import OrderExecution


def illegal_strategy_function():
    """
    非法函数示例：策略层直接使用执行层实现

    违反规则：
    - D01: 策略层禁止直接访问执行层
    - D07: 策略层禁止直接访问 broker 执行实现
    """
    order_exec = OrderExecution(config={})
    return order_exec
