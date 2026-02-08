"""
文件保护模块

实现服务器代码文件锁定机制：
1. 文件修改权限检查
2. 密钥验证
3. 文件锁定状态管理
"""

import os
import sys
import hashlib
import json
import logging
from pathlib import Path
from typing import Optional, Dict, List, Set
from datetime import datetime

logger = logging.getLogger(__name__)


class FileProtection:
    """文件保护管理器"""
    
    def __init__(self, protected_dir: Path, secret_key: str):
        """
        初始化文件保护管理器
        
        Args:
            protected_dir: 受保护的目录
            secret_key: 密钥（用于验证修改权限）
        """
        self.protected_dir = Path(protected_dir).resolve()
        self.secret_key = secret_key
        # Keep runtime lock under state/ to avoid cluttering project root.
        self.lock_file = self.protected_dir / "state" / "file_protection_lock.json"
        self.protected_files: Set[Path] = set()
        self.lock_state: Dict = {}
        
        # 加载锁定状态
        self._load_lock_state()
        
        # 扫描受保护文件
        self._scan_protected_files()
    
    def _load_lock_state(self):
        """加载锁定状态"""
        if self.lock_file.exists():
            try:
                with open(self.lock_file, "r", encoding="utf-8") as f:
                    self.lock_state = json.load(f)
            except Exception as e:
                logger.warning(f"Failed to load lock state: {e}")
                self.lock_state = {}
        else:
            self.lock_state = {
                "locked": True,
                "locked_at": datetime.now().isoformat(),
                "protected_files": []
            }
    
    def _save_lock_state(self):
        """保存锁定状态"""
        try:
            with open(self.lock_file, "w", encoding="utf-8") as f:
                json.dump(self.lock_state, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Failed to save lock state: {e}")
    
    def _scan_protected_files(self):
        """扫描受保护的文件"""
        protected_patterns = [
            "*.py",  # Python文件
            "*.ps1",  # PowerShell脚本
            "*.json",  # 配置文件
            "*.yaml",  # YAML配置
            "*.yml",  # YAML配置
        ]
        
        for pattern in protected_patterns:
            for file_path in self.protected_dir.rglob(pattern):
                # 排除锁定文件本身和临时文件
                if file_path.name.startswith(".") or file_path.name.startswith("~"):
                    continue
                # 排除__pycache__和测试文件（可选）
                if "__pycache__" in str(file_path) or ".pytest_cache" in str(file_path):
                    continue
                self.protected_files.add(file_path)
        
        # 更新锁定状态
        self.lock_state["protected_files"] = [
            str(f.relative_to(self.protected_dir)) for f in self.protected_files
        ]
        self._save_lock_state()
    
    def verify_key(self, provided_key: str) -> bool:
        """
        验证密钥
        
        Args:
            provided_key: 提供的密钥
            
        Returns:
            bool: 密钥是否正确
        """
        # 使用SHA256比较密钥（避免明文存储）
        provided_hash = hashlib.sha256(provided_key.encode()).hexdigest()
        expected_hash = hashlib.sha256(self.secret_key.encode()).hexdigest()
        return provided_hash == expected_hash
    
    def is_file_protected(self, file_path: Path) -> bool:
        """
        检查文件是否受保护
        
        Args:
            file_path: 文件路径
            
        Returns:
            bool: 文件是否受保护
        """
        resolved_path = Path(file_path).resolve()
        return resolved_path in self.protected_files
    
    def can_modify_file(self, file_path: Path, provided_key: Optional[str] = None) -> tuple[bool, str]:
        """
        检查是否可以修改文件
        
        Args:
            file_path: 文件路径
            provided_key: 提供的密钥（如果为None，从环境变量获取）
            
        Returns:
            tuple[bool, str]: (是否允许, 原因)
        """
        # 如果未锁定，允许修改
        if not self.lock_state.get("locked", False):
            return True, "Files are not locked"
        
        # 检查文件是否受保护
        if not self.is_file_protected(file_path):
            return True, "File is not protected"
        
        # 检查密钥
        if provided_key is None:
            provided_key = os.getenv("UNIFIED_SERVER_MODIFY_KEY", "")
        
        if not provided_key:
            return False, "UNIFIED_SERVER_MODIFY_KEY environment variable not set"
        
        if not self.verify_key(provided_key):
            return False, "Invalid modification key"
        
        return True, "Key verified"
    
    def lock_files(self):
        """锁定所有受保护文件"""
        self.lock_state["locked"] = True
        self.lock_state["locked_at"] = datetime.now().isoformat()
        self._save_lock_state()
        logger.info(f"Files locked at {self.lock_state['locked_at']}")
    
    def unlock_files(self, provided_key: str) -> bool:
        """
        解锁所有受保护文件
        
        Args:
            provided_key: 提供的密钥
            
        Returns:
            bool: 是否成功解锁
        """
        if not self.verify_key(provided_key):
            logger.error("Invalid key for unlocking")
            return False
        
        self.lock_state["locked"] = False
        self.lock_state["unlocked_at"] = datetime.now().isoformat()
        self._save_lock_state()
        logger.info(f"Files unlocked at {self.lock_state['unlocked_at']}")
        return True
    
    def get_protected_files(self) -> List[Path]:
        """获取所有受保护文件列表"""
        return sorted(self.protected_files)
    
    def get_lock_status(self) -> Dict:
        """获取锁定状态"""
        return {
            "locked": self.lock_state.get("locked", False),
            "locked_at": self.lock_state.get("locked_at"),
            "protected_files_count": len(self.protected_files),
            "protected_files": [
                str(f.relative_to(self.protected_dir)) for f in sorted(self.protected_files)
            ]
        }


# 全局文件保护实例
_file_protection: Optional[FileProtection] = None


def get_file_protection(protected_dir: Optional[Path] = None, secret_key: Optional[str] = None) -> FileProtection:
    """
    获取文件保护实例
    
    Args:
        protected_dir: 受保护的目录（如果为None，使用当前目录）
        secret_key: 密钥（如果为None，从环境变量获取）
        
    Returns:
        FileProtection: 文件保护实例
    """
    global _file_protection
    
    if _file_protection is None:
        if protected_dir is None:
            protected_dir = Path(__file__).parent.parent
        
        if secret_key is None:
            # 从导航文档读取密钥
            try:
                nav_script = protected_dir.parent / "read_secret_from_nav.py"
                if nav_script.exists():
                    import subprocess
                    result = subprocess.run(
                        [sys.executable, str(nav_script)],
                        capture_output=True,
                        text=True,
                        timeout=5
                    )
                    if result.returncode == 0:
                        secret_key = result.stdout.strip()
            except Exception as e:
                logger.warning(f"Failed to read secret from nav: {e}")
            
            # 如果从导航文档读取失败，尝试环境变量
            if not secret_key or secret_key == "":
                secret_key = os.getenv("UNIFIED_SERVER_SECRET_KEY", "default_secret_key_change_me")
        
        _file_protection = FileProtection(protected_dir, secret_key)
    
    return _file_protection
