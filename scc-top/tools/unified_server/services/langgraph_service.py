
"""
LangGraph服务包装器

将LangGraph服务整合到统一服务器
"""

import os
import sys
import logging
from pathlib import Path
from typing import Any, Optional

try:
    from ..core.service_registry import Service, ServiceStatus
except ImportError:
    # 兼容绝对导入（当作为模块直接运行时）
    from tools.unified_server.core.service_registry import Service, ServiceStatus

logger = logging.getLogger(__name__)


class LangGraphService(Service):
    """LangGraph服务包装器"""
    
    def __init__(self, name: str, enabled: bool, repo_root: Optional[Path] = None, path: str = "/langgraph"):
        super().__init__(name, enabled)
        self.path = path
        self.repo_root = repo_root or Path(__file__).parent.parent.parent.parent
        self._app: Any = None
    
    async def initialize(self) -> None:
        """初始化LangGraph服务"""
        try:
            # 尝试从多个位置导入LangGraph应用
            possible_paths = [
                self.repo_root / "app.py",  # 根目录app.py
                self.repo_root / "langgraph_workflow.py",  # 工作流文件
                self.repo_root / "langgraph_server.py"  # 服务器文件
            ]
            
            langgraph_app = None
            
            for app_path in possible_paths:
                if app_path.exists():
                    # 动态导入文件
                    import importlib.util
                    spec = importlib.util.spec_from_file_location("langgraph_app", app_path)
                    langgraph_module = importlib.util.module_from_spec(spec)
                    sys.modules["langgraph_app"] = langgraph_module
                    spec.loader.exec_module(langgraph_module)
                    
                    # 尝试获取app属性
                    if hasattr(langgraph_module, "app"):
                        langgraph_app = langgraph_module.app
                        logger.info(f"Found LangGraph app in {app_path}")
                        break
                    elif hasattr(langgraph_module, "graph"):
                        langgraph_app = langgraph_module.graph
                        logger.info(f"Found LangGraph graph in {app_path}")
                        break
            
            # 如果找到LangGraph应用
            if langgraph_app:
                # 将LangGraph应用包装为FastAPI应用
                from fastapi import FastAPI
                from fastapi.responses import JSONResponse
                
                app = FastAPI(title="LangGraph Service", version="1.0.0")
                
                @app.post("/invoke")
                async def invoke_graph(request):
                    """调用LangGraph应用"""
                    try:
                        data = await request.json()
                        result = langgraph_app.invoke(data)
                        return JSONResponse(content=result)
                    except Exception as e:
                        logger.error(f"LangGraph invoke error: {e}", exc_info=True)
                        return JSONResponse(
                            status_code=500,
                            content={"error": str(e)}
                        )
                    
                @app.get("/health")
                async def health():
                    """健康检查"""
                    return {"status": "healthy", "service": "langgraph"}
                    
                @app.get("/docs")
                async def docs():
                    """文档端点（兼容原LangGraph服务）"""
                    return {
                        "message": "LangGraph service is available",
                        "endpoints": {
                            "invoke": "/langgraph/invoke",
                            "health": "/langgraph/health"
                        }
                    }
                    
                self._app = app
                logger.info("LangGraph service initialized")
            else:
                # 如果没有找到LangGraph应用，创建一个简单的默认服务
                from fastapi import FastAPI
                
                app = FastAPI(title="LangGraph Service", version="1.0.0")
                
                @app.post("/invoke")
                async def invoke_graph(request):
                    """调用LangGraph应用"""
                    try:
                        data = await request.json()
                        return JSONResponse(content={"result": "LangGraph service is running", "input": data})
                    except Exception as e:
                        logger.error(f"LangGraph invoke error: {e}", exc_info=True)
                        return JSONResponse(
                            status_code=500,
                            content={"error": str(e)}
                        )
                    
                @app.get("/health")
                async def health():
                    return {"status": "healthy", "service": "langgraph"}
                    
                @app.get("/docs")
                async def docs():
                    return {
                        "message": "LangGraph service is available",
                        "endpoints": {
                            "invoke": "/langgraph/invoke",
                            "health": "/langgraph/health"
                        }
                    }
                    
                self._app = app
                logger.info("LangGraph service initialized (default service)")
        except Exception as e:
            logger.error(f"Failed to initialize LangGraph service: {e}", exc_info=True)
            raise
    
    async def shutdown(self) -> None:
        """关闭LangGraph服务"""
        logger.info("LangGraph service shutting down")
    
    def get_app(self) -> Any:
        """获取LangGraph应用"""
        return self._app
