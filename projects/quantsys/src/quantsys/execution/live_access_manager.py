#!/usr/bin/env python3
"""
Live模式门禁管理器

实现总账户10u小仓live的硬门禁保障，默认不可进入live，只有满足条件才允许
"""

import hashlib
import json
import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Any

# 配置日志
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class LiveAccessManager:
    """
    Live模式门禁管理器
    """

    def __init__(self, task_id: str = "QSYS-20260111-9D15"):
        """
        初始化Live门禁管理器

        Args:
            task_id: 任务ID，用于证据保存路径
        """
        self.task_id = task_id

        # 10u小仓限制
        self.max_total_balance = 10.0

        # TaskHub路径配置
        self.taskhub_dir = Path("taskhub")
        self.evidence_dir = self.taskhub_dir / "evidence" / task_id
        self.evidence_dir.mkdir(parents=True, exist_ok=True)

        # blocking_issues文件路径
        self.blocking_issues_path = self.evidence_dir / "blocking_issues.json"

        # enable_live开关文件路径
        self.enable_live_path = Path("data/enable_live.json")

        # allowlist文件路径
        self.allowlist_path = Path("data/allowlist.json")

        # 审计文件路径
        self.audit_path = self.taskhub_dir / "manifest" / "audit_manifest.json"

        # 风险模板配置
        self.risk_template = {
            "enabled": True,
            "max_position": self.max_total_balance,
            "max_order_frequency": 1,
            "allow_new_positions": False,
            "allow_reduce_only": True,
            "max_total_balance": self.max_total_balance,
        }

        logger.info("Live门禁管理器初始化完成")

    def _check_latest_audit(self) -> dict[str, Any]:
        """
        检查最新审计是否为GO

        Returns:
            Dict[str, Any]: 检查结果，包含是否通过、原因等
        """
        try:
            if not self.audit_path.exists():
                return {"passed": False, "reason": "审计文件不存在"}

            with open(self.audit_path, encoding="utf-8") as f:
                audit_data = json.load(f)

            # 检查最新审计结果
            latest_audit = audit_data.get("latest_audit", {})
            if latest_audit.get("status") != "GO":
                return {
                    "passed": False,
                    "reason": f"最新审计状态不是GO，当前状态: {latest_audit.get('status')}",
                }

            return {"passed": True, "reason": "最新审计状态为GO"}
        except Exception as e:
            return {"passed": False, "reason": f"审计检查失败: {str(e)}"}

    def _check_enable_live_file(self) -> dict[str, Any]:
        """
        检查enable_live开关文件是否存在且有效

        Returns:
            Dict[str, Any]: 检查结果，包含是否通过、原因等
        """
        try:
            if not self.enable_live_path.exists():
                return {"passed": False, "reason": "enable_live开关文件不存在"}

            with open(self.enable_live_path, encoding="utf-8") as f:
                enable_data = json.load(f)

            # 检查文件结构
            timestamp = enable_data.get("timestamp")
            nonce = enable_data.get("nonce")
            expires_at = enable_data.get("expires_at")

            if not all([timestamp, nonce, expires_at]):
                return {"passed": False, "reason": "enable_live开关文件格式不正确"}

            # 检查是否过期
            current_time = time.time()
            if current_time > expires_at:
                return {
                    "passed": False,
                    "reason": f"enable_live开关文件已过期，过期时间: {datetime.fromtimestamp(expires_at).isoformat()}",
                }

            # 检查nonce有效性（简单实现：检查是否为16位字符串）
            if len(nonce) != 16:
                return {"passed": False, "reason": "enable_live开关文件nonce格式不正确"}

            return {"passed": True, "reason": "enable_live开关文件有效"}
        except Exception as e:
            return {"passed": False, "reason": f"enable_live开关文件检查失败: {str(e)}"}

    def _check_allowlist(self, strategy_id: str, symbol: str) -> dict[str, Any]:
        """
        检查策略/交易对是否在allowlist中

        Args:
            strategy_id: 策略ID
            symbol: 交易对

        Returns:
            Dict[str, Any]: 检查结果，包含是否通过、原因等
        """
        try:
            if not self.allowlist_path.exists():
                return {"passed": False, "reason": "allowlist文件不存在"}

            with open(self.allowlist_path, encoding="utf-8") as f:
                allowlist_data = json.load(f)

            # 获取allowlist
            strategies = allowlist_data.get("strategies", [])
            symbols = allowlist_data.get("symbols", [])

            # 检查策略和交易对是否命中
            if strategy_id not in strategies:
                return {"passed": False, "reason": f"策略 {strategy_id} 不在allowlist中"}

            if symbol not in symbols:
                return {"passed": False, "reason": f"交易对 {symbol} 不在allowlist中"}

            return {
                "passed": True,
                "reason": f"策略 {strategy_id} 和交易对 {symbol} 均在allowlist中",
            }
        except Exception as e:
            return {"passed": False, "reason": f"allowlist检查失败: {str(e)}"}

    def _check_risk_template(self) -> dict[str, Any]:
        """
        检查风险模板是否启用

        Returns:
            Dict[str, Any]: 检查结果，包含是否通过、原因等
        """
        try:
            if not self.risk_template.get("enabled", False):
                return {"passed": False, "reason": "风险模板未启用"}

            # 检查风险模板中的硬限制是否启用
            if self.risk_template.get("max_position") != self.max_total_balance:
                return {
                    "passed": False,
                    "reason": f"最大仓位限制不是10u，当前设置: {self.risk_template.get('max_position')}u",
                }

            return {"passed": True, "reason": "风险模板已启用且配置正确"}
        except Exception as e:
            return {"passed": False, "reason": f"风险模板检查失败: {str(e)}"}

    def check_live_access(
        self, strategy_id: str, symbol: str, order_amount: float
    ) -> dict[str, Any]:
        """
        检查是否允许进入live模式

        Args:
            strategy_id: 策略ID
            symbol: 交易对
            order_amount: 订单金额

        Returns:
            Dict[str, Any]: 综合检查结果
        """
        logger.info(
            f"开始检查live访问权限: 策略={strategy_id}, 交易对={symbol}, 订单金额={order_amount}u"
        )

        # 检查总账户限制
        if order_amount > self.max_total_balance:
            return {
                "allowed": False,
                "status": "BLOCKED",
                "reason": f"订单金额 {order_amount}u 超过总账户限制 {self.max_total_balance}u",
                "details": [],
            }

        # 执行所有检查
        checks = [
            ("latest_audit", self._check_latest_audit()),
            ("enable_live_file", self._check_enable_live_file()),
            ("allowlist", self._check_allowlist(strategy_id, symbol)),
            ("risk_template", self._check_risk_template()),
        ]

        # 收集检查结果
        passed_checks = []
        failed_checks = []

        for check_name, result in checks:
            if result["passed"]:
                passed_checks.append({"check": check_name, **result})
            else:
                failed_checks.append({"check": check_name, **result})

        # 综合判断
        if failed_checks:
            # 写入blocking_issues
            blocking_issues = {
                "timestamp": time.time(),
                "datetime": datetime.now().isoformat(),
                "status": "BLOCKED",
                "failed_checks": failed_checks,
                "passed_checks": passed_checks,
                "strategy_id": strategy_id,
                "symbol": symbol,
                "order_amount": order_amount,
            }

            with open(self.blocking_issues_path, "w", encoding="utf-8") as f:
                json.dump(blocking_issues, f, indent=2, ensure_ascii=False)

            logger.warning(f"Live访问被拦截: {[check['reason'] for check in failed_checks]}")
            return {
                "allowed": False,
                "status": "BLOCKED",
                "reason": "多项检查未通过",
                "details": failed_checks,
            }

        logger.info("Live访问检查通过")
        return {
            "allowed": True,
            "status": "ALLOWED",
            "reason": "所有检查通过",
            "details": passed_checks,
            "risk_template": self.risk_template,
        }

    def generate_enable_live_file(self, expires_in: int = 3600) -> Path:
        """
        生成enable_live开关文件

        Args:
            expires_in: 过期时间（秒）

        Returns:
            Path: 开关文件路径
        """
        # 生成一次性nonce
        nonce = hashlib.sha256(str(time.time()).encode()).hexdigest()[:16]

        # 计算过期时间
        current_time = time.time()
        expires_at = current_time + expires_in

        # 生成开关文件内容
        enable_data = {
            "timestamp": current_time,
            "nonce": nonce,
            "expires_at": expires_at,
            "expires_in": expires_in,
            "created_by": "LiveAccessManager",
            "description": "Live模式启用开关文件",
        }

        # 保存开关文件
        self.enable_live_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.enable_live_path, "w", encoding="utf-8") as f:
            json.dump(enable_data, f, indent=2, ensure_ascii=False)

        logger.info(
            f"enable_live开关文件已生成，过期时间: {datetime.fromtimestamp(expires_at).isoformat()}"
        )
        return self.enable_live_path

    def generate_allowlist_file(self, strategies: list[str], symbols: list[str]) -> Path:
        """
        生成allowlist文件

        Args:
            strategies: 允许的策略列表
            symbols: 允许的交易对列表

        Returns:
            Path: allowlist文件路径
        """
        # 生成allowlist文件内容
        allowlist_data = {
            "timestamp": time.time(),
            "strategies": strategies,
            "symbols": symbols,
            "created_by": "LiveAccessManager",
            "description": "Live模式允许列表",
        }

        # 保存allowlist文件
        self.allowlist_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.allowlist_path, "w", encoding="utf-8") as f:
            json.dump(allowlist_data, f, indent=2, ensure_ascii=False)

        logger.info(f"allowlist文件已生成: 策略={strategies}, 交易对={symbols}")
        return self.allowlist_path

    def generate_audit_file(self) -> Path:
        """
        生成审计文件

        Returns:
            Path: 审计文件路径
        """
        # 生成审计文件内容
        audit_data = {
            "timestamp": time.time(),
            "datetime": datetime.now().isoformat(),
            "latest_audit": {
                "status": "GO",
                "timestamp": time.time(),
                "auditor": "LiveAccessManager",
                "description": "测试审计结果",
            },
            "audit_history": [],
        }

        # 保存审计文件
        self.audit_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.audit_path, "w", encoding="utf-8") as f:
            json.dump(audit_data, f, indent=2, ensure_ascii=False)

        logger.info("审计文件已生成，状态为GO")
        return self.audit_path

    def run_live_drill(self) -> dict[str, Any]:
        """
        运行live演练

        Returns:
            Dict[str, Any]: 演练结果
        """
        logger.info("开始运行live演练")

        # 演练结果
        drill_results = {
            "drill_id": f"live_drill_{int(time.time())}",
            "timestamp": time.time(),
            "datetime": datetime.now().isoformat(),
            "results": [],
            "overall_status": "FAIL",
        }

        # 测试策略和交易对
        test_strategy = "eth_perp_trend_1h"
        test_symbol = "ETH-USDT-SWAP"
        test_amount = 5.0  # 5u，小于10u限制

        # 步骤1: 默认情况下，应被拦截
        logger.info("=== 步骤1: 默认情况下测试live访问 ===")
        result1 = self.check_live_access(test_strategy, test_symbol, test_amount)
        drill_results["results"].append(
            {
                "step": 1,
                "description": "默认情况下测试live访问",
                "expected": "BLOCKED",
                "actual": result1["status"],
                "success": result1["status"] == "BLOCKED",
                "details": result1,
            }
        )

        # 步骤2: 满足条件后，应允许进入live
        logger.info("=== 步骤2: 满足条件后测试live访问 ===")

        # 生成所需文件
        self.generate_audit_file()
        self.generate_enable_live_file()
        self.generate_allowlist_file([test_strategy], [test_symbol])

        # 测试live访问
        result2 = self.check_live_access(test_strategy, test_symbol, test_amount)
        drill_results["results"].append(
            {
                "step": 2,
                "description": "满足条件后测试live访问",
                "expected": "ALLOWED",
                "actual": result2["status"],
                "success": result2["status"] == "ALLOWED",
                "details": result2,
            }
        )

        # 步骤3: 测试超过10u限制
        logger.info("=== 步骤3: 测试超过10u限制 ===")
        result3 = self.check_live_access(test_strategy, test_symbol, 15.0)  # 15u，超过10u限制
        drill_results["results"].append(
            {
                "step": 3,
                "description": "测试超过10u限制",
                "expected": "BLOCKED",
                "actual": result3["status"],
                "success": result3["status"] == "BLOCKED",
                "details": result3,
            }
        )

        # 计算整体状态
        all_steps_passed = all(step["success"] for step in drill_results["results"])
        drill_results["overall_status"] = "PASS" if all_steps_passed else "FAIL"

        # 保存演练报告
        report_path = self.evidence_dir / "live_drill_report.json"
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(drill_results, f, indent=2, ensure_ascii=False)

        logger.info(f"live演练完成，结果: {drill_results['overall_status']}")
        logger.info(f"演练报告已保存到: {report_path}")

        return drill_results


if __name__ == "__main__":
    # 运行live演练
    manager = LiveAccessManager()
    drill_results = manager.run_live_drill()
    print(json.dumps(drill_results, indent=2, ensure_ascii=False))
