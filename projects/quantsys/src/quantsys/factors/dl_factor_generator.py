#!/usr/bin/env python3
"""
深度学习因子生成模块
通过神经网络从零生成新因子
"""

import logging
from typing import Any

import numpy as np
import pandas as pd
import torch
import torch.nn as nn
import torch.optim as optim
from sklearn.preprocessing import StandardScaler
from tqdm import tqdm

# 配置日志
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class DLFactorGenerator:
    """
    深度学习因子生成器
    使用CNN-LSTM模型从原始数据中生成新因子
    """

    def __init__(self, raw_data: pd.DataFrame, seq_length: int = 24, factor_dim: int = 32):
        """
        初始化深度学习因子生成器

        Args:
            raw_data: 原始数据，包含OHLCV字段
            seq_length: 序列长度（用于生成时间序列样本）
            factor_dim: 生成的因子维度
        """
        self.raw_data = raw_data
        self.seq_length = seq_length
        self.factor_dim = factor_dim
        self.scaler = StandardScaler()
        self.model = None
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

        logger.info(
            f"深度学习因子生成器初始化完成，设备: {self.device}, 序列长度: {seq_length}, 因子维度: {factor_dim}"
        )

    def prepare_sequence_data(
        self, feature_cols: list[str] = None, target_col: str = "close"
    ) -> tuple[torch.Tensor, torch.Tensor, list[str]]:
        """
        准备序列数据用于深度学习模型

        Args:
            feature_cols: 用于生成因子的特征列
            target_col: 目标列（用于训练）

        Returns:
            X: 序列特征张量 [batch_size, seq_length, feature_dim]
            y: 目标张量 [batch_size, 1]
            feature_names: 特征列名
        """
        logger.info("开始准备序列数据")

        # 默认使用OHLCV特征
        if feature_cols is None:
            feature_cols = ["open", "high", "low", "close", "volume", "amount"]

        # 确保所有特征列存在
        available_cols = [col for col in feature_cols if col in self.raw_data.columns]
        if len(available_cols) != len(feature_cols):
            missing_cols = set(feature_cols) - set(available_cols)
            logger.warning(f"缺失特征列: {missing_cols}, 将使用可用列: {available_cols}")
            feature_cols = available_cols

        # 标准化数据
        scaled_data = self.scaler.fit_transform(self.raw_data[feature_cols])
        scaled_df = pd.DataFrame(scaled_data, columns=feature_cols, index=self.raw_data.index)

        # 生成序列数据
        X, y, indices = [], [], []

        for i in range(self.seq_length, len(scaled_df)):
            # 输入序列
            seq_x = scaled_df.iloc[i - self.seq_length : i][feature_cols].values
            # 目标值（未来收益率）
            future_close = self.raw_data.iloc[i][target_col]
            current_close = self.raw_data.iloc[i - 1][target_col]
            ret = (future_close / current_close - 1) * 100  # 放大收益便于训练

            X.append(seq_x)
            y.append(ret)
            indices.append(self.raw_data.index[i])

        # 转换为张量
        X_tensor = torch.FloatTensor(X).to(self.device)
        y_tensor = torch.FloatTensor(y).unsqueeze(1).to(self.device)

        logger.info(f"序列数据准备完成，形状: X={X_tensor.shape}, y={y_tensor.shape}")

        return X_tensor, y_tensor, indices, feature_cols

    class CNNLSTMModel(nn.Module):
        """
        CNN-LSTM模型，用于从序列数据中提取特征（生成因子）
        """

        def __init__(
            self,
            input_dim: int,
            hidden_dim: int,
            factor_dim: int,
            num_layers: int = 2,
            kernel_size: int = 3,
        ):
            super().__init__()

            # CNN层用于提取空间特征
            self.cnn = nn.Sequential(
                nn.Conv1d(
                    in_channels=input_dim,
                    out_channels=hidden_dim,
                    kernel_size=kernel_size,
                    padding=1,
                ),
                nn.ReLU(),
                nn.Conv1d(
                    in_channels=hidden_dim,
                    out_channels=hidden_dim,
                    kernel_size=kernel_size,
                    padding=1,
                ),
                nn.ReLU(),
                nn.AdaptiveMaxPool1d(output_size=1),
            )

            # LSTM层用于提取时间特征
            self.lstm = nn.LSTM(
                input_size=hidden_dim,
                hidden_size=hidden_dim,
                num_layers=num_layers,
                batch_first=True,
                dropout=0.2,
            )

            # 因子生成层
            self.factor_generator = nn.Sequential(
                nn.Linear(hidden_dim, hidden_dim), nn.ReLU(), nn.Linear(hidden_dim, factor_dim)
            )

            # 预测层（用于训练）
            self.predictor = nn.Linear(factor_dim, 1)

        def forward(self, x):
            # x shape: [batch_size, seq_length, input_dim]

            # 转换为CNN输入格式: [batch_size, input_dim, seq_length]
            cnn_input = x.permute(0, 2, 1)

            # CNN特征提取
            cnn_out = self.cnn(cnn_input)
            cnn_out = cnn_out.squeeze(2)  # [batch_size, hidden_dim]

            # 扩展维度用于LSTM: [batch_size, 1, hidden_dim]
            lstm_input = cnn_out.unsqueeze(1)

            # LSTM特征提取
            lstm_out, _ = self.lstm(lstm_input)
            lstm_out = lstm_out[:, -1, :]  # [batch_size, hidden_dim]

            # 生成因子
            factors = self.factor_generator(lstm_out)  # [batch_size, factor_dim]

            # 生成预测
            prediction = self.predictor(factors)  # [batch_size, 1]

            return factors, prediction

    def train_model(
        self,
        X: torch.Tensor,
        y: torch.Tensor,
        epochs: int = 50,
        batch_size: int = 64,
        learning_rate: float = 0.001,
    ) -> Any:
        """
        训练深度学习模型

        Args:
            X: 序列特征张量
            y: 目标张量
            epochs: 训练轮数
            batch_size: 批次大小
            learning_rate: 学习率

        Returns:
            model: 训练好的模型
        """
        logger.info(
            f"开始训练深度学习模型， epochs: {epochs}, batch_size: {batch_size}, lr: {learning_rate}"
        )

        # 获取输入维度
        input_dim = X.shape[2]
        hidden_dim = 64

        # 初始化模型
        model = self.CNNLSTMModel(input_dim, hidden_dim, self.factor_dim).to(self.device)

        # 损失函数和优化器
        criterion = nn.MSELoss()
        optimizer = optim.Adam(model.parameters(), lr=learning_rate)

        # 训练循环
        for epoch in tqdm(range(epochs), desc="训练模型", unit="轮", ncols=80):
            model.train()
            epoch_loss = 0

            # 随机打乱数据
            permutation = torch.randperm(X.size()[0])

            # 批次处理进度条
            batch_bar = tqdm(
                range(0, X.size()[0], batch_size),
                desc=f"Epoch {epoch + 1}/{epochs}",
                unit="批",
                ncols=80,
                leave=False,
            )
            for i in batch_bar:
                # 获取批次数据
                indices = permutation[i : i + batch_size]
                batch_x, batch_y = X[indices], y[indices]

                # 前向传播
                _, predictions = model(batch_x)
                loss = criterion(predictions, batch_y)

                # 反向传播和优化
                optimizer.zero_grad()
                loss.backward()
                optimizer.step()

                epoch_loss += loss.item()

                # 更新批次进度条
                batch_bar.set_postfix({"batch_loss": f"{loss.item():.4f}"})

            # 计算平均损失
            avg_loss = epoch_loss / (len(X) // batch_size)

            # 更新轮次进度条
            tqdm.write(f"Epoch [{epoch + 1}/{epochs}], Loss: {avg_loss:.4f}")

        logger.info("深度学习模型训练完成")
        self.model = model
        return model

    def generate_factors(self, X: torch.Tensor, indices: list[pd.Timestamp]) -> pd.DataFrame:
        """
        使用训练好的模型生成因子

        Args:
            X: 序列特征张量
            indices: 因子对应的时间索引

        Returns:
            factor_df: 生成的因子矩阵 [n_samples, factor_dim]
        """
        if self.model is None:
            raise ValueError("模型未训练，请先调用train_model方法")

        logger.info("开始生成深度学习因子")

        self.model.eval()
        with torch.no_grad():
            factors, _ = self.model(X)

        # 转换为DataFrame
        factor_df = pd.DataFrame(
            factors.cpu().numpy(),
            index=indices,
            columns=[f"dl_factor_{i + 1}" for i in range(self.factor_dim)],
        )

        logger.info(f"深度学习因子生成完成，形状: {factor_df.shape}")
        return factor_df

    def run_full_dl_pipeline(
        self, feature_cols: list[str] = None, epochs: int = 50, batch_size: int = 64
    ) -> pd.DataFrame:
        """
        运行完整的深度学习因子生成流程

        Args:
            feature_cols: 特征列
            epochs: 训练轮数
            batch_size: 批次大小

        Returns:
            generated_factors: 生成的因子矩阵
        """
        logger.info("开始运行完整深度学习因子生成流程")

        # 使用tqdm跟踪完整流程
        process_bar = tqdm(total=3, desc="DL因子生成流程", unit="步骤", ncols=80)

        # 1. 准备序列数据
        process_bar.set_description("步骤1/3: 准备序列数据")
        X, y, indices, used_cols = self.prepare_sequence_data(feature_cols)
        process_bar.update(1)

        # 2. 训练模型
        process_bar.set_description("步骤2/3: 训练深度学习模型")
        self.train_model(X, y, epochs=epochs, batch_size=batch_size)
        process_bar.update(1)

        # 3. 生成因子
        process_bar.set_description("步骤3/3: 生成深度学习因子")
        generated_factors = self.generate_factors(X, indices)
        process_bar.update(1)

        process_bar.set_description("DL因子生成流程完成")
        process_bar.close()

        logger.info("完整深度学习因子生成流程完成")
        return generated_factors


# 示例用法
if __name__ == "__main__":
    # 创建测试数据

    import numpy as np
    import pandas as pd

    # 生成测试数据
    dates = pd.date_range(start="2023-01-01", periods=1000, freq="h")
    price = 1500 + np.cumsum(np.random.normal(0, 1, len(dates)))

    test_data = pd.DataFrame(
        {
            "open": price + np.random.normal(0, 0.5, len(dates)),
            "high": price + np.random.normal(0, 1, len(dates)),
            "low": price - np.random.normal(0, 1, len(dates)),
            "close": price,
            "volume": np.random.uniform(1000, 10000, len(dates)),
            "amount": np.random.uniform(1000000, 10000000, len(dates)),
        },
        index=dates,
    )

    # 初始化DL因子生成器
    dl_generator = DLFactorGenerator(test_data, seq_length=24, factor_dim=10)

    # 生成因子
    factors = dl_generator.run_full_dl_pipeline(epochs=20, batch_size=32)

    print(f"生成的因子形状: {factors.shape}")
    print(factors.head())
