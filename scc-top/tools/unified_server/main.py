#!/usr/bin/env python3
"""
统一服务器 - 企业级架构实现

使用业界最佳实践：
- 应用工厂模式
- 生命周期管理
- 服务注册表
- 中间件系统
- 健康检查
- 优雅关闭
"""

import os
import sys
from pathlib import Path

# Ensure repo root is importable so `tools.*` namespace imports are consistent.
current_file = Path(__file__).resolve()
repo_root = current_file.parents[2]
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

# Import via package namespace to avoid duplicate module loads like `core.*`.
from tools.unified_server.core.app_factory import create_app

# 创建应用实例（使用工厂模式）
app = create_app()

# NOTE:
# `/executor/*` is provided by `tools.unified_server.services.ExecutorService` and mounted by the service registry.
# Keep `main.py` minimal to avoid conflicting routes.


def main():
    """启动统一服务器"""
    import socket
    import tempfile
    import atexit
    import signal
    import uvicorn
    from tools.unified_server.core.config import get_config
    
    # 获取配置
    config = get_config()
    
    # 检查端口是否被占用
    def is_port_listening(hostname: str, port_num: int) -> bool:
        # In containers we typically bind 0.0.0.0. You cannot connect to 0.0.0.0,
        # so use a loopback probe for the preflight check.
        probe_host = hostname
        if probe_host in {"0.0.0.0", "::"}:
            probe_host = "127.0.0.1"
        try:
            with socket.create_connection((probe_host, port_num), timeout=0.5):
                return True
        except OSError:
            return False
    
    # 检查统一服务器端口
    if is_port_listening(config.host, config.port):
        print(f"[unified_server] Port {config.host}:{config.port} is already in use", file=sys.stderr)
        sys.exit(1)
    
    # 外部访问统一走单一端口，不再检查/提示其它端口。
    
    # 创建锁文件
    lock_path = os.path.join(tempfile.gettempdir(), "quantsys-unified-server.lock")
    
    def cleanup_lock():
        try:
            if os.path.exists(lock_path):
                with open(lock_path, "r") as f:
                    if f.read().strip() == str(os.getpid()):
                        os.remove(lock_path)
        except OSError:
            pass
    
    try:
        with open(lock_path, "w") as f:
            f.write(str(os.getpid()))
    except OSError:
        pass
    
    atexit.register(cleanup_lock)
    
    # 注册信号处理器（优雅关闭）
    def signal_handler(signum, frame):
        print(f"\n[unified_server] Received signal {signum}, shutting down gracefully...")
        sys.exit(0)
    
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)
    
    print(f"=== {config.app_name} ===")
    print(f"Version: {config.app_version}")
    print(f"Server: http://{config.host}:{config.port}")
    print(f"Endpoints:")
    print(f"  - Health: http://{config.host}:{config.port}/health")
    print(f"  - Ready: http://{config.host}:{config.port}/health/ready")
    print(f"  - Live: http://{config.host}:{config.port}/health/live")
    print(f"  - MCP Bus: http://{config.host}:{config.port}/mcp")
    print(f"  - A2A Hub: http://{config.host}:{config.port}/api")
    print(f"  - Exchange: http://{config.host}:{config.port}/exchange")
    print(f"  - LangGraph: http://{config.host}:{config.port}/langgraph")
    print(f"  - OpenClaw (Clawdbot): http://{config.host}:{config.port}/clawdbot")
    print(f"  - OpenCode: http://{config.host}:{config.port}/opencode")
    print(f"  - SCC Console: http://{config.host}:{config.port}/scc")
    print(f"  - Executor: http://{config.host}:{config.port}/executor")
    print(f"    - Codex: http://{config.host}:{config.port}/executor/codex")
    print(f"================================")
    
    # 启动服务器
    uvicorn.run(
        app,
        host=config.host,
        port=config.port,
        log_level=config.log_level,
        access_log=True,
        reload=config.reload,
        workers=config.workers if not config.reload else 1,
    )


if __name__ == "__main__":
    main()
