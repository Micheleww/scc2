#!/usr/bin/env python3
"""
统一状态存储接口
提供统一的状态存储接口，支持数据库和文件两种存储方式
"""

import json
import logging
from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path
from typing import Any

# 配置日志
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class StateStorage(ABC):
    """
    状态存储抽象基类
    定义统一的状态存储接口
    """

    @abstractmethod
    def save_order(self, order: dict[str, Any]) -> bool:
        """保存订单"""
        pass

    @abstractmethod
    def get_order(self, order_id: str) -> dict[str, Any] | None:
        """获取订单"""
        pass

    @abstractmethod
    def update_order(self, order_id: str, updates: dict[str, Any]) -> bool:
        """更新订单"""
        pass

    @abstractmethod
    def save_position(self, symbol: str, position: dict[str, Any]) -> bool:
        """保存持仓"""
        pass

    @abstractmethod
    def get_position(self, symbol: str) -> dict[str, Any] | None:
        """获取持仓"""
        pass

    @abstractmethod
    def get_all_positions(self) -> dict[str, dict[str, Any]]:
        """获取所有持仓"""
        pass

    @abstractmethod
    def save_portfolio(self, portfolio: dict[str, Any]) -> bool:
        """保存组合状态"""
        pass

    @abstractmethod
    def get_portfolio(self) -> dict[str, Any] | None:
        """获取组合状态"""
        pass


class FileStateStorage(StateStorage):
    """
    文件状态存储实现
    使用JSON文件存储状态（用于测试和小规模使用）
    """

    def __init__(self, storage_dir: str = "data/state"):
        """
        初始化文件状态存储

        Args:
            storage_dir: 存储目录
        """
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)

        # 文件路径
        self.orders_file = self.storage_dir / "orders.json"
        self.positions_file = self.storage_dir / "positions.json"
        self.portfolio_file = self.storage_dir / "portfolio.json"

        # 初始化文件
        self._init_files()

        logger.info(f"FileStateStorage initialized: {self.storage_dir}")

    def _init_files(self):
        """初始化存储文件"""
        if not self.orders_file.exists():
            self._write_json(self.orders_file, {})
        if not self.positions_file.exists():
            self._write_json(self.positions_file, {})
        if not self.portfolio_file.exists():
            self._write_json(self.portfolio_file, {})

    def _read_json(self, file_path: Path) -> dict[str, Any]:
        """读取JSON文件"""
        try:
            with open(file_path, encoding="utf-8") as f:
                return json.load(f)
        except (OSError, json.JSONDecodeError) as e:
            logger.error(f"Failed to read {file_path}: {e}")
            return {}

    def _write_json(self, file_path: Path, data: dict[str, Any]):
        """写入JSON文件"""
        try:
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except OSError as e:
            logger.error(f"Failed to write {file_path}: {e}")

    def save_order(self, order: dict[str, Any]) -> bool:
        """保存订单"""
        orders = self._read_json(self.orders_file)
        order_id = order.get("order_id") or order.get("clOrdId") or order.get("ordId")
        if order_id:
            orders[order_id] = order
            self._write_json(self.orders_file, orders)
            return True
        return False

    def get_order(self, order_id: str) -> dict[str, Any] | None:
        """获取订单"""
        orders = self._read_json(self.orders_file)
        return orders.get(order_id)

    def update_order(self, order_id: str, updates: dict[str, Any]) -> bool:
        """更新订单"""
        orders = self._read_json(self.orders_file)
        if order_id in orders:
            orders[order_id].update(updates)
            orders[order_id]["updated_at"] = datetime.now().isoformat()
            self._write_json(self.orders_file, orders)
            return True
        return False

    def save_position(self, symbol: str, position: dict[str, Any]) -> bool:
        """保存持仓"""
        positions = self._read_json(self.positions_file)
        positions[symbol] = position
        self._write_json(self.positions_file, positions)
        return True

    def get_position(self, symbol: str) -> dict[str, Any] | None:
        """获取持仓"""
        positions = self._read_json(self.positions_file)
        return positions.get(symbol)

    def get_all_positions(self) -> dict[str, dict[str, Any]]:
        """获取所有持仓"""
        return self._read_json(self.positions_file)

    def save_portfolio(self, portfolio: dict[str, Any]) -> bool:
        """保存组合状态"""
        self._write_json(self.portfolio_file, portfolio)
        return True

    def get_portfolio(self) -> dict[str, Any] | None:
        """获取组合状态"""
        return self._read_json(self.portfolio_file)


class DatabaseStateStorage(StateStorage):
    """
    数据库状态存储实现
    使用数据库存储状态（用于生产环境）
    """

    def __init__(self, db_connection: Any):
        """
        初始化数据库状态存储

        Args:
            db_connection: 数据库连接对象
        """
        self.db = db_connection
        logger.info("DatabaseStateStorage initialized")

    def save_order(self, order: dict[str, Any]) -> bool:
        """保存订单到数据库"""
        # TODO: 实现数据库保存逻辑
        logger.warning("DatabaseStateStorage.save_order not implemented")
        return False

    def get_order(self, order_id: str) -> dict[str, Any] | None:
        """从数据库获取订单"""
        # TODO: 实现数据库查询逻辑
        logger.warning("DatabaseStateStorage.get_order not implemented")
        return None

    def update_order(self, order_id: str, updates: dict[str, Any]) -> bool:
        """更新数据库中的订单"""
        # TODO: 实现数据库更新逻辑
        logger.warning("DatabaseStateStorage.update_order not implemented")
        return False

    def save_position(self, symbol: str, position: dict[str, Any]) -> bool:
        """保存持仓到数据库"""
        # TODO: 实现数据库保存逻辑
        logger.warning("DatabaseStateStorage.save_position not implemented")
        return False

    def get_position(self, symbol: str) -> dict[str, Any] | None:
        """从数据库获取持仓"""
        # TODO: 实现数据库查询逻辑
        logger.warning("DatabaseStateStorage.get_position not implemented")
        return None

    def get_all_positions(self) -> dict[str, dict[str, Any]]:
        """从数据库获取所有持仓"""
        # TODO: 实现数据库查询逻辑
        logger.warning("DatabaseStateStorage.get_all_positions not implemented")
        return {}

    def save_portfolio(self, portfolio: dict[str, Any]) -> bool:
        """保存组合状态到数据库"""
        # TODO: 实现数据库保存逻辑
        logger.warning("DatabaseStateStorage.save_portfolio not implemented")
        return False

    def get_portfolio(self) -> dict[str, Any] | None:
        """从数据库获取组合状态"""
        # TODO: 实现数据库查询逻辑
        logger.warning("DatabaseStateStorage.get_portfolio not implemented")
        return None


class StateStorageFactory:
    """
    状态存储工厂
    根据配置创建对应的状态存储实例
    """

    @staticmethod
    def create(storage_type: str = "file", **kwargs) -> StateStorage:
        """
        创建状态存储实例

        Args:
            storage_type: 存储类型，"file" 或 "database"
            **kwargs: 其他参数

        Returns:
            StateStorage: 状态存储实例
        """
        if storage_type == "file":
            storage_dir = kwargs.get("storage_dir", "data/state")
            return FileStateStorage(storage_dir)
        elif storage_type == "database":
            db_connection = kwargs.get("db_connection")
            if not db_connection:
                raise ValueError("Database storage requires db_connection parameter")
            return DatabaseStateStorage(db_connection)
        else:
            raise ValueError(f"Unknown storage type: {storage_type}")
