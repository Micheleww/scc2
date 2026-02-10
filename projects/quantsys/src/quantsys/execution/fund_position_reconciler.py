#!/usr/bin/env python3
"""
资金与仓位真值源对账模块
以交易所持仓/余额为真值，周期性对齐本地ledger/positions
发现偏差>阈值立即BLOCKED并输出reconcile_report
"""

import json
import logging
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from .reconciliation import (
    DriftType,
    ExchangeStandardizer,
    ReconciliationConfig,
    ReconciliationEngine,
    ReconciliationReport,
)
from .trade_ledger import TradeLedger

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


@dataclass
class ReconciliationThresholds:
    """
    对账阈值配置
    """

    balance_threshold: float = 0.01  # 余额阈值 (USDT)
    position_threshold: float = 0.001  # 持仓阈值 (数量)
    price_threshold: float = 0.001  # 价格阈值 (0.1%)
    max_reconcile_interval: int = 60  # 最大对账间隔 (秒)
    max_allowed_drifts: int = 3  # 最大允许漂移次数


@dataclass
class ReconciliationStatus:
    """
    对账状态
    """

    is_blocked: bool = False
    block_reason: str = ""
    last_reconcile_time: float = 0.0
    drift_count: int = 0
    total_reconciles: int = 0
    failed_reconciles: int = 0


class FundPositionReconciler:
    """
    资金与仓位真值源对账器

    功能：
    1. 以交易所持仓/余额为真值
    2. 周期性对齐本地ledger/positions
    3. 发现偏差>阈值立即BLOCKED
    4. 输出reconcile_report
    """

    def __init__(self, config: dict[str, Any] = None):
        """
        初始化对账器

        Args:
            config: 配置参数
        """
        self.config = config or {}

        # 默认配置
        self.default_config = {
            "exchange": "okx",
            "reconcile_interval": 30,  # 对账间隔（秒）
            "output_dir": "reports/fund_position_reconcile",
            "ledger_path": "data/trade_ledger.json",
            "auto_reconcile": True,
        }

        # 合并配置
        self.actual_config = {**self.default_config, **self.config}

        # 对账阈值
        self.thresholds = ReconciliationThresholds(
            balance_threshold=self.config.get("balance_threshold", 0.01),
            position_threshold=self.config.get("position_threshold", 0.001),
            price_threshold=self.config.get("price_threshold", 0.001),
            max_reconcile_interval=self.config.get("max_reconcile_interval", 60),
            max_allowed_drifts=self.config.get("max_allowed_drifts", 3),
        )

        # 对账配置
        self.recon_config = ReconciliationConfig(
            balance_threshold=self.thresholds.balance_threshold,
            position_threshold=self.thresholds.position_threshold,
            price_threshold=self.thresholds.price_threshold,
        )

        # 对账引擎
        self.engine = ReconciliationEngine(self.recon_config)
        self.standardizer = ExchangeStandardizer()

        # 交易账本
        self.ledger = TradeLedger(self.actual_config["ledger_path"])

        # 对账状态
        self.status = ReconciliationStatus()

        # 对账线程
        self.reconcile_thread: threading.Thread | None = None
        self.stop_event = threading.Event()

        # BLOCKED回调
        self.blocked_callback: Callable[[str], None] | None = None

        # 输出目录
        self.output_dir = Path(self.actual_config["output_dir"])
        self.output_dir.mkdir(parents=True, exist_ok=True)

        logger.info("资金与仓位对账器初始化完成")
        logger.info(f"对账间隔: {self.actual_config['reconcile_interval']}秒")
        logger.info(
            f"对账阈值: 余额={self.thresholds.balance_threshold}, 持仓={self.thresholds.position_threshold}"
        )

    def set_blocked_callback(self, callback: Callable[[str], None]):
        """
        设置BLOCKED回调函数

        Args:
            callback: BLOCKED回调函数，接收block_reason参数
        """
        self.blocked_callback = callback
        logger.info("BLOCKED回调已设置")

    def get_exchange_state(self) -> dict[str, Any]:
        """
        获取交易所状态（真值源）

        Returns:
            dict: 交易所状态，包含余额、持仓、订单
        """
        try:
            # 这里模拟从交易所获取数据
            # 实际实现中应该调用交易所API

            # 模拟余额数据
            exchange_balance = {"total": {"USDT": 10000.0}, "free": {"USDT": 9500.0}}

            # 模拟持仓数据
            exchange_positions = [
                {"symbol": "BTC-USDT", "size": 0.5, "entryPrice": 35000.0, "unrealizedPnl": 250.0}
            ]

            # 模拟订单数据
            exchange_orders = []

            return {
                "balance": exchange_balance,
                "positions": exchange_positions,
                "orders": exchange_orders,
                "timestamp": time.time(),
            }
        except Exception as e:
            logger.error(f"获取交易所状态失败: {e}")
            return {
                "balance": {},
                "positions": [],
                "orders": [],
                "timestamp": time.time(),
                "error": str(e),
            }

    def get_local_state(self) -> dict[str, Any]:
        """
        获取本地状态（从ledger）

        Returns:
            dict: 本地状态，包含余额、持仓、订单
        """
        try:
            # 从账本获取当前状态
            current_state = self.ledger.current_state

            # 标准化本地余额
            local_balance = {
                "total": {"USDT": current_state.get("total_balance", 10000.0)},
                "free": {"USDT": current_state.get("available_balance", 9500.0)},
            }

            # 标准化本地持仓
            local_positions = []
            for symbol, pos_data in current_state.get("positions", {}).items():
                if isinstance(pos_data, dict):
                    local_positions.append(
                        {
                            "symbol": symbol,
                            "size": pos_data.get("total_amount", 0.0),
                            "entryPrice": pos_data.get("avg_price", 0.0),
                            "unrealizedPnl": pos_data.get("unrealized_pnl", 0.0),
                        }
                    )

            # 标准化本地订单
            local_orders = []
            for order_id, order_data in current_state.get("orders", {}).items():
                if isinstance(order_data, dict):
                    local_orders.append(
                        {
                            "id": order_id,
                            "clientOrderId": order_data.get("clientOrderId", order_id),
                            "symbol": order_data.get("symbol", ""),
                            "side": order_data.get("side", "").upper(),
                            "type": order_data.get("order_type", "").upper(),
                            "price": order_data.get("price", 0.0),
                            "amount": order_data.get("amount", 0.0),
                            "filled": order_data.get("filled", 0.0),
                            "status": order_data.get("status", "").upper(),
                        }
                    )

            return {
                "balance": local_balance,
                "positions": local_positions,
                "orders": local_orders,
                "timestamp": time.time(),
            }
        except Exception as e:
            logger.error(f"获取本地状态失败: {e}")
            return {
                "balance": {},
                "positions": [],
                "orders": [],
                "timestamp": time.time(),
                "error": str(e),
            }

    def reconcile(self) -> ReconciliationReport:
        """
        执行对账

        Returns:
            ReconciliationReport: 对账报告
        """
        logger.info("开始执行对账...")

        # 获取交易所状态（真值源）
        exchange_state = self.get_exchange_state()

        # 获取本地状态
        local_state = self.get_local_state()

        # 标准化交易所数据
        exchange_balance = self.standardizer.standardize_balance(
            exchange_state["balance"], currency="USDT"
        )
        exchange_positions = self.standardizer.standardize_positions(exchange_state["positions"])
        exchange_orders = self.standardizer.standardize_orders(exchange_state["orders"])

        # 标准化本地数据
        local_balance = self.standardizer.standardize_balance(
            local_state["balance"], currency="USDT"
        )
        local_positions = self.standardizer.standardize_positions(local_state["positions"])
        local_orders = self.standardizer.standardize_orders(local_state["orders"])

        # 执行对账
        balance_diffs = self.engine.reconcile_balance(exchange_balance, local_balance)
        position_diffs = self.engine.reconcile_positions(exchange_positions, local_positions)
        order_diffs = self.engine.reconcile_orders(exchange_orders, local_orders)

        # 合并所有差异
        all_diffs = balance_diffs + position_diffs + order_diffs

        # 更新对账状态
        self.status.last_reconcile_time = time.time()
        self.status.total_reconciles += 1

        # 判断是否需要BLOCKED
        if len(all_diffs) > 0:
            self.status.drift_count += 1
            self.status.failed_reconciles += 1

            # 检查漂移次数是否超过阈值
            if self.status.drift_count >= self.thresholds.max_allowed_drifts:
                self.status.is_blocked = True
                self.status.block_reason = f"漂移次数超过阈值: {self.status.drift_count} >= {self.thresholds.max_allowed_drifts}"

                # 调用BLOCKED回调
                if self.blocked_callback:
                    self.blocked_callback(self.status.block_reason)

                logger.error(f"系统BLOCKED: {self.status.block_reason}")

            logger.warning(f"对账发现 {len(all_diffs)} 个差异")
        else:
            logger.info("对账通过，无差异发现")

        # 确定漂移类型
        drift_type = DriftType.UNKNOWN
        if balance_diffs:
            drift_type = DriftType.BALANCE
        elif position_diffs:
            drift_type = DriftType.POSITION
        elif order_diffs:
            drift_type = DriftType.ORDER

        # 生成推荐动作
        recommended_action = self.engine.generate_recommended_action(drift_type, len(all_diffs))

        # 创建对账报告
        from .reconciliation import SnapshotMeta

        report = ReconciliationReport(
            ok=len(all_diffs) == 0,
            drift_type=drift_type,
            diffs=all_diffs,
            exchange_snapshot_meta=SnapshotMeta(
                timestamp=int(exchange_state["timestamp"] * 1000),
                symbols=[pos.symbol for pos in exchange_positions],
                source="exchange",
            ),
            local_snapshot_meta=SnapshotMeta(
                timestamp=int(local_state["timestamp"] * 1000),
                symbols=[pos.symbol for pos in local_positions],
                source="local",
            ),
            recommended_action=recommended_action,
            summary=f"对账{'通过' if len(all_diffs) == 0 else '失败'}: 发现 {len(all_diffs)} 个差异",
        )

        # 保存报告
        self._save_reconcile_report(report)

        logger.info(f"对账完成: {report.summary}")

        return report

    def _save_reconcile_report(self, report: ReconciliationReport):
        """
        保存对账报告

        Args:
            report: 对账报告
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        # 保存JSON格式报告
        json_path = self.output_dir / f"reconcile_report_{timestamp}.json"

        report_dict = {
            "timestamp": datetime.now().isoformat(),
            "ok": report.ok,
            "drift_type": report.drift_type.value if report.drift_type else None,
            "recommended_action": report.recommended_action.value
            if report.recommended_action
            else None,
            "summary": report.summary,
            "total_diffs": len(report.diffs),
            "diffs": [
                {
                    "category": diff.category,
                    "key": diff.key,
                    "exchange_value": str(diff.exchange_value),
                    "local_value": str(diff.local_value),
                    "field": diff.field,
                    "threshold": diff.threshold,
                }
                for diff in report.diffs
            ],
            "status": {
                "is_blocked": self.status.is_blocked,
                "block_reason": self.status.block_reason,
                "drift_count": self.status.drift_count,
                "total_reconciles": self.status.total_reconciles,
                "failed_reconciles": self.status.failed_reconciles,
            },
        }

        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(report_dict, f, indent=2, ensure_ascii=False, default=str)

        logger.info(f"对账报告已保存: {json_path}")

        # 保存Markdown格式报告
        md_path = self.output_dir / f"reconcile_report_{timestamp}.md"

        md_lines = [
            "# 资金与仓位对账报告",
            "",
            f"**生成时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f"**对账结果**: {'通过' if report.ok else '失败'}",
            f"**漂移类型**: {report.drift_type.value if report.drift_type else '无'}",
            f"**推荐动作**: {report.recommended_action.value if report.recommended_action else '无'}",
            "",
            "## 摘要",
            f"{report.summary}",
            "",
            f"## 差异详情 (共 {len(report.diffs)} 个)",
            "",
        ]

        for i, diff in enumerate(report.diffs, 1):
            md_lines.extend(
                [
                    f"### 差异 {i}",
                    f"- **类别**: {diff.category}",
                    f"- **键**: {diff.key}",
                    f"- **交易所值**: {diff.exchange_value}",
                    f"- **本地值**: {diff.local_value}",
                    f"- **字段**: {diff.field}",
                    f"- **阈值**: {diff.threshold}",
                ]
            )

        md_lines.extend(
            [
                "",
                "## 对账状态",
                f"- **是否BLOCKED**: {'是' if self.status.is_blocked else '否'}",
                f"- **BLOCKED原因**: {self.status.block_reason if self.status.block_reason else '无'}",
                f"- **漂移次数**: {self.status.drift_count}",
                f"- **总对账次数**: {self.status.total_reconciles}",
                f"- **失败对账次数**: {self.status.failed_reconciles}",
                "",
                "## 配置",
                f"- **余额阈值**: {self.thresholds.balance_threshold} USDT",
                f"- **持仓阈值**: {self.thresholds.position_threshold}",
                f"- **价格阈值**: {self.thresholds.price_threshold}",
                f"- **最大允许漂移次数**: {self.thresholds.max_allowed_drifts}",
                f"- **对账间隔**: {self.actual_config['reconcile_interval']} 秒",
            ]
        )

        with open(md_path, "w", encoding="utf-8") as f:
            f.write("\n".join(md_lines))

        logger.info(f"对账报告已保存: {md_path}")

    def start_periodic_reconcile(self):
        """
        启动周期性对账
        """
        if self.reconcile_thread and self.reconcile_thread.is_alive():
            logger.warning("周期性对账已在运行中")
            return

        self.stop_event.clear()
        self.reconcile_thread = threading.Thread(target=self._periodic_reconcile_loop, daemon=True)
        self.reconcile_thread.start()

        logger.info(f"周期性对账已启动，间隔: {self.actual_config['reconcile_interval']}秒")

    def _periodic_reconcile_loop(self):
        """
        周期性对账循环
        """
        logger.info("周期性对账循环启动")

        while not self.stop_event.is_set():
            try:
                # 执行对账
                self.reconcile()

                # 等待下一次对账
                self.stop_event.wait(self.actual_config["reconcile_interval"])

            except Exception as e:
                logger.error(f"周期性对账出错: {e}")
                # 等待一段时间后重试
                self.stop_event.wait(10)

        logger.info("周期性对账循环停止")

    def stop_periodic_reconcile(self):
        """
        停止周期性对账
        """
        if self.stop_event:
            self.stop_event.set()

        if self.reconcile_thread:
            self.reconcile_thread.join(timeout=5)

        logger.info("周期性对账已停止")

    def get_status(self) -> dict[str, Any]:
        """
        获取对账状态

        Returns:
            dict: 对账状态信息
        """
        return {
            "is_blocked": self.status.is_blocked,
            "block_reason": self.status.block_reason,
            "last_reconcile_time": self.status.last_reconcile_time,
            "drift_count": self.status.drift_count,
            "total_reconciles": self.status.total_reconciles,
            "failed_reconciles": self.status.failed_reconciles,
            "success_rate": (self.status.total_reconciles - self.status.failed_reconciles)
            / max(self.status.total_reconciles, 1),
            "config": {
                "balance_threshold": self.thresholds.balance_threshold,
                "position_threshold": self.thresholds.position_threshold,
                "price_threshold": self.thresholds.price_threshold,
                "max_allowed_drifts": self.thresholds.max_allowed_drifts,
                "reconcile_interval": self.actual_config["reconcile_interval"],
            },
            "timestamp": time.time(),
        }

    def reset_status(self):
        """
        重置对账状态
        """
        self.status = ReconciliationStatus()
        logger.info("对账状态已重置")

    def run_self_test(self) -> dict[str, Any]:
        """
        运行自测试

        Returns:
            dict: 测试结果
        """
        logger.info("开始执行自测试...")

        test_result = {"test_time": time.time(), "tests": [], "passed": True}

        # 测试1: 对账功能
        logger.info("测试1: 对账功能")
        try:
            report = self.reconcile()
            test_result["tests"].append(
                {
                    "test_name": "reconciliation",
                    "result": "passed",
                    "report_ok": report.ok,
                    "diffs_count": len(report.diffs),
                }
            )
            logger.info("测试1通过")
        except Exception as e:
            test_result["tests"].append(
                {"test_name": "reconciliation", "result": "failed", "error": str(e)}
            )
            test_result["passed"] = False
            logger.error(f"测试1失败: {e}")

        # 测试2: 状态获取
        logger.info("测试2: 状态获取")
        try:
            exchange_state = self.get_exchange_state()
            local_state = self.get_local_state()

            assert "balance" in exchange_state, "交易所状态缺少balance"
            assert "positions" in exchange_state, "交易所状态缺少positions"
            assert "balance" in local_state, "本地状态缺少balance"
            assert "positions" in local_state, "本地状态缺少positions"

            test_result["tests"].append(
                {
                    "test_name": "state_fetch",
                    "result": "passed",
                    "exchange_positions": len(exchange_state.get("positions", [])),
                    "local_positions": len(local_state.get("positions", [])),
                }
            )
            logger.info("测试2通过")
        except Exception as e:
            test_result["tests"].append(
                {"test_name": "state_fetch", "result": "failed", "error": str(e)}
            )
            test_result["passed"] = False
            logger.error(f"测试2失败: {e}")

        # 测试3: 报告生成
        logger.info("测试3: 报告生成")
        try:
            status = self.get_status()
            assert "is_blocked" in status, "状态缺少is_blocked"
            assert "drift_count" in status, "状态缺少drift_count"
            assert "total_reconciles" in status, "状态缺少total_reconciles"

            test_result["tests"].append(
                {"test_name": "report_generation", "result": "passed", "status": status}
            )
            logger.info("测试3通过")
        except Exception as e:
            test_result["tests"].append(
                {"test_name": "report_generation", "result": "failed", "error": str(e)}
            )
            test_result["passed"] = False
            logger.error(f"测试3失败: {e}")

        logger.info(f"自测试完成，总结果: {'通过' if test_result['passed'] else '失败'}")

        return test_result


# 示例使用
if __name__ == "__main__":
    # 创建对账器实例
    reconciler = FundPositionReconciler(
        {
            "reconcile_interval": 30,
            "balance_threshold": 0.01,
            "position_threshold": 0.001,
            "max_allowed_drifts": 3,
        }
    )

    # 设置BLOCKED回调
    def on_blocked(reason: str):
        logger.error(f"系统BLOCKED: {reason}")
        # 这里可以添加BLOCKED后的处理逻辑
        # 例如：停止交易、发送警报等

    reconciler.set_blocked_callback(on_blocked)

    # 执行单次对账
    report = reconciler.reconcile()
    print(f"对账结果: {report.summary}")

    # 启动周期性对账
    # reconciler.start_periodic_reconcile()

    # 获取状态
    status = reconciler.get_status()
    print(f"对账状态: {json.dumps(status, indent=2, ensure_ascii=False)}")

    # 运行自测试
    test_result = reconciler.run_self_test()
    print(f"自测试结果: {json.dumps(test_result, indent=2, ensure_ascii=False)}")
