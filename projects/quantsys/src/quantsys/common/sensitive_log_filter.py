#!/usr/bin/env python3
"""
日志脱敏过滤器
自动脱敏日志中的敏感信息（key/token/password等）
"""

import logging
import re


class SensitiveDataFilter(logging.Filter):
    """
    敏感数据过滤器

    自动脱敏日志中的敏感信息：
    - API密钥
    - API密钥
    - 数据库密码
    - JWT令牌
    - 其他密钥
    """

    def __init__(self):
        """初始化过滤器"""
        super().__init__()

        # 脱敏模式列表
        self.patterns = [
            # API密钥模式
            (r'api_key["\s*][=:]["\s*]+["\w]+', "api_key=***"),
            (r'api_key["\s*][=:]["\s*]+["\w]{32,}', "api_key=***"),
            (r'api_key["\s*][=:]["\s*]+["\w]{40,}', "api_key=***"),
            # API密钥模式
            (r'api_secret["\s*][=:]["\s*]+["\w]+', "api_secret=***"),
            (r'api_secret["\s*][=:]["\s*]+["\w]{32,}', "api_secret=***"),
            (r'api_secret["\s*][=:]["\s*]+["\w]{40,}', "api_secret=***"),
            # 密码模式
            (r'password["\s*][=:]["\s*]+["\S]+', "password=***"),
            (r'passwd["\s*][=:]["\s*]+["\S]+', "passwd=***"),
            (r'pwd["\s*][=:]["\s*]+["\S]+', "pwd=***"),
            # 令牌模式
            (r'token["\s*][=:]["\s*]+["\w]+', "token=***"),
            (r'token["\s*][=:]["\s*]+["\w]{32,}', "token=***"),
            (r'token["\s*][=:]["\s*]+["\w]{40,}', "token=***"),
            (r'jwt["\s*][=:]["\s*]+["\w]+', "jwt=***"),
            (r'jwt["\s*][=:]["\s*]+["\w]{32,}', "jwt=***"),
            # 密钥模式
            (r'secret["\s*][=:]["\s*]+["\w]+', "secret=***"),
            (r'secret["\s*][=:]["\s*]+["\w]{32,}', "secret=***"),
            (r'secret["\s*][=:]["\s*]+["\w]{40,}', "secret=***"),
            (r'key["\s*][=:]["\s*]+["\w]+', "key=***"),
            (r'key["\s*][=:]["\s*]+["\w]{32,}', "key=***"),
            # Bearer令牌
            (r'Bearer ["\w]+', "Bearer ***"),
            (r'Bearer ["\w]{32,}', "Bearer ***"),
            (r'Bearer ["\w]{40,}', "Bearer ***"),
            # 32字符密钥
            (r'["\w]{32}', "***"),
            # 40字符密钥
            (r'["\w]{40}', "***"),
            # 64字符密钥
            (r'["\w]{64}', "***"),
        ]

    def filter(self, record: logging.LogRecord) -> logging.LogRecord:
        """
        过滤日志记录

        Args:
            record: 日志记录

        Returns:
            logging.LogRecord: 过滤后的日志记录
        """
        if record.msg:
            record.msg = self._sanitize(record.msg)

        if record.args:
            record.args = tuple(self._sanitize(str(arg)) for arg in record.args)

        return record

    def _sanitize(self, message: str) -> str:
        """
        脱敏消息

        Args:
            message: 原始消息

        Returns:
            str: 脱敏后的消息
        """
        sanitized = message

        for pattern, replacement in self.patterns:
            sanitized = re.sub(pattern, replacement, sanitized, flags=re.IGNORECASE)

        return sanitized


class SensitiveDataFormatter(logging.Formatter):
    """
    敏感数据格式化器

    在格式化日志时自动脱敏敏感信息
    """

    def __init__(self, fmt: str = None, datefmt: str = None):
        """
        初始化格式化器

        Args:
            fmt: 格式字符串
            datefmt: 日期格式
        """
        super().__init__(fmt, datefmt)
        self.filter = SensitiveDataFilter()

    def format(self, record: logging.LogRecord) -> str:
        """
        格式化日志记录

        Args:
            record: 日志记录

        Returns:
            str: 格式化后的日志字符串
        """
        # 先应用过滤器脱敏
        record = self.filter.filter(record)
        # 再应用格式化
        return super().format(record)


def setup_sensitive_logging(
    level: int = logging.INFO, log_file: str = None, format_string: str = None
) -> logging.Logger:
    """
    设置敏感数据日志

    Args:
        level: 日志级别
        log_file: 日志文件路径
        format_string: 格式字符串

    Returns:
        logging.Logger: 配置好的日志记录器
    """
    if format_string is None:
        format_string = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

    # 创建日志记录器
    logger = logging.getLogger()
    logger.setLevel(level)

    # 清除现有处理器
    logger.handlers.clear()

    # 创建格式化器（带脱敏）
    formatter = SensitiveDataFormatter(format_string)

    # 控制台处理器
    console_handler = logging.StreamHandler()
    console_handler.setLevel(level)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # 文件处理器
    if log_file:
        from pathlib import Path

        Path(log_file).parent.mkdir(parents=True, exist_ok=True)

        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setLevel(level)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    return logger


def sanitize_message(message: str) -> str:
    """
    脱敏消息（便捷函数）

    Args:
        message: 原始消息

    Returns:
        str: 脱敏后的消息
    """
    filter_obj = SensitiveDataFilter()
    return filter_obj._sanitize(message)


if __name__ == "__main__":
    setup_sensitive_logging()

    logger = logging.getLogger(__name__)

    logger.info("测试日志脱敏功能")
    logger.info("API密钥: api_key=abc123def456ghi789jkl012mno345pqr678")
    logger.info("API密钥: api_secret=xyz789abc456def123ghi456jkl789mno012")
    logger.info("密码: password=mysecretpassword123")
    logger.info("令牌: token=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9")
    logger.info("Bearer令牌: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9")
    logger.info("密钥: secret=mysecretkey12345678901234567890123")
    logger.info("32字符密钥: abcdefghijklmnopqrstuvwxyz123456")
    logger.info("40字符密钥: abcdefghijklmnopqrstuvwxyz123456789012")

    logger.info("日志脱敏测试完成")
