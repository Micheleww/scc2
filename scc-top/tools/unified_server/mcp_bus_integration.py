
"""
MCP总线服务集成模块

将MCP总线服务集成到统一服务器中
"""

import os
import sys
from pathlib import Path
from fastapi import FastAPI

# 添加MCP总线路径
current_file = os.path.abspath(__file__)
unified_server_dir = os.path.dirname(current_file)
tools_dir = os.path.dirname(unified_server_dir)
repo_root = os.path.dirname(tools_dir)
mcp_bus_dir = os.path.join(tools_dir, "mcp_bus")
mcp_server_dir = os.path.join(mcp_bus_dir, "server")

# 添加路径
if repo_root not in sys.path:
    sys.path.insert(0, repo_root)
if os.path.join(repo_root, "src") not in sys.path:
    sys.path.insert(0, os.path.join(repo_root, "src"))
if mcp_server_dir not in sys.path:
    sys.path.insert(0, mcp_server_dir)

# 设置环境变量（如果需要）
os.environ.setdefault("REPO_ROOT", repo_root)

# 导入MCP总线的app
# 注意：需要直接导入main模块，因为app是在模块级别创建的
import importlib.util
spec = importlib.util.spec_from_file_location(
    "mcp_main",
    os.path.join(mcp_server_dir, "main.py")
)
mcp_main = importlib.util.module_from_spec(spec)
sys.modules["mcp_main"] = mcp_main
spec.loader.exec_module(mcp_main)
mcp_app = mcp_main.app


def create_mcp_bus_app() -> FastAPI:
    """
    创建MCP总线应用实例
    
    返回配置好的FastAPI应用，可以直接挂载到主应用
    """
    # MCP总线的app已经在导入时创建，直接返回
    return mcp_app
