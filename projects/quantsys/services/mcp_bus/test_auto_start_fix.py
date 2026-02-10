#!/usr/bin/env python
"""测试Freqtrade自动启动修复"""

import os
import sys
from pathlib import Path

# 添加项目路径
repo_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(repo_root / "tools" / "mcp_bus" / "server"))


def test_env_loading():
    """测试环境变量加载"""
    print("=== 测试环境变量加载 ===")

    # 测试1: 检查.env文件
    env_file = Path(__file__).parent / ".env"
    print(f"1. .env文件路径: {env_file}")
    print(f"   存在: {env_file.exists()}")

    if env_file.exists():
        content = env_file.read_text(encoding="utf-8")
        print(f"   内容:\n{content}")

    # 测试2: 加载.env文件
    from dotenv import load_dotenv

    load_dotenv(env_file)

    auto_start = os.getenv("AUTO_START_FREQTRADE", "NOT SET")
    print(f"2. AUTO_START_FREQTRADE: {auto_start}")

    # 测试3: 测试逻辑
    auto_start_env = auto_start.lower()
    auto_start_result = auto_start_env != "false"
    print(f"3. 自动启动逻辑结果: {auto_start_result}")
    print("   (未设置或'true' = 启用, 'false' = 禁用)")

    return auto_start_result


def test_startup_logic():
    """测试启动逻辑"""
    print("\n=== 测试启动逻辑 ===")

    test_cases = [
        ("", True, "未设置 -> 默认启用"),
        ("true", True, "true -> 启用"),
        ("TRUE", True, "TRUE -> 启用"),
        ("false", False, "false -> 禁用"),
        ("FALSE", False, "FALSE -> 禁用"),
        ("not_set", True, "其他值 -> 启用"),
    ]

    for env_value, expected, description in test_cases:
        result = env_value.lower() != "false"
        status = "✓" if result == expected else "✗"
        print(f"{status} {description}: {env_value} -> {result} (期望: {expected})")


if __name__ == "__main__":
    print("=" * 60)
    print("Freqtrade自动启动修复测试")
    print("=" * 60)
    print()

    test_env_loading()
    test_startup_logic()

    print("\n" + "=" * 60)
    print("测试完成")
    print("=" * 60)
    print("\n修复说明:")
    print("1. 默认启用自动启动（除非明确设置为false）")
    print("2. 创建了.env文件设置AUTO_START_FREQTRADE=true")
    print("3. 修改了启动逻辑，默认启用")
    print("\n重启服务器后，Freqtrade应该会自动启动！")
