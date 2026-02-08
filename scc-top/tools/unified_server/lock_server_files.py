#!/usr/bin/env python3
"""
锁定服务器文件脚本

锁定统一服务器的所有代码文件，只有提供正确密钥才能修改
"""

import os
import sys
import hashlib
from pathlib import Path

# 添加路径
current_file = Path(__file__).resolve()
unified_server_dir = current_file.parent
sys.path.insert(0, str(unified_server_dir))

from tools.unified_server.core.file_protection import FileProtection


def generate_secret_key() -> str:
    """生成密钥"""
    import secrets
    return secrets.token_urlsafe(32)


def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description="锁定/解锁统一服务器文件")
    parser.add_argument("action", choices=["lock", "unlock", "status", "generate-key"], 
                       help="操作：lock=锁定, unlock=解锁, status=查看状态, generate-key=生成密钥")
    parser.add_argument("--key", help="修改密钥（用于解锁）")
    parser.add_argument("--secret-key", help="设置密钥（用于锁定）")
    
    args = parser.parse_args()
    
    # 从导航文档读取密钥（这里需要实现从导航文档读取的逻辑）
    # 暂时从环境变量读取
    default_secret_key = os.getenv("UNIFIED_SERVER_SECRET_KEY")
    
    if args.action == "generate-key":
        key = generate_secret_key()
        key_hash = hashlib.sha256(key.encode()).hexdigest()
        print("=" * 60)
        print("生成的密钥（请保存到导航文档）")
        print("=" * 60)
        print(f"密钥: {key}")
        print(f"密钥哈希: {key_hash}")
        print()
        print("[WARN] 请将密钥添加到导航文档的以下位置：")
        print("   docs/arch/project_navigation__v0.1.0__ACTIVE__20260115.md")
        print("   统一服务器章节 > 文件保护密钥")
        print("=" * 60)
        return
    
    if args.action == "lock":
        secret_key = args.secret_key or default_secret_key
        if not secret_key:
            print("[ERROR] 错误: 需要提供密钥")
            print("   使用 --secret-key 参数或设置 UNIFIED_SERVER_SECRET_KEY 环境变量")
            print("   或使用 'python lock_server_files.py generate-key' 生成密钥")
            sys.exit(1)
        
        protection = FileProtection(unified_server_dir, secret_key)
        protection.lock_files()
        print("[OK] 文件已锁定")
        print(f"   受保护文件数: {len(protection.get_protected_files())}")
        return
    
    if args.action == "unlock":
        if not args.key:
            print("[ERROR] 错误: 解锁需要提供密钥")
            print("   使用 --key 参数或设置 UNIFIED_SERVER_MODIFY_KEY 环境变量")
            sys.exit(1)
        
        secret_key = default_secret_key
        if not secret_key:
            print("[ERROR] 错误: 未找到服务器密钥")
            print("   请从导航文档中获取密钥")
            sys.exit(1)
        
        protection = FileProtection(unified_server_dir, secret_key)
        if protection.unlock_files(args.key):
            print("[OK] 文件已解锁")
        else:
            print("[FAIL] 解锁失败: 密钥不正确")
            sys.exit(1)
        return
    
    if args.action == "status":
        secret_key = default_secret_key or "default"
        protection = FileProtection(unified_server_dir, secret_key)
        status = protection.get_lock_status()
        
        print("=" * 60)
        print("文件保护状态")
        print("=" * 60)
        print(f"锁定状态: {'[LOCKED] 已锁定' if status['locked'] else '[UNLOCKED] 未锁定'}")
        if status.get("locked_at"):
            print(f"锁定时间: {status['locked_at']}")
        print(f"受保护文件数: {status['protected_files_count']}")
        print()
        print("受保护文件列表:")
        for file in status['protected_files'][:20]:  # 只显示前20个
            print(f"  - {file}")
        if len(status['protected_files']) > 20:
            print(f"  ... 还有 {len(status['protected_files']) - 20} 个文件")
        print("=" * 60)


if __name__ == "__main__":
    main()
