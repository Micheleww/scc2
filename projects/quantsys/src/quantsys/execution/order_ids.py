#!/usr/bin/env python3
"""
订单ID管理模块
实现clientOrderId生成规则和幂等性检查
"""

import hashlib
import json
import logging
import os
import time
from datetime import datetime
from typing import Any

# 配置日志
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("order_ids")

# 导入订单状态机
from .order_state_machine import OrderStateMachine
from .trade_ledger import TradeLedger


class OrderIdManager:
    """
    订单ID管理器，负责生成稳定的clientOrderId和幂等性检查
    """

    def __init__(self, system_id: str = "quantsys"):
        """
        初始化订单ID管理器

        Args:
            system_id: 系统标识，用于clientOrderId生成
        """
        self.system_id = system_id
        self.order_ledger_path = "data/order_ledger.json"  # 订单账本路径
        self._init_order_ledger()

        # 初始化交易账本
        self.trade_ledger = TradeLedger()

    def _init_order_ledger(self):
        """
        初始化订单账本
        """
        if not os.path.exists(self.order_ledger_path):
            # 确保data目录存在
            os.makedirs(os.path.dirname(self.order_ledger_path), exist_ok=True)
            with open(self.order_ledger_path, "w") as f:
                json.dump([], f)

    def generate_client_order_id(
        self,
        strategy_id: str,
        symbol: str,
        side: str,
        price: float,
        amount: float,
        create_ts: float = None,
    ) -> str:
        """
        生成稳定的clientOrderId

        格式：{system_id}-{strategy_id}-{symbol}-{side}-{time_bucket}-{nonce}

        Args:
            strategy_id: 策略ID
            symbol: 交易对
            side: 买卖方向
            price: 交易价格
            amount: 交易数量
            create_ts: 创建时间戳（可选，默认当前时间）

        Returns:
            client_order_id: 生成的clientOrderId
        """
        create_ts = create_ts or time.time()

        # 时间桶：分钟粒度
        time_bucket = datetime.fromtimestamp(create_ts).strftime("%Y%m%d%H%M")

        # 生成nonce：使用价格、数量和时间戳的哈希值，确保同一信号不会重复下单
        nonce_input = f"{symbol}-{side}-{price}-{amount}-{create_ts:.3f}"
        nonce = hashlib.md5(nonce_input.encode()).hexdigest()[:8]  # 取前8位作为nonce

        # 构造clientOrderId
        client_order_id = f"{self.system_id}-{strategy_id}-{symbol}-{side}-{time_bucket}-{nonce}"

        return client_order_id

    def get_order_ledger(self) -> list:
        """
        获取订单账本

        Returns:
            order_ledger: 订单账本列表
        """
        with open(self.order_ledger_path) as f:
            return json.load(f)

    def save_order_ledger(self, order_ledger: list):
        """
        保存订单账本

        Args:
            order_ledger: 订单账本列表
        """
        with open(self.order_ledger_path, "w") as f:
            json.dump(order_ledger, f, indent=2)

    def check_order_exists(self, client_order_id: str) -> bool:
        """
        检查订单是否已存在（处于pending/open/filled状态）

        Args:
            client_order_id: 客户端订单ID

        Returns:
            exists: 是否存在有效订单
        """
        order_ledger = self.get_order_ledger()

        for order in order_ledger:
            if order["clientOrderId"] == client_order_id:
                status = order["status"]
                # 检查是否处于有效状态
                if status in ["CREATED", "SENT", "ACK", "OPEN", "PARTIAL", "FILLED"]:
                    return True

        return False

    def get_order_by_client_id(self, client_order_id: str) -> dict[str, Any] | None:
        """
        根据clientOrderId获取订单

        Args:
            client_order_id: 客户端订单ID

        Returns:
            order: 订单信息，如果不存在返回None
        """
        order_ledger = self.get_order_ledger()

        for order in order_ledger:
            if order["clientOrderId"] == client_order_id:
                return order

        return None

    def get_orders_by_feature_snapshot_hash(
        self, feature_snapshot_hash: str
    ) -> list[dict[str, Any]]:
        """
        根据特征快照哈希获取相关订单

        Args:
            feature_snapshot_hash: 特征快照哈希

        Returns:
            orders: 相关订单列表
        """
        order_ledger = self.get_order_ledger()
        return [
            order
            for order in order_ledger
            if order.get("feature_snapshot_hash") == feature_snapshot_hash
        ]

    def get_orders_by_run_id(self, run_id: str) -> list[dict[str, Any]]:
        """
        根据运行ID获取相关订单

        Args:
            run_id: 运行ID

        Returns:
            orders: 相关订单列表
        """
        order_ledger = self.get_order_ledger()
        return [order for order in order_ledger if order.get("run_id") == run_id]

    def get_orders_by_strategy_version(self, strategy_version: str) -> list[dict[str, Any]]:
        """
        根据策略版本获取相关订单

        Args:
            strategy_version: 策略版本

        Returns:
            orders: 相关订单列表
        """
        order_ledger = self.get_order_ledger()
        return [
            order for order in order_ledger if order.get("strategy_version") == strategy_version
        ]

    def get_orders_by_factor_version(self, factor_version: str) -> list[dict[str, Any]]:
        """
        根据因子版本获取相关订单

        Args:
            factor_version: 因子版本

        Returns:
            orders: 相关订单列表
        """
        order_ledger = self.get_order_ledger()
        return [order for order in order_ledger if order.get("factor_version") == factor_version]

    def get_feature_snapshot_hash_by_order_id(self, client_order_id: str) -> str | None:
        """
        根据订单ID获取特征快照哈希

        Args:
            client_order_id: 客户端订单ID

        Returns:
            feature_snapshot_hash: 特征快照哈希，如果不存在返回None
        """
        order = self.get_order_by_client_id(client_order_id)
        return order.get("feature_snapshot_hash") if order else None

    def self_test(self, order: dict[str, Any]) -> dict[str, Any]:
        """
        订单自测，验证订单信息的完整性和正确性

        Args:
            order: 订单信息

        Returns:
            test_result: 自测结果，包含测试项、结果和错误信息
        """
        test_result = {
            "clientOrderId": order.get("clientOrderId"),
            "test_time": time.time(),
            "tests": [],
            "passed": True,
        }

        # 测试1: 基本字段完整性
        basic_fields = [
            "clientOrderId",
            "symbol",
            "side",
            "order_type",
            "amount",
            "status",
            "create_ts",
        ]
        for field in basic_fields:
            if field not in order:
                test_result["tests"].append(
                    {
                        "test_name": f"basic_field_{field}",
                        "result": "failed",
                        "error": f"缺少基本字段: {field}",
                    }
                )
                test_result["passed"] = False
            else:
                test_result["tests"].append(
                    {"test_name": f"basic_field_{field}", "result": "passed"}
                )

        # 测试2: 追溯字段存在性（这些字段可能可选，但如果存在需要验证格式）
        trace_fields = ["strategy_version", "factor_version", "run_id", "feature_snapshot_hash"]
        for field in trace_fields:
            if field in order and order[field] is not None:
                # 简单验证：非空字符串
                if not isinstance(order[field], str) or len(order[field]) == 0:
                    test_result["tests"].append(
                        {
                            "test_name": f"trace_field_{field}_format",
                            "result": "failed",
                            "error": f"追溯字段格式错误: {field}, 值: {order[field]}",
                        }
                    )
                    test_result["passed"] = False
                else:
                    test_result["tests"].append(
                        {"test_name": f"trace_field_{field}_format", "result": "passed"}
                    )
            else:
                test_result["tests"].append(
                    {
                        "test_name": f"trace_field_{field}_existence",
                        "result": "skipped",
                        "error": f"追溯字段可选，当前未设置: {field}",
                    }
                )

        # 测试3: 状态转换合理性
        if "status" in order:
            valid_statuses = [
                "CREATED",
                "SENT",
                "ACK",
                "OPEN",
                "PARTIAL",
                "FILLED",
                "CANCELED",
                "REJECTED",
            ]
            if order["status"] not in valid_statuses:
                test_result["tests"].append(
                    {
                        "test_name": "status_validity",
                        "result": "failed",
                        "error": f"无效的订单状态: {order['status']}",
                    }
                )
                test_result["passed"] = False
            else:
                test_result["tests"].append({"test_name": "status_validity", "result": "passed"})

        return test_result

    def save_evidence(self, order: dict[str, Any], test_result: dict[str, Any]):
        """
        保存自测证据

        Args:
            order: 订单信息
            test_result: 自测结果
        """
        # 创建evidence目录
        evidence_dir = f"data/evidence/{datetime.now().strftime('%Y%m%d')}"
        os.makedirs(evidence_dir, exist_ok=True)

        # 生成evidence文件名：clientOrderId_test.json
        evidence_file_path = f"{evidence_dir}/{order['clientOrderId']}_test.json"

        # 准备证据数据
        evidence_data = {
            "order": order,
            "self_test_result": test_result,
            "evidence_create_ts": time.time(),
        }

        try:
            with open(evidence_file_path, "w") as f:
                json.dump(evidence_data, f, indent=2, ensure_ascii=False)
            logger.info(f"订单自测证据已保存: {evidence_file_path}")
        except Exception as e:
            logger.error(f"保存订单自测证据失败: {e}")

    def _save_trace_file(self, order: dict[str, Any]):
        """
        保存订单trace文件

        Args:
            order: 订单信息
        """
        # 创建trace目录
        trace_dir = f"data/trace/{datetime.now().strftime('%Y%m%d')}"
        os.makedirs(trace_dir, exist_ok=True)

        # 生成trace文件名：clientOrderId.json
        trace_file_path = f"{trace_dir}/{order['clientOrderId']}.json"

        try:
            with open(trace_file_path, "w") as f:
                json.dump(order, f, indent=2, ensure_ascii=False)
            logger.info(f"订单trace文件已保存: {trace_file_path}")
        except Exception as e:
            logger.error(f"保存订单trace文件失败: {e}")

    def add_order(
        self,
        client_order_id: str,
        symbol: str,
        side: str,
        order_type: str,
        amount: float,
        price: float | None = None,
        strategy_version: str | None = None,
        factor_version: str | None = None,
        run_id: str | None = None,
        feature_snapshot_hash: str | None = None,
    ) -> dict[str, Any]:
        """
        添加新订单到账本

        Args:
            client_order_id: 客户端订单ID
            symbol: 交易对
            side: 买卖方向
            order_type: 订单类型
            amount: 交易数量
            price: 交易价格（可选）
            strategy_version: 策略版本（可选）
            factor_version: 因子版本（可选）
            run_id: 运行ID（可选）
            feature_snapshot_hash: 关键特征快照哈希（可选）

        Returns:
            order: 添加的订单信息
        """
        order_ledger = self.get_order_ledger()

        # 检查订单是否已存在
        if self.check_order_exists(client_order_id):
            existing_order = self.get_order_by_client_id(client_order_id)
            if existing_order:
                return existing_order

        # 创建新订单
        order = {
            "clientOrderId": client_order_id,
            "symbol": symbol,
            "side": side,
            "order_type": order_type,
            "amount": amount,
            "price": price,
            "status": "CREATED",
            "create_ts": time.time(),
            "update_ts": time.time(),
            "exchange_order_id": None,
            "fill_amount": 0.0,
            "fill_price": None,
            "match_type": None,  # 用于对账匹配类型
            "strategy_version": strategy_version,
            "factor_version": factor_version,
            "run_id": run_id,
            "feature_snapshot_hash": feature_snapshot_hash,
        }

        # 添加到账本
        order_ledger.append(order)
        self.save_order_ledger(order_ledger)

        # 保存trace文件
        self._save_trace_file(order)

        # 执行自测
        test_result = self.self_test(order)

        # 保存自测证据
        self.save_evidence(order, test_result)

        # 记录到交易账本
        self.trade_ledger.record_order_created(order)

        # 写入TaskHub
        taskhub_orders_path = os.path.join("taskhub", "index", "orders.json")
        os.makedirs(os.path.dirname(taskhub_orders_path), exist_ok=True)

        # 读取现有订单
        taskhub_orders = []
        if os.path.exists(taskhub_orders_path):
            with open(taskhub_orders_path, encoding="utf-8") as f:
                taskhub_orders = json.load(f)

        # 添加新订单
        taskhub_orders.append(order)

        # 写入TaskHub
        with open(taskhub_orders_path, "w", encoding="utf-8") as f:
            json.dump(taskhub_orders, f, indent=2, ensure_ascii=False)

        return order

    def update_order_status(
        self, client_order_id: str, status: str, exchange_order_id: str | None = None
    ) -> bool:
        """
        更新订单状态

        Args:
            client_order_id: 客户端订单ID
            status: 新状态
            exchange_order_id: 交易所订单ID（可选）

        Returns:
            success: 更新是否成功
        """
        order_ledger = self.get_order_ledger()

        for i, order in enumerate(order_ledger):
            if order["clientOrderId"] == client_order_id:
                # 检查状态转换是否有效
                if not OrderStateMachine.is_valid_transition(order["status"], status):
                    logger.error(f"无效的状态转换: {order['status']} -> {status}")
                    return False

                # 更新状态
                order["status"] = status
                order["update_ts"] = time.time()
                if exchange_order_id:
                    order["exchange_order_id"] = exchange_order_id

                # 保存更新后的账本
                self.save_order_ledger(order_ledger)

                # 更新trace文件
                self._save_trace_file(order)

                # 记录到交易账本
                self.trade_ledger.record_order_updated(order)

                # 更新TaskHub订单状态
                taskhub_orders_path = os.path.join("taskhub", "index", "orders.json")
                if os.path.exists(taskhub_orders_path):
                    with open(taskhub_orders_path, encoding="utf-8") as f:
                        taskhub_orders = json.load(f)

                    # 更新对应订单
                    for j, taskhub_order in enumerate(taskhub_orders):
                        if taskhub_order["clientOrderId"] == client_order_id:
                            taskhub_orders[j] = order
                            break

                    # 写入TaskHub
                    with open(taskhub_orders_path, "w", encoding="utf-8") as f:
                        json.dump(taskhub_orders, f, indent=2, ensure_ascii=False)

                logger.info(f"订单状态已更新: {client_order_id} -> {status}")
                return True

        return False

    def update_order_fill(
        self, client_order_id: str, fill_amount: float, fill_price: float
    ) -> bool:
        """
        更新订单成交信息

        Args:
            client_order_id: 客户端订单ID
            fill_amount: 成交数量
            fill_price: 成交价格

        Returns:
            success: 更新是否成功
        """
        order_ledger = self.get_order_ledger()

        for i, order in enumerate(order_ledger):
            if order["clientOrderId"] == client_order_id:
                # 保存旧的成交信息
                old_fill_amount = order["fill_amount"]

                # 更新成交信息
                order["fill_amount"] = fill_amount
                order["fill_price"] = fill_price

                # 更新状态
                if fill_amount >= order["amount"]:
                    order["status"] = "FILLED"
                else:
                    order["status"] = "PARTIAL"

                order["update_ts"] = time.time()

                # 保存更新后的账本
                self.save_order_ledger(order_ledger)

                # 更新trace文件
                self._save_trace_file(order)

                # 记录到交易账本
                self.trade_ledger.record_order_updated(order)

                # 记录成交事件（仅当有新的成交量时）
                if fill_amount > old_fill_amount:
                    new_fill_amount = fill_amount - old_fill_amount
                    fill_data = {
                        "symbol": order["symbol"],
                        "side": order["side"],
                        "fillAmount": new_fill_amount,
                        "fillPrice": fill_price,
                        "clientOrderId": client_order_id,
                        "fillTime": time.time(),
                    }
                    self.trade_ledger.record_fill(fill_data)

                # 更新TaskHub订单状态
                taskhub_orders_path = os.path.join("taskhub", "index", "orders.json")
                if os.path.exists(taskhub_orders_path):
                    with open(taskhub_orders_path, encoding="utf-8") as f:
                        taskhub_orders = json.load(f)

                    # 更新对应订单
                    for j, taskhub_order in enumerate(taskhub_orders):
                        if taskhub_order["clientOrderId"] == client_order_id:
                            taskhub_orders[j] = order
                            break

                    # 写入TaskHub
                    with open(taskhub_orders_path, "w", encoding="utf-8") as f:
                        json.dump(taskhub_orders, f, indent=2, ensure_ascii=False)

                return True

        return False
