#!/usr/bin/env python3
"""
从导航文档读取密钥

从项目导航文档中读取统一服务器的文件保护密钥
"""

import re
import sys
from pathlib import Path

# 获取项目根目录
current_file = Path(__file__).resolve()
unified_server_dir = current_file.parent
repo_root = unified_server_dir.parent.parent

NAV_DOC = repo_root / "docs" / "arch" / "project_navigation__v0.1.0__ACTIVE__20260115.md"


def read_secret_from_nav() -> str:
    """从导航文档读取密钥"""
    if not NAV_DOC.exists():
        print(f"Error: Navigation document not found: {NAV_DOC}")
        return ""
    
    try:
        with open(NAV_DOC, "r", encoding="utf-8") as f:
            content = f.read()
        
        # 查找密钥部分（在"统一服务器文件保护密钥"部分）
        # 使用正则表达式查找密钥
        # 匹配格式：统一服务器文件保护密钥: sT_CLgGKwKayTDYfZ6tP9Or3RzO0lDD402PH5HYQzRY
        pattern = r"统一服务器文件保护密钥[:\s]*([a-zA-Z0-9_\-]+)"
        match = re.search(pattern, content)
        
        if match:
            return match.group(1).strip()
        
        # 如果没找到，尝试其他格式
        # 直接查找32-64位的密钥字符串
        pattern2 = r"sT_[a-zA-Z0-9_\-]{32,}"
        match2 = re.search(pattern2, content)
        
        if match2:
            return match2.group(0).strip()
        
        # 最后尝试匹配任何32位以上的字母数字字符串
        pattern3 = r"[a-zA-Z0-9_\-]{32,}"
        match3 = re.search(pattern3, content)
        
        if match3:
            # 检查是否是哈希值（通常更长且全是小写）
            key = match3.group(0).strip()
            if not key.islower() or len(key) < 64:
                return key
        
        print("Warning: No secret key found in navigation document")
        return ""
    except Exception as e:
        print(f"Error: Failed to read navigation document: {e}")
        return ""


if __name__ == "__main__":
    secret = read_secret_from_nav()
    if secret:
        print(secret)
    else:
        sys.exit(1)
