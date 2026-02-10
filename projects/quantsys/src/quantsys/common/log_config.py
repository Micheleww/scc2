#!/usr/bin/env python3
"""
统一日志配置模块

提供统一的日志配置接口，确保整个系统使用一致的日志格式和脱敏机制。
"""

import logging
import sys
from datetime import datetime
from pathlib import Path

from .log_redactor import LogRedactorFormatter, setup_log_redaction


class LogConfig:
    """日志配置类"""

    # 默认日志格式
    DEFAULT_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    DEFAULT_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

    # 默认日志目录
    DEFAULT_LOG_DIR = Path("logs")

    @staticmethod
    def setup_logging(
        name: str,
        level: int | str = logging.INFO,
        log_file: str | Path | None = None,
        format_string: str | None = None,
        date_format: str | None = None,
        enable_redaction: bool = True,
        enable_console: bool = True,
        enable_file: bool = True,
    ) -> logging.Logger:
        """
        设置日志配置

        Args:
            name: 日志记录器名称（通常是 __name__）
            level: 日志级别（logging.INFO, logging.DEBUG 等，或字符串 'INFO', 'DEBUG' 等）
            log_file: 日志文件路径（可选，如果为None则使用默认路径）
            format_string: 日志格式字符串（可选，使用默认格式）
            date_format: 日期格式字符串（可选，使用默认格式）
            enable_redaction: 是否启用日志脱敏（默认True）
            enable_console: 是否输出到控制台（默认True）
            enable_file: 是否输出到文件（默认True）

        Returns:
            logging.Logger: 配置好的日志记录器
        """
        # 转换日志级别
        if isinstance(level, str):
            level = getattr(logging, level.upper(), logging.INFO)

        # 使用默认格式
        if format_string is None:
            format_string = LogConfig.DEFAULT_FORMAT
        if date_format is None:
            date_format = LogConfig.DEFAULT_DATE_FORMAT

        # 创建日志记录器
        logger = logging.getLogger(name)
        logger.setLevel(level)

        # 清除现有处理器（避免重复添加）
        logger.handlers.clear()
        logger.propagate = False  # 防止传播到根日志记录器

        # 创建格式化器
        if enable_redaction:
            formatter = LogRedactorFormatter(format_string, date_format)
        else:
            formatter = logging.Formatter(format_string, date_format)

        # 控制台处理器
        if enable_console:
            console_handler = logging.StreamHandler(sys.stdout)
            console_handler.setLevel(level)
            console_handler.setFormatter(formatter)
            logger.addHandler(console_handler)

        # 文件处理器
        if enable_file:
            if log_file is None:
                # 使用默认日志文件路径
                log_dir = LogConfig.DEFAULT_LOG_DIR
                log_dir.mkdir(parents=True, exist_ok=True)
                log_file = (
                    log_dir
                    / f"{name.replace('.', '_')}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
                )
            else:
                log_file = Path(log_file)
                log_file.parent.mkdir(parents=True, exist_ok=True)

            file_handler = logging.FileHandler(log_file, encoding="utf-8")
            file_handler.setLevel(level)
            file_handler.setFormatter(formatter)
            logger.addHandler(file_handler)

        return logger

    @staticmethod
    def get_logger(
        name: str, level: int | str = logging.INFO, log_file: str | Path | None = None, **kwargs
    ) -> logging.Logger:
        """
        获取配置好的日志记录器（便捷方法）

        Args:
            name: 日志记录器名称
            level: 日志级别
            log_file: 日志文件路径（可选）
            **kwargs: 其他参数传递给 setup_logging

        Returns:
            logging.Logger: 配置好的日志记录器
        """
        return LogConfig.setup_logging(name, level, log_file, **kwargs)


def setup_logging(
    name: str, level: int | str = logging.INFO, log_file: str | Path | None = None, **kwargs
) -> logging.Logger:
    """
    便捷函数：设置日志配置

    Args:
        name: 日志记录器名称（通常是 __name__）
        level: 日志级别
        log_file: 日志文件路径（可选）
        **kwargs: 其他参数传递给 LogConfig.setup_logging

    Returns:
        logging.Logger: 配置好的日志记录器

    Example:
        >>> from quantsys.common.log_config import setup_logging
        >>> logger = setup_logging(__name__)
        >>> logger.info("This is a test message")
    """
    return LogConfig.setup_logging(name, level, log_file, **kwargs)


def get_logger(
    name: str, level: int | str = logging.INFO, log_file: str | Path | None = None, **kwargs
) -> logging.Logger:
    """
    便捷函数：获取配置好的日志记录器

    Args:
        name: 日志记录器名称
        level: 日志级别
        log_file: 日志文件路径（可选）
        **kwargs: 其他参数传递给 LogConfig.setup_logging

    Returns:
        logging.Logger: 配置好的日志记录器

    Example:
        >>> from quantsys.common.log_config import get_logger
        >>> logger = get_logger(__name__)
        >>> logger.info("This is a test message")
    """
    return LogConfig.get_logger(name, level, log_file, **kwargs)


# 设置根日志记录器的脱敏（全局生效）
setup_log_redaction()
