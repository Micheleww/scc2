#!/usr/bin/env python3

"""
因子计算引擎：按依赖排序批计算，输出统一格式与可用性标记
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import pandas as pd
from tqdm import tqdm

from .factor_registry import FactorRegistry

logger = logging.getLogger(__name__)


class FactorEngine:
    """因子计算引擎，按依赖顺序批量计算"""

    def __init__(self, registry_path: str = None):
        """初始化因子引擎"""
        self.registry = FactorRegistry(registry_path) if registry_path else None
        self.factor_specs: dict[str, dict[str, Any]] = {}
        self.availability_masks: dict[str, pd.Series] = {}

    def register_factor(self, spec: dict[str, Any]):
        """注册因子规格"""
        self.factor_specs[spec["code"]] = spec

    def register_factors(self, specs: list[dict[str, Any]]):
        """批量注册因子规格"""
        for spec in specs:
            self.register_factor(spec)

    def _get_dependencies(self, code: str) -> set[str]:
        """获取因子的所有依赖（递归）"""
        deps = set()
        spec = self.factor_specs[code]

        for dep in spec.dependencies:
            deps.add(dep)
            if dep in self.factor_specs:
                deps.update(self._get_dependencies(dep))

        return deps

    def _topological_sort(self) -> list[str]:
        """对因子进行拓扑排序，确保依赖先计算"""
        # 构建依赖图
        graph = {code: spec["dependencies"] for code, spec in self.factor_specs.items()}

        # 计算入度
        in_degree = dict.fromkeys(graph, 0)
        for code in graph:
            for dep in graph[code]:
                if dep in in_degree:
                    in_degree[dep] += 1

        # 拓扑排序
        result = []
        queue = [code for code in in_degree if in_degree[code] == 0]

        while queue:
            code = queue.pop(0)
            result.append(code)

            for neighbor in graph[code]:
                if neighbor in in_degree:
                    in_degree[neighbor] -= 1
                    if in_degree[neighbor] == 0:
                        queue.append(neighbor)

        # 检查是否有环
        if len(result) != len(self.factor_specs):
            raise ValueError("Factor dependencies contain cycles")

        return result

    def calculate(self, data: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
        """批量计算因子，返回结果和可用性掩码"""
        logger.info(f"开始计算 {len(self.factor_specs)} 个因子")

        # 拓扑排序
        sorted_codes = self._topological_sort()
        logger.info(f"因子计算顺序: {', '.join(sorted_codes)}")

        # 准备结果和掩码
        result = pd.DataFrame(index=data.index)
        availability = pd.DataFrame(index=data.index, columns=sorted_codes, dtype=bool)
        availability[:] = True

        # 计算每个因子
        for code in tqdm(sorted_codes):
            spec = self.factor_specs[code]
            logger.info(f"计算因子: {spec['code']} ({spec['name']})")

            # 检查依赖是否可用
            dep_available = True
            for dep in spec["dependencies"]:
                if dep not in result.columns and dep not in data.columns:
                    logger.error(f"因子 {code} 依赖 {dep} 不存在，跳过计算")
                    availability[code] = False
                    dep_available = False
                    break

            if not dep_available:
                continue

            # 简单的因子计算示例（实际实现需要根据formula进行）
            try:
                # 这里使用简单的计算作为示例，实际应该根据formula解析执行
                if spec["formula"] == "rolling_mean":
                    result[spec["output_col"]] = data[spec["dependencies"][0]].rolling(20).mean()
                elif spec["formula"] == "rolling_std":
                    result[spec["output_col"]] = data[spec["dependencies"][0]].rolling(20).std()
                elif spec["formula"] == "returns":
                    result[spec["output_col"]] = data[spec["dependencies"][0]].pct_change()
                else:
                    # 默认计算
                    result[spec["output_col"]] = data[spec["dependencies"][0]]

                # 计算可用性掩码
                availability[code] = result[spec["output_col"]].notna()
            except Exception as e:
                logger.error(f"计算因子 {code} 失败: {e}")
                availability[code] = False
                result[spec["output_col"]] = None

        return result, availability

    def save_results(
        self, result: pd.DataFrame, availability: pd.DataFrame, output_dir: str = "factors"
    ):
        """保存计算结果到文件"""
        output_path = Path(output_dir)
        output_path.mkdir(exist_ok=True)

        # 保存因子结果
        result_path = output_path / "factors_result.parquet"
        result.to_parquet(result_path)
        logger.info(f"因子结果已保存到: {result_path}")

        # 保存可用性掩码
        availability_path = output_path / "availability_mask.parquet"
        availability.to_parquet(availability_path)
        logger.info(f"可用性掩码已保存到: {availability_path}")

        return result_path, availability_path
