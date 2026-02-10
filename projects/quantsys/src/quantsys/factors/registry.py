"""
因子注册表
定义因子的元数据结构和注册接口
"""

import inspect
from collections.abc import Callable
from dataclasses import dataclass

import numpy as np
import pandas as pd


# 因子维度标签枚举
class DimensionTag:
    DIRECTION = "direction"  # 方向类因子（多空信号）
    MAGNITUDE = "magnitude"  # 幅度类因子（信号强度）
    TIME = "time"  # 时间类因子（周期、趋势延续性）


@dataclass
class FactorMetadata:
    """因子元数据结构"""

    name: str  # 因子名称
    version: str  # 因子版本
    input_fields: list[str]  # 输入字段列表
    lookback: int  # 回溯窗口大小
    update_freq: str  # 更新频率（如 '1m', '1h', '1d'）
    dimension_tags: list[str]  # 维度标签，必须包含 Direction/Magnitude/Time 至少其一
    notes: str  # 因子说明
    risk_flags: list[str]  # 风险标签（如 'high_volatility', 'non_stationary'）
    created_at: str  # 创建时间
    updated_at: str  # 更新时间


@dataclass
class Factor:
    """因子定义"""

    metadata: FactorMetadata  # 因子元数据
    compute: Callable[[pd.DataFrame], pd.Series | np.ndarray]  # 因子计算函数


class FactorRegistry:
    """因子注册表，管理所有注册的因子"""

    def __init__(self):
        self.factors: dict[str, Factor] = {}
        self.validate_dimension_tags = True  # 是否强制验证维度标签

    def register_factor(self, metadata: FactorMetadata, compute: Callable) -> bool:
        """注册因子

        Args:
            metadata: 因子元数据
            compute: 因子计算函数

        Returns:
            bool: 注册是否成功
        """
        # 验证元数据完整性
        if not self._validate_metadata(metadata):
            return False

        # 验证计算函数签名
        if not self._validate_compute_signature(compute):
            return False

        # 生成因子唯一标识符
        factor_id = f"{metadata.name}_v{metadata.version}"

        # 检查因子是否已存在
        if factor_id in self.factors:
            logger.error(f"因子 {factor_id} 已存在")
            return False

        # 创建因子对象
        factor = Factor(metadata=metadata, compute=compute)

        # 注册因子
        self.factors[factor_id] = factor
        logger.info(f"因子 {factor_id} 注册成功")
        return True

    def _validate_metadata(self, metadata: FactorMetadata) -> bool:
        """验证因子元数据完整性"""
        # 验证名称和版本
        if not metadata.name or not metadata.version:
            logger.error("因子名称和版本不能为空")
            return False

        # 验证输入字段
        if not isinstance(metadata.input_fields, list) or not metadata.input_fields:
            logger.error("因子输入字段必须是非空列表")
            return False

        # 验证回溯窗口
        if metadata.lookback < 0:
            logger.error("因子回溯窗口不能为负数")
            return False

        # 验证维度标签
        if self.validate_dimension_tags:
            valid_tags = [DimensionTag.DIRECTION, DimensionTag.MAGNITUDE, DimensionTag.TIME]
            if not isinstance(metadata.dimension_tags, list) or not metadata.dimension_tags:
                logger.error("因子维度标签必须是非空列表")
                return False

            # 检查是否包含至少一个有效维度标签
            has_valid_tag = any(tag in valid_tags for tag in metadata.dimension_tags)
            if not has_valid_tag:
                logger.error(f"因子维度标签必须包含至少一个有效标签: {valid_tags}")
                return False

            # 检查所有标签是否有效
            for tag in metadata.dimension_tags:
                if tag not in valid_tags:
                    logger.error(f"无效的维度标签: {tag}，有效标签: {valid_tags}")
                    return False

        # 验证风险标签
        if not isinstance(metadata.risk_flags, list):
            logger.error("因子风险标签必须是列表")
            return False

        return True

    def _validate_compute_signature(self, compute: Callable) -> bool:
        """验证因子计算函数签名"""
        sig = inspect.signature(compute)
        params = list(sig.parameters.keys())

        # 检查函数参数
        if len(params) != 1:
            logger.error("因子计算函数必须接受且仅接受一个参数（market_data）")
            return False

        return True

    def get_factor(self, name: str, version: str | None = None) -> Factor | None:
        """获取因子

        Args:
            name: 因子名称
            version: 因子版本，不指定则返回最新版本

        Returns:
            Optional[Factor]: 因子对象，如果不存在则返回 None
        """
        if version:
            factor_id = f"{name}_v{version}"
            return self.factors.get(factor_id)
        else:
            # 返回最新版本
            factor_ids = [fid for fid in self.factors if fid.startswith(f"{name}_v")]
            if not factor_ids:
                return None
            # 按版本号排序，返回最新版本
            factor_ids.sort(
                key=lambda x: tuple(map(int, x.split("_v")[1].split("."))), reverse=True
            )
            return self.factors[factor_ids[0]]

    def list_factors(self) -> list[str]:
        """列出所有注册的因子"""
        return list(self.factors.keys())

    def get_factor_metadata(self, factor_id: str) -> FactorMetadata | None:
        """获取因子元数据"""
        factor = self.factors.get(factor_id)
        return factor.metadata if factor else None

    def remove_factor(self, factor_id: str) -> bool:
        """移除因子"""
        if factor_id in self.factors:
            del self.factors[factor_id]
            logger.info(f"因子 {factor_id} 已移除")
            return True
        else:
            logger.error(f"因子 {factor_id} 不存在")
            return False

    def clear(self) -> None:
        """清空注册表"""
        self.factors.clear()
        logger.info("因子注册表已清空")


# 全局因子注册表实例
factor_registry = FactorRegistry()

# 日志配置
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.FileHandler("factor_registry.log"), logging.StreamHandler()],
)
logger = logging.getLogger("FactorRegistry")
