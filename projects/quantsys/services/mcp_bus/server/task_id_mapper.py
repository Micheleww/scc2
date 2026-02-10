"""
Task ID 映射服务
处理 taskcode -> task_id 的映射（兼容旧格式）
"""

import json
import sqlite3
from pathlib import Path
from typing import Optional


class TaskIDMapper:
    """Task ID 映射器"""
    
    def __init__(self, repo_root: Path, db_path: Optional[Path] = None):
        self.repo_root = repo_root
        if db_path is None:
            db_path = repo_root / "docs" / "REPORT" / "ata" / "task_id_mapping.db"
        self.db_path = db_path
        self._init_db()
    
    def _init_db(self) -> None:
        """初始化数据库"""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS task_id_mapping (
                taskcode TEXT PRIMARY KEY,
                task_id TEXT NOT NULL UNIQUE,
                created_at TEXT NOT NULL,
                updated_at TEXT
            )
        """)
        conn.commit()
        conn.close()
    
    def get_task_id(self, taskcode: str) -> Optional[str]:
        """从 taskcode 获取 task_id"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT task_id FROM task_id_mapping WHERE taskcode = ?", (taskcode,))
        result = cursor.fetchone()
        conn.close()
        return result[0] if result else None
    
    def get_taskcode(self, task_id: str) -> Optional[str]:
        """从 task_id 获取 taskcode"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT taskcode FROM task_id_mapping WHERE task_id = ?", (task_id,))
        result = cursor.fetchone()
        conn.close()
        return result[0] if result else None
    
    def create_mapping(self, taskcode: str, task_id: str) -> None:
        """创建映射关系"""
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc).isoformat()
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT OR REPLACE INTO task_id_mapping (taskcode, task_id, created_at, updated_at)
            VALUES (?, ?, COALESCE((SELECT created_at FROM task_id_mapping WHERE taskcode = ?), ?), ?)
        """, (taskcode, task_id, taskcode, now, now))
        conn.commit()
        conn.close()
    
    def ensure_task_id(self, taskcode: str, area: Optional[str] = None) -> str:
        """
        确保 task_id 存在，如果不存在则生成
        
        使用统一的 task_id 管理模块生成 task_id
        """
        # 先检查是否已有映射
        existing_task_id = self.get_task_id(taskcode)
        if existing_task_id:
            return existing_task_id
        
        # 使用统一 task_id 管理模块生成 task_id
        from .task_id_manager import get_task_id_manager
        task_id_manager = get_task_id_manager()
        
        # 尝试从 taskcode 解析生成 task_id
        # 格式: {AREA}__{DATE} -> {AREA}-{DATE}-{seq}
        if "__" in taskcode:
            parts = taskcode.split("__")
            if len(parts) >= 2:
                area_from_code = parts[0] if area is None else area
                date_part = parts[1][:8] if len(parts[1]) >= 8 else None
                if date_part and date_part.isdigit():
                    # 生成 task_id
                    task_id = task_id_manager.generate(area_from_code, date_part)
                    self.create_mapping(taskcode, task_id)
                    # 同时注册到 task_id_manager 的映射表
                    task_id_manager.register_mapping(taskcode, task_id)
                    return task_id
        
        # 如果无法解析，使用 taskcode 作为 task_id（兼容旧格式）
        # 但仍然需要映射到统一格式
        use_area = area if area is not None else "QSYS"
        task_id = task_id_manager.migrate_taskcode(taskcode, use_area)
        self.create_mapping(taskcode, task_id)
        return task_id
