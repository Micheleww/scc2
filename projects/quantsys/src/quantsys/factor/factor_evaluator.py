#!/usr/bin/env python3
"""
因子评估器

用于评估因子的有效性，包括IC/IR、分层收益、稳定性等指标
"""

from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


class FactorEvaluator:
    """
    因子评估器类
    """

    def __init__(
        self, dataset_manifest: dict[str, Any], data_version: str = "v1", random_seed: int = 42
    ):
        """
        初始化因子评估器

        Args:
            dataset_manifest: 数据集manifest
            data_version: 数据版本
            random_seed: 随机种子
        """
        self.dataset_manifest = dataset_manifest
        self.data_version = data_version
        self.random_seed = random_seed
        self.data = None

    def load_data(self) -> None:
        """
        加载数据集
        """
        # 加载特征数据
        features_path = Path("dataset/features/features_data.parquet")
        if not features_path.exists():
            print("警告: 找不到特征数据，尝试从clean数据生成特征...")
            self._generate_features()
        else:
            self.data = pd.read_parquet(features_path)
            print(f"   已加载特征数据: {len(self.data)} 样本")

        # 确保数据按时间排序
        self.data = self.data.sort_values(by=["symbol", "timestamp"])

    def _generate_features(self) -> None:
        """
        从clean数据生成特征
        """
        # 加载clean数据
        clean_path = Path("dataset/clean/clean_data.parquet")
        if not clean_path.exists():
            raise FileNotFoundError(f"找不到clean数据: {clean_path}")

        clean_df = pd.read_parquet(clean_path)
        clean_df = clean_df.sort_values(by=["symbol", "timestamp"])

        # 生成特征
        features_df = clean_df.copy()

        # 计算收益率
        features_df["returns"] = features_df.groupby("symbol")["close"].pct_change()

        # 计算24h波动率（假设1h数据，24个周期）
        features_df["volatility_24h"] = (
            features_df.groupby("symbol")["returns"]
            .rolling(window=24)
            .std()
            .reset_index(level=0, drop=True)
        )

        # 计算RSI-14
        def calculate_rsi(series, window=14):
            delta = series.diff()
            gain = (delta.where(delta > 0, 0)).rolling(window=window).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(window=window).mean()
            rs = gain / loss
            rsi = 100 - (100 / (1 + rs))
            return rsi

        features_df["rsi_14"] = features_df.groupby("symbol")["close"].apply(
            lambda x: calculate_rsi(x, window=14)
        )

        # 计算简单移动平均线
        features_df["ma_5"] = (
            features_df.groupby("symbol")["close"]
            .rolling(window=5)
            .mean()
            .reset_index(level=0, drop=True)
        )
        features_df["ma_20"] = (
            features_df.groupby("symbol")["close"]
            .rolling(window=20)
            .mean()
            .reset_index(level=0, drop=True)
        )
        features_df["ma_50"] = (
            features_df.groupby("symbol")["close"]
            .rolling(window=50)
            .mean()
            .reset_index(level=0, drop=True)
        )

        # 计算MACD
        def calculate_macd(series, fast=12, slow=26, signal=9):
            exp1 = series.ewm(span=fast, adjust=False).mean()
            exp2 = series.ewm(span=slow, adjust=False).mean()
            macd = exp1 - exp2
            signal_line = macd.ewm(span=signal, adjust=False).mean()
            hist = macd - signal_line
            return macd, signal_line, hist

        macd, signal_line, hist = calculate_macd(
            features_df.groupby("symbol")["close"]
            .apply(lambda x: x)
            .reset_index(level=0, drop=True)
        )
        features_df["macd"] = macd
        features_df["macd_signal"] = signal_line
        features_df["macd_hist"] = hist

        # 填充缺失值
        features_df = features_df.fillna(method="ffill").fillna(method="bfill")

        self.data = features_df
        print(f"   已生成特征数据: {len(self.data)} 样本")

    def calculate_ic(self, factor: str, return_window: int = 1) -> tuple[float, float]:
        """
        计算IC（信息系数）和IR（信息比率）

        Args:
            factor: 因子名称
            return_window: 收益窗口（默认1天）

        Returns:
            tuple: (IC均值, IR)
        """
        # 计算未来收益
        self.data["future_returns"] = self.data.groupby("symbol")["returns"].shift(-return_window)

        # 计算IC
        ic_values = []
        for timestamp in self.data["timestamp"].unique():
            # 获取当前时间戳的因子和未来收益
            subset = self.data[self.data["timestamp"] == timestamp]

            # 计算相关系数
            if len(subset) > 1:
                correlation = subset[[factor, "future_returns"]].corr().iloc[0, 1]
                if not np.isnan(correlation):
                    ic_values.append(correlation)

        # 计算IC均值和IR
        ic_mean = np.mean(ic_values)
        ir = ic_mean / np.std(ic_values) if np.std(ic_values) != 0 else 0

        return ic_mean, ir

    def calculate_risk_adjusted_return(self, factor: str, n_quantiles: int = 5) -> dict[str, Any]:
        """
        计算分层收益

        Args:
            factor: 因子名称
            n_quantiles: 分位数数量

        Returns:
            dict: 分层收益结果
        """
        # 对因子进行分层
        self.data[f"{factor}_quantile"] = self.data.groupby("timestamp")[factor].transform(
            lambda x: pd.qcut(x, q=n_quantiles, labels=False, duplicates="drop") + 1
        )

        # 计算各层的平均收益
        quantile_returns = self.data.groupby(f"{factor}_quantile")["returns"].agg(
            ["mean", "std", "count"]
        )

        # 计算最高层与最低层的收益差
        if len(quantile_returns) >= 2:
            top_bottom_diff = quantile_returns.iloc[-1]["mean"] - quantile_returns.iloc[0]["mean"]
            top_bottom_ir = (
                top_bottom_diff
                / (quantile_returns.iloc[-1]["std"] + quantile_returns.iloc[0]["std"])
                if (quantile_returns.iloc[-1]["std"] + quantile_returns.iloc[0]["std"]) != 0
                else 0
            )
        else:
            top_bottom_diff = 0
            top_bottom_ir = 0

        return {
            "quantile_returns": quantile_returns.to_dict(),
            "top_bottom_diff": top_bottom_diff,
            "top_bottom_ir": top_bottom_ir,
        }

    def calculate_stability(self, factor: str, test_ratio: float = 0.3) -> dict[str, Any]:
        """
        计算因子稳定性

        Args:
            factor: 因子名称
            test_ratio: 测试集比例

        Returns:
            dict: 稳定性结果
        """
        # 按时间划分训练集和测试集
        timestamps = sorted(self.data["timestamp"].unique())
        split_idx = int(len(timestamps) * (1 - test_ratio))
        train_timestamps = timestamps[:split_idx]
        test_timestamps = timestamps[split_idx:]

        train_data = self.data[self.data["timestamp"].isin(train_timestamps)]
        test_data = self.data[self.data["timestamp"].isin(test_timestamps)]

        # 计算训练集和测试集的因子分布
        train_mean = train_data[factor].mean()
        train_std = train_data[factor].std()
        test_mean = test_data[factor].mean()
        test_std = test_data[factor].std()

        # 计算稳定性指标
        mean_diff = abs(train_mean - test_mean) / train_std if train_std != 0 else 0
        std_ratio = test_std / train_std if train_std != 0 else 0

        # 计算IC稳定性
        train_ic, _ = self.calculate_ic(factor, return_window=1)
        test_ic, _ = self.calculate_ic(factor, return_window=1)
        ic_stability = abs(train_ic - test_ic)

        return {
            "mean_diff": mean_diff,
            "std_ratio": std_ratio,
            "ic_stability": ic_stability,
            "train_ic": train_ic,
            "test_ic": test_ic,
        }

    def evaluate_factors(self, factors: list[str]) -> dict[str, Any]:
        """
        评估多个因子

        Args:
            factors: 因子列表

        Returns:
            dict: 评估结果
        """
        results = {
            "factors": [],
            "metadata": {
                "timestamp": datetime.now().isoformat(),
                "random_seed": self.random_seed,
                "data_version": self.data_version,
                "dataset_manifest": self.dataset_manifest["version"],
            },
        }

        for factor in factors:
            if factor not in self.data.columns:
                print(f"警告: 因子 {factor} 不在数据中")
                continue

            print(f"   评估因子: {factor}")

            # 计算IC和IR
            ic_mean, ir = self.calculate_ic(factor)

            # 计算分层收益
            risk_adjusted_return = self.calculate_risk_adjusted_return(factor)

            # 计算稳定性
            stability = self.calculate_stability(factor)

            # 添加结果
            results["factors"].append(
                {
                    "name": factor,
                    "ic_mean": float(ic_mean),
                    "ir": float(ir),
                    "risk_adjusted_return": risk_adjusted_return,
                    "stability": stability,
                }
            )

        return results

    def generate_reports(self, eval_results: dict[str, Any]) -> tuple[dict[str, Any], str]:
        """
        生成评估报告

        Args:
            eval_results: 评估结果

        Returns:
            tuple: (JSON报告, Markdown报告)
        """
        # 生成JSON报告
        json_report = eval_results.copy()

        # 生成Markdown报告
        md_report = self._generate_markdown_report(eval_results)

        return json_report, md_report

    def _generate_markdown_report(self, eval_results: dict[str, Any]) -> str:
        """
        生成Markdown报告

        Args:
            eval_results: 评估结果

        Returns:
            str: Markdown报告
        """
        lines = [
            "# 因子评估报告",
            "",
            f"生成时间: {eval_results['metadata']['timestamp']}",
            f"数据版本: {eval_results['metadata']['data_version']}",
            f"随机种子: {eval_results['metadata']['random_seed']}",
            f"数据集版本: {eval_results['metadata']['dataset_manifest']}",
            "",
        ]

        # Top因子列表
        lines.append("## Top 因子列表")
        lines.append("| 因子 | IC均值 | IR | 分层收益差 | 稳定性评分 |")
        lines.append("|------|--------|----|------------|------------|")

        # 对因子按IC均值排序
        factors_sorted = sorted(eval_results["factors"], key=lambda x: x["ic_mean"], reverse=True)

        for factor in factors_sorted:
            stability_score = 1 / (
                factor["stability"]["mean_diff"]
                + factor["stability"]["std_ratio"]
                + factor["stability"]["ic_stability"]
            )
            lines.append(
                f"| {factor['name']} | {factor['ic_mean']:.4f} | {factor['ir']:.4f} | {factor['risk_adjusted_return']['top_bottom_diff']:.4f} | {stability_score:.4f} |"
            )

        lines.append("")

        # 因子详细分析
        for factor in factors_sorted:
            lines.append(f"## {factor['name']} 因子分析")
            lines.append("")

            # 基本指标
            lines.append("### 基本指标")
            lines.append(f"- **IC均值**: {factor['ic_mean']:.4f}")
            lines.append(f"- **IR**: {factor['ir']:.4f}")
            lines.append(
                f"- **分层收益差**: {factor['risk_adjusted_return']['top_bottom_diff']:.4f}"
            )
            lines.append(f"- **分层IR**: {factor['risk_adjusted_return']['top_bottom_ir']:.4f}")
            lines.append("")

            # 稳定性
            lines.append("### 稳定性")
            lines.append(f"- **均值差异**: {factor['stability']['mean_diff']:.4f}")
            lines.append(f"- **标准差比率**: {factor['stability']['std_ratio']:.4f}")
            lines.append(f"- **IC稳定性**: {factor['stability']['ic_stability']:.4f}")
            lines.append(f"- **训练集IC**: {factor['stability']['train_ic']:.4f}")
            lines.append(f"- **测试集IC**: {factor['stability']['test_ic']:.4f}")
            lines.append("")

            # 分层收益
            lines.append("### 分层收益")
            quantile_returns = factor["risk_adjusted_return"]["quantile_returns"]
            # 使用实际的分位数索引
            if "mean" in quantile_returns:
                for quantile_idx, mean_return in quantile_returns["mean"].items():
                    std_return = quantile_returns["std"][quantile_idx]
                    count = quantile_returns["count"][quantile_idx]
                    lines.append(
                        f"- **第 {quantile_idx} 层**: 平均收益 = {mean_return:.4f}, 标准差 = {std_return:.4f}, 样本数 = {count}"
                    )
            lines.append("")

        # 稳定性结论
        lines.append("## 稳定性结论")
        stable_factors = [f for f in factors_sorted if f["stability"]["ic_stability"] < 0.1]
        unstable_factors = [f for f in factors_sorted if f["stability"]["ic_stability"] >= 0.1]

        lines.append(
            f"- **稳定因子 ({len(stable_factors)}):** {', '.join([f['name'] for f in stable_factors])}"
        )
        lines.append(
            f"- **不稳定因子 ({len(unstable_factors)}):** {', '.join([f['name'] for f in unstable_factors])}"
        )
        lines.append("")

        # 风险提示
        lines.append("## 风险提示")
        lines.append("1. 因子表现可能随时间变化，建议定期重新评估")
        lines.append("2. 高IC/IR不保证未来表现")
        lines.append("3. 建议结合实际交易成本考虑因子的实用性")
        lines.append("4. 因子相关性可能导致过度拟合，建议进行因子正交化")

        return "\n".join(lines)
