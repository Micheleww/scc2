#!/usr/bin/env python3

"""
风险引擎模块
实现ETH永续合约的风险控制逻辑
"""

import json
import logging
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any

# 配置日志
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


@dataclass
class RiskDecision:
    """
    风险决策结果
    """

    decision: str  # ALLOW 或 BLOCK
    reason: str  # 决策原因
    calculation_process: list[str]  # 关键计算过程
    risk_state: dict[str, Any]  # 当前风险状态
    timestamp: str  # 决策时间戳


class RiskEngine:
    """
    风险引擎类
    实现ETH永续合约的风险控制逻辑
    """

    def __init__(self):
        """
        初始化风险引擎
        """
        # 风险参数配置
        self.risk_params = {
            "total_capital_budget": 10.0,  # 总资金预算 = 10u (硬上限)
            "single_trade_notional": 3.3,  # 单笔名义仓位 = 3.3u (硬上限)
            "single_trade_risk": 0.008,  # 单笔风险 = 0.8%
            "max_positions": 1,  # 最多1仓
            "max_drawdown": 0.08,  # 最大回撤8%
        }

        # 风险状态
        self.risk_state = {
            "current_positions": 0,  # 当前持仓数量
            "total_exposure": 0.0,  # 当前总暴露
            "current_equity": 10.0,  # 当前权益（初始为总资金）
            "initial_equity": 10.0,  # 初始权益
            "high_watermark": 10.0,  # 权益最高点
            "drawdown": 0.0,  # 当前回撤
            "safe_stop_triggered": False,  # 是否触发安全停止
        }

        logger.info("风险引擎初始化完成，风险参数: %s", self.risk_params)

    def calculate_drawdown(self, equity: float) -> float:
        """
        计算当前回撤比例

        Args:
            equity: 当前权益

        Returns:
            float: 回撤比例（0-1）
        """
        # 更新最高点
        if equity > self.risk_state["high_watermark"]:
            self.risk_state["high_watermark"] = equity

        # 计算回撤
        if self.risk_state["high_watermark"] == 0:
            return 0.0

        drawdown = (self.risk_state["high_watermark"] - equity) / self.risk_state["high_watermark"]
        return drawdown

    def check_single_trade_risk(
        self, notional: float, stop_distance: float | None, price: float
    ) -> (bool, list[str]):
        """
        检查单笔交易风险

        Args:
            notional: 单笔名义金额
            stop_distance: 止损距离（如果缺失则BLOCK）
            price: 当前价格

        Returns:
            (bool, List[str]): (是否通过, 计算过程)
        """
        process = []

        # 检查止损距离是否缺失
        if stop_distance is None:
            process.append("止损距离缺失，触发BLOCK")
            return False, process

        # 检查单笔名义仓位限制
        if notional > self.risk_params["single_trade_notional"]:
            process.append(
                f"单笔名义仓位 {notional:.2f}u 超过硬上限 {self.risk_params['single_trade_notional']}u"
            )
            return False, process

        # 计算基于止损距离的最大允许仓位
        risk_amount = self.risk_state["current_equity"] * self.risk_params["single_trade_risk"]
        max_position_by_risk = risk_amount / stop_distance if stop_distance > 0 else 0
        max_notional_by_risk = max_position_by_risk * price

        process.append(f"当前权益: {self.risk_state['current_equity']:.2f}u")
        process.append(f"单笔风险上限: {risk_amount:.4f}u")
        process.append(f"止损距离: {stop_distance:.2f}u")
        process.append(f"基于风险的最大仓位: {max_position_by_risk:.6f}")
        process.append(f"基于风险的最大名义金额: {max_notional_by_risk:.2f}u")

        if notional > max_notional_by_risk:
            process.append(
                f"单笔名义金额 {notional:.2f}u 超过基于风险的最大允许金额 {max_notional_by_risk:.2f}u"
            )
            return False, process

        return True, process

    def check_total_exposure(self, new_exposure: float) -> (bool, list[str]):
        """
        检查总暴露是否超过限制

        Args:
            new_exposure: 新的总暴露

        Returns:
            (bool, List[str]): (是否通过, 计算过程)
        """
        process = []

        if new_exposure > self.risk_params["total_capital_budget"]:
            process.append(
                f"总暴露 {new_exposure:.2f}u 超过硬上限 {self.risk_params['total_capital_budget']}u"
            )
            return False, process

        process.append(
            f"总暴露 {new_exposure:.2f}u 符合限制 {self.risk_params['total_capital_budget']}u"
        )
        return True, process

    def check_position_limit(self) -> (bool, list[str]):
        """
        检查是否超过最大持仓数量

        Returns:
            (bool, List[str]): (是否通过, 计算过程)
        """
        process = []

        if self.risk_state["current_positions"] >= self.risk_params["max_positions"]:
            process.append(
                f"当前持仓数量 {self.risk_state['current_positions']} 超过最大限制 {self.risk_params['max_positions']}"
            )
            return False, process

        process.append(
            f"当前持仓数量 {self.risk_state['current_positions']} 符合限制 {self.risk_params['max_positions']}"
        )
        return True, process

    def check_drawdown(self) -> (bool, list[str]):
        """
        检查是否超过最大回撤

        Returns:
            (bool, List[str]): (是否通过, 计算过程)
        """
        process = []

        # 检查是否已经触发安全停止
        if self.risk_state["safe_stop_triggered"]:
            process.append("已触发安全停止，禁止所有开仓")
            return False, process

        # 计算当前回撤
        drawdown = self.calculate_drawdown(self.risk_state["current_equity"])
        self.risk_state["drawdown"] = drawdown

        process.append(f"当前权益: {self.risk_state['current_equity']:.2f}u")
        process.append(f"权益最高点: {self.risk_state['high_watermark']:.2f}u")
        process.append(f"当前回撤: {drawdown:.4f}")

        if drawdown >= self.risk_params["max_drawdown"]:
            self.risk_state["safe_stop_triggered"] = True
            process.append(
                f"回撤 {drawdown:.4f} 超过最大限制 {self.risk_params['max_drawdown']}，触发安全停止"
            )
            return False, process

        process.append(f"回撤 {drawdown:.4f} 符合限制 {self.risk_params['max_drawdown']}")
        return True, process

    def evaluate_risk(
        self, symbol: str, side: str, amount: float, price: float, stop_distance: float | None
    ) -> RiskDecision:
        """
        评估交易风险

        Args:
            symbol: 交易对
            side: 买卖方向
            amount: 交易数量
            price: 交易价格
            stop_distance: 止损距离

        Returns:
            RiskDecision: 风险决策结果
        """
        calculation_process = []
        decision = "ALLOW"
        reason = "风险检查通过"

        logger.info(
            "开始风险评估: %s %s %f @ %f, 止损距离: %s", symbol, side, amount, price, stop_distance
        )

        # 1. 检查是否为ETH永续合约
        if not symbol.startswith("ETH-"):
            decision = "BLOCK"
            reason = "非ETH永续合约"
            calculation_process.append("非ETH永续合约，触发BLOCK")
            return RiskDecision(
                decision=decision,
                reason=reason,
                calculation_process=calculation_process,
                risk_state=self.risk_state.copy(),
                timestamp=datetime.now().isoformat(),
            )

        # 2. 计算单笔名义金额
        notional = amount * price
        calculation_process.append(f"计算单笔名义金额: {amount} * {price} = {notional:.2f}u")

        # 3. 检查安全停止状态
        drawdown_ok, drawdown_process = self.check_drawdown()
        calculation_process.extend(drawdown_process)
        if not drawdown_ok:
            decision = "BLOCK"
            reason = "触发安全停止"
            return RiskDecision(
                decision=decision,
                reason=reason,
                calculation_process=calculation_process,
                risk_state=self.risk_state.copy(),
                timestamp=datetime.now().isoformat(),
            )

        # 4. 检查持仓数量限制
        position_ok, position_process = self.check_position_limit()
        calculation_process.extend(position_process)
        if not position_ok:
            decision = "BLOCK"
            reason = "超过最大持仓数量"
            return RiskDecision(
                decision=decision,
                reason=reason,
                calculation_process=calculation_process,
                risk_state=self.risk_state.copy(),
                timestamp=datetime.now().isoformat(),
            )

        # 5. 检查单笔交易风险
        risk_ok, risk_process = self.check_single_trade_risk(notional, stop_distance, price)
        calculation_process.extend(risk_process)
        if not risk_ok:
            decision = "BLOCK"
            reason = "单笔交易风险不通过"
            return RiskDecision(
                decision=decision,
                reason=reason,
                calculation_process=calculation_process,
                risk_state=self.risk_state.copy(),
                timestamp=datetime.now().isoformat(),
            )

        # 6. 检查总暴露限制
        new_exposure = self.risk_state["total_exposure"] + notional
        exposure_ok, exposure_process = self.check_total_exposure(new_exposure)
        calculation_process.extend(exposure_process)
        if not exposure_ok:
            decision = "BLOCK"
            reason = "总暴露超过限制"
            return RiskDecision(
                decision=decision,
                reason=reason,
                calculation_process=calculation_process,
                risk_state=self.risk_state.copy(),
                timestamp=datetime.now().isoformat(),
            )

        # 风险检查通过，更新风险状态
        if decision == "ALLOW" and side == "buy":
            self.risk_state["current_positions"] += 1
            self.risk_state["total_exposure"] = new_exposure

        logger.info("风险评估完成: %s, 原因: %s", decision, reason)

        return RiskDecision(
            decision=decision,
            reason=reason,
            calculation_process=calculation_process,
            risk_state=self.risk_state.copy(),
            timestamp=datetime.now().isoformat(),
        )

    def update_equity(self, equity: float):
        """
        更新当前权益

        Args:
            equity: 新的权益值
        """
        self.risk_state["current_equity"] = equity
        # 重新计算回撤
        self.risk_state["drawdown"] = self.calculate_drawdown(equity)

        # 检查是否触发安全停止
        if self.risk_state["drawdown"] >= self.risk_params["max_drawdown"]:
            self.risk_state["safe_stop_triggered"] = True

        logger.info(
            "权益更新完成，当前权益: %s, 回撤: %s, 安全停止: %s",
            equity,
            self.risk_state["drawdown"],
            self.risk_state["safe_stop_triggered"],
        )

    def close_position(self, notional: float):
        """
        平仓操作，更新风险状态

        Args:
            notional: 平仓名义金额
        """
        if self.risk_state["current_positions"] > 0:
            self.risk_state["current_positions"] -= 1
            self.risk_state["total_exposure"] = max(
                0.0, self.risk_state["total_exposure"] - notional
            )

        logger.info(
            "平仓操作完成，当前持仓数量: %s, 当前总暴露: %s",
            self.risk_state["current_positions"],
            self.risk_state["total_exposure"],
        )

    def get_risk_decision_json(
        self, symbol: str, side: str, amount: float, price: float, stop_distance: float | None
    ) -> str:
        """
        获取风险决策的JSON字符串

        Args:
            symbol: 交易对
            side: 买卖方向
            amount: 交易数量
            price: 交易价格
            stop_distance: 止损距离

        Returns:
            str: 风险决策JSON
        """
        decision = self.evaluate_risk(symbol, side, amount, price, stop_distance)
        return json.dumps(asdict(decision), indent=2, ensure_ascii=False)

    def save_risk_decision(
        self,
        symbol: str,
        side: str,
        amount: float,
        price: float,
        stop_distance: float | None,
        filename: str = "risk_decision.json",
    ):
        """
        保存风险决策到JSON文件

        Args:
            symbol: 交易对
            side: 买卖方向
            amount: 交易数量
            price: 交易价格
            stop_distance: 止损距离
            filename: 输出文件名
        """
        json_str = self.get_risk_decision_json(symbol, side, amount, price, stop_distance)
        with open(filename, "w", encoding="utf-8") as f:
            f.write(json_str)
        logger.info("风险决策已保存到 %s", filename)
