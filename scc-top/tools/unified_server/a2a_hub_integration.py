
"""
A2A Hub服务集成模块

将Flask A2A Hub服务转换为FastAPI并集成到统一服务器中
"""

import os
import sys
from pathlib import Path
from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
import asyncio
from concurrent.futures import ThreadPoolExecutor
import threading

# 添加A2A Hub路径
current_file = os.path.abspath(__file__)
unified_server_dir = os.path.dirname(current_file)
tools_dir = os.path.dirname(unified_server_dir)
a2a_hub_dir = os.path.join(tools_dir, "a2a_hub")

# 添加路径
if a2a_hub_dir not in sys.path:
    sys.path.insert(0, a2a_hub_dir)

# 导入Flask应用
# 使用importlib直接加载模块
import importlib.util
spec = importlib.util.spec_from_file_location(
    "a2a_main",
    os.path.join(a2a_hub_dir, "main.py")
)
a2a_main = importlib.util.module_from_spec(spec)
sys.modules["a2a_main"] = a2a_main
spec.loader.exec_module(a2a_main)

flask_app = a2a_main.app
init_db = a2a_main.init_db
check_required_secrets = a2a_main.check_required_secrets
check_expired_leases = a2a_main.check_expired_leases
check_priority_aging = a2a_main.check_priority_aging

# 创建线程池用于运行Flask应用
executor = ThreadPoolExecutor(max_workers=10)


def run_flask_app(environ, start_response):
    """在WSGI环境中运行Flask应用"""
    return flask_app(environ, start_response)


def create_a2a_hub_app() -> FastAPI:
    """
    创建A2A Hub FastAPI应用
    
    将Flask应用包装为FastAPI应用
    """
    # 初始化数据库和检查密钥
    try:
        check_required_secrets()
        init_db()
        
        # 启动后台线程
        lease_checker_thread = threading.Thread(target=check_expired_leases, daemon=True)
        lease_checker_thread.start()
        
        priority_aging_thread = threading.Thread(target=check_priority_aging, daemon=True)
        priority_aging_thread.start()
    except Exception as e:
        print(f"[a2a_hub_integration] Warning: Initialization error: {e}")
    
    # 创建FastAPI应用
    app = FastAPI(title="A2A Hub", version="1.0.0")
    
    # 将Flask路由转换为FastAPI路由
    # 使用ASGI适配器
    from fastapi.middleware.wsgi import WSGIMiddleware
    
    app.mount("/", WSGIMiddleware(flask_app))
    
    return app
