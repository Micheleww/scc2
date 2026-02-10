#!/usr/bin/env python3
"""
日志脱敏模块

提供日志脱敏过滤器，自动对日志中的敏感信息进行脱敏处理
"""

import logging
import re

# 敏感信息正则表达式模式
SENSITIVE_PATTERNS = {
    "api_key": r'(?i)(api[_-]?key|apikey)\s*[:=]\s*["\']?([a-zA-Z0-9-_]{16,})["\']?',
    "secret_key": r'(?i)(secret[_-]?key|secretkey|private[_-]?key|privatekey)\s*[:=]\s*["\']?([a-zA-Z0-9-_]{32,})["\']?',
    "token": r'(?i)(token|auth[_-]?token|authtoken|access[_-]?token|accesstoken)\s*[:=]\s*["\']?([a-zA-Z0-9-_\.]{20,})["\']?',
    "signature": r'(?i)(signature|sign|sig)\s*[:=]\s*["\']?([a-zA-Z0-9-_]{40,})["\']?',
    "password": r'(?i)(password|passwd|pwd)\s*[:=]\s*["\']?([a-zA-Z0-9-_@#$%^&*()]{8,})["\']?',
    "jwt_token": r"(eyJ[a-zA-Z0-9_-]+\.eyJ[a-zA-Z0-9_-]+\.[a-zA-Z0-9_-]+)",
    "ssh_key": r"(ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABgQC[0-9a-zA-Z+/]+[=]{0,3})",
    "aws_access_key": r'(?i)aws[_-]?access[_-]?key[_-]?id\s*[:=]\s*["\']?([A-Z0-9]{16})["\']?',
    "aws_secret_key": r'(?i)aws[_-]?secret[_-]?access[_-]?key\s*[:=]\s*["\']?([a-zA-Z0-9+/]{40})["\']?',
}


class LogRedactor(logging.Filter):
    """
    日志脱敏过滤器

    自动对日志消息中的敏感信息进行脱敏处理
    """

    def __init__(self, name: str = ""):
        """
        初始化日志脱敏过滤器

        Args:
            name: 过滤器名称
        """
        super().__init__(name)

    def redact_sensitive_info(self, message: str) -> str:
        """
        对消息中的敏感信息进行脱敏处理

        Args:
            message: 原始日志消息

        Returns:
            str: 脱敏后的日志消息
        """
        redacted_message = message

        # 对每种敏感信息类型进行脱敏
        for pattern_name, pattern in SENSITIVE_PATTERNS.items():
            # 根据敏感信息类型选择脱敏方式
            def replace_func(match: re.Match) -> str:
                """替换敏感信息的函数"""
                if len(match.groups()) > 1:
                    # 有分组，保留键名，脱敏值
                    key_part = match.group(1)
                    return f"{key_part}='***REDACTED***'"
                else:
                    # 无分组，直接脱敏整个匹配
                    return "***REDACTED***"

            redacted_message = re.sub(pattern, replace_func, redacted_message)

        return redacted_message

    def filter(self, record: logging.LogRecord) -> bool:
        """
        过滤日志记录，对消息进行脱敏处理

        Args:
            record: 日志记录

        Returns:
            bool: 是否保留该日志记录
        """
        # 对消息进行脱敏
        if hasattr(record, "msg"):
            original_msg = record.msg
            if isinstance(original_msg, str):
                record.msg = self.redact_sensitive_info(original_msg)

        return True


class LogRedactorFormatter(logging.Formatter):
    """
    日志脱敏格式化器

    在格式化日志时对消息进行脱敏处理
    """

    def __init__(
        self, fmt: str = None, datefmt: str = None, style: str = "%", validate: bool = True
    ):
        """
        初始化日志脱敏格式化器

        Args:
            fmt: 日志格式字符串
            datefmt: 日期格式字符串
            style: 格式字符串风格
            validate: 是否验证格式字符串
        """
        super().__init__(fmt, datefmt, style, validate)
        self.redactor = LogRedactor()

    def format(self, record: logging.LogRecord) -> str:
        """
        格式化日志记录

        Args:
            record: 日志记录

        Returns:
            str: 格式化后的日志记录
        """
        # 对消息进行脱敏
        original_msg = record.msg
        if isinstance(original_msg, str):
            record.msg = self.redactor.redact_sensitive_info(original_msg)

        # 使用父类的格式化方法
        return super().format(record)


def setup_log_redaction() -> None:
    """
    设置日志脱敏，将脱敏过滤器添加到所有日志处理器
    """
    # 创建脱敏过滤器
    redactor = LogRedactor()

    # 获取根日志记录器
    root_logger = logging.getLogger()

    # 将脱敏过滤器添加到所有处理器
    for handler in root_logger.handlers:
        handler.addFilter(redactor)

    # 同时设置全局格式化器为脱敏格式化器
    for handler in root_logger.handlers:
        if isinstance(handler, logging.StreamHandler) or isinstance(handler, logging.FileHandler):
            # 保留原有的格式化器格式
            if hasattr(handler, "formatter") and handler.formatter:
                fmt = handler.formatter._fmt
                datefmt = handler.formatter.datefmt
                # Get the correct style character
                if hasattr(handler.formatter, "_style"):
                    style_obj = handler.formatter._style
                    if hasattr(style_obj, "_fmt"):
                        # Determine style based on formatter type
                        if isinstance(style_obj, logging.PercentStyle):
                            style = "%"
                        elif isinstance(style_obj, logging.StrFormatStyle):
                            style = "{"
                        elif isinstance(style_obj, logging.StringTemplateStyle):
                            style = "$"
                        else:
                            style = "%"  # Default to % style
                    else:
                        style = "%"
                else:
                    style = "%"
                handler.setFormatter(LogRedactorFormatter(fmt, datefmt, style))


# 确保日志脱敏在模块导入时自动设置
setup_log_redaction()
