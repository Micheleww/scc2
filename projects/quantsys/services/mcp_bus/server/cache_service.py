"""
缓存服务模块 - 提供Redis和内存缓存支持
支持API响应缓存、静态资源缓存等
"""

import hashlib
import json
import logging
import os
import time
from collections.abc import Callable
from functools import wraps
from typing import Any

logger = logging.getLogger(__name__)

# 尝试导入Redis，如果不可用则使用内存缓存
try:
    import redis

    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False
    logger.warning("Redis not available, using in-memory cache")


class CacheService:
    """缓存服务 - 支持Redis和内存缓存"""

    def __init__(self):
        self.redis_client: Any | None = None
        self.memory_cache: dict[str, dict[str, Any]] = {}
        self.use_redis = False

        # 尝试连接Redis
        redis_host = os.getenv("REDIS_HOST", "localhost")
        redis_port = int(os.getenv("REDIS_PORT", "6379"))
        redis_db = int(os.getenv("REDIS_DB", "0"))
        redis_password = os.getenv("REDIS_PASSWORD")

        if REDIS_AVAILABLE:
            try:
                self.redis_client = redis.Redis(
                    host=redis_host,
                    port=redis_port,
                    db=redis_db,
                    password=redis_password,
                    decode_responses=True,
                    socket_connect_timeout=2,
                    socket_timeout=2,
                )
                # 测试连接
                self.redis_client.ping()
                self.use_redis = True
                logger.info(f"Redis cache connected: {redis_host}:{redis_port}/{redis_db}")
            except Exception as e:
                logger.warning(f"Redis connection failed, using memory cache: {e}")
                self.redis_client = None
                self.use_redis = False
        else:
            logger.info("Using in-memory cache (Redis not installed)")

    def _generate_key(self, prefix: str, *args, **kwargs) -> str:
        """生成缓存键"""
        key_parts = [prefix]
        if args:
            key_parts.extend(str(arg) for arg in args)
        if kwargs:
            sorted_kwargs = sorted(kwargs.items())
            key_parts.extend(f"{k}={v}" for k, v in sorted_kwargs)

        key_string = ":".join(key_parts)
        # 使用MD5生成固定长度的键（Redis键名限制）
        return f"cache:{prefix}:{hashlib.md5(key_string.encode()).hexdigest()}"

    def get(self, key: str) -> Any | None:
        """获取缓存值"""
        try:
            if self.use_redis and self.redis_client:
                value = self.redis_client.get(key)
                if value:
                    return json.loads(value)
            else:
                # 内存缓存
                if key in self.memory_cache:
                    entry = self.memory_cache[key]
                    # 检查是否过期
                    if time.time() < entry["expires_at"]:
                        return entry["value"]
                    else:
                        # 过期，删除
                        del self.memory_cache[key]
        except Exception as e:
            logger.error(f"Cache get error for key {key}: {e}")
        return None

    def set(self, key: str, value: Any, ttl: int = 300) -> bool:
        """设置缓存值（TTL单位：秒）"""
        try:
            if self.use_redis and self.redis_client:
                self.redis_client.setex(key, ttl, json.dumps(value, default=str))
                return True
            else:
                # 内存缓存
                self.memory_cache[key] = {"value": value, "expires_at": time.time() + ttl}
                # 限制内存缓存大小（防止内存溢出）
                if len(self.memory_cache) > 10000:
                    # 删除最旧的10%
                    sorted_items = sorted(
                        self.memory_cache.items(), key=lambda x: x[1]["expires_at"]
                    )
                    for old_key, _ in sorted_items[:1000]:
                        del self.memory_cache[old_key]
                return True
        except Exception as e:
            logger.error(f"Cache set error for key {key}: {e}")
            return False

    def delete(self, key: str) -> bool:
        """删除缓存"""
        try:
            if self.use_redis and self.redis_client:
                self.redis_client.delete(key)
            else:
                if key in self.memory_cache:
                    del self.memory_cache[key]
            return True
        except Exception as e:
            logger.error(f"Cache delete error for key {key}: {e}")
            return False

    def clear_pattern(self, pattern: str) -> int:
        """清除匹配模式的所有缓存（仅Redis支持）"""
        if self.use_redis and self.redis_client:
            try:
                keys = self.redis_client.keys(pattern)
                if keys:
                    return self.redis_client.delete(*keys)
            except Exception as e:
                logger.error(f"Cache clear_pattern error for {pattern}: {e}")
        return 0

    def get_stats(self) -> dict[str, Any]:
        """获取缓存统计信息"""
        stats = {
            "type": "redis" if self.use_redis else "memory",
            "connected": self.use_redis and self.redis_client is not None,
        }

        if self.use_redis and self.redis_client:
            try:
                info = self.redis_client.info("stats")
                stats.update(
                    {
                        "keys": self.redis_client.dbsize(),
                        "hits": info.get("keyspace_hits", 0),
                        "misses": info.get("keyspace_misses", 0),
                    }
                )
            except Exception as e:
                logger.error(f"Failed to get Redis stats: {e}")
        else:
            stats.update(
                {
                    "keys": len(self.memory_cache),
                    "hits": 0,  # 内存缓存不统计命中率
                    "misses": 0,
                }
            )

        return stats


# 全局缓存服务实例
cache_service = CacheService()


def cached(prefix: str, ttl: int = 300, key_func: Callable | None = None):
    """
    缓存装饰器 - 用于API端点缓存

    Args:
        prefix: 缓存键前缀
        ttl: 缓存时间（秒）
        key_func: 自定义键生成函数，接收(*args, **kwargs)返回键字符串
    """

    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # 生成缓存键
            if key_func:
                cache_key = key_func(*args, **kwargs)
            else:
                # 默认基于函数名和参数生成键
                key_parts = [prefix, func.__name__]
                # 尝试从kwargs中提取关键参数
                for k, v in sorted(kwargs.items()):
                    if k not in ["request", "response", "token"]:  # 排除request/response/token对象
                        # 只序列化简单类型
                        if isinstance(v, (str, int, float, bool, type(None))):
                            key_parts.append(f"{k}={v}")
                cache_key = cache_service._generate_key(*key_parts)

            # 尝试从缓存获取
            cached_value = cache_service.get(cache_key)
            if cached_value is not None:
                logger.debug(f"Cache hit: {cache_key}")
                # 如果缓存的是字典，直接返回（FastAPI会自动转换为JSON）
                return cached_value

            # 执行函数
            logger.debug(f"Cache miss: {cache_key}")
            result = await func(*args, **kwargs)

            # 只缓存字典类型的响应（FastAPI的JSON响应）
            if isinstance(result, dict):
                cache_service.set(cache_key, result, ttl)

            return result

        return wrapper

    return decorator


def cache_key_from_request(request, prefix: str = "api") -> str:
    """从请求生成缓存键"""
    # 基于路径和查询参数生成键
    path = request.url.path
    query_string = str(sorted(request.query_params.items()))
    key_string = f"{prefix}:{path}:{query_string}"
    return cache_service._generate_key(prefix, key_string)
