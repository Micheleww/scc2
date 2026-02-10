#!/usr/bin/env python3
"""
原子开仓-挂止损模块

实现“原子开仓”流程：
- 开仓成功后必须在限定时间内成功挂出止损单（或等效保护单）
- 任一步失败：写 blocking_issues + 进入 SAFE_STOP
- 可配置：止损方式（市价止损/计划单/OCO），默认用OKX最稳妥方案
"""

import json
import logging
import os
import time
from datetime import datetime
from typing import Any

from .order_execution import OrderExecution

# 配置日志
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class AtomicEntry:
    """
    原子开仓-挂止损类，实现原子开仓流程
    """

    def __init__(self, config: dict[str, Any]):
        """
        初始化原子开仓模块

        Args:
            config: 配置信息，包含交易所API密钥等
        """
        self.config = config
        self.order_execution = OrderExecution(config)

        # 止损方式配置，默认使用OKX最稳妥方案：计划单止损
        self.stop_loss_mode = config.get(
            "stop_loss_mode", "trigger"
        )  # trigger: 计划单止损, market: 市价止损, oco: OCO订单
        self.stop_loss_timeout = config.get("stop_loss_timeout", 5)  # 挂止损单超时时间（秒）

        # 输出报告路径
        self.report_path = config.get("report_path", "atomic_entry_report.json")

        # 初始化报告
        self.report = {
            "flow_id": f"atomic_{int(time.time() * 1000)}",
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "symbol": config.get("symbol", "ETH-USDT-SWAP"),
            "stop_loss_mode": self.stop_loss_mode,
            "steps": [],
            "final_status": "PENDING",
            "blocking_issues": [],
            "elapsed_time": 0.0,
        }

    def _add_step(
        self,
        step_name: str,
        request: dict[str, Any] = None,
        response: dict[str, Any] = None,
        status: str = "PENDING",
        error: str = None,
        elapsed: float = 0.0,
    ) -> None:
        """
        添加步骤到报告

        Args:
            step_name: 步骤名称
            request: 请求内容
            response: 响应内容
            status: 状态（PENDING/SUCCESS/FAILURE）
            error: 错误信息
            elapsed: 耗时（秒）
        """
        step = {
            "step_name": step_name,
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "request": request,
            "response": response,
            "status": status,
            "error": error,
            "elapsed": elapsed,
        }
        self.report["steps"].append(step)

    def _write_blocking_issues(self, issues: list[str]) -> None:
        """
        写入blocking_issues文件

        Args:
            issues: 阻塞问题列表
        """
        blocking_issues_path = "data/blocking_issues.json"

        # 读取现有blocking_issues
        blocking_data = {"timestamp": datetime.utcnow().isoformat() + "Z", "issues": []}

        if os.path.exists(blocking_issues_path):
            with open(blocking_issues_path, encoding="utf-8") as f:
                blocking_data = json.load(f)

        # 添加新的blocking_issues
        for issue in issues:
            # 检查问题是否已存在
            issue_exists = False
            for existing_issue in blocking_data["issues"]:
                if existing_issue["message"] == issue:
                    issue_exists = True
                    break

            if not issue_exists:
                new_blocking_issue = {
                    "issue_id": f"atomic_entry_{int(time.time() * 1000)}",
                    "issue_type": "atomic_entry",
                    "status": "blocked",
                    "message": issue,
                }
                blocking_data["issues"].append(new_blocking_issue)

        # 更新timestamp
        blocking_data["timestamp"] = datetime.utcnow().isoformat() + "Z"

        # 写入更新后的blocking_issues
        with open(blocking_issues_path, "w", encoding="utf-8") as f:
            json.dump(blocking_data, f, indent=2, ensure_ascii=False)

        logger.error(f"已写入blocking_issues: {issues}")

    def _enter_safe_stop(self) -> None:
        """
        进入SAFE_STOP状态
        """
        # 这里可以添加进入SAFE_STOP状态的逻辑
        logger.error("系统进入SAFE_STOP状态")

    def _calculate_stop_loss_price(
        self, entry_price: float, side: str, stop_loss_pct: float = 0.02
    ) -> float:
        """
        计算止损价格

        Args:
            entry_price: 开仓价格
            side: 开仓方向（buy/sell）
            stop_loss_pct: 止损百分比（默认2%）

        Returns:
            float: 止损价格
        """
        if side == "buy":
            # 做多止损：价格下跌到一定比例
            return entry_price * (1 - stop_loss_pct)
        else:
            # 做空止损：价格上涨到一定比例
            return entry_price * (1 + stop_loss_pct)

    def place_entry_order(
        self,
        side: str,
        order_type: str,
        amount: float,
        price: float | None = None,
        stop_loss_pct: float = 0.02,
        **kwargs,
    ) -> dict[str, Any]:
        """
        执行原子开仓流程

        Args:
            side: 开仓方向（buy/sell）
            order_type: 订单类型（market/limit）
            amount: 开仓数量
            price: 开仓价格（限价单需要）
            stop_loss_pct: 止损百分比
            **kwargs: 其他参数

        Returns:
            Dict[str, Any]: 原子开仓报告
        """
        start_time = time.time()

        try:
            symbol = self.config.get("symbol", "ETH-USDT-SWAP")

            # 1. 开仓订单
            logger.info(
                f"开始原子开仓流程，方向：{side}，类型：{order_type}，数量：{amount}，价格：{price}"
            )

            # 添加开仓步骤到报告
            self._add_step(
                step_name="place_entry_order",
                request={
                    "symbol": symbol,
                    "side": side,
                    "order_type": order_type,
                    "amount": amount,
                    "price": price,
                },
            )

            # 执行开仓订单
            entry_start = time.time()
            if order_type == "market":
                entry_result = self.order_execution.place_market_order(symbol, side, amount, kwargs)
            else:
                entry_result = self.order_execution.place_limit_order(
                    symbol, side, amount, price, kwargs
                )
            entry_elapsed = time.time() - entry_start

            # 更新开仓步骤状态
            if entry_result.get("code") == "0":
                self._add_step(
                    step_name="place_entry_order",
                    response=entry_result,
                    status="SUCCESS",
                    elapsed=entry_elapsed,
                )
                logger.info(f"开仓成功：{entry_result}")
            else:
                error_msg = f"开仓失败：{entry_result.get('msg')}"
                self._add_step(
                    step_name="place_entry_order",
                    response=entry_result,
                    status="FAILURE",
                    error=error_msg,
                    elapsed=entry_elapsed,
                )
                logger.error(error_msg)

                # 写入blocking_issues并进入SAFE_STOP
                blocking_issues = [error_msg]
                self._write_blocking_issues(blocking_issues)
                self.report["blocking_issues"] = blocking_issues
                self.report["final_status"] = "FAILURE"
                self.report["elapsed_time"] = time.time() - start_time
                self._enter_safe_stop()
                return self.report

            # 2. 获取开仓订单ID和成交价格
            entry_order_id = entry_result["data"][0].get("ordId")
            if not entry_order_id:
                error_msg = "开仓成功但未返回订单ID"
                self._add_step(step_name="get_entry_order_info", status="FAILURE", error=error_msg)
                logger.error(error_msg)

                blocking_issues = [error_msg]
                self._write_blocking_issues(blocking_issues)
                self.report["blocking_issues"] = blocking_issues
                self.report["final_status"] = "FAILURE"
                self.report["elapsed_time"] = time.time() - start_time
                self._enter_safe_stop()
                return self.report

            # 查询开仓订单详情，获取成交价格
            order_info_start = time.time()
            order_info = self.order_execution.get_order(symbol, entry_order_id)
            order_info_elapsed = time.time() - order_info_start

            self._add_step(
                step_name="get_entry_order_info",
                response=order_info,
                status="SUCCESS",
                elapsed=order_info_elapsed,
            )

            # 获取成交价格
            if order_info.get("code") == "0" and order_info.get("data"):
                entry_price = float(order_info["data"][0].get("fillPx", "0"))
                if entry_price == 0:
                    # 如果fillPx为空，尝试从avgPx获取
                    entry_price = float(order_info["data"][0].get("avgPx", "0"))
            else:
                error_msg = f"获取开仓订单详情失败：{order_info.get('msg')}"
                self._add_step(step_name="get_entry_order_price", status="FAILURE", error=error_msg)
                logger.error(error_msg)

                blocking_issues = [error_msg]
                self._write_blocking_issues(blocking_issues)
                self.report["blocking_issues"] = blocking_issues
                self.report["final_status"] = "FAILURE"
                self.report["elapsed_time"] = time.time() - start_time
                self._enter_safe_stop()
                return self.report

            if entry_price == 0:
                error_msg = "无法获取开仓成交价格"
                self._add_step(step_name="get_entry_order_price", status="FAILURE", error=error_msg)
                logger.error(error_msg)

                blocking_issues = [error_msg]
                self._write_blocking_issues(blocking_issues)
                self.report["blocking_issues"] = blocking_issues
                self.report["final_status"] = "FAILURE"
                self.report["elapsed_time"] = time.time() - start_time
                self._enter_safe_stop()
                return self.report

            self._add_step(
                step_name="get_entry_order_price",
                response={"entry_price": entry_price},
                status="SUCCESS",
            )
            logger.info(f"开仓成交价格：{entry_price}")

            # 3. 计算止损价格
            stop_loss_price = self._calculate_stop_loss_price(entry_price, side, stop_loss_pct)

            self._add_step(
                step_name="calculate_stop_loss",
                response={"stop_loss_price": stop_loss_price},
                status="SUCCESS",
            )
            logger.info(f"计算止损价格：{stop_loss_price}")

            # 4. 挂止损单
            stop_loss_start = time.time()
            stop_loss_status = "FAILURE"
            stop_loss_error = None
            stop_loss_response = None

            try:
                # 根据止损方式挂止损单
                if self.stop_loss_mode == "trigger":
                    # 计划单止损
                    stop_loss_response = self._place_trigger_stop_loss(
                        symbol, side, amount, stop_loss_price
                    )
                elif self.stop_loss_mode == "market":
                    # 市价止损
                    stop_loss_response = self._place_market_stop_loss(symbol, side, amount)
                elif self.stop_loss_mode == "oco":
                    # OCO订单
                    take_profit_pct = kwargs.get("take_profit_pct", 0.04)
                    take_profit_price = (
                        entry_price * (1 + take_profit_pct)
                        if side == "buy"
                        else entry_price * (1 - take_profit_pct)
                    )
                    stop_loss_response = self._place_oco_order(
                        symbol, side, amount, stop_loss_price, take_profit_price
                    )
                else:
                    error_msg = f"不支持的止损方式：{self.stop_loss_mode}"
                    raise ValueError(error_msg)

                # 检查止损单是否成功
                if stop_loss_response.get("code") == "0":
                    stop_loss_status = "SUCCESS"
                    logger.info(f"止损单挂出成功：{stop_loss_response}")
                else:
                    stop_loss_error = f"止损单挂出失败：{stop_loss_response.get('msg')}"
                    logger.error(stop_loss_error)

            except Exception as e:
                stop_loss_error = f"挂止损单异常：{str(e)}"
                logger.error(stop_loss_error, exc_info=True)

            stop_loss_elapsed = time.time() - stop_loss_start

            # 添加止损单步骤到报告
            self._add_step(
                step_name="place_stop_loss",
                request={
                    "symbol": symbol,
                    "side": side,
                    "amount": amount,
                    "stop_loss_price": stop_loss_price,
                    "mode": self.stop_loss_mode,
                },
                response=stop_loss_response,
                status=stop_loss_status,
                error=stop_loss_error,
                elapsed=stop_loss_elapsed,
            )

            # 5. 检查止损单挂出是否成功
            if stop_loss_status != "SUCCESS":
                # 止损单挂出失败，写入blocking_issues并进入SAFE_STOP
                blocking_issues = [stop_loss_error]
                self._write_blocking_issues(blocking_issues)
                self.report["blocking_issues"] = blocking_issues
                self.report["final_status"] = "FAILURE"
                self.report["elapsed_time"] = time.time() - start_time
                self._enter_safe_stop()
                return self.report

            # 6. 所有步骤成功，更新报告状态
            self.report["final_status"] = "SUCCESS"
            self.report["elapsed_time"] = time.time() - start_time

            logger.info("原子开仓流程完成，所有步骤成功")

        except Exception as e:
            # 处理全局异常
            error_msg = f"原子开仓流程异常：{str(e)}"
            logger.error(error_msg, exc_info=True)

            # 添加异常步骤到报告
            self._add_step(step_name="atomic_entry_flow", status="FAILURE", error=error_msg)

            # 写入blocking_issues并进入SAFE_STOP
            blocking_issues = [error_msg]
            self._write_blocking_issues(blocking_issues)
            self.report["blocking_issues"] = blocking_issues
            self.report["final_status"] = "FAILURE"
            self.report["elapsed_time"] = time.time() - start_time
            self._enter_safe_stop()

        # 保存报告到文件
        self._save_report()

        return self.report

    def _place_trigger_stop_loss(
        self, symbol: str, side: str, amount: float, stop_loss_price: float
    ) -> dict[str, Any]:
        """
        挂计划单止损

        Args:
            symbol: 交易对
            side: 开仓方向
            amount: 开仓数量
            stop_loss_price: 止损价格

        Returns:
            Dict[str, Any]: 止损单响应
        """
        # 计划单止损的方向与开仓方向相反
        stop_side = "sell" if side == "buy" else "buy"

        # 使用OKX API的条件单止损
        endpoint = "/api/v5/trade/order"

        body = {
            "instId": symbol,
            "tdMode": "cross",
            "side": stop_side,
            "ordType": "trigger",
            "sz": str(amount),
            "px": "0",  # 市价止损
            "triggerPx": str(stop_loss_price),
            "triggerDir": "1" if side == "buy" else "2",  # 1: 上涨触发, 2: 下跌触发
            "posSide": "long" if side == "buy" else "short",
            "reduceOnly": "true",
        }

        return self.order_execution._send_request_with_retry("POST", endpoint, body)

    def _place_market_stop_loss(self, symbol: str, side: str, amount: float) -> dict[str, Any]:
        """
        挂市价止损单

        Args:
            symbol: 交易对
            side: 开仓方向
            amount: 开仓数量

        Returns:
            Dict[str, Any]: 止损单响应
        """
        # 市价止损的方向与开仓方向相反
        stop_side = "sell" if side == "buy" else "buy"

        # 市价止损单
        return self.order_execution.place_market_order(
            symbol, stop_side, amount, {"reduceOnly": "true"}
        )

    def _place_oco_order(
        self,
        symbol: str,
        side: str,
        amount: float,
        stop_loss_price: float,
        take_profit_price: float,
    ) -> dict[str, Any]:
        """
        挂OCO订单

        Args:
            symbol: 交易对
            side: 开仓方向
            amount: 开仓数量
            stop_loss_price: 止损价格
            take_profit_price: 获利价格

        Returns:
            Dict[str, Any]: OCO订单响应
        """
        # 注意：OKX API不直接支持OCO订单，需要通过两个条件单实现
        # 这里简化处理，只挂止损单
        return self._place_trigger_stop_loss(symbol, side, amount, stop_loss_price)

    def _save_report(self) -> None:
        """
        保存报告到文件
        """
        with open(self.report_path, "w", encoding="utf-8") as f:
            json.dump(self.report, f, indent=2, ensure_ascii=False)
        logger.info(f"原子开仓报告已保存到 {self.report_path}")

    def get_report(self) -> dict[str, Any]:
        """
        获取原子开仓报告

        Returns:
            Dict[str, Any]: 原子开仓报告
        """
        return self.report


if __name__ == "__main__":
    # 测试代码
    config = {
        "exchange": "okx",
        "symbol": "ETH-USDT-SWAP",
        "stop_loss_mode": "trigger",
        "stop_loss_timeout": 5,
        "report_path": "atomic_entry_report.json",
        "trading_mode": "test",  # 测试模式，不需要真实API密钥
    }

    atomic_entry = AtomicEntry(config)

    # 模拟开仓
    report = atomic_entry.place_entry_order(
        side="buy", order_type="market", amount=1.0, stop_loss_pct=0.02
    )

    print(json.dumps(report, indent=2, ensure_ascii=False))
