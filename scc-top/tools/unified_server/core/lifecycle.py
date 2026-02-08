"""
生命周期管理模块

使用FastAPI的lifespan context manager管理应用生命周期
"""

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator, Dict, Any, Callable
from collections import defaultdict

logger = logging.getLogger(__name__)


class LifecycleManager:
    """生命周期管理器"""
    
    def __init__(self):
        self.startup_tasks: list[Callable] = []
        self.shutdown_tasks: list[Callable] = []
        self.background_tasks: list[asyncio.Task] = []
        self.resources: Dict[str, Any] = {}
    
    def register_startup(self, func: Callable):
        """注册启动任务"""
        self.startup_tasks.append(func)
        return func
    
    def register_shutdown(self, func: Callable):
        """注册关闭任务"""
        self.shutdown_tasks.append(func)
        return func
    
    def register_background_task(self, task: asyncio.Task):
        """注册后台任务"""
        self.background_tasks.append(task)
    
    def register_resource(self, name: str, resource: Any):
        """注册资源"""
        self.resources[name] = resource
    
    def get_resource(self, name: str) -> Any:
        """获取资源"""
        return self.resources.get(name)
    
    async def startup(self):
        """执行所有启动任务"""
        logger.info("Starting application lifecycle...")
        
        for task in self.startup_tasks:
            try:
                if asyncio.iscoroutinefunction(task):
                    await task()
                else:
                    task()
                logger.info(f"Startup task completed: {task.__name__}")
            except Exception as e:
                logger.error(f"Startup task failed: {task.__name__}, error: {e}", exc_info=True)
                raise
        
        logger.info("Application startup completed")
    
    async def shutdown(self):
        """执行所有关闭任务"""
        logger.info("Shutting down application lifecycle...")
        
        # 取消所有后台任务
        for task in self.background_tasks:
            if not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        
        # 执行关闭任务（逆序）
        for task in reversed(self.shutdown_tasks):
            try:
                if asyncio.iscoroutinefunction(task):
                    await task()
                else:
                    task()
                logger.info(f"Shutdown task completed: {task.__name__}")
            except Exception as e:
                logger.error(f"Shutdown task failed: {task.__name__}, error: {e}", exc_info=True)
        
        # 清理资源
        self.resources.clear()
        
        logger.info("Application shutdown completed")
    
    @asynccontextmanager
    async def lifespan(self, app) -> AsyncGenerator[None, None]:
        """生命周期context manager"""
        await self.startup()
        yield
        await self.shutdown()


# 全局生命周期管理器实例
_lifecycle_manager: LifecycleManager = None


def get_lifecycle_manager() -> LifecycleManager:
    """获取生命周期管理器实例"""
    global _lifecycle_manager
    if _lifecycle_manager is None:
        _lifecycle_manager = LifecycleManager()
    return _lifecycle_manager
