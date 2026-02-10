#!/usr/bin/env python3
"""
启动校验模块
实现系统启动时的密钥完整性校验，缺失则BLOCKED
"""

import logging
import sys
from pathlib import Path

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class StartupValidator:
    """
    启动校验器

    功能：
    1. 校验密钥完整性
    2. 校验配置文件存在性
    3. 校验必要目录存在性
    4. 缺失则BLOCKED系统
    """

    def __init__(self):
        """初始化启动校验器"""
        self.is_valid = False
        self.blocking_reasons = []
        self.warnings = []

        logger.info("启动校验器初始化完成")

    def validate_all(self) -> bool:
        """
        执行所有校验

        Returns:
            bool: 是否通过校验
        """
        logger.info("开始启动校验...")

        # 校验密钥完整性
        self._validate_secrets()

        # 校验配置文件
        self._validate_config_files()

        # 校验必要目录
        self._validate_directories()

        # 校验Python环境
        self._validate_python_env()

        self.is_valid = len(self.blocking_reasons) == 0

        if self.is_valid:
            logger.info("启动校验通过")
            return True
        else:
            logger.error("启动校验失败，系统将被BLOCKED")
            for reason in self.blocking_reasons:
                logger.error(f"  BLOCKED: {reason}")

            if self.warnings:
                logger.warning("警告信息：")
                for warning in self.warnings:
                    logger.warning(f"  WARNING: {warning}")

            return False

    def _validate_secrets(self):
        """
        校验密钥完整性
        """
        logger.info("校验密钥完整性...")

        try:
            from src.quantsys.common.secret_manager import create_secret_manager

            manager = create_secret_manager()

            if not manager.is_valid:
                self.blocking_reasons.extend(manager.validation_errors)
            else:
                logger.info("密钥校验通过")

        except Exception as e:
            self.blocking_reasons.append(f"密钥校验失败: {e}")

    def _validate_config_files(self):
        """
        校验配置文件存在性
        """
        logger.info("校验配置文件...")

        config_files = [
            "configs/runner_config.json",
            "configs/config.json",
            "configs/config_backtest.json",
            "configs/config_live.json",
        ]

        for config_file in config_files:
            path = Path(config_file)
            if not path.exists():
                self.warnings.append(f"配置文件不存在: {config_file}")
            else:
                logger.info(f"配置文件存在: {config_file}")

    def _validate_directories(self):
        """
        校验必要目录存在性
        """
        logger.info("校验必要目录...")

        required_dirs = ["logs", "reports", "data", "config"]

        for dir_path in required_dirs:
            path = Path(dir_path)
            if not path.exists():
                try:
                    path.mkdir(parents=True, exist_ok=True)
                    logger.info(f"创建目录: {dir_path}")
                except Exception as e:
                    self.warnings.append(f"无法创建目录 {dir_path}: {e}")
            else:
                logger.info(f"目录存在: {dir_path}")

    def _validate_python_env(self):
        """
        校验Python环境
        """
        logger.info("校验Python环境...")

        python_version = sys.version_info
        logger.info(
            f"Python版本: {python_version.major}.{python_version.minor}.{python_version.micro}"
        )

        if python_version.major < 3 or (python_version.major == 3 and python_version.minor < 8):
            self.blocking_reasons.append(
                f"Python版本过低: {python_version.major}.{python_version.minor}.{python_version.micro}，需要3.8+"
            )
        else:
            logger.info("Python版本校验通过")

    def get_status(self) -> dict:
        """
        获取校验状态

        Returns:
            dict: 状态信息
        """
        return {
            "is_valid": self.is_valid,
            "blocking_reasons": self.blocking_reasons,
            "warnings": self.warnings,
            "blocking_count": len(self.blocking_reasons),
            "warning_count": len(self.warnings),
        }


def validate_startup() -> bool:
    """
    执行启动校验

    Returns:
        bool: 是否通过校验
    """
    validator = StartupValidator()
    return validator.validate_all()


def get_startup_status() -> dict:
    """
    获取启动状态

    Returns:
        dict: 启动状态信息
    """
    validator = StartupValidator()
    validator.validate_all()
    return validator.get_status()


if __name__ == "__main__":
    import json

    status = get_startup_status()

    print(json.dumps(status, indent=2, ensure_ascii=False))

    if not status["is_valid"]:
        logger.error("启动校验失败，系统BLOCKED")
        sys.exit(1)
    else:
        logger.info("启动校验通过")
        sys.exit(0)
