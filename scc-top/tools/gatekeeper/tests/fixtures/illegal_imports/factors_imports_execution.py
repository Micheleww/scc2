"""
负例样本：因子层非法导入执行层实现

此文件用于验证 gatekeeper 规则 D04、D09 是否能正确检测到违规导入。
因子层禁止直接访问执行层（包括 broker 执行实现）。

预期：gatekeeper import-scan 应该检测到违规并失败。
"""

from src.quantsys.execution.order_execution import OrderExecution


def illegal_factor_function():
    """
    非法函数示例：因子层直接使用执行层实现

    违反规则：
    - D04: 因子层禁止直接访问执行层
    - D09: 因子层禁止直接访问 broker 执行实现
    """
    order_exec = OrderExecution(config={})
    return order_exec
