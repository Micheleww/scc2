"""
文件写入守卫

在文件写入时自动检查权限，防止未授权修改
"""

import os
import sys
import builtins
from pathlib import Path
from typing import Optional

# 保存原始的open函数
_original_open = builtins.open
_original_write = None


def _check_write_permission(file_path: Path) -> bool:
    """检查文件写入权限"""
    try:
        from .file_protection import get_file_protection
        
        protection = get_file_protection()
        allowed, reason = protection.can_modify_file(file_path)
        
        if not allowed:
            print(f"[FILE_PROTECTION] 拒绝写入: {file_path}")
            print(f"[FILE_PROTECTION] 原因: {reason}")
            print(f"[FILE_PROTECTION] 提示: 设置 UNIFIED_SERVER_MODIFY_KEY 环境变量")
            return False
        
        return True
    except Exception as e:
        # 如果检查失败，默认允许（开发模式）
        # 在生产环境中可以改为拒绝（fail-closed）
        return True


def _protected_open(file, mode='r', buffering=-1, encoding=None, errors=None, newline=None, closefd=True, opener=None):
    """
    受保护的open函数
    
    在写入受保护文件时检查权限
    """
    # 如果是读取模式，直接使用原始open
    if 'r' in mode and 'w' not in mode and 'a' not in mode and 'x' not in mode:
        return _original_open(file, mode, buffering, encoding, errors, newline, closefd, opener)
    
    # 写入模式需要检查权限
    file_path = Path(file) if isinstance(file, (str, Path)) else None
    
    if file_path and file_path.exists():
        # 检查是否是受保护的文件
        if not _check_write_permission(file_path):
            raise PermissionError(
                f"文件受保护，无法修改: {file_path}\n"
                f"请设置 UNIFIED_SERVER_MODIFY_KEY 环境变量或使用 lock_server_files.py unlock"
            )
    
    return _original_open(file, mode, buffering, encoding, errors, newline, closefd, opener)


def enable_file_protection():
    """启用文件保护"""
    if builtins.open != _protected_open:
        builtins.open = _protected_open
        print("[FILE_PROTECTION] 文件保护已启用")


def disable_file_protection():
    """禁用文件保护"""
    if builtins.open == _protected_open:
        builtins.open = _original_open
        print("[FILE_PROTECTION] 文件保护已禁用")
