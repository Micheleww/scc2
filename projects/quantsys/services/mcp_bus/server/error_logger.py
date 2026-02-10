#!/usr/bin/env python3
"""
错误日志集中管理系统
"""

import json
import logging
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class LogLevel(Enum):
    """日志级别"""

    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


@dataclass
class ErrorLog:
    """错误日志记录"""

    id: str
    timestamp: datetime
    level: str
    service: str
    message: str
    error_type: str | None = None
    stack_trace: str | None = None
    context: dict[str, Any] | None = None
    resolved: bool = False


class ErrorLogger:
    """错误日志管理器"""

    def __init__(self, db_path: Path | None = None):
        if db_path is None:
            db_path = Path(__file__).parent.parent.parent / "data" / "error_logs.db"

        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_database()

        # 设置日志处理器
        self._setup_log_handler()

    def _init_database(self):
        """初始化数据库"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS error_logs (
                id TEXT PRIMARY KEY,
                timestamp TEXT NOT NULL,
                level TEXT NOT NULL,
                service TEXT NOT NULL,
                message TEXT NOT NULL,
                error_type TEXT,
                stack_trace TEXT,
                context TEXT,
                resolved INTEGER DEFAULT 0
            )
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_timestamp ON error_logs(timestamp)
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_level ON error_logs(level)
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_service ON error_logs(service)
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_resolved ON error_logs(resolved)
        """)

        conn.commit()
        conn.close()

    def _setup_log_handler(self):
        """设置日志处理器"""
        handler = DatabaseLogHandler(self)
        handler.setLevel(logging.ERROR)
        formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
        handler.setFormatter(formatter)

        # 添加到根logger
        root_logger = logging.getLogger()
        root_logger.addHandler(handler)

    def log_error(
        self,
        level: str,
        service: str,
        message: str,
        error_type: str | None = None,
        stack_trace: str | None = None,
        context: dict[str, Any] | None = None,
    ) -> str:
        """记录错误日志"""
        log_id = f"{service}_{int(datetime.now().timestamp() * 1000)}"

        error_log = ErrorLog(
            id=log_id,
            timestamp=datetime.now(),
            level=level,
            service=service,
            message=message,
            error_type=error_type,
            stack_trace=stack_trace,
            context=context,
        )

        self._save_to_database(error_log)

        return log_id

    def _save_to_database(self, error_log: ErrorLog):
        """保存到数据库"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute(
            """
            INSERT INTO error_logs 
            (id, timestamp, level, service, message, error_type, stack_trace, context, resolved)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
            (
                error_log.id,
                error_log.timestamp.isoformat(),
                error_log.level,
                error_log.service,
                error_log.message,
                error_log.error_type,
                error_log.stack_trace,
                json.dumps(error_log.context) if error_log.context else None,
                0,
            ),
        )

        conn.commit()
        conn.close()

    def search_logs(
        self,
        level: str | None = None,
        service: str | None = None,
        keyword: str | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        resolved: bool | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """搜索日志"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        query = "SELECT * FROM error_logs WHERE 1=1"
        params = []

        if level:
            query += " AND level = ?"
            params.append(level)

        if service:
            query += " AND service = ?"
            params.append(service)

        if keyword:
            query += " AND (message LIKE ? OR error_type LIKE ?)"
            params.extend([f"%{keyword}%", f"%{keyword}%"])

        if start_time:
            query += " AND timestamp >= ?"
            params.append(start_time.isoformat())

        if end_time:
            query += " AND timestamp <= ?"
            params.append(end_time.isoformat())

        if resolved is not None:
            query += " AND resolved = ?"
            params.append(1 if resolved else 0)

        query += " ORDER BY timestamp DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        cursor.execute(query, params)
        rows = cursor.fetchall()

        columns = [desc[0] for desc in cursor.description]
        logs = []

        for row in rows:
            log_dict = dict(zip(columns, row))
            if log_dict.get("context"):
                try:
                    log_dict["context"] = json.loads(log_dict["context"])
                except:
                    pass
            logs.append(log_dict)

        conn.close()
        return logs

    def get_statistics(
        self, start_time: datetime | None = None, end_time: datetime | None = None
    ) -> dict[str, Any]:
        """获取统计信息"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        if not start_time:
            start_time = datetime.now() - timedelta(days=7)
        if not end_time:
            end_time = datetime.now()

        # 总数统计
        cursor.execute(
            """
            SELECT COUNT(*) FROM error_logs 
            WHERE timestamp >= ? AND timestamp <= ?
        """,
            (start_time.isoformat(), end_time.isoformat()),
        )
        total_count = cursor.fetchone()[0]

        # 按级别统计
        cursor.execute(
            """
            SELECT level, COUNT(*) FROM error_logs 
            WHERE timestamp >= ? AND timestamp <= ?
            GROUP BY level
        """,
            (start_time.isoformat(), end_time.isoformat()),
        )
        level_stats = dict(cursor.fetchall())

        # 按服务统计
        cursor.execute(
            """
            SELECT service, COUNT(*) FROM error_logs 
            WHERE timestamp >= ? AND timestamp <= ?
            GROUP BY service
        """,
            (start_time.isoformat(), end_time.isoformat()),
        )
        service_stats = dict(cursor.fetchall())

        # 未解决数量
        cursor.execute(
            """
            SELECT COUNT(*) FROM error_logs 
            WHERE timestamp >= ? AND timestamp <= ? AND resolved = 0
        """,
            (start_time.isoformat(), end_time.isoformat()),
        )
        unresolved_count = cursor.fetchone()[0]

        conn.close()

        return {
            "total_count": total_count,
            "unresolved_count": unresolved_count,
            "level_stats": level_stats,
            "service_stats": service_stats,
            "period": {"start": start_time.isoformat(), "end": end_time.isoformat()},
        }

    def resolve_log(self, log_id: str):
        """标记日志为已解决"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute(
            """
            UPDATE error_logs SET resolved = 1 WHERE id = ?
        """,
            (log_id,),
        )

        conn.commit()
        conn.close()

    def export_logs(
        self,
        format: str = "json",
        start_time: datetime | None = None,
        end_time: datetime | None = None,
    ) -> str:
        """导出日志"""
        logs = self.search_logs(start_time=start_time, end_time=end_time, limit=10000)

        if format == "json":
            return json.dumps(logs, indent=2, ensure_ascii=False, default=str)
        elif format == "csv":
            import csv
            import io

            output = io.StringIO()
            if logs:
                writer = csv.DictWriter(output, fieldnames=logs[0].keys())
                writer.writeheader()
                writer.writerows(logs)
            return output.getvalue()
        else:
            raise ValueError(f"Unsupported format: {format}")


class DatabaseLogHandler(logging.Handler):
    """数据库日志处理器"""

    def __init__(self, error_logger: ErrorLogger):
        super().__init__()
        self.error_logger = error_logger

    def emit(self, record):
        """发送日志记录"""
        try:
            # 提取错误类型和堆栈跟踪
            error_type = None
            stack_trace = None

            if record.exc_info:
                error_type = record.exc_info[0].__name__ if record.exc_info[0] else None
                import traceback

                stack_trace = "".join(traceback.format_exception(*record.exc_info))

            # 提取服务名称
            service = record.name.split(".")[0] if "." in record.name else "unknown"

            # 记录错误
            self.error_logger.log_error(
                level=record.levelname,
                service=service,
                message=record.getMessage(),
                error_type=error_type,
                stack_trace=stack_trace,
                context={
                    "module": record.module,
                    "funcName": record.funcName,
                    "lineno": record.lineno,
                    "pathname": record.pathname,
                },
            )
        except Exception:
            self.handleError(record)


# 全局错误日志管理器实例
error_logger = ErrorLogger()
