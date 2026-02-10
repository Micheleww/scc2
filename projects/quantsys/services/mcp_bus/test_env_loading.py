#!/usr/bin/env python
"""测试环境变量加载"""

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

# 模拟main.py的加载逻辑
print("=== 测试环境变量加载 ===")

# 添加项目路径
repo_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(repo_root))

# 加载.env文件（支持多个路径）
env_paths = [
    Path(__file__).parent / ".env",  # tools/mcp_bus/.env
    repo_root / ".env",  # 项目根目录/.env
]

env_loaded = False
for env_path in env_paths:
    print(f"\n检查: {env_path}")
    print(f"  存在: {env_path.exists()}")
    if env_path.exists():
        load_dotenv(env_path, override=False)
        print("  ✅ 已加载")
        env_loaded = True
        break

if not env_loaded:
    print("\n未找到.env文件，尝试从当前目录加载...")
    load_dotenv()

# 检查环境变量
print("\n=== 环境变量检查 ===")
auto_start = os.getenv("AUTO_START_FREQTRADE", "NOT SET")
print(f"AUTO_START_FREQTRADE: {auto_start}")

# 测试逻辑
auto_start_env = auto_start.lower()
auto_start_result = auto_start_env != "false"
print("\n自动启动逻辑:")
print(f"  环境变量值: '{auto_start}'")
print(f"  转换为小写: '{auto_start_env}'")
print(f"  是否启用: {auto_start_result}")
print("  (未设置或'true' = 启用, 'false' = 禁用)")

if auto_start_result:
    print("\n✅ 自动启动已启用")
else:
    print("\n❌ 自动启动已禁用")
