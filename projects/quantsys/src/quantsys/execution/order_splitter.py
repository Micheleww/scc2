#!/usr/bin/env python3
"""
订单分拆模块
实现大订单的智能分拆功能，支持多种分拆策略和约束条件
"""

import json
import logging
import os
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from .execution_context import ExecutionContext
from .guards.risk_guard import OrderIntent, RiskGuard

# 配置日志
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


@dataclass
class SplitOrderConfig:
    """
    订单分拆配置
    """

    # 最大单笔订单数量
    max_single_order_amount: float = 10.0
    # 最小订单间隔时间（秒）
    min_order_interval: float = 1.0
    # 最大订单速率（订单数/分钟）
    max_order_rate: int = 30
    # 盘口约束：允许的滑点百分比
    allowed_slippage: float = 0.1
    # 分拆策略：twap, fixed_size
    split_strategy: str = "fixed_size"
    # TWAP时间窗口（秒）
    twap_window: int = 300
    # 失败重试次数
    max_retries: int = 3
    # 重试间隔时间（秒）
    retry_interval: float = 5.0
    # 幂等性检查开关
    enable_idempotency: bool = True


@dataclass
class SplitOrderResult:
    """
    订单分拆结果
    """

    # 原始订单ID
    original_order_id: str
    # 分拆订单列表
    split_orders: list[dict[str, Any]]
    # 分拆结果状态
    status: str  # success, partial, failed
    # 分拆完成时间
    completed_at: float = field(default_factory=lambda: time.time())
    # 失败原因（如果有）
    failure_reason: str = ""


class OrderSplitter:
    """
    订单分拆管理器
    """

    def __init__(self, config: dict[str, Any] | None = None):
        """
        初始化订单分拆管理器

        Args:
            config: 分拆配置
        """
        # 使用默认配置或传入的配置
        default_config = SplitOrderConfig()
        self.config = SplitOrderConfig(**(config or {}))

        # 初始化 Runtime Guard
        risk_guard_config = config.get("risk_guard", {}) if config else {}
        risk_guard_enabled = risk_guard_config.get("enabled", True)
        self.risk_guard = RiskGuard(enabled=risk_guard_enabled)

        # 订单速率控制计数器
        self.order_rate_counter = 0
        self.rate_window_start = time.time()

        # 创建幂等性检查存储目录
        self.idempotency_dir = "data/idempotency"
        os.makedirs(self.idempotency_dir, exist_ok=True)

        logger.info(f"订单分拆管理器初始化完成，策略: {self.config.split_strategy}")

    def _check_rate_limit(self) -> bool:
        """
        检查订单速率限制

        Returns:
            bool: 是否允许下单
        """
        current_time = time.time()
        time_since_window_start = current_time - self.rate_window_start

        # 如果超过1分钟，重置计数器
        if time_since_window_start > 60:
            self.rate_window_start = current_time
            self.order_rate_counter = 0
            return True

        # 检查是否超过速率限制
        if self.order_rate_counter >= self.config.max_order_rate:
            logger.warning(
                f"订单速率超过限制: {self.order_rate_counter}/{self.config.max_order_rate} 订单/分钟"
            )
            return False

        return True

    def _wait_for_rate_limit(self) -> None:
        """
        等待直到满足速率限制
        """
        while not self._check_rate_limit():
            time.sleep(0.5)

    def _get_market_depth(self, symbol: str) -> dict[str, float]:
        """
        获取市场盘口数据（简化版）

        Args:
            symbol: 交易对

        Returns:
            market_depth: 包含买一价和卖一价的字典
        """
        # 这里应该调用交易所API获取真实的盘口数据
        # 简化实现：返回模拟数据
        logger.info(f"获取 {symbol} 的盘口数据（模拟）")
        # 模拟盘口数据，实际应该从交易所API获取
        return {
            "bid_price": 35000.0,  # 买一价
            "ask_price": 35001.0,  # 卖一价
        }

    def _adjust_price_for_slippage(self, symbol: str, side: str, price: float) -> float:
        """
        根据盘口约束调整订单价格

        Args:
            symbol: 交易对
            side: 买卖方向
            price: 原始订单价格

        Returns:
            adjusted_price: 调整后的订单价格
        """
        # 获取市场盘口数据
        market_depth = self._get_market_depth(symbol)

        # 计算允许的滑点范围
        if side == "buy":
            # 买入时，价格不能高于卖一价 + 滑点
            reference_price = market_depth["ask_price"]
            max_allowed_price = reference_price * (1 + self.config.allowed_slippage / 100)
            if price > max_allowed_price:
                logger.info(f"买入价格 {price} 超出滑点限制，调整为 {max_allowed_price:.2f}")
                return max_allowed_price
        else:
            # 卖出时，价格不能低于买一价 - 滑点
            reference_price = market_depth["bid_price"]
            min_allowed_price = reference_price * (1 - self.config.allowed_slippage / 100)
            if price < min_allowed_price:
                logger.info(f"卖出价格 {price} 超出滑点限制，调整为 {min_allowed_price:.2f}")
                return min_allowed_price

        # 价格在允许范围内，无需调整
        return price

    def split_order(
        self,
        symbol: str,
        side: str,
        order_type: str,
        amount: float,
        price: float | None = None,
        params: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """
        拆分订单

        Args:
            symbol: 交易对
            side: 买卖方向
            order_type: 订单类型
            amount: 总交易数量
            price: 交易价格（限价单需要）
            params: 其他参数

        Returns:
            List[Dict[str, Any]]: 分拆后的订单列表
        """
        logger.info(f"开始分拆订单: {side} {order_type} {symbol} {amount} {price}")

        # 初始化参数
        params = params or {}
        split_orders = []

        # 根据分拆策略计算分拆数量
        if self.config.split_strategy == "twap":
            # TWAP策略：按时间窗口均匀拆分
            num_splits = max(1, int(self.config.twap_window / self.config.min_order_interval))
            single_amount = amount / num_splits
            # TWAP策略不使用固定大小调整
            adjusted_num_splits = num_splits
        else:
            # fixed_size策略：按固定大小拆分
            num_splits = max(1, int(amount / self.config.max_single_order_amount))
            single_amount = amount / num_splits

            # 计算实际分拆数量（处理小数情况）
            adjusted_num_splits = max(
                1,
                int(amount / self.config.max_single_order_amount)
                + (1 if amount % self.config.max_single_order_amount > 0 else 0),
            )

        logger.info(
            f"分拆结果：总数量 {amount}，拆分为 {adjusted_num_splits} 笔，每笔 {single_amount:.6f}"
        )

        # 生成分拆订单
        for i in range(adjusted_num_splits):
            # 处理最后一笔订单，确保总数量准确
            if i == adjusted_num_splits - 1:
                current_amount = amount - (i * single_amount)
            else:
                current_amount = single_amount

            # 根据盘口约束调整价格
            adjusted_price = price
            if order_type == "limit" and price is not None:
                adjusted_price = self._adjust_price_for_slippage(symbol, side, price)

            # 创建分拆订单
            split_order = {
                "symbol": symbol,
                "side": side,
                "order_type": order_type,
                "amount": current_amount,
                "price": adjusted_price,
                "params": params.copy(),
                "split_index": i,
                "total_splits": adjusted_num_splits,
            }

            split_orders.append(split_order)

        logger.info(f"订单分拆完成，生成 {len(split_orders)} 笔分拆订单")
        return split_orders

    def execute_split_orders(
        self, order_executor: Any, split_orders: list[dict[str, Any]]
    ) -> SplitOrderResult:
        """
        执行分拆订单

        Args:
            order_executor: 订单执行器实例
            split_orders: 分拆订单列表

        Returns:
            SplitOrderResult: 订单执行结果
        """
        if not split_orders:
            return SplitOrderResult(
                original_order_id="",
                split_orders=[],
                status="failed",
                failure_reason="没有可执行的分拆订单",
            )

        original_order_id = split_orders[0]["params"].get("original_order_id", "unknown")
        executed_orders = []
        failed_count = 0

        logger.info(f"开始执行分拆订单，共 {len(split_orders)} 笔")

        for i, split_order in enumerate(split_orders):
            # 检查速率限制
            self._wait_for_rate_limit()

            # 执行订单
            success = False
            retries = 0

            while not success and retries < self.config.max_retries:
                try:
                    # 执行订单
                    result = order_executor.place_order(
                        symbol=split_order["symbol"],
                        side=split_order["side"],
                        order_type=split_order["order_type"],
                        amount=split_order["amount"],
                        price=split_order["price"],
                        params=split_order["params"],
                    )

                    # 检查执行结果
                    if result.get("code") == "0":
                        success = True
                        executed_orders.append(
                            {
                                "order_info": split_order,
                                "execution_result": result,
                                "status": "success",
                                "executed_at": time.time(),
                            }
                        )
                        logger.info(f"第 {i + 1}/{len(split_orders)} 笔分拆订单执行成功")

                        # 更新速率计数器
                        self.order_rate_counter += 1
                    else:
                        retries += 1
                        logger.warning(
                            f"第 {i + 1}/{len(split_orders)} 笔分拆订单执行失败，重试 {retries}/{self.config.max_retries}: {result.get('msg', '')}"
                        )
                        time.sleep(self.config.retry_interval)
                except Exception as e:
                    retries += 1
                    logger.error(
                        f"第 {i + 1}/{len(split_orders)} 笔分拆订单执行异常，重试 {retries}/{self.config.max_retries}: {str(e)}"
                    )
                    time.sleep(self.config.retry_interval)

            # 处理最终失败情况
            if not success:
                failed_count += 1
                executed_orders.append(
                    {
                        "order_info": split_order,
                        "execution_result": None,
                        "status": "failed",
                        "executed_at": time.time(),
                        "failure_reason": f"超过最大重试次数 {self.config.max_retries}",
                    }
                )
                logger.error(
                    f"第 {i + 1}/{len(split_orders)} 笔分拆订单执行失败，已超过最大重试次数"
                )

            # 等待最小订单间隔（除了最后一笔）
            if i < len(split_orders) - 1:
                logger.info(f"等待 {self.config.min_order_interval} 秒后执行下一笔分拆订单")
                time.sleep(self.config.min_order_interval)

        # 确定分拆结果状态
        if failed_count == 0:
            status = "success"
            failure_reason = ""
        elif failed_count == len(split_orders):
            status = "failed"
            failure_reason = "所有分拆订单执行失败"
        else:
            status = "partial"
            failure_reason = f"部分分拆订单执行失败，失败数: {failed_count}"

        logger.info(
            f"分拆订单执行完成，状态: {status}，成功: {len(executed_orders) - failed_count}，失败: {failed_count}"
        )

        # 生成分拆结果
        return SplitOrderResult(
            original_order_id=original_order_id,
            split_orders=executed_orders,
            status=status,
            failure_reason=failure_reason,
        )

    def _save_split_evidence(
        self, original_order_id: str, split_orders: list[dict[str, Any]], result: SplitOrderResult
    ):
        """
        保存分拆订单的证据

        Args:
            original_order_id: 原始订单ID
            split_orders: 分拆后的订单列表
            result: 分拆执行结果
        """
        # 创建evidence目录
        evidence_dir = f"data/evidence/split_orders/{datetime.now().strftime('%Y%m%d')}"
        os.makedirs(evidence_dir, exist_ok=True)

        # 生成evidence文件名
        evidence_file = f"{evidence_dir}/{original_order_id}.json"

        # 准备证据数据
        evidence_data = {
            "original_order_id": original_order_id,
            "split_time": time.time(),
            "split_orders": split_orders,
            "execution_result": {
                "status": result.status,
                "completed_at": result.completed_at,
                "failure_reason": result.failure_reason,
                "executed_orders_count": len(result.split_orders),
            },
            "config": {
                "split_strategy": self.config.split_strategy,
                "max_single_order_amount": self.config.max_single_order_amount,
                "min_order_interval": self.config.min_order_interval,
                "max_order_rate": self.config.max_order_rate,
                "allowed_slippage": self.config.allowed_slippage,
                "twap_window": self.config.twap_window,
                "max_retries": self.config.max_retries,
                "retry_interval": self.config.retry_interval,
                "enable_idempotency": self.config.enable_idempotency,
            },
        }

        try:
            with open(evidence_file, "w") as f:
                json.dump(evidence_data, f, indent=2, ensure_ascii=False)
            logger.info(f"分拆订单证据已保存: {evidence_file}")
        except Exception as e:
            logger.error(f"保存分拆订单证据失败: {e}")

    def split_and_execute(
        self,
        order_executor: Any,
        symbol: str,
        side: str,
        order_type: str,
        amount: float,
        price: float | None = None,
        params: dict[str, Any] | None = None,
        context: ExecutionContext | None = None,
    ) -> SplitOrderResult:
        """
        拆分并执行订单（一站式服务）

        Args:
            order_executor: 订单执行器实例
            symbol: 交易对
            side: 买卖方向
            order_type: 订单类型
            amount: 总交易数量
            price: 交易价格（限价单需要）
            params: 其他参数[DEPRECATED: Use context instead]
            context: 执行上下文（包含 session_id, trace_id, env, account_id, venue, strategy_id, strategy_version, risk_verdict）

        Returns:
            SplitOrderResult: 分拆和执行结果
        """
        # Migration: Support both old params and new context param
        # TODO: Remove params param in next major version
        if context is None and params is not None:
            import uuid

            trace_id = f"trace_{int(time.time())}_{uuid.uuid4().hex[:8]}"
            context = ExecutionContext(
                session_id=params.get("session_id", "default") if params else "default",
                trace_id=trace_id,
                env=params.get("env", "paper") if params else "paper",
                account_id=params.get("account_id", "default") if params else "default",
                venue=params.get("venue", "okx") if params else "okx",
                strategy_id=params.get("strategy_id", "default") if params else "default",
                strategy_version=params.get("strategy_version", "v1.0.0") if params else "v1.0.0",
                risk_verdict=params.get("risk_verdict") if params else None,
            )
        elif context is None:
            import uuid

            trace_id = f"trace_{int(time.time())}_{uuid.uuid4().hex[:8]}"
            context = ExecutionContext(
                session_id="default",
                trace_id=trace_id,
                env="paper",
                account_id="default",
                venue="okx",
                strategy_id="default",
                strategy_version="v1.0.0",
                risk_verdict=None,
            )

        # Runtime Guard: Validate verdict for split operation
        # Extract context fields
        strategy_id = context.strategy_id
        strategy_version = context.strategy_version
        session_id = context.session_id
        account_id = context.account_id
        venue = context.venue

        # Create OrderIntent for split operation
        intent = OrderIntent(
            symbol=symbol,
            side=side,
            order_type=order_type,
            amount=amount,
            price=price,
            strategy_id=strategy_id,
            strategy_version=strategy_version,
            session_id=session_id,
            account_id=account_id,
            venue=venue,
        )

        # Get verdict from context (may be None, which will be blocked if guard is enabled)
        verdict = context.risk_verdict

        # Require valid verdict (raises GuardBlockedError if validation fails)
        self.risk_guard.require_verdict(verdict, intent)

        # 初始化参数
        params = params or {}

        # 生成原始订单ID
        original_order_id = params.get("original_order_id", f"order_{int(time.time())}")
        params["original_order_id"] = original_order_id

        # 幂等性检查
        if self.check_idempotency(order_executor, original_order_id):
            logger.info(f"订单 {original_order_id} 已执行过，直接返回成功结果")
            return SplitOrderResult(
                original_order_id=original_order_id,
                split_orders=[],
                status="success",
                failure_reason="订单已执行过（幂等性检查通过）",
            )

        # 拆分订单
        split_orders = self.split_order(symbol, side, order_type, amount, price, params)

        # 执行分拆订单
        result = self.execute_split_orders(order_executor, split_orders)

        # 保存幂等性记录
        self._save_idempotency_record(original_order_id, result)

        # 保存分拆证据
        self._save_split_evidence(original_order_id, split_orders, result)

        return result

    def self_test(self) -> dict[str, Any]:
        """
        订单分拆模块自测

        Returns:
            test_result: 自测结果，包含测试项、结果和错误信息
        """
        test_result = {"test_time": time.time(), "tests": [], "passed": True}

        logger.info("开始执行订单分拆模块自测...")

        # 测试1: 固定大小分拆策略
        logger.info("测试1: 固定大小分拆策略")
        try:
            # 创建测试配置
            test_config = {"split_strategy": "fixed_size", "max_single_order_amount": 5.0}
            splitter = OrderSplitter(test_config)

            # 测试分拆逻辑
            split_orders = splitter.split_order(
                symbol="BTC-USDT", side="buy", order_type="limit", amount=12.0, price=35000.0
            )

            # 验证分拆结果
            assert len(split_orders) == 3, f"预期分拆为3笔订单，实际得到{len(split_orders)}笔"

            # 验证总数量
            total_amount = sum(order["amount"] for order in split_orders)
            assert abs(total_amount - 12.0) < 0.0001, f"预期总数量12.0，实际得到{total_amount}"

            test_result["tests"].append({"test_name": "fixed_size_split", "result": "passed"})
            logger.info("测试1通过")
        except Exception as e:
            test_result["tests"].append(
                {"test_name": "fixed_size_split", "result": "failed", "error": str(e)}
            )
            test_result["passed"] = False
            logger.error(f"测试1失败: {e}")

        # 测试2: TWAP分拆策略
        logger.info("测试2: TWAP分拆策略")
        try:
            # 创建测试配置
            test_config = {
                "split_strategy": "twap",
                "twap_window": 60,  # 60秒
                "min_order_interval": 10,  # 10秒间隔
            }
            splitter = OrderSplitter(test_config)

            # 测试分拆逻辑
            split_orders = splitter.split_order(
                symbol="BTC-USDT", side="buy", order_type="limit", amount=6.0, price=35000.0
            )

            # 验证分拆结果
            assert len(split_orders) == 6, f"预期分拆为6笔订单，实际得到{len(split_orders)}笔"

            # 验证总数量
            total_amount = sum(order["amount"] for order in split_orders)
            assert abs(total_amount - 6.0) < 0.0001, f"预期总数量6.0，实际得到{total_amount}"

            test_result["tests"].append({"test_name": "twap_split", "result": "passed"})
            logger.info("测试2通过")
        except Exception as e:
            test_result["tests"].append(
                {"test_name": "twap_split", "result": "failed", "error": str(e)}
            )
            test_result["passed"] = False
            logger.error(f"测试2失败: {e}")

        # 测试3: 价格滑点调整
        logger.info("测试3: 价格滑点调整")
        try:
            # 创建测试配置
            test_config = {
                "allowed_slippage": 0.1  # 0.1%滑点
            }
            splitter = OrderSplitter(test_config)

            # 测试买入价格调整（模拟买一价35000，卖一价35001）
            adjusted_price = splitter._adjust_price_for_slippage("BTC-USDT", "buy", 35010.0)
            max_allowed = 35001.0 * (1 + 0.1 / 100)  # 35004.5001
            assert adjusted_price <= max_allowed, (
                f"预期价格不超过{max_allowed}，实际得到{adjusted_price}"
            )

            # 测试卖出价格调整（模拟买一价35000，卖一价35001）
            adjusted_price = splitter._adjust_price_for_slippage("BTC-USDT", "sell", 34990.0)
            min_allowed = 35000.0 * (1 - 0.1 / 100)  # 34965.0
            assert adjusted_price >= min_allowed, (
                f"预期价格不低于{min_allowed}，实际得到{adjusted_price}"
            )

            test_result["tests"].append(
                {"test_name": "price_slippage_adjustment", "result": "passed"}
            )
            logger.info("测试3通过")
        except Exception as e:
            test_result["tests"].append(
                {"test_name": "price_slippage_adjustment", "result": "failed", "error": str(e)}
            )
            test_result["passed"] = False
            logger.error(f"测试3失败: {e}")

        # 测试4: 幂等性检查
        logger.info("测试4: 幂等性检查")
        try:
            # 创建测试配置
            test_config = {"enable_idempotency": True}
            splitter = OrderSplitter(test_config)

            # 模拟订单执行
            original_order_id = f"test_idempotency_{int(time.time())}"

            # 第一次检查：应该返回未执行
            first_check = splitter.check_idempotency(None, original_order_id)
            assert first_check is False, f"第一次幂等性检查应该返回False，实际得到{first_check}"

            # 手动创建幂等性记录
            idempotency_file = f"{splitter.idempotency_dir}/{original_order_id}.json"
            with open(idempotency_file, "w") as f:
                json.dump(
                    {
                        "original_order_id": original_order_id,
                        "status": "success",
                        "completed_at": time.time(),
                    },
                    f,
                )

            # 第二次检查：应该返回已执行
            second_check = splitter.check_idempotency(None, original_order_id)
            assert second_check is True, f"第二次幂等性检查应该返回True，实际得到{second_check}"

            # 清理测试文件
            os.remove(idempotency_file)

            test_result["tests"].append({"test_name": "idempotency_check", "result": "passed"})
            logger.info("测试4通过")
        except Exception as e:
            test_result["tests"].append(
                {"test_name": "idempotency_check", "result": "failed", "error": str(e)}
            )
            test_result["passed"] = False
            logger.error(f"测试4失败: {e}")

        # 测试5: 速率限制检查
        logger.info("测试5: 速率限制检查")
        try:
            # 创建测试配置
            test_config = {
                "max_order_rate": 2  # 每分钟2笔订单
            }
            splitter = OrderSplitter(test_config)

            # 模拟速率限制
            splitter.order_rate_counter = 2
            splitter.rate_window_start = time.time()

            # 检查速率限制
            rate_check = splitter._check_rate_limit()
            assert rate_check is False, f"速率限制检查应该返回False，实际得到{rate_check}"

            test_result["tests"].append({"test_name": "rate_limit_check", "result": "passed"})
            logger.info("测试5通过")
        except Exception as e:
            test_result["tests"].append(
                {"test_name": "rate_limit_check", "result": "failed", "error": str(e)}
            )
            test_result["passed"] = False
            logger.error(f"测试5失败: {e}")

        logger.info(f"订单分拆模块自测完成，总结果: {'通过' if test_result['passed'] else '失败'}")
        return test_result

    def check_idempotency(self, order_executor: Any, original_order_id: str) -> bool:
        """
        检查订单是否已经执行过（幂等性检查）

        Args:
            order_executor: 订单执行器实例
            original_order_id: 原始订单ID

        Returns:
            bool: 是否已执行过
        """
        if not self.config.enable_idempotency:
            logger.info("幂等性检查已禁用，直接返回未执行")
            return False

        # 检查幂等性文件是否存在
        idempotency_file = f"{self.idempotency_dir}/{original_order_id}.json"
        if os.path.exists(idempotency_file):
            try:
                with open(idempotency_file) as f:
                    data = json.load(f)
                logger.info(f"订单 {original_order_id} 已执行过，执行结果: {data.get('status')}")
                return True
            except Exception as e:
                logger.error(f"读取幂等性文件失败: {e}")
                # 读取失败时，假设订单未执行过
                return False

        logger.info(f"订单 {original_order_id} 未执行过")
        return False

    def _save_idempotency_record(self, original_order_id: str, result: SplitOrderResult):
        """
        保存幂等性记录

        Args:
            original_order_id: 原始订单ID
            result: 分拆订单执行结果
        """
        if not self.config.enable_idempotency:
            return

        idempotency_file = f"{self.idempotency_dir}/{original_order_id}.json"
        record = {
            "original_order_id": original_order_id,
            "status": result.status,
            "completed_at": result.completed_at,
            "failure_reason": result.failure_reason,
            "saved_at": time.time(),
        }

        try:
            with open(idempotency_file, "w") as f:
                json.dump(record, f, indent=2, ensure_ascii=False)
            logger.info(f"幂等性记录已保存: {idempotency_file}")
        except Exception as e:
            logger.error(f"保存幂等性记录失败: {e}")
