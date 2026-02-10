import logging
import random
from collections import deque

import numpy as np
import torch
import torch.nn as nn
import torch.optim as optim

# 配置日志
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class RLFactorOptimizer:
    """
    基于强化学习的因子优化器
    使用DQN算法自动优化因子权重和组合
    """

    def __init__(self, factor_codes, state_size=5, action_size=10, hidden_size=64):
        """
        初始化强化学习因子优化器

        Args:
            factor_codes: 因子代码列表
            state_size: 状态空间大小
            action_size: 动作空间大小
            hidden_size: 神经网络隐藏层大小
        """
        self.factor_codes = factor_codes
        self.n_factors = len(factor_codes)
        self.state_size = state_size
        self.action_size = action_size
        self.hidden_size = hidden_size

        # DQN参数
        self.gamma = 0.95  # 折扣因子
        self.epsilon = 1.0  # 探索率
        self.epsilon_min = 0.01  # 最小探索率
        self.epsilon_decay = 0.995  # 探索率衰减
        self.learning_rate = 0.001  # 学习率

        # 经验回放缓冲区
        self.memory = deque(maxlen=2000)

        # 创建DQN模型
        self.model = self._build_model()
        self.target_model = self._build_model()
        self.optimizer = optim.Adam(self.model.parameters(), lr=self.learning_rate)
        self.criterion = nn.MSELoss()

        # 更新目标模型
        self.update_target_model()

        logger.info(f"强化学习因子优化器初始化完成，因子数量: {self.n_factors}")

    def _build_model(self):
        """
        构建DQN神经网络模型
        """
        model = nn.Sequential(
            nn.Linear(self.state_size + self.n_factors, self.hidden_size),
            nn.ReLU(),
            nn.Linear(self.hidden_size, self.hidden_size),
            nn.ReLU(),
            nn.Linear(self.hidden_size, self.action_size),
        )
        return model

    def update_target_model(self):
        """
        更新目标模型权重
        """
        self.target_model.load_state_dict(self.model.state_dict())

    def remember(self, state, action, reward, next_state, done):
        """
        将经验存储到回放缓冲区
        """
        self.memory.append((state, action, reward, next_state, done))

    def act(self, state):
        """
        根据当前状态选择动作

        Args:
            state: 当前状态

        Returns:
            action: 选择的动作
        """
        if np.random.rand() <= self.epsilon:
            # 随机探索
            return np.random.choice(self.action_size)

        # 贪婪选择
        act_values = self.model(torch.FloatTensor(state))
        return torch.argmax(act_values[0]).item()

    def replay(self, batch_size=32):
        """
        从回放缓冲区中采样并训练模型

        Args:
            batch_size: 批次大小
        """
        if len(self.memory) < batch_size:
            return

        # 随机采样
        minibatch = random.sample(self.memory, batch_size)

        for state, action, reward, next_state, done in minibatch:
            state = torch.FloatTensor(state)
            next_state = torch.FloatTensor(next_state)

            # 计算目标Q值
            target = reward
            if not done:
                target = reward + self.gamma * torch.max(self.target_model(next_state)[0]).item()

            # 获取当前Q值
            target_f = self.model(state)
            target_f[0][action] = target

            # 训练模型
            self.optimizer.zero_grad()
            loss = self.criterion(target_f, self.model(state))
            loss.backward()
            self.optimizer.step()

        # 更新探索率
        if self.epsilon > self.epsilon_min:
            self.epsilon *= self.epsilon_decay

    def get_factor_weights(self, state):
        """
        根据当前状态获取因子权重

        Args:
            state: 当前状态

        Returns:
            weights: 因子权重数组
        """
        # 使用DQN模型生成因子权重
        act_values = self.model(torch.FloatTensor(state))
        action = torch.argmax(act_values[0]).item()

        # 将动作转换为因子权重
        weights = np.zeros(self.n_factors)

        # 基于动作生成权重分布
        if action < self.n_factors:
            # 单因子策略
            weights[action] = 1.0
        else:
            # 多因子组合策略
            combo_idx = action - self.n_factors
            n_combos = self.action_size - self.n_factors

            # 生成均匀分布的权重
            weights = np.ones(self.n_factors) / self.n_factors

            # 根据组合索引调整权重
            for i in range(self.n_factors):
                weights[i] += 0.1 * np.sin(combo_idx + i)

            # 归一化权重
            weights = np.clip(weights, 0, None)
            if np.sum(weights) > 0:
                weights /= np.sum(weights)

        return weights

    def train(self, factor_data, returns_data, episodes=1000, batch_size=32):
        """
        训练强化学习模型

        Args:
            factor_data: 因子数据，形状为 (n_samples, n_factors)
            returns_data: 收益数据，形状为 (n_samples,)
            episodes: 训练回合数
            batch_size: 批次大小
        """
        logger.info(f"开始训练强化学习模型，回合数: {episodes}")

        n_samples = len(factor_data)

        for e in range(episodes):
            # 初始化状态
            state_idx = np.random.randint(0, n_samples - self.state_size)
            current_state = self._get_state(factor_data, returns_data, state_idx)

            total_reward = 0
            done = False

            for t in range(100):
                # 选择动作
                action = self.act(current_state)

                # 获取因子权重
                weights = self.get_factor_weights(current_state)

                # 计算组合因子值
                combo_factor = np.dot(factor_data[state_idx], weights)

                # 计算收益和风险
                next_return = returns_data[state_idx + 1]

                # 计算奖励
                reward = self._calculate_reward(combo_factor, next_return)
                total_reward += reward

                # 下一个状态
                next_state_idx = state_idx + 1
                if next_state_idx >= n_samples - self.state_size:
                    done = True
                    next_state = current_state
                else:
                    next_state = self._get_state(factor_data, returns_data, next_state_idx)

                # 存储经验
                self.remember(current_state, action, reward, next_state, done)

                # 训练模型
                self.replay(batch_size)

                # 更新状态
                current_state = next_state
                state_idx = next_state_idx

                if done:
                    break

            # 每100个回合更新目标模型
            if e % 100 == 0:
                self.update_target_model()
                logger.info(f"回合: {e}, 总奖励: {total_reward:.4f}, 探索率: {self.epsilon:.4f}")

        logger.info("强化学习模型训练完成")

    def _get_state(self, factor_data, returns_data, idx):
        """
        获取当前状态

        Args:
            factor_data: 因子数据
            returns_data: 收益数据
            idx: 当前索引

        Returns:
            state: 当前状态，形状为 (1, state_size + n_factors)
        """
        # 最近的收益序列
        recent_returns = returns_data[idx : idx + self.state_size]

        # 当前因子值
        current_factors = factor_data[idx]

        # 组合状态
        state = np.concatenate([recent_returns, current_factors])
        return state.reshape(1, -1)

    def _calculate_reward(self, factor_value, next_return):
        """
        计算奖励

        Args:
            factor_value: 组合因子值
            next_return: 下一期收益

        Returns:
            reward: 奖励值
        """
        # 基于因子值和收益的相关性计算奖励
        # 如果因子值为正且收益为正，或者因子值为负且收益为负，奖励为正
        if (factor_value > 0 and next_return > 0) or (factor_value < 0 and next_return < 0):
            reward = abs(next_return) * 100
        else:
            reward = -abs(next_return) * 100

        # 加入风险惩罚
        risk_penalty = -0.1 * abs(factor_value)

        return reward + risk_penalty

    def optimize_factor_combination(self, factor_data, returns_data):
        """
        优化因子组合

        Args:
            factor_data: 因子数据
            returns_data: 收益数据

        Returns:
            optimal_weights: 最优因子权重
        """
        logger.info("开始优化因子组合")

        # 训练模型
        self.train(factor_data, returns_data)

        # 使用训练好的模型计算最优权重
        n_samples = len(factor_data)
        weights_list = []

        for idx in range(n_samples - self.state_size):
            state = self._get_state(factor_data, returns_data, idx)
            weights = self.get_factor_weights(state)
            weights_list.append(weights)

        # 计算平均权重作为最优权重
        optimal_weights = np.mean(weights_list, axis=0)

        # 归一化权重
        optimal_weights = np.clip(optimal_weights, 0, None)
        if np.sum(optimal_weights) > 0:
            optimal_weights /= np.sum(optimal_weights)
        else:
            optimal_weights = np.ones(self.n_factors) / self.n_factors

        logger.info(f"因子组合优化完成，最优权重: {optimal_weights}")
        return optimal_weights


class FactorLibraryRL:
    """
    基于强化学习的因子库扩展类
    """

    def __init__(self, factor_codes):
        """
        初始化强化学习因子库

        Args:
            factor_codes: 因子代码列表
        """
        self.factor_codes = factor_codes
        self.rl_optimizer = RLFactorOptimizer(factor_codes)

    def calculate_rl_factor(self, df, factor_data, returns_data):
        """
        计算强化学习因子

        Args:
            df: 价格数据
            factor_data: 因子数据
            returns_data: 收益数据

        Returns:
            df: 添加了RL因子的数据
        """
        # 优化因子权重
        optimal_weights = self.rl_optimizer.optimize_factor_combination(factor_data, returns_data)

        # 计算组合因子
        rl_factor = np.dot(factor_data, optimal_weights)

        # 将RL因子添加到数据框
        df["rl_factor"] = np.nan
        if len(rl_factor) <= len(df):
            df.iloc[-len(rl_factor) :, df.columns.get_loc("rl_factor")] = rl_factor

        return df, optimal_weights
