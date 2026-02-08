"""
端口分配器

自动为新服务分配不常用的端口，避免与业界常用端口冲突
"""

import logging
import socket
from typing import Dict, Optional, Set
from pathlib import Path
import json

logger = logging.getLogger(__name__)

# 业界常用端口（避免使用）
COMMON_PORTS = {
    # HTTP/HTTPS
    80, 443, 8080, 8443, 8000, 8888,
    # 开发服务器
    3000, 3001, 5000, 5001, 5173, 5174,
    # 数据库
    3306, 5432, 6379, 27017,
    # 其他常用服务
    22, 21, 25, 53, 110, 143, 993, 995,
    8001, 8002, 8003, 8004, 8005,
    9000, 9001, 9090,
}

# 不常用端口范围（推荐使用）
# 使用 18000-19999 范围，避免与常用端口冲突
PORT_RANGE_START = 18000
PORT_RANGE_END = 19999

# 已分配的端口（从配置加载）
# Keep runtime state under tools/unified_server/state/ to avoid cluttering project root.
ALLOCATED_PORTS_FILE = Path(__file__).parent.parent / "state" / "allocated_ports.json"


class PortAllocator:
    """端口分配器"""
    
    def __init__(self, start_port: int = PORT_RANGE_START, end_port: int = PORT_RANGE_END):
        """
        初始化端口分配器
        
        Args:
            start_port: 端口范围起始
            end_port: 端口范围结束
        """
        self.start_port = start_port
        self.end_port = end_port
        self.allocated_ports: Dict[str, int] = {}  # service_name -> port
        self.reserved_ports: Set[int] = set()  # 手动保留的端口
        self._load_allocated_ports()
    
    def _load_allocated_ports(self):
        """从文件加载已分配的端口"""
        if ALLOCATED_PORTS_FILE.exists():
            try:
                with open(ALLOCATED_PORTS_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.allocated_ports = data.get('allocated', {})
                    self.reserved_ports = set(data.get('reserved', []))
                    logger.info(f"Loaded {len(self.allocated_ports)} allocated ports from file")
            except Exception as e:
                logger.warning(f"Failed to load allocated ports: {e}")
    
    def _save_allocated_ports(self):
        """保存已分配的端口到文件"""
        try:
            data = {
                'allocated': self.allocated_ports,
                'reserved': list(self.reserved_ports),
            }
            with open(ALLOCATED_PORTS_FILE, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            logger.debug(f"Saved {len(self.allocated_ports)} allocated ports to file")
        except Exception as e:
            logger.error(f"Failed to save allocated ports: {e}")
    
    def is_port_available(self, port: int) -> bool:
        """
        检查端口是否可用
        
        Args:
            port: 端口号
            
        Returns:
            True if available, False otherwise
        """
        # 检查是否在范围内
        if not (self.start_port <= port <= self.end_port):
            return False
        
        # 检查是否是常用端口
        if port in COMMON_PORTS:
            return False
        
        # 检查是否已被分配
        if port in self.allocated_ports.values():
            return False
        
        # 检查是否被保留
        if port in self.reserved_ports:
            return False
        
        # 检查端口是否被占用
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(0.1)
                result = s.connect_ex(('127.0.0.1', port))
                if result == 0:
                    # 端口已被占用
                    return False
        except Exception:
            pass
        
        return True
    
    def allocate_port(self, service_name: str, preferred_port: Optional[int] = None) -> int:
        """
        为服务分配端口
        
        Args:
            service_name: 服务名称
            preferred_port: 首选端口（如果可用）
            
        Returns:
            分配的端口号
            
        Raises:
            RuntimeError: 如果无法分配端口
        """
        # 如果服务已有分配的端口，返回现有端口
        if service_name in self.allocated_ports:
            existing_port = self.allocated_ports[service_name]
            if self.is_port_available(existing_port):
                logger.info(f"Service '{service_name}' already has allocated port: {existing_port}")
                return existing_port
            else:
                # 端口不可用，重新分配
                logger.warning(f"Service '{service_name}' allocated port {existing_port} is no longer available, reallocating...")
                del self.allocated_ports[service_name]
        
        # 如果指定了首选端口，先尝试使用
        if preferred_port and self.is_port_available(preferred_port):
            self.allocated_ports[service_name] = preferred_port
            self._save_allocated_ports()
            logger.info(f"Allocated preferred port {preferred_port} to service '{service_name}'")
            return preferred_port
        
        # 从端口范围中查找可用端口
        # 使用步进策略，避免连续分配
        step = 7  # 使用质数步进，避免冲突
        start = self.start_port
        
        # 尝试从不同起始点开始，增加随机性
        import random
        offset = random.randint(0, min(100, (self.end_port - self.start_port) // step))
        start = self.start_port + (offset * step)
        
        for port in range(start, self.end_port + 1, step):
            if self.is_port_available(port):
                self.allocated_ports[service_name] = port
                self._save_allocated_ports()
                logger.info(f"Allocated port {port} to service '{service_name}'")
                return port
        
        # 如果步进策略失败，尝试顺序查找
        for port in range(self.start_port, self.end_port + 1):
            if self.is_port_available(port):
                self.allocated_ports[service_name] = port
                self._save_allocated_ports()
                logger.info(f"Allocated port {port} to service '{service_name}'")
                return port
        
        raise RuntimeError(
            f"No available port in range {self.start_port}-{self.end_port} for service '{service_name}'"
        )
    
    def release_port(self, service_name: str) -> bool:
        """
        释放服务占用的端口
        
        Args:
            service_name: 服务名称
            
        Returns:
            True if port was released, False if service had no allocated port
        """
        if service_name in self.allocated_ports:
            port = self.allocated_ports.pop(service_name)
            self._save_allocated_ports()
            logger.info(f"Released port {port} from service '{service_name}'")
            return True
        return False
    
    def get_port(self, service_name: str) -> Optional[int]:
        """
        获取服务已分配的端口
        
        Args:
            service_name: 服务名称
            
        Returns:
            端口号，如果未分配则返回None
        """
        return self.allocated_ports.get(service_name)
    
    def reserve_port(self, port: int, reason: str = ""):
        """
        手动保留端口（防止被自动分配）
        
        Args:
            port: 端口号
            reason: 保留原因
        """
        self.reserved_ports.add(port)
        self._save_allocated_ports()
        logger.info(f"Reserved port {port} (reason: {reason})")
    
    def unreserve_port(self, port: int):
        """
        取消端口保留
        
        Args:
            port: 端口号
        """
        if port in self.reserved_ports:
            self.reserved_ports.remove(port)
            self._save_allocated_ports()
            logger.info(f"Unreserved port {port}")
    
    def list_allocated_ports(self) -> Dict[str, int]:
        """
        列出所有已分配的端口
        
        Returns:
            服务名称到端口的映射
        """
        return self.allocated_ports.copy()
    
    def get_statistics(self) -> Dict:
        """
        获取端口分配统计信息
        
        Returns:
            统计信息字典
        """
        total_range = self.end_port - self.start_port + 1
        allocated_count = len(self.allocated_ports)
        reserved_count = len(self.reserved_ports)
        available_count = total_range - allocated_count - reserved_count - len(COMMON_PORTS)
        
        return {
            'port_range': f"{self.start_port}-{self.end_port}",
            'total_ports': total_range,
            'allocated': allocated_count,
            'reserved': reserved_count,
            'common_ports_excluded': len(COMMON_PORTS),
            'available': available_count,
            'utilization': f"{(allocated_count / total_range * 100):.2f}%",
        }


# 全局端口分配器实例
_port_allocator: Optional[PortAllocator] = None


def get_port_allocator() -> PortAllocator:
    """获取全局端口分配器实例"""
    global _port_allocator
    if _port_allocator is None:
        _port_allocator = PortAllocator()
    return _port_allocator


def allocate_port_for_service(service_name: str, preferred_port: Optional[int] = None) -> int:
    """
    为服务分配端口的便捷函数
    
    Args:
        service_name: 服务名称
        preferred_port: 首选端口
        
    Returns:
        分配的端口号
    """
    return get_port_allocator().allocate_port(service_name, preferred_port)
