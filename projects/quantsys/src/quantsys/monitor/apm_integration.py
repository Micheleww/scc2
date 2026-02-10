#!/usr/bin/env python3
"""
APM (Application Performance Monitoring) 集成
支持 Sentry、Datadog 等 APM 工具
"""

import functools
import logging
import time
from collections.abc import Callable
from contextlib import contextmanager
from typing import Any

logger = logging.getLogger(__name__)

# 尝试导入 APM 库
try:
    import sentry_sdk
    from sentry_sdk.integrations.logging import LoggingIntegration

    SENTRY_AVAILABLE = True
except ImportError:
    SENTRY_AVAILABLE = False
    logger.warning("Sentry SDK not available")

try:
    from datadog import initialize, statsd

    DATADOG_AVAILABLE = True
except ImportError:
    DATADOG_AVAILABLE = False
    logger.warning("Datadog SDK not available")


class APMManager:
    """APM 管理器，统一管理性能监控"""

    def __init__(self, config: dict[str, Any] | None = None):
        """
        初始化 APM 管理器

        Args:
            config: APM 配置
        """
        self.config = config or {}
        self.sentry_enabled = False
        self.datadog_enabled = False

        # 初始化 Sentry
        if SENTRY_AVAILABLE and self.config.get("sentry", {}).get("enabled", False):
            self._init_sentry()

        # 初始化 Datadog
        if DATADOG_AVAILABLE and self.config.get("datadog", {}).get("enabled", False):
            self._init_datadog()

    def _init_sentry(self):
        """初始化 Sentry"""
        try:
            sentry_config = self.config.get("sentry", {})
            sentry_sdk.init(
                dsn=sentry_config.get("dsn", ""),
                environment=sentry_config.get("environment", "development"),
                traces_sample_rate=sentry_config.get("traces_sample_rate", 1.0),
                integrations=[LoggingIntegration(level=logging.INFO, event_level=logging.ERROR)],
            )
            self.sentry_enabled = True
            logger.info("Sentry APM initialized")
        except Exception as e:
            logger.warning(f"Sentry initialization failed: {e}")

    def _init_datadog(self):
        """初始化 Datadog"""
        try:
            datadog_config = self.config.get("datadog", {})
            initialize(
                api_key=datadog_config.get("api_key", ""),
                app_key=datadog_config.get("app_key", ""),
                host_name=datadog_config.get("host_name", "localhost"),
            )
            self.datadog_enabled = True
            logger.info("Datadog APM initialized")
        except Exception as e:
            logger.warning(f"Datadog initialization failed: {e}")

    @contextmanager
    def trace(self, operation_name: str, tags: dict[str, str] | None = None):
        """
        性能追踪上下文管理器

        Args:
            operation_name: 操作名称
            tags: 标签字典
        """
        start_time = time.time()
        tags = tags or {}

        # Sentry 追踪
        if self.sentry_enabled:
            with sentry_sdk.start_transaction(op=operation_name, name=operation_name):
                try:
                    yield
                except Exception as e:
                    sentry_sdk.capture_exception(e)
                    raise

        # Datadog 追踪
        elif self.datadog_enabled:
            with statsd.timed(operation_name, tags=[f"{k}:{v}" for k, v in tags.items()]):
                yield

        # 简单的时间追踪
        else:
            try:
                yield
            finally:
                duration = time.time() - start_time
                logger.info(f"Operation {operation_name} took {duration:.3f}s")

    def capture_exception(self, exception: Exception, context: dict[str, Any] | None = None):
        """捕获异常"""
        if self.sentry_enabled:
            with sentry_sdk.push_scope() as scope:
                if context:
                    for key, value in context.items():
                        scope.set_extra(key, value)
                sentry_sdk.capture_exception(exception)
        else:
            logger.error(f"Exception: {exception}", exc_info=True, extra=context)

    def record_metric(self, metric_name: str, value: float, tags: dict[str, str] | None = None):
        """记录指标"""
        tags = tags or {}

        if self.datadog_enabled:
            statsd.gauge(metric_name, value, tags=[f"{k}:{v}" for k, v in tags.items()])
        else:
            logger.debug(f"Metric {metric_name}: {value} (tags: {tags})")

    def increment_counter(
        self, counter_name: str, value: int = 1, tags: dict[str, str] | None = None
    ):
        """增加计数器"""
        tags = tags or {}

        if self.datadog_enabled:
            statsd.increment(counter_name, value, tags=[f"{k}:{v}" for k, v in tags.items()])
        else:
            logger.debug(f"Counter {counter_name} incremented by {value} (tags: {tags})")


def performance_monitor(operation_name: str | None = None, tags: dict[str, str] | None = None):
    """
    性能监控装饰器

    Usage:
        @performance_monitor("data_load")
        def load_data():
            ...
    """

    def decorator(func: Callable) -> Callable:
        op_name = operation_name or f"{func.__module__}.{func.__name__}"

        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            # 这里需要全局 APM 管理器实例
            # 实际使用时应该注入或使用单例
            apm = APMManager()  # 临时创建，实际应该使用单例
            with apm.trace(op_name, tags):
                return func(*args, **kwargs)

        return wrapper

    return decorator
