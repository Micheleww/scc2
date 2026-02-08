"""
服务注册表模块

管理所有服务的注册、初始化和生命周期
"""

import logging
from typing import Dict, Any, Optional, Callable
from abc import ABC, abstractmethod
from enum import Enum

from .port_allocator import get_port_allocator

logger = logging.getLogger(__name__)


class ServiceStatus(Enum):
    """服务状态"""
    UNINITIALIZED = "uninitialized"
    INITIALIZING = "initializing"
    READY = "ready"
    ERROR = "error"
    SHUTTING_DOWN = "shutting_down"
    SHUTDOWN = "shutdown"


class Service(ABC):
    """服务基类"""
    
    def __init__(self, name: str, enabled: bool = True, auto_allocate_port: bool = False, preferred_port: Optional[int] = None):
        """
        初始化服务
        
        Args:
            name: 服务名称
            enabled: 是否启用
            auto_allocate_port: 是否自动分配端口
            preferred_port: 首选端口（如果自动分配）
        """
        self.name = name
        self.enabled = enabled
        self.status = ServiceStatus.UNINITIALIZED
        self.error: Optional[Exception] = None
        self.allocated_port: Optional[int] = None
        
        # 如果需要自动分配端口
        if auto_allocate_port:
            try:
                allocator = get_port_allocator()
                self.allocated_port = allocator.allocate_port(name, preferred_port)
                logger.info(f"Service '{name}' allocated port: {self.allocated_port}")
            except Exception as e:
                logger.warning(f"Failed to allocate port for service '{name}': {e}")
                # 不抛出异常，允许服务在没有端口的情况下运行（如果不需要端口）
    
    @abstractmethod
    async def initialize(self) -> None:
        """初始化服务"""
        pass
    
    @abstractmethod
    async def shutdown(self) -> None:
        """关闭服务"""
        pass
    
    @abstractmethod
    def get_app(self) -> Any:
        """获取服务应用实例"""
        pass
    
    def is_ready(self) -> bool:
        """检查服务是否就绪"""
        return self.status == ServiceStatus.READY
    
    def is_healthy(self) -> bool:
        """检查服务是否健康"""
        return self.status == ServiceStatus.READY and self.error is None


class ServiceRegistry:
    """服务注册表"""
    
    def __init__(self):
        self.services: Dict[str, Service] = {}
        self.service_factories: Dict[str, Callable] = {}
    
    def register(self, name: str, service: Service):
        """注册服务实例"""
        self.services[name] = service
        logger.info(f"Service registered: {name}")
    
    def register_factory(self, name: str, factory: Callable):
        """注册服务工厂"""
        self.service_factories[name] = factory
        logger.info(f"Service factory registered: {name}")
    
    def get(self, name: str) -> Optional[Service]:
        """获取服务"""
        return self.services.get(name)
    
    def get_all(self) -> Dict[str, Service]:
        """获取所有服务"""
        return self.services.copy()
    
    async def initialize_all(self):
        """初始化所有服务"""
        logger.info(f"Initializing all services: {list(self.services.keys())}")
        for name, service in self.services.items():
            if not service.enabled:
                logger.info(f"Service {name} is disabled, skipping initialization")
                continue
            
            try:
                logger.info(f"Initializing service {name}")
                service.status = ServiceStatus.INITIALIZING
                logger.info(f"Service {name} status set to INITIALIZING")
                await service.initialize()
                logger.info(f"Service {name} initialization completed")
                service.status = ServiceStatus.READY
                logger.info(f"Service {name} status set to READY")
                logger.info(f"Service {name} initialized successfully")
            except Exception as e:
                logger.error(f"Service {name} initialization failed: {e}", exc_info=True)
                service.status = ServiceStatus.ERROR
                service.error = e
                logger.error(f"Service {name} status set to ERROR: {e}")
                # 不抛出异常，继续初始化其他服务
                logger.info(f"Continuing with other services despite {name} initialization failure")
    
    async def shutdown_all(self):
        """关闭所有服务"""
        # 逆序关闭
        for name, service in reversed(list(self.services.items())):
            if not service.enabled:
                continue
            
            try:
                service.status = ServiceStatus.SHUTTING_DOWN
                await service.shutdown()
                service.status = ServiceStatus.SHUTDOWN
                
                # 释放分配的端口
                if service.allocated_port:
                    allocator = get_port_allocator()
                    allocator.release_port(name)
                    logger.info(f"Released port {service.allocated_port} from service {name}")
                
                logger.info(f"Service {name} shut down successfully")
            except Exception as e:
                logger.error(f"Service {name} shutdown failed: {e}", exc_info=True)
    
    def get_health_status(self) -> Dict[str, Any]:
        """获取所有服务的健康状态"""
        return {
            name: {
                "status": service.status.value,
                "enabled": service.enabled,
                "ready": service.is_ready(),
                "healthy": service.is_healthy(),
                "error": str(service.error) if service.error else None,
                "allocated_port": service.allocated_port
            }
            for name, service in self.services.items()
        }
    
    def get_port_allocations(self) -> Dict[str, int]:
        """获取所有服务的端口分配情况"""
        return {
            name: service.allocated_port
            for name, service in self.services.items()
            if service.allocated_port is not None
        }


# 全局服务注册表实例
_registry: ServiceRegistry = None


def get_service_registry() -> ServiceRegistry:
    """获取服务注册表实例"""
    global _registry
    if _registry is None:
        _registry = ServiceRegistry()
    return _registry
