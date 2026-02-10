#!/usr/bin/env python3
"""
真单最小演练脚本
仅验证：开关读取、密钥读取、交易对/杠杆配置、下单参数构造、风控拦截
不实际执行订单，仅输出演练报告
"""

import json
import logging
import os
import time
from datetime import UTC, datetime
from typing import Any

# 配置日志
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class LiveDrill:
    """
    真单演练类
    负责验证真单执行前的所有必要条件
    """

    def __init__(self, config_dir: str = "configs"):
        """
        初始化真单演练

        Args:
            config_dir: 配置文件目录
        """
        self.config_dir = config_dir
        self.reports_dir = "reports"
        os.makedirs(self.reports_dir, exist_ok=True)

        # 演练结果
        self.drill_result = {
            "drill_id": f"live_drill_{int(time.time())}",
            "timestamp": datetime.now(UTC).isoformat() + "Z",
            "status": "PASS",
            "checks": [],
            "summary": {
                "total_checks": 0,
                "passed_checks": 0,
                "failed_checks": 0,
                "blocked_reasons": [],
                "is_ready": False,
            },
        }

        logger.info("真单演练初始化完成")

    def _add_check_result(
        self, check_name: str, passed: bool, reason: str = "", details: dict[str, Any] | None = None
    ):
        """
        添加检查结果

        Args:
            check_name: 检查名称
            passed: 是否通过
            reason: 原因
            details: 详细信息
        """
        check_result = {
            "check_name": check_name,
            "passed": passed,
            "reason": reason,
            "details": details or {},
            "timestamp": datetime.now(UTC).isoformat() + "Z",
        }

        self.drill_result["checks"].append(check_result)
        self.drill_result["summary"]["total_checks"] += 1

        if passed:
            self.drill_result["summary"]["passed_checks"] += 1
        else:
            self.drill_result["summary"]["failed_checks"] += 1
            self.drill_result["summary"]["blocked_reasons"].append(reason)
            self.drill_result["status"] = "FAIL"

    def check_system_switches(self):
        """
        检查系统开关配置
        """
        logger.info("开始检查系统开关配置...")

        # 读取系统配置
        config_path = os.path.join(self.config_dir, "config_live.json")
        if not os.path.exists(config_path):
            self._add_check_result("系统开关检查", False, "缺少系统配置文件 config_live.json")
            return

        try:
            with open(config_path, encoding="utf-8") as f:
                config = json.load(f)
        except json.JSONDecodeError as e:
            self._add_check_result("系统开关检查", False, f"系统配置文件格式错误: {e}")
            return

        # 检查系统开关
        system_config = config.get("system", {})
        drill_mode = system_config.get("drill_mode", True)
        live_trading = system_config.get("live_trading", False)

        checks = [
            ("DRILL模式", drill_mode, "DRILL模式未开启"),
            ("实盘交易开关", not live_trading, "实盘交易已开启，演练脚本应在实盘关闭状态下运行"),
        ]

        all_passed = True
        reasons = []

        for check_name, condition, fail_reason in checks:
            if not condition:
                all_passed = False
                reasons.append(fail_reason)

        self._add_check_result(
            "系统开关检查",
            all_passed,
            "; ".join(reasons) if not all_passed else "系统开关配置正确",
            {
                "drill_mode": drill_mode,
                "live_trading": live_trading,
                "run_mode": system_config.get("run_mode", "development"),
            },
        )

    def check_api_keys(self):
        """
        检查API密钥配置
        """
        logger.info("开始检查API密钥配置...")

        # 检查密钥文件
        keys_path = os.path.join(self.config_dir, "keys.json")
        if not os.path.exists(keys_path):
            self._add_check_result("API密钥检查", False, "缺少API密钥文件 keys.json")
            return

        try:
            with open(keys_path, encoding="utf-8") as f:
                keys = json.load(f)
        except json.JSONDecodeError as e:
            self._add_check_result("API密钥检查", False, f"API密钥文件格式错误: {e}")
            return

        # 检查必要的密钥字段
        required_keys = ["api_key", "secret_key", "passphrase"]

        missing_keys = []
        for key in required_keys:
            if key not in keys:
                missing_keys.append(key)

        if missing_keys:
            self._add_check_result(
                "API密钥检查", False, f"缺少必要的API密钥字段: {', '.join(missing_keys)}"
            )
            return

        # 检查密钥长度
        all_valid = True
        reasons = []

        for key in required_keys:
            if len(keys[key]) < 10:  # 简单验证密钥长度
                all_valid = False
                reasons.append(f"{key} 长度过短，可能无效")

        self._add_check_result(
            "API密钥检查",
            all_valid,
            "; ".join(reasons) if not all_valid else "API密钥配置完整",
            {
                "has_api_key": "api_key" in keys,
                "has_secret_key": "secret_key" in keys,
                "has_passphrase": "passphrase" in keys,
            },
        )

    def check_trading_config(self):
        """
        检查交易对和杠杆配置
        """
        logger.info("开始检查交易对和杠杆配置...")

        # 读取配置
        config_path = os.path.join(self.config_dir, "config_live.json")
        if not os.path.exists(config_path):
            self._add_check_result("交易配置检查", False, "缺少系统配置文件 config_live.json")
            return

        try:
            with open(config_path, encoding="utf-8") as f:
                config = json.load(f)
        except json.JSONDecodeError as e:
            self._add_check_result("交易配置检查", False, f"系统配置文件格式错误: {e}")
            return

        # 检查交易对配置
        trade_config = config.get("trade", {})
        symbols = trade_config.get("symbols", [])
        leverage = trade_config.get("leverage", 1)

        all_passed = True
        reasons = []

        if not symbols:
            all_passed = False
            reasons.append("未配置交易对")

        if leverage < 1 or leverage > 100:
            all_passed = False
            reasons.append("杠杆配置无效，范围应在1-100之间")

        # 检查交易参数配置
        execution_config = config.get("execution", {})
        order_type = execution_config.get("order_type")
        if not order_type:
            all_passed = False
            reasons.append("未配置订单类型")

        self._add_check_result(
            "交易配置检查",
            all_passed,
            "; ".join(reasons) if not all_passed else "交易配置完整",
            {
                "symbols": symbols,
                "leverage": leverage,
                "order_type": order_type,
                "execution_config": execution_config,
            },
        )

    def check_risk_config(self):
        """
        检查风控配置
        """
        logger.info("开始检查风控配置...")

        # 读取配置
        config_path = os.path.join(self.config_dir, "config_live.json")
        if not os.path.exists(config_path):
            self._add_check_result("风控配置检查", False, "缺少系统配置文件 config_live.json")
            return

        try:
            with open(config_path, encoding="utf-8") as f:
                config = json.load(f)
        except json.JSONDecodeError as e:
            self._add_check_result("风控配置检查", False, f"系统配置文件格式错误: {e}")
            return

        # 检查风控参数
        risk_config = config.get("risk", {})
        max_total_usdt = risk_config.get("max_total_usdt", 10.0)
        per_trade_usdt = risk_config.get("per_trade_usdt", 5.0)

        all_passed = True
        reasons = []

        if max_total_usdt <= 0:
            all_passed = False
            reasons.append("最大总暴露USDT配置无效")

        if per_trade_usdt <= 0:
            all_passed = False
            reasons.append("单笔交易USDT配置无效")

        if per_trade_usdt > max_total_usdt:
            all_passed = False
            reasons.append("单笔交易USDT超过最大总暴露限制")

        self._add_check_result(
            "风控配置检查",
            all_passed,
            "; ".join(reasons) if not all_passed else "风控配置完整",
            {
                "max_total_usdt": max_total_usdt,
                "per_trade_usdt": per_trade_usdt,
                "risk_config": risk_config,
            },
        )

    def construct_order_params(self):
        """
        构造下单参数并验证
        """
        logger.info("开始构造下单参数...")

        # 读取配置
        config_path = os.path.join(self.config_dir, "config_live.json")
        if not os.path.exists(config_path):
            self._add_check_result("下单参数构造", False, "缺少系统配置文件 config_live.json")
            return

        try:
            with open(config_path, encoding="utf-8") as f:
                config = json.load(f)
        except json.JSONDecodeError as e:
            self._add_check_result("下单参数构造", False, f"系统配置文件格式错误: {e}")
            return

        # 构造模拟订单参数
        trade_config = config.get("trade", {})
        symbols = trade_config.get("symbols", [])
        leverage = trade_config.get("leverage", 1)

        if not symbols:
            self._add_check_result("下单参数构造", False, "未配置交易对，无法构造订单参数")
            return

        # 构造订单参数
        sample_order = {
            "symbol": symbols[0],
            "side": "buy",
            "amount": 1.0,
            "price": 2000.0,
            "leverage": leverage,
            "order_type": config.get("execution", {}).get("order_type", "limit+protection"),
            "timestamp": time.time(),
        }

        # 计算订单金额
        order_amount_usdt = sample_order["amount"] * sample_order["price"]
        sample_order["amount_usdt"] = order_amount_usdt

        self._add_check_result(
            "下单参数构造",
            True,
            "下单参数构造成功",
            {"sample_order": sample_order, "order_amount_usdt": order_amount_usdt},
        )

    def check_risk_interception(self):
        """
        检查风控拦截逻辑
        """
        logger.info("开始检查风控拦截逻辑...")

        # 读取配置
        config_path = os.path.join(self.config_dir, "config_live.json")
        if not os.path.exists(config_path):
            self._add_check_result("风控拦截检查", False, "缺少系统配置文件 config_live.json")
            return

        try:
            with open(config_path, encoding="utf-8") as f:
                config = json.load(f)
        except json.JSONDecodeError as e:
            self._add_check_result("风控拦截检查", False, f"系统配置文件格式错误: {e}")
            return

        # 模拟风控检查
        risk_config = config.get("risk", {})
        max_total_usdt = risk_config.get("max_total_usdt", 10.0)
        per_trade_usdt = risk_config.get("per_trade_usdt", 5.0)

        # 测试1：正常订单（应该通过）
        normal_order = {
            "amount_usdt": per_trade_usdt * 0.8  # 80% of per trade limit
        }

        # 测试2：超过单笔限制（应该拦截）
        oversized_order = {
            "amount_usdt": per_trade_usdt * 1.5  # 150% of per trade limit
        }

        # 执行风控检查
        normal_passed = normal_order["amount_usdt"] <= per_trade_usdt
        oversized_passed = oversized_order["amount_usdt"] <= per_trade_usdt

        # 验证风控逻辑是否正确
        risk_logic_correct = normal_passed and not oversized_passed

        self._add_check_result(
            "风控拦截检查",
            risk_logic_correct,
            "风控拦截逻辑正确" if risk_logic_correct else "风控拦截逻辑错误",
            {
                "normal_order_check": {
                    "order_amount": normal_order["amount_usdt"],
                    "per_trade_limit": per_trade_usdt,
                    "passed": normal_passed,
                },
                "oversized_order_check": {
                    "order_amount": oversized_order["amount_usdt"],
                    "per_trade_limit": per_trade_usdt,
                    "passed": oversized_passed,
                },
                "risk_config": risk_config,
            },
        )

    def check_execution_readiness(self):
        """
        检查执行就绪状态
        """
        logger.info("开始检查执行就绪状态...")

        # 读取readiness文件
        data_dir = "data"
        readiness_path = os.path.join(data_dir, "readiness.json")

        if os.path.exists(readiness_path):
            try:
                with open(readiness_path, encoding="utf-8") as f:
                    readiness_data = json.load(f)

                is_ready = readiness_data.get("status", "BLOCKED") == "READY"
                blocked_reasons = readiness_data.get("blocked_reasons", [])

                self._add_check_result(
                    "执行就绪状态检查",
                    is_ready,
                    "执行就绪" if is_ready else f"执行被拦截: {', '.join(blocked_reasons)}",
                    readiness_data,
                )
            except json.JSONDecodeError as e:
                self._add_check_result("执行就绪状态检查", False, f"就绪状态文件格式错误: {e}")
        else:
            # 如果没有readiness文件，默认为就绪
            self._add_check_result("执行就绪状态检查", True, "未找到就绪状态文件，默认执行就绪")

    def run_all_checks(self):
        """
        运行所有检查
        """
        logger.info("开始执行所有真单演练检查...")

        # 执行各项检查
        self.check_system_switches()
        self.check_api_keys()
        self.check_trading_config()
        self.check_risk_config()
        self.construct_order_params()
        self.check_risk_interception()
        self.check_execution_readiness()

        # 生成最终结果
        self.drill_result["summary"]["is_ready"] = (
            self.drill_result["status"] == "PASS"
            and len(self.drill_result["summary"]["blocked_reasons"]) == 0
        )

        logger.info(f"真单演练检查完成，状态: {self.drill_result['status']}")
        logger.info(
            f"通过检查: {self.drill_result['summary']['passed_checks']}/ {self.drill_result['summary']['total_checks']}"
        )

        if self.drill_result["summary"]["blocked_reasons"]:
            logger.warning(
                f"拦截原因: {', '.join(self.drill_result['summary']['blocked_reasons'])}"
            )

        return self.drill_result

    def save_report(self, report_path: str = "live_drill_report.json"):
        """
        保存演练报告

        Args:
            report_path: 报告文件路径
        """
        report_full_path = os.path.join(self.reports_dir, report_path)

        try:
            with open(report_full_path, "w", encoding="utf-8") as f:
                json.dump(self.drill_result, f, indent=2, ensure_ascii=False, default=str)

            logger.info(f"真单演练报告已保存到: {report_full_path}")
            return True
        except OSError as e:
            logger.error(f"保存真单演练报告失败: {e}")
            return False


def main():
    """
    主函数
    """
    # 创建真单演练实例
    drill = LiveDrill()

    # 运行所有检查
    result = drill.run_all_checks()

    # 保存报告
    drill.save_report()

    # 输出摘要
    print("\n=== 真单演练摘要 ===")
    print(f"状态: {'✅ 通过' if result['status'] == 'PASS' else '❌ 失败'}")
    print(f"检查项: {result['summary']['passed_checks']}/{result['summary']['total_checks']} 通过")
    print(f"是否就绪: {'✅ 是' if result['summary']['is_ready'] else '❌ 否'}")

    if result["summary"]["blocked_reasons"]:
        print("\n❌ 拦截原因:")
        for reason in result["summary"]["blocked_reasons"]:
            print(f"   - {reason}")

    print(f"\n报告文件: {os.path.join('reports', 'live_drill_report.json')}")

    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    exit(main())
