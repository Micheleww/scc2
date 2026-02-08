#!/usr/bin/env python3
"""
启动统一服务器脚本

这个脚本会启动整合了所有服务的统一服务器
"""

import os
import sys
from pathlib import Path

# Ensure repo root is importable so `tools.*` namespace imports are consistent.
current_file = Path(__file__).resolve()
repo_root = current_file.parents[2]
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

# 设置环境变量
os.environ.setdefault("UNIFIED_SERVER_HOST", "127.0.0.1")
os.environ.setdefault("UNIFIED_SERVER_PORT", "18788")
os.environ.setdefault("UNIFIED_SERVER_MODE", "1")

# 导入并运行主应用（package namespace）
from tools.unified_server.main import main

if __name__ == "__main__":
    main()
