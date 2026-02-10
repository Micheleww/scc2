#!/usr/bin/env python3
"""
DRILL模式管理模块
负责DRILL模式的执行、报告生成和监控摘要
"""

import json
import logging
import os
from datetime import datetime
from typing import Any

# 配置日志
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class DrillModeManager:
    """
    DRILL模式管理器
    负责DRILL模式的执行、报告生成和监控摘要
    """

    def __init__(self, config: dict[str, Any]):
        """
        初始化DRILL模式管理器

        Args:
            config: 配置信息
        """
        self.config = config
        self.drill_enabled = config.get("system", {}).get("drill_mode", True)
        self.live_trading = config.get("system", {}).get("live_trading", False)

        # DRILL模式统计数据
        self.drill_stats = {
            "signal_count": 0,
            "allow_count": 0,
            "block_count": 0,
            "block_reasons": {},
            "expected_usage_usdt": 0.0,
        }

        # 确保报告目录存在
        self.reports_dir = "reports"
        os.makedirs(self.reports_dir, exist_ok=True)

        logger.info(
            f"DRILL模式管理器初始化完成，DRILL模式: {'开启' if self.drill_enabled else '关闭'}"
        )

    def record_signal(
        self, signal: dict[str, Any], allowed: bool, reason: str | None = None
    ) -> None:
        """
        记录信号处理结果

        Args:
            signal: 信号信息
            allowed: 是否允许执行
            reason: 拒绝原因（如果allowed为False）
        """
        self.drill_stats["signal_count"] += 1

        if allowed:
            self.drill_stats["allow_count"] += 1
            # 计算预计占用USDT
            amount = signal.get("amount", 0.0)
            price = signal.get("price", 0.0)
            self.drill_stats["expected_usage_usdt"] += amount * price
        else:
            self.drill_stats["block_count"] += 1
            # 记录拒绝原因
            if reason:
                if reason not in self.drill_stats["block_reasons"]:
                    self.drill_stats["block_reasons"][reason] = 0
                self.drill_stats["block_reasons"][reason] += 1

    def generate_drill_report(self) -> dict[str, Any]:
        """
        生成DRILL模式报告

        Returns:
            Dict[str, Any]: DRILL模式报告
        """
        logger.info("生成DRILL模式报告")

        # 生成报告时间戳
        timestamp = datetime.utcnow().isoformat() + "Z"

        # 排序拒绝原因
        sorted_block_reasons = dict(
            sorted(self.drill_stats["block_reasons"].items(), key=lambda x: x[1], reverse=True)
        )

        # 生成报告
        report = {
            "timestamp": timestamp,
            "drill_enabled": self.drill_enabled,
            "live_trading": self.live_trading,
            "stats": {
                "signal_count": self.drill_stats["signal_count"],
                "allow_count": self.drill_stats["allow_count"],
                "block_count": self.drill_stats["block_count"],
                "block_reasons": sorted_block_reasons,
                "expected_usage_usdt": round(self.drill_stats["expected_usage_usdt"], 2),
                "expected_usage_ok": self.drill_stats["expected_usage_usdt"] <= 10.0,
            },
            "summary": {
                "top_block_reasons": list(sorted_block_reasons.keys())[:3],
                "usage_status": "PASS"
                if self.drill_stats["expected_usage_usdt"] <= 10.0
                else "FAIL",
                "overall_status": "OK" if self.drill_enabled else "DISABLED",
            },
        }

        # 保存报告到文件
        report_path = os.path.join(self.reports_dir, "drill_report.json")
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, ensure_ascii=False, default=str)

        logger.info(f"DRILL模式报告已生成: {report_path}")
        return report

    def generate_live_snapshot(self) -> dict[str, Any]:
        """
        生成监控摘要（live_snapshot）

        Returns:
            Dict[str, Any]: 监控摘要
        """
        logger.info("生成监控摘要")

        # 生成时间戳
        timestamp = datetime.utcnow().isoformat() + "Z"

        # 生成JSON格式的监控摘要
        snapshot_json = {
            "timestamp": timestamp,
            "system_status": {
                "drill_mode": self.drill_enabled,
                "live_trading": self.live_trading,
                "run_mode": self.config.get("system", {}).get("run_mode", "development"),
            },
            "drill_stats": self.drill_stats,
            "execution_readiness": {
                "status": "READY",  # 这里可以从readiness模块获取真实状态
                "blocked_reasons": [],
            },
            "market_data": {
                "symbols": self.config.get("data_collection", {}).get("symbols", []),
                "exchanges": self.config.get("data_collection", {}).get("exchanges", []),
            },
            "risk_status": {
                "max_total_usdt": 10.0,
                "expected_usage_usdt": round(self.drill_stats["expected_usage_usdt"], 2),
                "usage_ok": self.drill_stats["expected_usage_usdt"] <= 10.0,
            },
            "reconciliation_status": {
                "status": "OK",  # 这里可以从reconciliation模块获取真实状态
                "last_reconciliation_time": timestamp,
            },
        }

        # 保存JSON格式的监控摘要
        json_path = os.path.join(self.reports_dir, "live_snapshot.json")
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(snapshot_json, f, indent=2, ensure_ascii=False, default=str)

        # 生成Markdown格式的监控摘要
        md_content = self._generate_live_snapshot_md(snapshot_json)
        md_path = os.path.join(self.reports_dir, "live_snapshot.md")
        with open(md_path, "w", encoding="utf-8") as f:
            f.write(md_content)

        logger.info(f"监控摘要已生成: {json_path} 和 {md_path}")
        return snapshot_json

    def _generate_live_snapshot_md(self, snapshot: dict[str, Any]) -> str:
        """
        生成Markdown格式的监控摘要

        Args:
            snapshot: JSON格式的监控摘要

        Returns:
            str: Markdown格式的监控摘要
        """
        md = f"""# 实时监控摘要

## 基本信息
- **生成时间**: {datetime.fromisoformat(snapshot["timestamp"].replace("Z", "")).strftime("%Y-%m-%d %H:%M:%S UTC")}
- **系统模式**: {snapshot["system_status"]["run_mode"].upper()}
- **DRILL模式**: {"✅ 开启" if snapshot["system_status"]["drill_mode"] else "❌ 关闭"}
- **实盘交易**: {"✅ 开启" if snapshot["system_status"]["live_trading"] else "❌ 关闭"}

## 执行状态
- **就绪状态**: {"✅ READY" if snapshot["execution_readiness"]["status"] == "READY" else "❌ BLOCKED"}
- **阻塞原因**: {", ".join(snapshot["execution_readiness"]["blocked_reasons"]) if snapshot["execution_readiness"]["blocked_reasons"] else "无"}

## DRILL模式统计
- **信号总数**: {snapshot["drill_stats"]["signal_count"]}
- **允许执行**: {snapshot["drill_stats"]["allow_count"]}
- **拒绝执行**: {snapshot["drill_stats"]["block_count"]}

### 拒绝原因Top
"""

        # 添加拒绝原因Top
        block_reasons = snapshot["drill_stats"]["block_reasons"]
        sorted_reasons = sorted(block_reasons.items(), key=lambda x: x[1], reverse=True)
        for i, (reason, count) in enumerate(sorted_reasons[:5], 1):
            md += f"- {i}. {reason}: {count}次\n"

        if not block_reasons:
            md += "- 无\n"

        # 添加风险状态
        risk_status = snapshot["risk_status"]
        md += f"""
## 风险状态
- **最大允许USDT**: {risk_status["max_total_usdt"]}u
- **预计占用USDT**: {risk_status["expected_usage_usdt"]}u
- **占用状态**: {"✅ 正常" if risk_status["usage_ok"] else "❌ 超出限制"}

## 市场数据
- **监控交易对**: {", ".join(snapshot["market_data"]["symbols"])}
- **交易所**: {", ".join(snapshot["market_data"]["exchanges"])}

## 对账状态
- **状态**: {"✅ OK" if snapshot["reconciliation_status"]["status"] == "OK" else "❌ 异常"}
- **上次对账时间**: {datetime.fromisoformat(snapshot["reconciliation_status"]["last_reconciliation_time"].replace("Z", "")).strftime("%Y-%m-%d %H:%M:%S UTC")}

## 总结
"""

        # 添加总结
        if (
            snapshot["execution_readiness"]["status"] == "READY"
            and snapshot["risk_status"]["usage_ok"]
        ):
            md += "✅ 系统当前可以进入LIVE模式\n"
        else:
            md += "❌ 系统当前不建议进入LIVE模式\n"

        return md

    def reset_stats(self) -> None:
        """
        重置统计数据
        """
        self.drill_stats = {
            "signal_count": 0,
            "allow_count": 0,
            "block_count": 0,
            "block_reasons": {},
            "expected_usage_usdt": 0.0,
        }
        logger.info("DRILL模式统计数据已重置")

    def is_drill_enabled(self) -> bool:
        """
        检查DRILL模式是否开启

        Returns:
            bool: DRILL模式是否开启
        """
        return self.drill_enabled

    def set_drill_mode(self, enabled: bool) -> None:
        """
        设置DRILL模式开关

        Args:
            enabled: 是否开启DRILL模式
        """
        self.drill_enabled = enabled
        logger.info(f"DRILL模式已{'开启' if enabled else '关闭'}")
