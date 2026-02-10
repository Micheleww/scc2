#!/usr/bin/env python3
"""
Run ID 管理器
功能：生成和管理统一的run_id，确保所有产物（日志、回测结果、优化结果等）都使用统一的run_id关联
"""

import os
from datetime import datetime
from pathlib import Path


class RunIDManager:
    """
    Run ID 管理器类
    """

    def __init__(self, run_id=None, strategy_version=None, factor_version=None):
        """
        初始化Run ID管理器

        Args:
            run_id: 可选，指定run_id。如果不指定，将生成新的run_id
            strategy_version: 可选，策略版本
            factor_version: 可选，因子版本
        """
        self._run_id = run_id or self.generate_run_id()
        self._strategy_version = strategy_version
        self._factor_version = factor_version
        self._run_dir = self.create_run_directory()

    @staticmethod
    def generate_run_id():
        """
        生成唯一的run_id
        格式：YYYYMMDD_HHMMSS

        Returns:
            str: 生成的run_id
        """
        return datetime.now().strftime("%Y%m%d_%H%M%S")

    def create_run_directory(self):
        """
        创建run_id对应的产物目录
        结构：runs/{run_id}/
             ├── logs/           # 日志文件
             ├── backtest/       # 回测结果
             ├── optimize/       # 优化结果
             ├── data/           # 数据文件
             └── strategy/       # 策略文件

        Returns:
            Path: run目录的Path对象
        """
        run_dir = Path(f"runs/{self._run_id}")

        # 创建主目录
        run_dir.mkdir(parents=True, exist_ok=True)

        # 创建子目录
        subdirs = ["logs", "backtest", "optimize", "data", "strategy"]
        for subdir in subdirs:
            (run_dir / subdir).mkdir(exist_ok=True)

        return run_dir

    @property
    def run_id(self):
        """
        获取run_id

        Returns:
            str: run_id
        """
        return self._run_id

    @property
    def run_dir(self):
        """
        获取run目录路径

        Returns:
            str: run目录路径
        """
        return str(self._run_dir)

    @property
    def strategy_version(self):
        """
        获取策略版本

        Returns:
            str: 策略版本
        """
        return self._strategy_version

    @property
    def factor_version(self):
        """
        获取因子版本

        Returns:
            str: 因子版本
        """
        return self._factor_version

    def get_logs_dir(self):
        """
        获取日志目录路径

        Returns:
            str: 日志目录路径
        """
        return str(self._run_dir / "logs")

    def get_backtest_dir(self):
        """
        获取回测结果目录路径

        Returns:
            str: 回测结果目录路径
        """
        return str(self._run_dir / "backtest")

    def get_optimize_dir(self):
        """
        获取优化结果目录路径

        Returns:
            str: 优化结果目录路径
        """
        return str(self._run_dir / "optimize")

    def get_data_dir(self):
        """
        获取数据目录路径

        Returns:
            str: 数据目录路径
        """
        return str(self._run_dir / "data")

    def get_strategy_dir(self):
        """
        获取策略目录路径

        Returns:
            str: 策略目录路径
        """
        return str(self._run_dir / "strategy")

    def get_file_path(self, category, filename, include_run_id=True):
        """
        获取指定分类的文件路径

        Args:
            category: 文件分类，可选值：logs, backtest, optimize, data, strategy
            filename: 文件名
            include_run_id: 是否在文件名中包含run_id，默认True

        Returns:
            str: 完整的文件路径
        """
        category_dirs = {
            "logs": self.get_logs_dir(),
            "backtest": self.get_backtest_dir(),
            "optimize": self.get_optimize_dir(),
            "data": self.get_data_dir(),
            "strategy": self.get_strategy_dir(),
        }

        if category not in category_dirs:
            raise ValueError(f"Invalid category: {category}")

        # 添加run_id到文件名
        if include_run_id:
            name, ext = os.path.splitext(filename)
            filename = f"{name}_{self._run_id}{ext}"

        return os.path.join(category_dirs[category], filename)
