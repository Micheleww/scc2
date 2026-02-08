"""
文件修改守卫

在文件修改前检查权限，确保只有授权用户可以修改服务器文件
"""

import os
import sys
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


def check_file_modification_permission(file_path: Path) -> tuple[bool, str]:
    """
    检查文件修改权限
    
    Args:
        file_path: 要修改的文件路径
        
    Returns:
        tuple[bool, str]: (是否允许, 原因)
    """
    # 导入文件保护模块
    try:
        from .file_protection import get_file_protection
        
        # 获取文件保护实例
        protection = get_file_protection()
        
        # 检查权限
        return protection.can_modify_file(file_path)
    except ImportError:
        # 如果文件保护模块不可用，默认允许（开发模式）
        logger.warning("File protection module not available, allowing modification")
        return True, "File protection disabled"
    except Exception as e:
        logger.error(f"Error checking file modification permission: {e}")
        # 出错时默认拒绝（fail-closed）
        return False, f"Error checking permission: {str(e)}"


def require_modification_key(func):
    """
    装饰器：要求修改密钥才能执行函数
    
    使用示例:
        @require_modification_key
        def modify_server_file():
            # 修改服务器文件的代码
            pass
    """
    def wrapper(*args, **kwargs):
        # 检查环境变量中的密钥
        modify_key = os.getenv("UNIFIED_SERVER_MODIFY_KEY")
        if not modify_key:
            raise PermissionError(
                "UNIFIED_SERVER_MODIFY_KEY environment variable is required to modify server files. "
                "Please set the key from the navigation document."
            )
        
        # 验证密钥
        try:
            from .file_protection import get_file_protection
            protection = get_file_protection()
            
            if not protection.verify_key(modify_key):
                raise PermissionError(
                    "Invalid modification key. Please check the key in the navigation document."
                )
        except ImportError:
            logger.warning("File protection not available, skipping key verification")
        
        return func(*args, **kwargs)
    
    return wrapper
