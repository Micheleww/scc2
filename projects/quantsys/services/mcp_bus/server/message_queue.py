
"""
可靠消息队列 - SQLite 实现
支持 ack/nack、重试、去重、DLQ
"""

import json
import sqlite3
import time
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Optional


class MessageStatus(str, Enum):
    """消息状态"""
    PENDING = "pending"
    SENT = "sent"
    ACKED = "acked"
    NACKED = "nacked"
    FAILED = "failed"
    DLQ = "dlq"


class MessageQueue:
    """可靠消息队列（SQLite）"""
    
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()
        self.max_retries = 3
        self.retry_delays = [1, 2, 4]  # 指数退避：1s, 2s, 4s
    
    def _init_db(self) -> None:
        """初始化数据库"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # 消息表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                message_id TEXT PRIMARY KEY,
                task_id TEXT,
                to_agent TEXT NOT NULL,
                payload TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                retry_count INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                sent_at TEXT,
                acked_at TEXT,
                next_retry_at TEXT,
                error_message TEXT
            )
        """)
        
        # 去重表（基于 message_id）
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS message_dedupe (
                message_id TEXT PRIMARY KEY,
                created_at TEXT NOT NULL
            )
        """)
        
        # DLQ 表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS dlq (
                message_id TEXT PRIMARY KEY,
                task_id TEXT,
                to_agent TEXT NOT NULL,
                payload TEXT NOT NULL,
                failed_at TEXT NOT NULL,
                error_message TEXT,
                retry_count INTEGER NOT NULL
            )
        """)
        
        # 索引
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_status ON messages(status)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_next_retry ON messages(next_retry_at)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_task_id ON messages(task_id)")
        
        conn.commit()
        conn.close()
    
    def enqueue(self, message_id: str, task_id: Optional[str], to_agent: str, payload: dict) -> bool:
        """
        入队消息（带去重检查）
        
        Returns:
            True: 成功入队
            False: 重复消息（已存在）
        """
        # 检查去重
        if self._is_duplicate(message_id):
            return False
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        now = datetime.now(timezone.utc).isoformat()
        
        try:
            cursor.execute("""
                INSERT INTO messages (message_id, task_id, to_agent, payload, status, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (message_id, task_id, to_agent, json.dumps(payload), MessageStatus.PENDING.value, now))
            
            # 记录去重
            cursor.execute("""
                INSERT INTO message_dedupe (message_id, created_at)
                VALUES (?, ?)
            """, (message_id, now))
            
            conn.commit()
            return True
        except sqlite3.IntegrityError:
            # 重复消息
            conn.rollback()
            return False
        finally:
            conn.close()
    
    def _is_duplicate(self, message_id: str) -> bool:
        """检查消息是否重复"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT 1 FROM message_dedupe WHERE message_id = ?", (message_id,))
        result = cursor.fetchone()
        conn.close()
        return result is not None
    
    def get_pending_messages(self, limit: int = 10) -> list[dict]:
        """获取待发送消息（包括需要重试的）"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        now = datetime.now(timezone.utc).isoformat()
        
        cursor.execute("""
            SELECT * FROM messages
            WHERE status = ? OR (status = ? AND next_retry_at <= ?)
            ORDER BY created_at ASC
            LIMIT ?
        """, (MessageStatus.PENDING.value, MessageStatus.NACKED.value, now, limit))
        
        rows = cursor.fetchall()
        messages = [dict(row) for row in rows]
        conn.close()
        
        # 解析 payload
        for msg in messages:
            msg["payload"] = json.loads(msg["payload"])
        
        return messages
    
    def mark_sent(self, message_id: str) -> None:
        """标记消息已发送"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        now = datetime.now(timezone.utc).isoformat()
        cursor.execute("""
            UPDATE messages
            SET status = ?, sent_at = ?
            WHERE message_id = ?
        """, (MessageStatus.SENT.value, now, message_id))
        conn.commit()
        conn.close()
    
    def mark_acked(self, message_id: str) -> None:
        """标记消息已确认"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        now = datetime.now(timezone.utc).isoformat()
        cursor.execute("""
            UPDATE messages
            SET status = ?, acked_at = ?
            WHERE message_id = ?
        """, (MessageStatus.ACKED.value, now, message_id))
        conn.commit()
        conn.close()
    
    def mark_nacked(self, message_id: str, error_message: Optional[str] = None) -> None:
        """标记消息未确认（需要重试）"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT retry_count FROM messages WHERE message_id = ?", (message_id,))
        result = cursor.fetchone()
        retry_count = result[0] if result else 0
        
        if retry_count >= self.max_retries:
            # 超过最大重试次数，进入 DLQ
            self._move_to_dlq(message_id, error_message, retry_count)
        else:
            # 计算下次重试时间
            delay = self.retry_delays[min(retry_count, len(self.retry_delays) - 1)]
            next_retry_at = datetime.now(timezone.utc).timestamp() + delay
            next_retry_iso = datetime.fromtimestamp(next_retry_at, timezone.utc).isoformat()
            
            cursor.execute("""
                UPDATE messages
                SET status = ?, retry_count = ?, next_retry_at = ?, error_message = ?
                WHERE message_id = ?
            """, (MessageStatus.NACKED.value, retry_count + 1, next_retry_iso, error_message, message_id))
        
        conn.commit()
        conn.close()
    
    def _move_to_dlq(self, message_id: str, error_message: Optional[str], retry_count: int) -> None:
        """移动消息到 DLQ"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # 获取消息
        cursor.execute("SELECT task_id, to_agent, payload FROM messages WHERE message_id = ?", (message_id,))
        result = cursor.fetchone()
        if result:
            task_id, to_agent, payload = result
            now = datetime.now(timezone.utc).isoformat()
            
            # 插入 DLQ
            cursor.execute("""
                INSERT OR REPLACE INTO dlq (message_id, task_id, to_agent, payload, failed_at, error_message, retry_count)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (message_id, task_id, to_agent, payload, now, error_message, retry_count))
            
            # 更新消息状态
            cursor.execute("""
                UPDATE messages
                SET status = ?
                WHERE message_id = ?
            """, (MessageStatus.DLQ.value, message_id))
        
        conn.commit()
        conn.close()
    
    def get_dlq_messages(self, limit: int = 100) -> list[dict]:
        """获取 DLQ 消息"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM dlq ORDER BY failed_at DESC LIMIT ?", (limit,))
        rows = cursor.fetchall()
        messages = [dict(row) for row in rows]
        conn.close()
        
        # 解析 payload
        for msg in messages:
            msg["payload"] = json.loads(msg["payload"])
        
        return messages
    
    def replay_dlq_message(self, message_id: str) -> bool:
        """重放 DLQ 消息（重新入队）"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # 获取 DLQ 消息
        cursor.execute("SELECT task_id, to_agent, payload FROM dlq WHERE message_id = ?", (message_id,))
        result = cursor.fetchone()
        if not result:
            conn.close()
            return False
        
        task_id, to_agent, payload = result
        
        # 重新入队
        success = self.enqueue(message_id, task_id, to_agent, json.loads(payload))
        
        if success:
            # 从 DLQ 删除
            cursor.execute("DELETE FROM dlq WHERE message_id = ?", (message_id,))
            conn.commit()
        
        conn.close()
        return success
