#!/usr/bin/env python3
"""
敏感信息检测器
用于识别和过滤敏感信息，如API密钥、Token、签名等
"""

import logging
import re
from typing import Any

logger = logging.getLogger(__name__)


class SensitiveInfoDetector:
    """
    敏感信息检测器，用于识别和过滤敏感信息
    """

    # 敏感信息正则表达式模式
    SENSITIVE_PATTERNS = [
        # API密钥模式
        (r"api[_\-]?key|API[_\-]?KEY", r"[a-zA-Z0-9]{32,}", "API密钥"),
        (r"secret[_\-]?key|SECRET[_\-]?KEY", r"[a-zA-Z0-9]{32,}", "密钥"),
        (
            r"passphrase|PASSPHRASE",
            r'[a-zA-Z0-9!@#$%^&*()_+\-=\[\]{};\':"\\|,.<>\/?]{8,}',
            "密码短语",
        ),
        # Token模式
        (r"access[_\-]?token|ACCESS[_\-]?TOKEN", r"[a-zA-Z0-9\-_]{64,}", "访问令牌"),
        (r"id[_\-]?token|ID[_\-]?TOKEN", r"[a-zA-Z0-9\-_\.]{64,}", "ID令牌"),
        (r"jwt|JWT", r"eyJ[a-zA-Z0-9\-_]+\.[a-zA-Z0-9\-_]+\.[a-zA-Z0-9\-_]+", "JWT令牌"),
        (r"bearer|BEARER", r"[a-zA-Z0-9\-_]{64,}", "Bearer令牌"),
        # 签名和哈希模式
        (r"signature|SIGNATURE", r"[a-zA-Z0-9]{64,}", "签名"),
        (r"hash|HASH", r"[a-zA-Z0-9]{64}", "哈希值"),
        (r"hmac|HMAC", r"[a-zA-Z0-9]{64}", "HMAC值"),
        (r"sha256|SHA256", r"[a-zA-Z0-9]{64}", "SHA256哈希"),
        (r"md5|MD5", r"[a-f0-9]{32}", "MD5哈希"),
        # 其他敏感信息
        (r"password|PASSWORD", r'[a-zA-Z0-9!@#$%^&*()_+\-=\[\]{};\':"\\|,.<>\/?]{8,}', "密码"),
        (
            r"private[_\-]?key|PRIVATE[_\-]?KEY",
            r"-----BEGIN (?:RSA|DSA|EC|OPENSSH|PGP) PRIVATE KEY-----[\s\S]+?-----END (?:RSA|DSA|EC|OPENSSH|PGP) PRIVATE KEY-----",
            "私钥",
        ),
    ]

    # 配置文件中需要检测的敏感字段
    CONFIG_SENSITIVE_FIELDS = [
        "api_key",
        "api_secret",
        "secret_key",
        "passphrase",
        "access_token",
        "id_token",
        "jwt",
        "bearer_token",
        "password",
        "private_key",
        "signature",
        "hmac",
        "sha256",
        "md5",
        "aws_access_key_id",
        "aws_secret_access_key",
        "google_api_key",
        "facebook_app_secret",
        "slack_token",
        "discord_token",
    ]

    @classmethod
    def detect_sensitive_info(cls, text: str) -> list[tuple[str, str, str, int, int]]:
        """
        检测文本中的敏感信息

        Args:
            text: 要检测的文本

        Returns:
            List[Tuple[str, str, str, int, int]]: 检测到的敏感信息列表，格式为 (类型, 原始值, 脱敏值, 开始位置, 结束位置)
        """
        results = []

        for pattern_name, pattern_regex, info_type in cls.SENSITIVE_PATTERNS:
            # 先查找包含敏感字段名的行
            field_matches = re.finditer(pattern_name, text, re.IGNORECASE)

            for field_match in field_matches:
                # 在包含敏感字段名的行中查找敏感值
                line_start = text.rfind("\n", 0, field_match.start()) + 1
                line_end = text.find("\n", field_match.end())
                if line_end == -1:
                    line_end = len(text)

                line = text[line_start:line_end]

                # 查找敏感值
                value_matches = re.finditer(pattern_regex, line, re.MULTILINE | re.DOTALL)
                for value_match in value_matches:
                    # 计算在原始文本中的位置
                    start_pos = line_start + value_match.start()
                    end_pos = line_start + value_match.end()
                    original_value = value_match.group()

                    # 生成脱敏值
                    redacted_value = cls._redact_value(original_value, info_type)

                    results.append((info_type, original_value, redacted_value, start_pos, end_pos))

        return results

    @classmethod
    def _redact_value(cls, value: str, info_type: str) -> str:
        """
        对敏感值进行脱敏处理

        Args:
            value: 原始敏感值
            info_type: 敏感信息类型

        Returns:
            str: 脱敏后的敏感值
        """
        if not value:
            return value

        # 根据敏感信息类型和长度决定脱敏方式
        if len(value) <= 8:
            return "*" * len(value)
        elif len(value) <= 32:
            return f"{value[:4]}***{value[-4:]}"
        elif len(value) <= 64:
            return f"{value[:8]}***{value[-8:]}"
        else:
            return f"{value[:16]}***{value[-16:]}"

    @classmethod
    def redact_text(cls, text: str) -> tuple[str, int]:
        """
        对文本中的敏感信息进行脱敏处理

        Args:
            text: 要脱敏的文本

        Returns:
            Tuple[str, int]: 脱敏后的文本和脱敏的敏感信息数量
        """
        detected = cls.detect_sensitive_info(text)

        # 按照位置倒序处理，避免位置偏移
        detected.sort(key=lambda x: x[3], reverse=True)

        redacted_text = text
        redacted_count = 0

        for info_type, original, redacted, start, end in detected:
            redacted_text = redacted_text[:start] + redacted + redacted_text[end:]
            redacted_count += 1

        return redacted_text, redacted_count

    @classmethod
    def scan_file(cls, file_path: str) -> list[dict[str, Any]]:
        """
        扫描文件中的敏感信息

        Args:
            file_path: 要扫描的文件路径

        Returns:
            List[Dict[str, Any]]: 扫描结果列表
        """
        results = []

        try:
            with open(file_path, encoding="utf-8", errors="ignore") as f:
                content = f.read()

            detected = cls.detect_sensitive_info(content)

            for info_type, original, redacted, start, end in detected:
                # 计算行号
                line_no = content[:start].count("\n") + 1

                # 获取上下文
                line_start = content.rfind("\n", 0, start) + 1
                line_end = content.find("\n", end)
                if line_end == -1:
                    line_end = len(content)
                context = content[line_start:line_end].strip()

                results.append(
                    {
                        "file_path": file_path,
                        "line_no": line_no,
                        "info_type": info_type,
                        "original_value": original,
                        "redacted_value": redacted,
                        "context": context,
                        "start_pos": start,
                        "end_pos": end,
                    }
                )

        except Exception as e:
            logger.error(f"扫描文件 {file_path} 时出错: {e}")

        return results

    @classmethod
    def scan_config(cls, config_data: dict[str, Any], parent_key: str = "") -> list[dict[str, Any]]:
        """
        扫描配置数据中的敏感信息

        Args:
            config_data: 要扫描的配置数据
            parent_key: 父键名，用于构建完整路径

        Returns:
            List[Dict[str, Any]]: 扫描结果列表
        """
        results = []

        if isinstance(config_data, dict):
            for key, value in config_data.items():
                full_key = f"{parent_key}.{key}" if parent_key else key

                # 检查是否为敏感字段
                if key.lower() in [field.lower() for field in cls.CONFIG_SENSITIVE_FIELDS]:
                    if isinstance(value, str) and len(value) > 0:
                        results.append(
                            {
                                "key": full_key,
                                "info_type": "配置敏感字段",
                                "original_value": value,
                                "redacted_value": cls._redact_value(value, "配置敏感字段"),
                            }
                        )

                # 递归扫描嵌套结构
                results.extend(cls.scan_config(value, full_key))
        elif isinstance(config_data, list):
            for i, item in enumerate(config_data):
                full_key = f"{parent_key}[{i}]" if parent_key else f"[{i}]"
                results.extend(cls.scan_config(item, full_key))

        return results

    @classmethod
    def scan_directory(
        cls, directory_path: str, file_patterns: list[str] = None
    ) -> list[dict[str, Any]]:
        """
        扫描目录中的文件

        Args:
            directory_path: 要扫描的目录路径
            file_patterns: 要扫描的文件模式列表

        Returns:
            List[Dict[str, Any]]: 扫描结果列表
        """
        import fnmatch
        import os

        results = []

        # 默认扫描的文件类型
        default_patterns = ["*.log", "*.json", "*.yaml", "*.yml", "*.env", "*.conf", "*.config"]
        scan_patterns = file_patterns or default_patterns

        for root, dirs, files in os.walk(directory_path):
            for file in files:
                # 检查文件是否匹配模式
                if any(fnmatch.fnmatch(file.lower(), pattern.lower()) for pattern in scan_patterns):
                    file_path = os.path.join(root, file)
                    file_results = cls.scan_file(file_path)
                    results.extend(file_results)

        return results


class RedactFilter(logging.Filter):
    """
    日志脱敏过滤器，用于在日志记录时自动脱敏敏感信息
    """

    def __init__(self, name: str = ""):
        """
        初始化日志脱敏过滤器

        Args:
            name: 过滤器名称
        """
        super().__init__(name)
        self.detector = SensitiveInfoDetector()

    def filter(self, record: logging.LogRecord) -> bool:
        """
        过滤日志记录，脱敏敏感信息

        Args:
            record: 日志记录对象

        Returns:
            bool: 总是返回True，只修改日志记录
        """
        # 脱敏消息
        if hasattr(record, "msg") and isinstance(record.msg, str):
            redacted_msg, count = self.detector.redact_text(record.msg)
            if count > 0:
                record.msg = redacted_msg
                logger.debug(f"已脱敏 {count} 个敏感信息")

        return True

    def filter_record(self, record: logging.LogRecord) -> logging.LogRecord:
        """
        过滤日志记录，脱敏敏感信息（兼容Python 3.2+）

        Args:
            record: 日志记录对象

        Returns:
            logging.LogRecord: 脱敏后的日志记录对象
        """
        self.filter(record)
        return record


def apply_redact_filter_to_all_loggers():
    """
    为所有日志器添加脱敏过滤器
    """
    redact_filter = RedactFilter()

    # 为根日志器添加过滤器
    root_logger = logging.getLogger()
    root_logger.addFilter(redact_filter)

    # 为所有已创建的日志器添加过滤器
    for logger_name in logging.Logger.manager.loggerDict:
        logger = logging.getLogger(logger_name)
        logger.addFilter(redact_filter)

    logger.info("已为所有日志器添加脱敏过滤器")


# 全局实例
sensitive_detector = SensitiveInfoDetector()
