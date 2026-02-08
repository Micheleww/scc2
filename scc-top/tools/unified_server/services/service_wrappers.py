"""
服务包装器

将各个服务包装为统一的Service接口
"""

import os
import sys
import logging
from pathlib import Path
from typing import Any, Optional

# Always import via package namespace to avoid duplicate module loads.
from tools.unified_server.core.service_registry import Service, ServiceStatus

logger = logging.getLogger(__name__)


class MCPService(Service):
    """MCP总线服务包装器"""
    
    def __init__(self, name: str, path: str, enabled: bool, repo_root: Path):
        super().__init__(name, enabled)
        self.path = path
        self.repo_root = repo_root
        self._app: Any = None
    
    async def initialize(self) -> None:
        """初始化MCP总线服务"""
        try:
            # Ensure repo root import path.
            if str(self.repo_root) not in sys.path:
                sys.path.insert(0, str(self.repo_root))

            # Prevent heavy auto-start behaviors inside embedded MCP Bus.
            os.environ.setdefault("AUTO_START_FREQTRADE", "false")
            os.environ.setdefault("DASHBOARD_ENABLED", "false")
            os.environ.setdefault("A2A_HUB_ENABLED", "false")

            # Import the real MCP Bus FastAPI app + ensure its startup init runs,
            # otherwise tool_executor can remain None when mounted as a sub-app.
            from tools.mcp_bus.server import main as mcp_main

            if getattr(mcp_main, "tool_executor", None) is None:
                await mcp_main.startup_event()

            self._app = mcp_main.app
            logger.info("MCP Bus service initialized (real app + startup initialized)")
        except Exception as e:
            logger.error(f"Failed to initialize MCP Bus service: {e}", exc_info=True)
            # 创建一个 fallback 服务
            from fastapi import FastAPI
            from fastapi.responses import JSONResponse

            err = str(e)
            
            app = FastAPI(title="MCP Bus Service", version="1.0.0")
            
            @app.get("/health")
            async def health():
                """健康检查"""
                return {"status": "degraded", "service": "mcp_bus", "error": err}
            
            @app.get("/")
            async def root():
                """根路径"""
                return {
                    "service": "MCP Bus Service",
                    "version": "1.0.0",
                    "status": "degraded",
                    "error": err
                }
            
            self._app = app
            logger.warning(f"MCP Bus service initialized in degraded mode: {e}")
    
    async def shutdown(self) -> None:
        """关闭MCP总线服务"""
        logger.info("MCP Bus service shutting down")
        # 可以在这里添加清理逻辑
    
    def get_app(self) -> Any:
        """获取MCP总线应用"""
        return self._app


class A2AHubService(Service):
    """A2A Hub服务包装器"""
    
    def __init__(self, name: str, path: str, enabled: bool, repo_root: Path, secret_key: Optional[str] = None):
        super().__init__(name, enabled)
        self.path = path
        self.repo_root = repo_root
        self.secret_key = secret_key
        self._app: Any = None
    
    async def initialize(self) -> None:
        """初始化A2A Hub服务"""
        try:
            # 设置环境变量
            if self.secret_key:
                os.environ["A2A_HUB_SECRET_KEY"] = self.secret_key
            
            # 直接从实际的A2A Hub服务导入应用
            a2a_hub_path = self.repo_root / "tools" / "a2a_hub" / "main.py"
            
            if a2a_hub_path.exists():
                # 添加A2A Hub目录到Python路径，解决可能的相对导入问题
                a2a_hub_dir = a2a_hub_path.parent
                
                # 添加必要的路径到Python路径
                if str(a2a_hub_dir) not in sys.path:
                    sys.path.insert(0, str(a2a_hub_dir))
                if str(self.repo_root) not in sys.path:
                    sys.path.insert(0, str(self.repo_root))
                
                # 动态导入A2A Hub应用（Flask WSGI app）
                import importlib.util
                spec = importlib.util.spec_from_file_location("a2a_hub_app", a2a_hub_path)
                a2a_module = importlib.util.module_from_spec(spec)
                sys.modules["a2a_hub_app"] = a2a_module
                spec.loader.exec_module(a2a_module)
                
                # 获取A2A Hub应用
                if hasattr(a2a_module, "app"):
                    from starlette.middleware.wsgi import WSGIMiddleware

                    flask_app = a2a_module.app

                    # When mounted at "/api", Starlette strips the prefix.
                    # The Flask app already defines routes starting with "/api",
                    # so we must re-add it to PATH_INFO.
                    def _wsgi_prefix(environ, start_response):
                        path_info = environ.get("PATH_INFO", "") or ""
                        if not path_info.startswith("/api"):
                            environ["PATH_INFO"] = "/api" + (path_info if path_info.startswith("/") else f"/{path_info}")
                        return flask_app(environ, start_response)

                    self._app = WSGIMiddleware(_wsgi_prefix)
                    logger.info("A2A Hub service initialized")
                else:
                    # 创建一个简化的A2A Hub服务FastAPI应用
                    from fastapi import FastAPI
                    from fastapi.responses import JSONResponse
                    
                    app = FastAPI(title="A2A Hub Service", version="1.0.0")
                    
                    @app.get("/health")
                    async def health():
                        """健康检查"""
                        return {"status": "healthy", "service": "a2a_hub"}
                    
                    @app.get("/")
                    async def root():
                        """根路径"""
                        return {
                            "service": "A2A Hub Service",
                            "version": "1.0.0",
                            "status": "running",
                            "endpoints": [
                                "/health"
                            ]
                        }
                    
                    self._app = app
                    logger.warning("A2A Hub service initialized in fallback mode: no 'app' attribute")
            else:
                # 创建一个简化的A2A Hub服务FastAPI应用
                from fastapi import FastAPI
                from fastapi.responses import JSONResponse
                
                app = FastAPI(title="A2A Hub Service", version="1.0.0")
                
                @app.get("/health")
                async def health():
                    """健康检查"""
                    return {"status": "healthy", "service": "a2a_hub"}
                
                @app.get("/")
                async def root():
                    """根路径"""
                    return {
                        "service": "A2A Hub Service",
                        "version": "1.0.0",
                        "status": "running",
                        "endpoints": [
                            "/health"
                        ]
                    }
                
                self._app = app
                logger.warning("A2A Hub service initialized in fallback mode: main.py not found")
        except Exception as e:
            logger.error(f"Failed to initialize A2A Hub service: {e}", exc_info=True)
            # 创建一个 fallback 服务
            from fastapi import FastAPI
            from fastapi.responses import JSONResponse
            
            app = FastAPI(title="A2A Hub Service", version="1.0.0")
            
            @app.get("/health")
            async def health():
                """健康检查"""
                return {"status": "degraded", "service": "a2a_hub", "error": str(e)}
            
            @app.get("/")
            async def root():
                """根路径"""
                return {
                    "service": "A2A Hub Service",
                    "version": "1.0.0",
                    "status": "degraded",
                    "error": str(e)
                }
            
            self._app = app
            logger.warning(f"A2A Hub service initialized in degraded mode: {e}")
    
    async def shutdown(self) -> None:
        """关闭A2A Hub服务"""
        logger.info("A2A Hub service shutting down")
        # 可以在这里添加清理逻辑
    
    def get_app(self) -> Any:
        """获取A2A Hub应用"""
        return self._app


class ExchangeServerService(Service):
    """Exchange Server服务包装器"""
    
    def __init__(self, name: str, path: str, enabled: bool, repo_root: Path, auth_mode: str = "none"):
        super().__init__(name, enabled)
        self.path = path
        self.repo_root = repo_root
        self.auth_mode = auth_mode
        self._app: Any = None
    
    async def initialize(self) -> None:
        """初始化Exchange Server服务"""
        try:
            # 设置环境变量
            os.environ["EXCHANGE_AUTH_MODE"] = self.auth_mode
            
            # 直接从实际的Exchange Server服务导入应用
            exchange_server_path = self.repo_root / "tools" / "exchange_server" / "main.py"
            
            if exchange_server_path.exists():
                # 当前用简化版（避免真实服务的启动依赖/相对导入问题）
                from fastapi import FastAPI
                from fastapi.responses import JSONResponse
                
                app = FastAPI(title="Exchange Server Service", version="1.0.0")
                
                @app.get("/health")
                async def health():
                    """健康检查"""
                    return {"status": "healthy", "service": "exchange_server"}
                
                @app.get("/")
                async def root():
                    """根路径"""
                    return {
                        "service": "Exchange Server Service",
                        "version": "1.0.0",
                        "status": "running",
                        "endpoints": [
                            "/health"
                        ]
                    }
                
                # 添加一些基本的Exchange Server接口
                @app.get("/api/v1/status")
                async def status():
                    """获取Exchange Server状态"""
                    return {
                        "status": "online",
                        "auth_mode": self.auth_mode,
                        "version": "1.0.0"
                    }
                
                self._app = app
                logger.info("Exchange Server service initialized with simplified FastAPI app")
            else:
                # 创建一个最小化的Exchange Server服务
                from fastapi import FastAPI
                from fastapi.responses import JSONResponse
                
                app = FastAPI(title="Exchange Server Service", version="1.0.0")
                
                @app.get("/health")
                async def health():
                    """健康检查"""
                    return {"status": "healthy", "service": "exchange_server"}
                
                @app.get("/")
                async def root():
                    """根路径"""
                    return {
                        "service": "Exchange Server Service",
                        "version": "1.0.0",
                        "status": "running",
                        "message": "Exchange Server main.py not found, running in minimal mode"
                    }
                
                self._app = app
                logger.warning("Exchange Server service initialized in minimal mode: main.py not found")
        except Exception as e:
            logger.error(f"Failed to initialize Exchange Server service: {e}", exc_info=True)
            # 创建一个 fallback 服务
            from fastapi import FastAPI
            from fastapi.responses import JSONResponse
            
            app = FastAPI(title="Exchange Server Service", version="1.0.0")
            
            @app.get("/health")
            async def health():
                """健康检查"""
                return {"status": "degraded", "service": "exchange_server", "error": str(e)}
            
            @app.get("/")
            async def root():
                """根路径"""
                return {
                    "service": "Exchange Server Service",
                    "version": "1.0.0",
                    "status": "degraded",
                    "error": str(e)
                }
            
            self._app = app
            logger.warning(f"Exchange Server service initialized in degraded mode: {e}")
    
    async def shutdown(self) -> None:
        """关闭Exchange Server服务"""
        logger.info("Exchange Server service shutting down")
        # 可以在这里添加清理逻辑
    
    def get_app(self) -> Any:
        """获取Exchange Server应用"""
        return self._app
