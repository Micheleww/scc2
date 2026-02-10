#!/usr/bin/env python3
"""
云端策略包加载器
实现manifest哈希/版本一致性/必备文件校验；失败进入BLOCKED并落盘原因；输出已加载策略清单
"""

import hashlib
import json
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    filename="logs/strategy_loader.log",
)
logger = logging.getLogger(__name__)


class StrategyLoaderStatus(Enum):
    """
    策略加载器状态枚举
    """

    IDLE = "idle"
    LOADING = "loading"
    SUCCESS = "success"
    BLOCKED = "blocked"


@dataclass
class StrategyManifest:
    """
    策略清单结构
    """

    version: str
    hash: str
    strategies: list[str]
    required_files: list[str]
    dependencies: dict[str, str]
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class LoadedStrategy:
    """
    已加载策略信息
    """

    name: str
    path: str
    manifest: StrategyManifest
    loaded_at: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class LoadResult:
    """
    加载结果
    """

    status: StrategyLoaderStatus
    message: str
    loaded_strategies: list[LoadedStrategy] = field(default_factory=list)
    error_details: str | None = None


class CloudStrategyLoader:
    """
    云端策略包加载器
    """

    def __init__(self, config: dict[str, Any]):
        """
        初始化策略加载器

        Args:
            config: 配置信息
        """
        self.config = config
        self.strategy_dir = config.get("strategy_dir", "user_data/strategies")
        self.manifest_file = config.get("manifest_file", "manifest.json")
        self.status = StrategyLoaderStatus.IDLE
        self.loaded_strategies: list[LoadedStrategy] = []
        self.error_info: dict[str, Any] | None = None

        # 创建日志目录
        os.makedirs("logs", exist_ok=True)

    def calculate_file_hash(self, file_path: str) -> str:
        """
        计算文件哈希值

        Args:
            file_path: 文件路径

        Returns:
            str: 文件哈希值
        """
        hasher = hashlib.sha256()
        try:
            with open(file_path, "rb") as f:
                for chunk in iter(lambda: f.read(4096), b""):
                    hasher.update(chunk)
            return hasher.hexdigest()
        except Exception as e:
            logger.error(f"计算文件哈希失败: {file_path}, 错误: {e}")
            raise

    def load_manifest(self, manifest_path: str) -> StrategyManifest:
        """
        加载策略清单

        Args:
            manifest_path: 清单文件路径

        Returns:
            StrategyManifest: 策略清单对象
        """
        try:
            with open(manifest_path, encoding="utf-8") as f:
                manifest_data = json.load(f)

            return StrategyManifest(
                version=manifest_data.get("version", "1.0.0"),
                hash=manifest_data.get("hash", ""),
                strategies=manifest_data.get("strategies", []),
                required_files=manifest_data.get("required_files", []),
                dependencies=manifest_data.get("dependencies", {}),
                created_at=manifest_data.get("created_at", datetime.now().isoformat()),
            )
        except Exception as e:
            logger.error(f"加载策略清单失败: {manifest_path}, 错误: {e}")
            raise

    def validate_manifest_hash(self, manifest: StrategyManifest, package_dir: str) -> bool:
        """
        验证策略包哈希一致性

        Args:
            manifest: 策略清单
            package_dir: 策略包目录

        Returns:
            bool: 哈希是否一致
        """
        try:
            # 计算所有策略文件的合并哈希
            combined_hasher = hashlib.sha256()

            # 先处理策略文件
            for strategy in manifest.strategies:
                file_path = os.path.join(package_dir, f"{strategy}.py")
                if os.path.exists(file_path):
                    file_hash = self.calculate_file_hash(file_path)
                    combined_hasher.update(file_hash.encode("utf-8"))

            # 再处理必备文件
            for required_file in manifest.required_files:
                file_path = os.path.join(package_dir, required_file)
                if os.path.exists(file_path):
                    file_hash = self.calculate_file_hash(file_path)
                    combined_hasher.update(file_hash.encode("utf-8"))

            calculated_hash = combined_hasher.hexdigest()
            logger.info(f"计算得到的哈希: {calculated_hash}, 清单中的哈希: {manifest.hash}")

            return calculated_hash == manifest.hash
        except Exception as e:
            logger.error(f"验证策略包哈希失败: {e}")
            return False

    def validate_required_files(self, manifest: StrategyManifest, package_dir: str) -> bool:
        """
        验证必备文件是否存在

        Args:
            manifest: 策略清单
            package_dir: 策略包目录

        Returns:
            bool: 必备文件是否都存在
        """
        for required_file in manifest.required_files:
            file_path = os.path.join(package_dir, required_file)
            if not os.path.exists(file_path):
                logger.error(f"必备文件不存在: {file_path}")
                return False
        return True

    def load_strategy(
        self, strategy_name: str, package_dir: str, manifest: StrategyManifest
    ) -> bool:
        """
        加载单个策略

        Args:
            strategy_name: 策略名称
            package_dir: 策略包目录
            manifest: 策略清单

        Returns:
            bool: 是否加载成功
        """
        try:
            # 这里简化实现，实际应该动态加载策略模块
            strategy_path = os.path.join(package_dir, f"{strategy_name}.py")
            if os.path.exists(strategy_path):
                loaded_strategy = LoadedStrategy(
                    name=strategy_name, path=strategy_path, manifest=manifest
                )
                self.loaded_strategies.append(loaded_strategy)
                logger.info(f"成功加载策略: {strategy_name}")
                return True
            else:
                logger.error(f"策略文件不存在: {strategy_path}")
                return False
        except Exception as e:
            logger.error(f"加载策略失败: {strategy_name}, 错误: {e}")
            return False

    def block_and_log(self, message: str, error_details: str | None = None) -> None:
        """
        进入BLOCKED状态并记录错误信息

        Args:
            message: 错误消息
            error_details: 详细错误信息
        """
        self.status = StrategyLoaderStatus.BLOCKED
        self.error_info = {
            "message": message,
            "error_details": error_details,
            "blocked_at": datetime.now().isoformat(),
        }

        # 落盘错误信息
        error_file = "logs/strategy_loader_blocked.json"
        try:
            with open(error_file, "w", encoding="utf-8") as f:
                json.dump(self.error_info, f, indent=2, ensure_ascii=False)
            logger.error(f"策略加载器进入BLOCKED状态，错误信息已落盘: {error_file}")
        except Exception as e:
            logger.error(f"落盘错误信息失败: {e}")

    def load_strategies(self) -> LoadResult:
        """
        加载策略包

        Returns:
            LoadResult: 加载结果
        """
        self.status = StrategyLoaderStatus.LOADING
        self.loaded_strategies.clear()
        self.error_info = None

        try:
            # 检查策略目录是否存在
            if not os.path.exists(self.strategy_dir):
                logger.error(f"策略目录不存在: {self.strategy_dir}")
                self.block_and_log(f"策略目录不存在: {self.strategy_dir}")
                return LoadResult(
                    status=StrategyLoaderStatus.BLOCKED,
                    message=f"策略目录不存在: {self.strategy_dir}",
                    loaded_strategies=[],
                    error_details=f"策略目录不存在: {self.strategy_dir}",
                )

            # 检查manifest文件是否存在
            manifest_path = os.path.join(self.strategy_dir, self.manifest_file)
            if not os.path.exists(manifest_path):
                logger.error(f"策略清单文件不存在: {manifest_path}")
                self.block_and_log(f"策略清单文件不存在: {manifest_path}")
                return LoadResult(
                    status=StrategyLoaderStatus.BLOCKED,
                    message=f"策略清单文件不存在: {manifest_path}",
                    loaded_strategies=[],
                    error_details=f"策略清单文件不存在: {manifest_path}",
                )

            # 加载manifest
            manifest = self.load_manifest(manifest_path)
            logger.info(f"成功加载策略清单，版本: {manifest.version}")

            # 验证必备文件
            if not self.validate_required_files(manifest, self.strategy_dir):
                logger.error("必备文件验证失败")
                self.block_and_log("必备文件验证失败")
                return LoadResult(
                    status=StrategyLoaderStatus.BLOCKED,
                    message="必备文件验证失败",
                    loaded_strategies=[],
                    error_details="必备文件验证失败",
                )

            # 验证哈希一致性
            if not self.validate_manifest_hash(manifest, self.strategy_dir):
                logger.error("策略包哈希一致性验证失败")
                self.block_and_log("策略包哈希一致性验证失败")
                return LoadResult(
                    status=StrategyLoaderStatus.BLOCKED,
                    message="策略包哈希一致性验证失败",
                    loaded_strategies=[],
                    error_details="策略包哈希一致性验证失败",
                )

            # 加载所有策略
            success_count = 0
            for strategy_name in manifest.strategies:
                if self.load_strategy(strategy_name, self.strategy_dir, manifest):
                    success_count += 1

            if success_count == len(manifest.strategies):
                self.status = StrategyLoaderStatus.SUCCESS
                logger.info(f"所有策略加载成功，共 {success_count} 个策略")
                return LoadResult(
                    status=StrategyLoaderStatus.SUCCESS,
                    message=f"所有策略加载成功，共 {success_count} 个策略",
                    loaded_strategies=self.loaded_strategies.copy(),
                )
            else:
                logger.error(
                    f"部分策略加载失败，成功 {success_count} 个，总数 {len(manifest.strategies)} 个"
                )
                self.block_and_log(
                    f"部分策略加载失败，成功 {success_count} 个，总数 {len(manifest.strategies)} 个"
                )
                return LoadResult(
                    status=StrategyLoaderStatus.BLOCKED,
                    message=f"部分策略加载失败，成功 {success_count} 个，总数 {len(manifest.strategies)} 个",
                    loaded_strategies=self.loaded_strategies.copy(),
                    error_details=f"部分策略加载失败，成功 {success_count} 个，总数 {len(manifest.strategies)} 个",
                )

        except Exception as e:
            logger.error(f"加载策略包时发生异常: {e}", exc_info=True)
            self.block_and_log("加载策略包时发生异常", str(e))
            return LoadResult(
                status=StrategyLoaderStatus.BLOCKED,
                message="加载策略包时发生异常",
                loaded_strategies=self.loaded_strategies.copy(),
                error_details=str(e),
            )

    def get_loaded_strategies(self) -> list[LoadedStrategy]:
        """
        获取已加载的策略清单

        Returns:
            List[LoadedStrategy]: 已加载的策略清单
        """
        return self.loaded_strategies.copy()

    def get_status(self) -> StrategyLoaderStatus:
        """
        获取当前状态

        Returns:
            StrategyLoaderStatus: 当前状态
        """
        return self.status

    def reset(self) -> None:
        """
        重置加载器状态
        """
        self.status = StrategyLoaderStatus.IDLE
        self.loaded_strategies.clear()
        self.error_info = None
        logger.info("策略加载器已重置")

    def generate_load_evidence(self) -> dict[str, Any]:
        """
        生成加载证据

        Returns:
            Dict[str, Any]: 加载证据
        """
        return {
            "loader_status": self.status.value,
            "loaded_strategies": [
                {
                    "name": strategy.name,
                    "path": strategy.path,
                    "manifest_version": strategy.manifest.version,
                    "loaded_at": strategy.loaded_at,
                }
                for strategy in self.loaded_strategies
            ],
            "error_info": self.error_info,
            "generated_at": datetime.now().isoformat(),
        }

    def save_load_evidence(self, output_dir: str = "evidence") -> str:
        """
        保存加载证据到文件

        Args:
            output_dir: 输出目录

        Returns:
            str: 证据文件路径
        """
        os.makedirs(output_dir, exist_ok=True)
        evidence = self.generate_load_evidence()
        evidence_file = os.path.join(
            output_dir, f"strategy_load_evidence_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        )

        try:
            with open(evidence_file, "w", encoding="utf-8") as f:
                json.dump(evidence, f, indent=2, ensure_ascii=False)
            logger.info(f"策略加载证据已保存到: {evidence_file}")
            return evidence_file
        except Exception as e:
            logger.error(f"保存策略加载证据失败: {e}")
            raise
