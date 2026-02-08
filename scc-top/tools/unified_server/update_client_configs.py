#!/usr/bin/env python3
"""
更新客户端配置文件脚本

自动更新所有客户端配置文件，适配统一服务器
"""

import os
import sys
import json
from pathlib import Path

# 添加路径
current_file = Path(__file__).resolve()
unified_server_dir = current_file.parent
repo_root = unified_server_dir.parent.parent

def update_trae_config():
    """更新TRAE MCP配置"""
    trae_config_path = repo_root / ".trae" / "mcp.json"
    
    if not trae_config_path.exists():
        print(f"⚠️ TRAE配置文件不存在: {trae_config_path}")
        return False
    
    try:
        with open(trae_config_path, "r", encoding="utf-8") as f:
            config = json.load(f)
        
        # 更新MCP服务器URL
        if "mcpServers" in config:
            for server_name, server_config in config["mcpServers"].items():
                if "transport" in server_config and "url" in server_config["transport"]:
                    old_url = server_config["transport"]["url"]
                    # 更新为统一服务器URL
                    if "8001" in old_url or "8000" in old_url or "18788" in old_url:
                        new_url = "http://localhost:18788/mcp"
                        server_config["transport"]["url"] = new_url
                        print(f"✅ 更新 {server_name}: {old_url} -> {new_url}")
        
        # 保存配置
        with open(trae_config_path, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
        
        print(f"✅ TRAE配置已更新: {trae_config_path}")
        return True
    except Exception as e:
        print(f"❌ 更新TRAE配置失败: {e}")
        return False

def update_test_scripts():
    """更新测试脚本中的URL"""
    test_scripts = [
        repo_root / "tools" / "exchange_server" / "sse_selftest.py",
        repo_root / "tools" / "mcp_verify.py",
        repo_root / "tools" / "mcp_smoke_test.py",
    ]
    
    updated_count = 0
    for script_path in test_scripts:
        if not script_path.exists():
            continue
        
        try:
            with open(script_path, "r", encoding="utf-8") as f:
                content = f.read()
            
            # 替换旧端口URL
            replacements = [
                ("http://localhost:18788/", "http://localhost:18788/exchange"),
                ("http://localhost:18788/mcp", "http://localhost:18788/mcp"),
                ("http://localhost:18788/api", "http://localhost:18788/api"),
                ("http://localhost:18788/", "http://localhost:18788"),
                ("http://127.0.0.1:18788/", "http://127.0.0.1:18788/exchange"),
                ("http://127.0.0.1:18788/mcp", "http://127.0.0.1:18788/mcp"),
                ("http://127.0.0.1:18788/api", "http://127.0.0.1:18788/api"),
                ("http://127.0.0.1:18788/", "http://127.0.0.1:18788"),
            ]
            
            modified = False
            for old_url, new_url in replacements:
                if old_url in content:
                    content = content.replace(old_url, new_url)
                    modified = True
            
            if modified:
                with open(script_path, "w", encoding="utf-8") as f:
                    f.write(content)
                print(f"✅ 更新测试脚本: {script_path}")
                updated_count += 1
        except Exception as e:
            print(f"⚠️ 更新测试脚本失败 {script_path}: {e}")
    
    return updated_count

def main():
    """主函数"""
    print("=== 更新客户端配置 ===")
    print(f"项目根目录: {repo_root}")
    print()
    
    results = []
    
    # 更新TRAE配置
    print("1. 更新TRAE MCP配置...")
    results.append(("TRAE配置", update_trae_config()))
    print()
    
    # 更新测试脚本
    print("2. 更新测试脚本...")
    count = update_test_scripts()
    results.append(("测试脚本", count > 0))
    print(f"   更新了 {count} 个文件")
    print()
    
    # 汇总
    print("=== 更新结果 ===")
    for name, success in results:
        status = "✅ 成功" if success else "❌ 失败"
        print(f"{name}: {status}")
    
    print()
    print("⚠️ 注意: 请手动检查以下配置文件:")
    print("  - .trae/mcp.json")
    print("  - 其他客户端配置文件")
    print("  - 环境变量中的URL配置")

if __name__ == "__main__":
    main()
