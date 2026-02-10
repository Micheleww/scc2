#!/usr/bin/env python3
"""
配置加载器
实现从TaskHub/index优先加载配置，其次从configs目录
"""

import json
import os
from typing import Any


class ConfigLoader:
    """
    配置加载器，支持从多个来源加载配置，优先级：
    1. TaskHub/index
    2. configs目录
    """

    def __init__(self, taskhub_dir: str = "taskhub", configs_dir: str = "configs"):
        """
        初始化配置加载器

        Args:
            taskhub_dir: TaskHub目录路径
            configs_dir: 配置目录路径
        """
        self.taskhub_dir = taskhub_dir
        self.configs_dir = configs_dir
        self.index_dir = os.path.join(taskhub_dir, "index")

        # 确保目录存在
        os.makedirs(self.index_dir, exist_ok=True)

    def load_config(self, config_name: str) -> dict[str, Any]:
        """
        加载配置文件

        Args:
            config_name: 配置文件名（不含扩展名）

        Returns:
            Dict[str, Any]: 加载的配置
        """
        config = {}

        # 1. 优先从TaskHub/index加载
        taskhub_config_path = os.path.join(self.index_dir, f"{config_name}.json")
        if os.path.exists(taskhub_config_path):
            try:
                with open(taskhub_config_path, encoding="utf-8") as f:
                    config = json.load(f)
                return config
            except (OSError, json.JSONDecodeError) as e:
                print(f"从TaskHub/index加载配置失败: {e}")

        # 2. 其次从configs目录加载
        configs_config_path = os.path.join(self.configs_dir, f"{config_name}.json")
        if os.path.exists(configs_config_path):
            try:
                with open(configs_config_path, encoding="utf-8") as f:
                    config = json.load(f)
                return config
            except (OSError, json.JSONDecodeError) as e:
                print(f"从configs目录加载配置失败: {e}")

        return config

    def save_config(self, config_name: str, config: dict[str, Any]) -> None:
        """
        保存配置到TaskHub/index

        Args:
            config_name: 配置文件名（不含扩展名）
            config: 要保存的配置
        """
        taskhub_config_path = os.path.join(self.index_dir, f"{config_name}.json")
        try:
            with open(taskhub_config_path, "w", encoding="utf-8") as f:
                json.dump(config, f, indent=2, ensure_ascii=False)
        except OSError as e:
            print(f"保存配置到TaskHub/index失败: {e}")

    def get_trade_live_switch(self) -> bool:
        """
        获取trade_live开关状态

        Returns:
            bool: trade_live开关状态，默认false
        """
        # 从配置中获取trade_live开关
        config = self.load_config("live_config")
        return config.get("trade_live", False)

    def set_trade_live_switch(self, enabled: bool) -> None:
        """
        设置trade_live开关状态

        Args:
            enabled: 开关状态
        """
        config = self.load_config("live_config")
        config["trade_live"] = enabled
        self.save_config("live_config", config)

    def get_real_order_config(self) -> dict[str, Any]:
        """
        获取真单配置

        Returns:
            Dict[str, Any]: 真单配置
        """
        config = self.load_config("live_config")
        return config.get("real_order", {})
