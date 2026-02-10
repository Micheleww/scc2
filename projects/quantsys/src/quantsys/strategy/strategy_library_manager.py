#!/usr/bin/env python3
"""
策略库管理模块
用于保存和管理不同的策略，实现策略的持久化存储和查询
"""

import json
import logging
import os
import pickle
from datetime import datetime
from typing import Any

import pandas as pd

# 配置日志
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class StrategyLibraryManager:
    """
    策略库管理器，用于保存和管理不同的策略
    """

    def __init__(self, library_path: str = "strategy_library"):
        """
        初始化策略库管理器

        Args:
            library_path: 策略库存储路径
        """
        self.library_path = library_path
        self.strategy_info_file = os.path.join(library_path, "strategy_info.json")
        self.strategies_dir = os.path.join(library_path, "strategies")

        # 确保目录存在
        os.makedirs(self.library_path, exist_ok=True)
        os.makedirs(self.strategies_dir, exist_ok=True)

        # 加载策略信息
        self.strategy_info = self._load_strategy_info()

        logger.info(f"策略库管理器初始化完成，策略库路径: {self.library_path}")

    def _load_strategy_info(self) -> dict[str, dict[str, Any]]:
        """
        加载策略信息

        Returns:
            strategy_info: 策略信息字典
        """
        if os.path.exists(self.strategy_info_file):
            with open(self.strategy_info_file) as f:
                return json.load(f)
        return {}

    def _save_strategy_info(self):
        """
        保存策略信息
        """
        with open(self.strategy_info_file, "w") as f:
            json.dump(self.strategy_info, f, indent=2, ensure_ascii=False)

    def save_strategy(self, strategy_data: dict[str, Any], strategy_name: str | None = None) -> str:
        """
        保存策略到策略库

        Args:
            strategy_data: 策略数据，包含模型、因子、配置等
            strategy_name: 策略名称，如果不提供则自动生成

        Returns:
            strategy_id: 保存的策略ID
        """
        # 生成策略ID
        if strategy_name:
            strategy_id = strategy_name
        else:
            strategy_id = f"strategy_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

        # 保存策略数据
        strategy_file = os.path.join(self.strategies_dir, f"{strategy_id}.pkl")
        with open(strategy_file, "wb") as f:
            pickle.dump(strategy_data, f)

        # 更新策略信息
        self.strategy_info[strategy_id] = {
            "strategy_id": strategy_id,
            "created_at": datetime.now().isoformat(),
            "model_type": strategy_data.get("model_type", "unknown"),
            "performance_metrics": strategy_data.get("performance_metrics", {}),
            "factor_count": len(strategy_data.get("best_factors", {}).columns)
            if isinstance(strategy_data.get("best_factors"), pd.DataFrame)
            else 0,
            "config": strategy_data.get("config", {}),
        }

        # 保存策略信息
        self._save_strategy_info()

        logger.info(f"策略保存成功，策略ID: {strategy_id}")
        return strategy_id

    def load_strategy(self, strategy_id: str) -> dict[str, Any] | None:
        """
        从策略库中加载策略

        Args:
            strategy_id: 策略ID

        Returns:
            strategy_data: 策略数据，如果策略不存在则返回None
        """
        strategy_file = os.path.join(self.strategies_dir, f"{strategy_id}.pkl")

        if os.path.exists(strategy_file):
            with open(strategy_file, "rb") as f:
                logger.info(f"策略加载成功，策略ID: {strategy_id}")
                return pickle.load(f)
        else:
            logger.error(f"策略不存在，策略ID: {strategy_id}")
            return None

    def get_strategy_info(self, strategy_id: str) -> dict[str, Any] | None:
        """
        获取策略信息

        Args:
            strategy_id: 策略ID

        Returns:
            strategy_info: 策略信息，如果策略不存在则返回None
        """
        return self.strategy_info.get(strategy_id)

    def list_strategies(self) -> list[dict[str, Any]]:
        """
        获取策略列表

        Returns:
            strategy_list: 策略信息列表
        """
        return list(self.strategy_info.values())

    def delete_strategy(self, strategy_id: str) -> bool:
        """
        删除策略

        Args:
            strategy_id: 策略ID

        Returns:
            success: 是否删除成功
        """
        strategy_file = os.path.join(self.strategies_dir, f"{strategy_id}.pkl")

        if os.path.exists(strategy_file):
            os.remove(strategy_file)
            if strategy_id in self.strategy_info:
                del self.strategy_info[strategy_id]
                self._save_strategy_info()
            logger.info(f"策略删除成功，策略ID: {strategy_id}")
            return True
        else:
            logger.error(f"策略不存在，策略ID: {strategy_id}")
            return False

    def update_strategy_info(self, strategy_id: str, update_data: dict[str, Any]) -> bool:
        """
        更新策略信息

        Args:
            strategy_id: 策略ID
            update_data: 要更新的策略信息

        Returns:
            success: 是否更新成功
        """
        if strategy_id in self.strategy_info:
            self.strategy_info[strategy_id].update(update_data)
            self._save_strategy_info()
            logger.info(f"策略信息更新成功，策略ID: {strategy_id}")
            return True
        else:
            logger.error(f"策略不存在，策略ID: {strategy_id}")
            return False

    def get_best_strategy(self, metric: str = "sharpe_ratio") -> str | None:
        """
        获取表现最好的策略

        Args:
            metric: 评估指标，默认为sharpe_ratio

        Returns:
            strategy_id: 表现最好的策略ID，如果没有策略则返回None
        """
        if not self.strategy_info:
            return None

        # 按指定指标排序，找到表现最好的策略
        best_strategy = max(
            self.strategy_info.items(),
            key=lambda x: x[1].get("performance_metrics", {}).get(metric, -float("inf")),
        )

        return best_strategy[0]

    def get_strategies_by_model_type(self, model_type: str) -> list[str]:
        """
        根据模型类型获取策略列表

        Args:
            model_type: 模型类型

        Returns:
            strategy_ids: 策略ID列表
        """
        return [
            strategy_id
            for strategy_id, info in self.strategy_info.items()
            if info.get("model_type") == model_type
        ]


# 测试代码
if __name__ == "__main__":
    # 初始化策略库管理器
    strategy_library = StrategyLibraryManager()

    # 测试保存策略
    test_strategy = {
        "model": "test_model",
        "model_type": "ridge",
        "best_factors": pd.DataFrame({"factor1": [1, 2, 3], "factor2": [4, 5, 6]}),
        "performance_metrics": {"sharpe_ratio": 1.5, "max_drawdown": -0.1},
        "config": {"n_factors": 50, "n_best": 15},
    }

    strategy_id = strategy_library.save_strategy(test_strategy)
    print(f"保存的策略ID: {strategy_id}")

    # 测试列出策略
    strategies = strategy_library.list_strategies()
    print(f"策略列表: {strategies}")

    # 测试加载策略
    loaded_strategy = strategy_library.load_strategy(strategy_id)
    print(f"加载的策略: {loaded_strategy}")

    # 测试获取策略信息
    strategy_info = strategy_library.get_strategy_info(strategy_id)
    print(f"策略信息: {strategy_info}")

    # 测试获取最佳策略
    best_strategy_id = strategy_library.get_best_strategy()
    print(f"最佳策略ID: {best_strategy_id}")

    # 测试更新策略信息
    strategy_library.update_strategy_info(strategy_id, {"description": "测试策略"})
    updated_info = strategy_library.get_strategy_info(strategy_id)
    print(f"更新后的策略信息: {updated_info}")

    # 测试删除策略
    # strategy_library.delete_strategy(strategy_id)
    # print(f"删除后策略列表: {strategy_library.list_strategies()}")
