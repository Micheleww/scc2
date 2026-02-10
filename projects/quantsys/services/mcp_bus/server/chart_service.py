"""
图表服务模块 - 提供数据可视化功能
支持交易数据图表、性能指标图表、实时数据推送等
"""

import json
import logging
import os
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class ChartConfig:
    """图表配置"""

    chart_id: str
    chart_type: str  # 'trading', 'performance', 'custom'
    title: str
    config: dict[str, Any]
    created_at: str
    updated_at: str


class ChartService:
    """图表服务 - 提供数据可视化功能"""

    def __init__(self, repo_root: str | None = None):
        self.repo_root = Path(repo_root) if repo_root else Path(os.getenv("REPO_ROOT", "."))
        self.charts_db_path = self.repo_root / "data" / "charts.db"
        self.charts_db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_database()

    def _init_database(self):
        """初始化图表配置数据库"""
        try:
            conn = sqlite3.connect(str(self.charts_db_path))
            cursor = conn.cursor()

            # 创建图表配置表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS chart_configs (
                    chart_id TEXT PRIMARY KEY,
                    chart_type TEXT NOT NULL,
                    title TEXT NOT NULL,
                    config TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
            """)

            conn.commit()
            conn.close()
            logger.info(f"Chart database initialized: {self.charts_db_path}")
        except Exception as e:
            logger.error(f"Failed to initialize chart database: {e}")

    def get_trading_data(
        self,
        symbol: str | None = None,
        timeframe: str = "1h",
        limit: int = 100,
        start_time: str | None = None,
        end_time: str | None = None,
    ) -> dict[str, Any]:
        """
        获取交易数据（K线数据）

        Args:
            symbol: 交易对，如 'BTC_USDT'
            timeframe: 时间周期，如 '1m', '5m', '1h', '1d'
            limit: 返回数据条数
            start_time: 开始时间（ISO格式）
            end_time: 结束时间（ISO格式）
        """
        try:
            # 尝试从数据库获取数据
            db_paths = [
                self.repo_root / "tradesv3.sqlite",
                self.repo_root / "tradesv3.dryrun.sqlite",
                self.repo_root / "user_data" / "tradesv3.sqlite",
                self.repo_root / "user_data" / "tradesv3.dryrun.sqlite",
            ]

            db_path = None
            for path in db_paths:
                if path.exists():
                    db_path = path
                    break

            if not db_path:
                return {
                    "symbol": symbol or "BTC_USDT",
                    "timeframe": timeframe,
                    "data": [],
                    "message": "No database found",
                }

            # 查询交易数据
            conn = sqlite3.connect(str(db_path))
            cursor = conn.cursor()

            # 构建查询
            query = "SELECT * FROM trades"
            conditions = []
            params = []

            if symbol:
                conditions.append("pair = ?")
                params.append(symbol.replace("_", "/"))

            if start_time:
                conditions.append("open_date >= ?")
                params.append(start_time)

            if end_time:
                conditions.append("open_date <= ?")
                params.append(end_time)

            if conditions:
                query += " WHERE " + " AND ".join(conditions)

            query += " ORDER BY open_date DESC LIMIT ?"
            params.append(limit)

            cursor.execute(query, params)
            rows = cursor.fetchall()

            # 获取列名
            columns = [description[0] for description in cursor.description]

            # 转换为字典列表
            trades = []
            for row in rows:
                trade = dict(zip(columns, row))
                trades.append(trade)

            conn.close()

            # 格式化数据用于图表
            chart_data = {
                "symbol": symbol or "BTC_USDT",
                "timeframe": timeframe,
                "data": trades,
                "count": len(trades),
            }

            return chart_data

        except Exception as e:
            logger.error(f"Failed to get trading data: {e}")
            return {
                "symbol": symbol or "BTC_USDT",
                "timeframe": timeframe,
                "data": [],
                "error": str(e),
            }

    def get_performance_data(
        self, days: int = 30, metrics: list[str] | None = None
    ) -> dict[str, Any]:
        """
        获取性能指标数据

        Args:
            days: 查询天数
            metrics: 指标列表，如 ['profit', 'win_rate', 'sharpe']
        """
        try:
            # 从监控服务获取系统指标
            from .monitoring import monitoring_service

            if not monitoring_service.metrics_history:
                return {"metrics": [], "period_days": days, "message": "No metrics data available"}

            # 获取最近N天的数据
            cutoff_time = datetime.now() - timedelta(days=days)
            recent_metrics = [
                m for m in monitoring_service.metrics_history if m.timestamp >= cutoff_time
            ]

            # 格式化数据
            chart_data = []
            for metric in recent_metrics[-100:]:  # 最多返回100个数据点
                chart_data.append(
                    {
                        "timestamp": metric.timestamp.isoformat(),
                        "cpu_percent": metric.cpu_percent,
                        "memory_percent": metric.memory_percent,
                        "memory_used_mb": metric.memory_used_mb,
                        "disk_percent": metric.disk_percent,
                        "network_sent_mb": metric.network_sent_mb,
                        "network_recv_mb": metric.network_recv_mb,
                    }
                )

            return {"metrics": chart_data, "period_days": days, "count": len(chart_data)}

        except Exception as e:
            logger.error(f"Failed to get performance data: {e}")
            return {"metrics": [], "period_days": days, "error": str(e)}

    def save_chart_config(
        self, chart_id: str, chart_type: str, title: str, config: dict[str, Any]
    ) -> bool:
        """保存图表配置"""
        try:
            conn = sqlite3.connect(str(self.charts_db_path))
            cursor = conn.cursor()

            now = datetime.now().isoformat()

            # 检查是否存在
            cursor.execute("SELECT chart_id FROM chart_configs WHERE chart_id = ?", (chart_id,))
            exists = cursor.fetchone()

            if exists:
                # 更新
                cursor.execute(
                    """
                    UPDATE chart_configs
                    SET chart_type = ?, title = ?, config = ?, updated_at = ?
                    WHERE chart_id = ?
                """,
                    (chart_type, title, json.dumps(config), now, chart_id),
                )
            else:
                # 插入
                cursor.execute(
                    """
                    INSERT INTO chart_configs (chart_id, chart_type, title, config, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                """,
                    (chart_id, chart_type, title, json.dumps(config), now, now),
                )

            conn.commit()
            conn.close()

            logger.info(f"Chart config saved: {chart_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to save chart config: {e}")
            return False

    def get_chart_config(self, chart_id: str) -> dict[str, Any] | None:
        """获取图表配置"""
        try:
            conn = sqlite3.connect(str(self.charts_db_path))
            cursor = conn.cursor()

            cursor.execute(
                """
                SELECT chart_id, chart_type, title, config, created_at, updated_at
                FROM chart_configs
                WHERE chart_id = ?
            """,
                (chart_id,),
            )

            row = cursor.fetchone()
            conn.close()

            if row:
                return {
                    "chart_id": row[0],
                    "chart_type": row[1],
                    "title": row[2],
                    "config": json.loads(row[3]),
                    "created_at": row[4],
                    "updated_at": row[5],
                }

            return None

        except Exception as e:
            logger.error(f"Failed to get chart config: {e}")
            return None

    def list_chart_configs(self, chart_type: str | None = None) -> list[dict[str, Any]]:
        """列出所有图表配置"""
        try:
            conn = sqlite3.connect(str(self.charts_db_path))
            cursor = conn.cursor()

            if chart_type:
                cursor.execute(
                    """
                    SELECT chart_id, chart_type, title, config, created_at, updated_at
                    FROM chart_configs
                    WHERE chart_type = ?
                    ORDER BY updated_at DESC
                """,
                    (chart_type,),
                )
            else:
                cursor.execute("""
                    SELECT chart_id, chart_type, title, config, created_at, updated_at
                    FROM chart_configs
                    ORDER BY updated_at DESC
                """)

            rows = cursor.fetchall()
            conn.close()

            charts = []
            for row in rows:
                charts.append(
                    {
                        "chart_id": row[0],
                        "chart_type": row[1],
                        "title": row[2],
                        "config": json.loads(row[3]),
                        "created_at": row[4],
                        "updated_at": row[5],
                    }
                )

            return charts

        except Exception as e:
            logger.error(f"Failed to list chart configs: {e}")
            return []

    def delete_chart_config(self, chart_id: str) -> bool:
        """删除图表配置"""
        try:
            conn = sqlite3.connect(str(self.charts_db_path))
            cursor = conn.cursor()

            cursor.execute("DELETE FROM chart_configs WHERE chart_id = ?", (chart_id,))

            conn.commit()
            conn.close()

            logger.info(f"Chart config deleted: {chart_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to delete chart config: {e}")
            return False


# 全局图表服务实例
chart_service = ChartService()
