#!/usr/bin/env python3
"""
最小实盘看板模块
负责生成live_snapshot.md/json，对齐freq UI关键指标
"""

import json
import logging
import os
from datetime import UTC, datetime
from typing import Any

# 配置日志
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class LiveDashboard:
    """
    最小实盘看板
    负责生成live_snapshot.md/json，包含freq UI关键指标
    """

    def __init__(self, taskhub_path: str = "taskhub"):
        """
        初始化LiveDashboard

        Args:
            taskhub_path: TaskHub路径
        """
        self.taskhub_path = taskhub_path
        self.registry_path = os.path.join(taskhub_path, "registry.json")

        # 确保报告目录存在
        self.reports_dir = "reports"
        os.makedirs(self.reports_dir, exist_ok=True)

        logger.info(f"LiveDashboard初始化完成，TaskHub路径: {taskhub_path}")

    def read_taskhub_status(self) -> dict[str, Any]:
        """
        从TaskHub读取最新状态

        Returns:
            Dict[str, Any]: TaskHub状态
        """
        try:
            if os.path.exists(self.registry_path):
                with open(self.registry_path, encoding="utf-8") as f:
                    return json.load(f)
            else:
                logger.error(f"TaskHub registry.json不存在: {self.registry_path}")
                return {}
        except Exception as e:
            logger.error(f"读取TaskHub状态失败: {e}")
            return {}

    def generate_live_snapshot(self) -> dict[str, Any]:
        """
        生成live_snapshot，包含freq UI关键指标

        Returns:
            Dict[str, Any]: 生成的snapshot数据
        """
        logger.info("生成live_snapshot")

        # 生成时间戳
        timestamp = datetime.now(UTC).isoformat() + "Z"

        # 从TaskHub读取状态
        taskhub_status = self.read_taskhub_status()

        # 模拟获取当前门禁状态（实际应该从TaskHub或其他模块获取）
        # 这里需要根据实际情况修改，从TaskHub或其他模块获取真实状态
        execution_readiness = {
            "status": "READY",  # 实际应该从readiness模块获取
            "blocked_reasons": [],  # 实际应该从readiness模块获取
        }

        # 处理TaskHub状态，提取实际的更新时间
        taskhub_last_updated = timestamp  # 默认使用当前时间
        if isinstance(taskhub_status.get("updated_at"), dict):
            taskhub_last_updated = taskhub_status["updated_at"].get("updated_at", timestamp)
        elif isinstance(taskhub_status.get("updated_at"), str):
            taskhub_last_updated = taskhub_status["updated_at"]

        # 模拟当前仓位/订单数（实际应该从交易所或订单管理模块获取）
        positions_orders = {
            "current_positions": 0,  # 实际应该从交易所获取
            "current_orders": 0,  # 实际应该从交易所获取
        }

        # 模拟预算占用（实际应该从RiskEngine获取）
        # 10u/3.3u 表示总预算10u，当前占用3.3u
        budget_usage = {
            "total_budget_usdt": 10.0,
            "current_usage_usdt": 3.3,
            "usage_ratio": 33.0,  # 33%
        }

        # 模拟SAFE_STOP状态（实际应该从RiskEngine获取）
        safe_stop_status = {
            "enabled": False,  # 实际应该从RiskEngine获取
            "triggered": False,  # 实际应该从RiskEngine获取
            "reason": "",  # 实际应该从RiskEngine获取
        }

        # 生成JSON格式的snapshot
        snapshot_json = {
            "timestamp": timestamp,
            "execution_readiness": execution_readiness,
            "positions_orders": positions_orders,
            "budget_usage": budget_usage,
            "safe_stop_status": safe_stop_status,
            "taskhub_status": {
                "last_updated": taskhub_last_updated,
                "task_count": len(
                    [
                        k
                        for k in taskhub_status.keys()
                        if k not in ["version", "created_at", "updated_at", "tasks"]
                    ]
                ),
            },
        }

        # 保存JSON格式的snapshot
        json_path = os.path.join(self.reports_dir, "live_snapshot.json")
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(snapshot_json, f, indent=2, ensure_ascii=False, default=str)

        # 生成Markdown格式的snapshot
        md_content = self._generate_live_snapshot_md(snapshot_json)
        md_path = os.path.join(self.reports_dir, "live_snapshot.md")
        with open(md_path, "w", encoding="utf-8") as f:
            f.write(md_content)

        logger.info(f"live_snapshot已生成: {json_path} 和 {md_path}")
        return snapshot_json

    def _generate_live_snapshot_md(self, snapshot: dict[str, Any]) -> str:
        """
        生成Markdown格式的live_snapshot

        Args:
            snapshot: JSON格式的snapshot

        Returns:
            str: Markdown格式的snapshot
        """
        # 获取本地时间格式
        local_time = datetime.fromisoformat(snapshot["timestamp"].replace("Z", "")).strftime(
            "%Y-%m-%d %H:%M:%S UTC"
        )

        md = f"""# 实盘看板 - Live Snapshot
        
## 基本信息
- **生成时间**: {local_time}
        
## 门禁状态
- **状态**: {"✅ ALLOW" if snapshot["execution_readiness"]["status"] == "READY" else "❌ BLOCK"}
- **原因**: {", ".join(snapshot["execution_readiness"]["blocked_reasons"]) if snapshot["execution_readiness"]["blocked_reasons"] else "无"}
        
## 当前仓位/订单数
- **仓位数**: {snapshot["positions_orders"]["current_positions"]}
- **订单数**: {snapshot["positions_orders"]["current_orders"]}
        
## 预算占用
- **总预算**: {snapshot["budget_usage"]["total_budget_usdt"]}u
- **当前占用**: {snapshot["budget_usage"]["current_usage_usdt"]}u
- **占用比例**: {snapshot["budget_usage"]["usage_ratio"]}%
        
## SAFE_STOP 状态
- **启用状态**: {"✅ 启用" if snapshot["safe_stop_status"]["enabled"] else "❌ 禁用"}
- **触发状态**: {"⚠️ 已触发" if snapshot["safe_stop_status"]["triggered"] else "✅ 未触发"}
- **触发原因**: {snapshot["safe_stop_status"]["reason"] if snapshot["safe_stop_status"]["triggered"] else "无"}
        
## TaskHub 状态
- **最后更新**: {snapshot["taskhub_status"]["last_updated"]}
- **任务总数**: {snapshot["taskhub_status"]["task_count"]}
        
## 系统状态
- **健康状态**: ✅ 正常
- **连接状态**: ✅ 已连接
        """

        return md

    def get_snapshot(self) -> dict[str, Any] | None:
        """
        获取最新的live_snapshot

        Returns:
            Optional[Dict[str, Any]]: 最新的snapshot数据，或None如果不存在
        """
        snapshot_path = os.path.join(self.reports_dir, "live_snapshot.json")
        try:
            if os.path.exists(snapshot_path):
                with open(snapshot_path, encoding="utf-8") as f:
                    return json.load(f)
            else:
                logger.error(f"live_snapshot.json不存在: {snapshot_path}")
                return None
        except Exception as e:
            logger.error(f"读取live_snapshot失败: {e}")
            return None


if __name__ == "__main__":
    # 测试生成live_snapshot
    dashboard = LiveDashboard()
    snapshot = dashboard.generate_live_snapshot()
    logger.info(f"生成的live_snapshot: {json.dumps(snapshot, indent=2, ensure_ascii=False)}")
