"""
统一限流与退避模块

实现API请求的统一限流、自动退避、队列化请求和指标记录
"""

import logging
import queue
import threading
import time
from collections.abc import Callable
from datetime import datetime
from functools import wraps
from typing import Any

import requests

# 配置日志
logger = logging.getLogger(__name__)


class RateLimiter:
    """
    统一限流管理器

    特性:
    - 基于令牌桶算法的限流
    - 支持不同endpoint的独立配置
    - 自动处理429错误的退避策略
    - 请求队列化
    - 指标记录与日志锚点
    """

    def __init__(self, config: dict[str, Any] | None = None):
        """
        初始化限流管理器

        Args:
            config: 限流配置，格式为 {
                "endpoint_name": {
                    "rate_limit": int,       # 每分钟允许的请求数
                    "burst_limit": int,      # 突发请求数
                    "retry_max": int,        # 最大重试次数
                    "retry_base_delay": float,  # 基础退避延迟(秒)
                    "retry_exponential": float,  # 指数退避系数
                    "timeout": float         # 请求超时时间(秒)
                }
            }
        """
        self.config = config or {}
        self.endpoints = {}
        self.metrics = {
            "total_requests": 0,
            "successful_requests": 0,
            "failed_requests": 0,
            "retries": 0,
            "last_reset": datetime.now().isoformat(),
        }
        self.lock = threading.Lock()
        self.queues: dict[str, queue.Queue] = {}
        self.workers: dict[str, threading.Thread] = {}

        # 初始化端点配置
        self._init_endpoints()

    def _init_endpoints(self):
        """初始化所有端点的限流配置"""
        for endpoint, cfg in self.config.items():
            self.endpoints[endpoint] = {
                "rate_limit": cfg.get("rate_limit", 60),  # 默认每分钟60次请求
                "burst_limit": cfg.get("burst_limit", 10),  # 默认突发10次
                "retry_max": cfg.get("retry_max", 3),  # 默认最多重试3次
                "retry_base_delay": cfg.get("retry_base_delay", 1.0),  # 基础延迟1秒
                "retry_exponential": cfg.get("retry_exponential", 2.0),  # 指数退避
                "timeout": cfg.get("timeout", 30.0),  # 默认超时30秒
                "tokens": cfg.get("burst_limit", 10),  # 初始令牌数
                "last_refill": time.time(),
                "lock": threading.Lock(),
            }

            # 为每个端点创建队列和工作线程
            self.queues[endpoint] = queue.Queue()
            self.workers[endpoint] = threading.Thread(
                target=self._worker, args=(endpoint,), daemon=True
            )
            self.workers[endpoint].start()

    def _refill_tokens(self, endpoint: str):
        """
        为指定端点补充令牌

        Args:
            endpoint: 端点名称
        """
        with self.endpoints[endpoint]["lock"]:
            now = time.time()
            time_passed = now - self.endpoints[endpoint]["last_refill"]
            tokens_to_add = (time_passed / 60) * self.endpoints[endpoint]["rate_limit"]

            if tokens_to_add > 0:
                self.endpoints[endpoint]["tokens"] = min(
                    self.endpoints[endpoint]["tokens"] + tokens_to_add,
                    self.endpoints[endpoint]["burst_limit"],
                )
                self.endpoints[endpoint]["last_refill"] = now

    def _wait_for_token(self, endpoint: str):
        """
        等待获取令牌

        Args:
            endpoint: 端点名称
        """
        while True:
            self._refill_tokens(endpoint)

            with self.endpoints[endpoint]["lock"]:
                if self.endpoints[endpoint]["tokens"] >= 1:
                    self.endpoints[endpoint]["tokens"] -= 1
                    return

            # 等待后重试
            time.sleep(0.1)

    def _exponential_backoff(
        self, retry_count: int, base_delay: float, exponential: float
    ) -> float:
        """
        计算指数退避延迟

        Args:
            retry_count: 当前重试次数
            base_delay: 基础延迟(秒)
            exponential: 指数系数

        Returns:
            延迟时间(秒)
        """
        return base_delay * (exponential**retry_count)

    def _worker(self, endpoint: str):
        """
        请求处理工作线程

        Args:
            endpoint: 端点名称
        """
        while True:
            try:
                # 从队列获取请求
                func, args, kwargs, callback = self.queues[endpoint].get()

                # 执行请求
                result = self._execute_with_rate_limit(endpoint, func, args, kwargs)

                # 调用回调函数
                if callback:
                    callback(result)

                # 标记任务完成
                self.queues[endpoint].task_done()
            except Exception as e:
                logger.error(f"Worker error for {endpoint}: {e}")
                self.queues[endpoint].task_done()

    def _execute_with_rate_limit(
        self, endpoint: str, func: Callable, args: tuple, kwargs: dict
    ) -> Any:
        """
        执行带限流的函数调用

        Args:
            endpoint: 端点名称
            func: 要执行的函数
            args: 函数参数
            kwargs: 函数关键字参数

        Returns:
            函数执行结果
        """
        retry_count = 0

        while retry_count <= self.endpoints[endpoint]["retry_max"]:
            try:
                # 等待获取令牌
                self._wait_for_token(endpoint)

                # 更新指标
                with self.lock:
                    self.metrics["total_requests"] += 1

                # 执行请求
                logger.info(
                    f"[RATE_LIMITER] Executing request for {endpoint} (attempt {retry_count + 1})"
                )
                result = func(*args, **kwargs)

                # 更新成功指标
                with self.lock:
                    self.metrics["successful_requests"] += 1

                logger.info(f"[RATE_LIMITER] Request for {endpoint} succeeded")
                return result

            except requests.exceptions.HTTPError as e:
                if e.response.status_code == 429:
                    # 处理429错误
                    retry_count += 1
                    with self.lock:
                        self.metrics["retries"] += 1

                    delay = self._exponential_backoff(
                        retry_count,
                        self.endpoints[endpoint]["retry_base_delay"],
                        self.endpoints[endpoint]["retry_exponential"],
                    )

                    logger.warning(
                        f"[RATE_LIMITER] 429 Too Many Requests for {endpoint}, retrying in {delay:.2f}s (attempt {retry_count}/{self.endpoints[endpoint]['retry_max']})"
                    )
                    time.sleep(delay)
                    continue
                else:
                    # 其他HTTP错误
                    logger.error(f"[RATE_LIMITER] HTTP Error for {endpoint}: {e}")
                    with self.lock:
                        self.metrics["failed_requests"] += 1
                    raise

            except requests.exceptions.RequestException as e:
                # 网络错误，重试
                retry_count += 1
                with self.lock:
                    self.metrics["retries"] += 1

                delay = self._exponential_backoff(
                    retry_count,
                    self.endpoints[endpoint]["retry_base_delay"],
                    self.endpoints[endpoint]["retry_exponential"],
                )

                logger.warning(
                    f"[RATE_LIMITER] Request exception for {endpoint}: {e}, retrying in {delay:.2f}s (attempt {retry_count}/{self.endpoints[endpoint]['retry_max']})"
                )
                time.sleep(delay)
                continue

            except Exception as e:
                # 其他错误
                logger.error(f"[RATE_LIMITER] Error for {endpoint}: {e}")
                with self.lock:
                    self.metrics["failed_requests"] += 1
                raise

        # 达到最大重试次数
        logger.error(f"[RATE_LIMITER] Max retries reached for {endpoint}")
        with self.lock:
            self.metrics["failed_requests"] += 1
        raise Exception(f"Max retries reached for {endpoint}")

    def execute(self, endpoint: str, func: Callable, *args, **kwargs) -> Any:
        """
        同步执行带限流的请求

        Args:
            endpoint: 端点名称
            func: 要执行的函数
            *args: 函数参数
            **kwargs: 函数关键字参数

        Returns:
            函数执行结果
        """
        if endpoint not in self.endpoints:
            raise ValueError(f"Unknown endpoint: {endpoint}")

        return self._execute_with_rate_limit(endpoint, func, args, kwargs)

    def execute_async(
        self, endpoint: str, func: Callable, callback: Callable | None = None, *args, **kwargs
    ):
        """
        异步执行带限流的请求

        Args:
            endpoint: 端点名称
            func: 要执行的函数
            callback: 回调函数
            *args: 函数参数
            **kwargs: 函数关键字参数
        """
        if endpoint not in self.endpoints:
            raise ValueError(f"Unknown endpoint: {endpoint}")

        self.queues[endpoint].put((func, args, kwargs, callback))

    def get_metrics(self) -> dict[str, Any]:
        """
        获取限流指标

        Returns:
            指标字典
        """
        with self.lock:
            metrics = self.metrics.copy()
            metrics["success_rate"] = (
                metrics["successful_requests"] / metrics["total_requests"]
                if metrics["total_requests"] > 0
                else 0
            )
            metrics["retry_rate"] = (
                metrics["retries"] / metrics["total_requests"]
                if metrics["total_requests"] > 0
                else 0
            )
            return metrics

    def reset_metrics(self):
        """重置指标"""
        with self.lock:
            self.metrics = {
                "total_requests": 0,
                "successful_requests": 0,
                "failed_requests": 0,
                "retries": 0,
                "last_reset": datetime.now().isoformat(),
            }

    def close(self):
        """关闭所有工作线程"""
        for worker in self.workers.values():
            worker.join(timeout=1.0)

    def add_endpoint(self, name: str, config: dict[str, Any]):
        """
        添加新的端点配置

        Args:
            name: 端点名称
            config: 端点配置
        """
        self.config[name] = config
        self._init_endpoints()


def with_rate_limit(endpoint: str, rate_limiter: RateLimiter):
    """
    装饰器：为函数添加限流

    Args:
        endpoint: 端点名称
        rate_limiter: 限流管理器实例

    Returns:
        装饰后的函数
    """

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            return rate_limiter.execute(endpoint, func, *args, **kwargs)

        return wrapper

    return decorator


# 全局限流管理器实例
DEFAULT_RATE_LIMITER = RateLimiter(
    {
        "okx": {
            "rate_limit": 60,  # 每分钟60次请求
            "burst_limit": 10,  # 突发10次
            "retry_max": 3,  # 最多重试3次
            "retry_base_delay": 1.0,  # 基础延迟1秒
            "retry_exponential": 2.0,  # 指数退避
            "timeout": 30.0,  # 超时30秒
        },
        "blockchain.com": {
            "rate_limit": 30,  # 每分钟30次请求
            "burst_limit": 5,  # 突发5次
            "retry_max": 3,
            "retry_base_delay": 2.0,
            "retry_exponential": 2.0,
            "timeout": 60.0,
        },
        "etherscan": {
            "rate_limit": 5,  # 每分钟5次请求
            "burst_limit": 2,  # 突发2次
            "retry_max": 3,
            "retry_base_delay": 5.0,  # 基础延迟5秒
            "retry_exponential": 2.0,
            "timeout": 60.0,
        },
        "coingecko": {
            "rate_limit": 10,  # 每分钟10次请求
            "burst_limit": 3,  # 突发3次
            "retry_max": 3,
            "retry_base_delay": 3.0,
            "retry_exponential": 2.0,
            "timeout": 60.0,
        },
        "alternative.me": {
            "rate_limit": 60,  # 每分钟60次请求
            "burst_limit": 10,
            "retry_max": 3,
            "retry_base_delay": 1.0,
            "retry_exponential": 2.0,
            "timeout": 30.0,
        },
    }
)


# 请求封装函数
def get_with_rate_limit(
    rate_limiter: RateLimiter, endpoint: str, *args, **kwargs
) -> requests.Response:
    """
    带限流的GET请求

    Args:
        rate_limiter: 限流管理器
        endpoint: 端点名称
        *args: requests.get的位置参数
        **kwargs: requests.get的关键字参数

    Returns:
        requests.Response对象
    """
    return rate_limiter.execute(endpoint, requests.get, *args, **kwargs)


def post_with_rate_limit(
    rate_limiter: RateLimiter, endpoint: str, *args, **kwargs
) -> requests.Response:
    """
    带限流的POST请求

    Args:
        rate_limiter: 限流管理器
        endpoint: 端点名称
        *args: requests.post的位置参数
        **kwargs: requests.post的关键字参数

    Returns:
        requests.Response对象
    """
    return rate_limiter.execute(endpoint, requests.post, *args, **kwargs)
