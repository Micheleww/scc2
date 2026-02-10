#!/usr/bin/env python3
"""
统一task_id管理模块
实现{area}-{date}-{seq}格式的task_id生成和映射
"""

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Dict, List


class TaskIDManager:
    """统一task_id管理类"""
    
    # 统一task_id正则表达式
    TASK_ID_PATTERN = re.compile(r"^([a-zA-Z0-9_-]+)-([0-9]{8})-([0-9]{3,})$")
    
    def __init__(self, storage_dir: Path = None):
        """
        初始化task_id管理器
        
        Args:
            storage_dir: 存储序列号和映射的目录，默认使用当前目录
        """
        if storage_dir is None:
            storage_dir = Path(__file__).parent
        self.storage_dir = storage_dir
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        
        # 映射文件路径
        self.mapping_file = self.storage_dir / "task_id_mappings.json"
        
        # 加载现有映射
        self.mappings: Dict[str, str] = self._load_mappings()
    
    def _load_mappings(self) -> Dict[str, str]:
        """加载taskcode到task_id的映射"""
        if self.mapping_file.exists():
            try:
                import json
                with open(self.mapping_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception:
                return {}
        return {}
    
    def _save_mappings(self):
        """保存映射到文件"""
        import json
        with open(self.mapping_file, 'w', encoding='utf-8') as f:
            json.dump(self.mappings, f, indent=2, ensure_ascii=False)
    
    def generate(self, area: str, date: Optional[str] = None, seq: Optional[int] = None) -> str:
        """
        生成统一task_id
        
        格式: {area}-{date}-{seq:03d}
        示例: QSYS-20260125-001
        
        Args:
            area: 区域标识（如QSYS、ATA、ORCH、CI等）
            date: 日期，格式为YYYYMMDD，默认使用当前日期
            seq: 序列号，默认从文件存储获取
        
        Returns:
            str: 生成的task_id
        """
        # Use local date for human-facing task IDs and to avoid timezone-related day drift.
        if date is None:
            date = datetime.now().strftime("%Y%m%d")
        
        if seq is None:
            # 从持久化存储获取下一个序列号
            seq_file = self.storage_dir / f"task_seq_{date}.txt"
            try:
                if seq_file.exists():
                    with open(seq_file, 'r') as f:
                        seq = int(f.read().strip()) + 1
                else:
                    seq = 1
                # 保存新序列号
                with open(seq_file, 'w') as f:
                    f.write(str(seq))
            except Exception:
                # 异常时使用随机数作为后备
                seq = 1
        
        return f"{area}-{date}-{seq:03d}"
    
    def parse(self, task_id: str) -> Dict[str, Optional[str]]:
        """
        解析task_id
        
        Args:
            task_id: 要解析的task_id
        
        Returns:
            Dict: 包含area、date、seq的字典，如果解析失败则返回空字典
        """
        match = self.TASK_ID_PATTERN.match(task_id)
        if match:
            return {
                "area": match.group(1),
                "date": match.group(2),
                "seq": match.group(3)
            }
        return {}
    
    def is_valid(self, task_id: str) -> bool:
        """
        验证task_id是否符合统一格式
        
        Args:
            task_id: 要验证的task_id
        
        Returns:
            bool: 是否有效
        """
        return bool(self.TASK_ID_PATTERN.match(task_id))
    
    def register_mapping(self, taskcode: str, task_id: str):
        """
        注册taskcode到task_id的映射
        
        Args:
            taskcode: 旧的taskcode
            task_id: 新的统一task_id
        """
        self.mappings[taskcode] = task_id
        self._save_mappings()
    
    def get_task_id(self, taskcode: str) -> Optional[str]:
        """
        通过taskcode获取对应的task_id
        
        Args:
            taskcode: 旧的taskcode
        
        Returns:
            Optional[str]: 对应的task_id，如果不存在则返回None
        """
        return self.mappings.get(taskcode)
    
    def get_taskcode(self, task_id: str) -> Optional[str]:
        """
        通过task_id获取对应的taskcode（反向映射）
        
        Args:
            task_id: 新的统一task_id
        
        Returns:
            Optional[str]: 对应的taskcode，如果不存在则返回None
        """
        for code, id_ in self.mappings.items():
            if id_ == task_id:
                return code
        return None
    
    def migrate_taskcode(self, taskcode: str, area: str = "QSYS") -> str:
        """
        将旧的taskcode迁移为新的统一task_id
        
        Args:
            taskcode: 旧的taskcode
            area: 区域标识
        
        Returns:
            str: 新的统一task_id
        """
        # 如果已经有映射，直接返回
        if taskcode in self.mappings:
            return self.mappings[taskcode]
        
        # 尝试从taskcode中提取日期
        date_match = re.search(r"(\d{8})", taskcode)
        if date_match:
            date = date_match.group(1)
        else:
            # 如果没有日期，使用当前日期
            date = datetime.now(timezone.utc).strftime("%Y%m%d")
        
        # 生成新的task_id
        task_id = self.generate(area, date)
        
        # 注册映射
        self.register_mapping(taskcode, task_id)
        
        return task_id
    
    def batch_migrate(self, taskcodes: List[str], area: str = "QSYS") -> Dict[str, str]:
        """
        批量迁移taskcode到统一task_id
        
        Args:
            taskcodes: 旧的taskcode列表
            area: 区域标识
        
        Returns:
            Dict[str, str]: taskcode到task_id的映射
        """
        result = {}
        for taskcode in taskcodes:
            result[taskcode] = self.migrate_taskcode(taskcode, area)
        return result


# 单例模式
_task_id_manager = None

def get_task_id_manager(storage_dir: Path = None) -> TaskIDManager:
    """
    获取task_id管理器单例
    
    Args:
        storage_dir: 存储目录
    
    Returns:
        TaskIDManager: task_id管理器实例
    """
    global _task_id_manager
    if _task_id_manager is None:
        _task_id_manager = TaskIDManager(storage_dir)
    return _task_id_manager


if __name__ == "__main__":
    # 测试代码
    manager = TaskIDManager()
    
    # 生成task_id
    task_id1 = manager.generate("QSYS")
    print(f"Generated task_id: {task_id1}")
    
    # 解析task_id
    parsed = manager.parse(task_id1)
    print(f"Parsed task_id: {parsed}")
    
    # 验证task_id
    print(f"Is valid: {manager.is_valid(task_id1)}")
    
    # 测试映射
    manager.register_mapping("OLD_TASK_001", task_id1)
    print(f"Mapping: {manager.get_task_id('OLD_TASK_001')}")
    
    # 测试迁移
    migrated = manager.migrate_taskcode("OLD_TASK_002")
    print(f"Migrated: OLD_TASK_002 -> {migrated}")
