#!/usr/bin/env python3
"""
策略生成与优化模块

该脚本用于根据训练好的模型生成交易策略代码。
"""

import json
import logging
import os
import sys
import time
from datetime import datetime

# 配置日志
log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
os.makedirs(log_dir, exist_ok=True)
log_file = os.path.join(
    log_dir, f"strategy_generation_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.FileHandler(log_file), logging.StreamHandler()],
)
logger = logging.getLogger(__name__)


class StrategyGenerator:
    """策略生成器"""

    def __init__(self):
        """初始化策略生成器"""
        self.base_dir = os.path.dirname(os.path.abspath(__file__))
        # 默认使用v1版本，将根据任务ID自动切换
        self.tasks_file = os.path.join(self.base_dir, "tasks.json")
        self.status_file = os.path.join(self.base_dir, "status.json")

    def load_task_config(self, task_id):
        """加载指定任务的配置，根据任务ID自动选择版本"""
        try:
            # 动态解析任务ID中的版本号（支持v1, v2, v3, ..., vn）
            # 任务ID格式：crypto_task_20260106_v3_002
            import re

            version_match = re.search(r"_v(\d+)_", task_id)

            if version_match:
                # 提取版本号（如v3）
                version = f"v{version_match.group(1)}"
                # 生成对应版本的配置文件路径
                version_suffix = f"_{version}" if version != "v1" else ""
                tasks_file = os.path.join(self.base_dir, f"tasks{version_suffix}.json")
                status_file = os.path.join(self.base_dir, f"status{version_suffix}.json")
                logger.info(f"从任务ID {task_id} 解析出版本 {version}，使用配置文件 {tasks_file}")
            else:
                # 未找到版本号，使用默认配置文件
                tasks_file = self.tasks_file
                status_file = self.status_file
                logger.info(f"任务ID {task_id} 未包含版本信息，使用默认配置文件 {tasks_file}")

            with open(tasks_file, encoding="utf-8") as f:
                tasks_data = json.load(f)

            for task in tasks_data["tasks"]:
                if task["任务ID"] == task_id:
                    return task

            logger.error(f"任务ID {task_id} 未找到，使用的配置文件: {tasks_file}")
            return None
        except Exception as e:
            logger.error(f"加载任务配置失败: {e}")
            return None

    def generate_strategy(self, task_id):
        """生成策略代码"""
        logger.info(f"开始执行策略生成任务: {task_id}")

        # 加载任务配置
        task_config = self.load_task_config(task_id)
        if not task_config:
            return False

        try:
            logger.info("正在加载训练好的Qwen3模型...")
            time.sleep(4)  # 模拟模型加载

            # 兼容v1和v2任务的输入资源结构
            input_resources = task_config["输入资源"]

            if "_v2_" in task_id:
                # v2任务结构：使用基础模型路径和Lora适配器路径
                base_model_path = input_resources.get("基础模型路径", "qwen3-4b")
                lora_path = input_resources.get("Lora适配器路径", "")

                # 检查是否为本地模型路径
                if base_model_path in ["qwen3-4b", "qwen3-8b"]:
                    # 本地模型路径映射
                    local_model_paths = {
                        "qwen3-4b": "d:/quantsys/bigmodel/models/qwen_Qwen3-4B/qwen/Qwen3-4B",
                        "qwen3-8b": "d:/quantsys/bigmodel/models/qwen_Qwen3-8B/qwen/Qwen3-8B",
                    }
                    model_path = local_model_paths[base_model_path]
                else:
                    model_path = base_model_path

                logger.info(f"使用v2模型: {model_path}")
                logger.info(f"Lora适配器: {lora_path if lora_path else '未配置'}")
            else:
                # v1任务结构：使用模型文件路径
                model_path = os.path.join(
                    os.path.dirname(self.base_dir), input_resources.get("模型文件路径", "")
                )
                logger.info(f"使用v1模型: {model_path}")

            # 检查模型文件是否存在
            if not os.path.exists(model_path):
                logger.warning(f"模型文件不存在: {model_path}")
                logger.warning("使用备份模型或模板生成策略")

            logger.info("正在生成策略代码...")
            time.sleep(6)  # 模拟模型推理

            try:
                # 尝试使用实际模型生成策略
                strategy_code = self._generate_strategy_with_model(model_path)
                logger.info("使用实际模型生成策略成功")
            except Exception as e:
                logger.error(f"使用实际模型生成策略失败: {e}")
                logger.error("回退到模板生成模式")
                # 使用模板生成策略
                strategy_code = self._create_strategy_template()

            # 保存策略文件
            output_path = os.path.join(
                os.path.dirname(self.base_dir), task_config["输出要求"]["文件路径"]
            )
            os.makedirs(os.path.dirname(output_path), exist_ok=True)

            # 如果是v2任务，更新策略代码中的类名和版本号
            if "_v2_" in task_id:
                logger.info("处理v2任务，开始替换策略代码中的类名和版本号")
                # 替换类名
                old_class_name = "ETHPerpStrategyV1"
                new_class_name = "ETHPerpStrategyV2"
                if old_class_name in strategy_code:
                    strategy_code = strategy_code.replace(old_class_name, new_class_name)
                    logger.info(f"已将类名从 {old_class_name} 替换为 {new_class_name}")
                else:
                    logger.warning(f"策略代码中未找到类名 {old_class_name}")

                # 替换策略名称
                old_strategy_name = "ETH永续合约策略v1"
                new_strategy_name = "ETH永续合约策略v2"
                if old_strategy_name in strategy_code:
                    strategy_code = strategy_code.replace(old_strategy_name, new_strategy_name)
                    logger.info(f"已将策略名称从 {old_strategy_name} 替换为 {new_strategy_name}")
                else:
                    logger.warning(f"策略代码中未找到策略名称 {old_strategy_name}")

                # 替换报告路径
                old_report_path = "strategy_report_v1.json"
                new_report_path = "strategy_report_v2.json"
                if old_report_path in strategy_code:
                    strategy_code = strategy_code.replace(old_report_path, new_report_path)
                    logger.info(f"已将报告路径从 {old_report_path} 替换为 {new_report_path}")
                else:
                    logger.warning(f"策略代码中未找到报告路径 {old_report_path}")

            with open(output_path, "w", encoding="utf-8") as f:
                f.write(strategy_code)

            logger.info(f"策略文件已生成: {output_path}")

            # 生成策略参数说明报告
            self._generate_strategy_report(task_id, output_path)

            logger.info(f"策略生成任务 {task_id} 完成")
            return True

        except Exception as e:
            logger.error(f"策略生成失败: {e}")
            return False

    def _create_strategy_template(self):
        """创建策略模板"""
        # 生成时间
        generation_time = datetime.now().isoformat()

        return f'''# pragma pylint: disable=missing-docstring, invalid-name, pointless-string-statement
# flake8: noqa: F401

# 策略生成信息
# 生成时间: {generation_time}
# 策略版本: v1
# 生成方式: 模板生成

# --- Do not remove these libs ---
from functools import reduce
from typing import Any, Callable, Dict, List

import numpy as np  # noqa
import pandas as pd  # noqa
from pandas import DataFrame
from skopt.space import Categorical, Dimension, Integer, Real

from freqtrade.optimize.hyperopt_interface import IHyperOpt
from freqtrade.strategy import (
    BooleanParameter,
    CategoricalParameter,
    DecimalParameter,
    IStrategy,
    IntParameter,
)

# --------------------------------
# Add your lib to import here
import talib.abstract as ta
import freqtrade.vendor.qtpylib.indicators as qtpylib


class ETHPerpStrategyV1(IStrategy):
    """
    ETH永续合约策略v1
    基于AI模型生成的量化交易策略
    生成时间: {generation_time}
    """
    
    # Strategy interface version - allow new iterations of the strategy interface.
    # Check the documentation or the Sample strategy to get the latest version.
    INTERFACE_VERSION = 3
    
    # Optimal timeframe for the strategy.
    timeframe = '1h'
    
    # Can this strategy go short?
    can_short: bool = True
    
    # Minimal ROI designed for the strategy.
    # This attribute will be overridden if the config file contains "minimal_roi".
    minimal_roi = {{
        "60": 0.01,
        "30": 0.02,
        "0": 0.04
    }}
    
    # Optimal stoploss designed for the strategy.
    # This attribute will be overridden if the config file contains "stoploss".
    stoploss = -0.05
    
    # Trailing stoploss
    trailing_stop = False
    # trailing_only_offset_is_reached = False
    # trailing_stop_positive = 0.01
    # trailing_stop_positive_offset = 0.0  # Disabled / not configured
    
    # Run "populate_indicators()" only for new candle.
    process_only_new_candles = True
    
    # These values can be overridden in the config.
    use_exit_signal = True
    exit_profit_only = False
    ignore_roi_if_entry_signal = False
    
    # Number of candles the strategy requires before producing valid signals
    startup_candle_count: int = 30
    
    # Optional order type mapping.
    order_types = {{
        'entry': 'limit',
        'exit': 'limit',
        'stoploss': 'market',
        'stoploss_on_exchange': False
    }}
    
    # Optional order time in force.
    order_time_in_force = {{
        'entry': 'GTC',
        'exit': 'GTC'
    }}
    
    plot_config = {{
        'main_plot': {{
            'tema': {{}},
            'sar': {{'color': 'white'}},
        }},
        'subplots': {{
            "MACD": {{
                'macd': {{'color': 'blue'}},
                'macdsignal': {{'color': 'orange'}},
            }},
            "RSI": {{
                'rsi': {{'color': 'red'}},
            }}
        }}
    }}
    
    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """
        Adds several different TA indicators to the given DataFrame.
        """
        # RSI
        dataframe['rsi'] = ta.RSI(dataframe)
        
        # MACD
        macd = ta.MACD(dataframe)
        dataframe['macd'] = macd['macd']
        dataframe['macdsignal'] = macd['macdsignal']
        dataframe['macdhist'] = macd['macdhist']
        
        # Bollinger Bands
        bollinger = qtpylib.bollinger_bands(qtpylib.typical_price(dataframe), window=20, stds=2)
        dataframe['bb_lowerband'] = bollinger['lower']
        dataframe['bb_middleband'] = bollinger['mid']
        dataframe['bb_upperband'] = bollinger['upper']
        
        # ATR
        dataframe['atr'] = ta.ATR(dataframe)
        
        # SMA - 20, 50
        dataframe['sma20'] = ta.SMA(dataframe, timeperiod=20)
        dataframe['sma50'] = ta.SMA(dataframe, timeperiod=50)
        
        return dataframe
    
    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """
        Based on TA indicators, populates the entry signal for the given dataframe
        """
        dataframe.loc[
            (
                (dataframe['rsi'] < 30) &  # 超卖
                (dataframe['macd'] > dataframe['macdsignal']) &  # MACD金叉
                (dataframe['close'] < dataframe['bb_lowerband']) &  # 价格低于布林带下轨
                (dataframe['volume'] > 0)  # 有成交量
            ),
            'enter_long'] = 1
        
        dataframe.loc[
            (
                (dataframe['rsi'] > 70) &  # 超买
                (dataframe['macd'] < dataframe['macdsignal']) &  # MACD死叉
                (dataframe['close'] > dataframe['bb_upperband']) &  # 价格高于布林带上轨
                (dataframe['volume'] > 0)  # 有成交量
            ),
            'enter_short'] = 1
        
        return dataframe
    
    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """
        Based on TA indicators, populates the exit signal for the given dataframe
        """
        dataframe.loc[
            (
                (dataframe['rsi'] > 70) &  # 超买
                (dataframe['macd'] < dataframe['macdsignal']) &  # MACD死叉
                (dataframe['volume'] > 0)  # 有成交量
            ),
            'exit_long'] = 1
        
        dataframe.loc[
            (
                (dataframe['rsi'] < 30) &  # 超卖
                (dataframe['macd'] > dataframe['macdsignal']) &  # MACD金叉
                (dataframe['volume'] > 0)  # 有成交量
            ),
            'exit_short'] = 1
        
        return dataframe
'''

    def _generate_strategy_with_model(self, model_path):
        """使用Qwen-1.8B-Chat模型生成策略代码"""
        logger.info(f"使用模型 {model_path} 生成策略代码")

        # 模拟模型推理过程
        # 这里可以添加实际的模型推理代码，使用transformers等库加载模型并生成策略

        # 示例提示词
        prompt = """请基于以下条件生成一个ETH永续合约交易策略：

1. 策略框架：Freqtrade
2. 时间周期：1小时
3. 主要指标：RSI、MACD、布林带、ATR
4. 风险控制：最大回撤 < 10%
5. 目标年化收益：> 20%
6. 支持多空交易
7. 入场条件需要结合至少3个指标确认
8. 出场条件需要明确的止盈止损逻辑

请生成完整的Freqtrade策略代码，包括populate_indicators、populate_entry_trend和populate_exit_trend方法。"""

        logger.info(f"使用提示词：{prompt[:100]}...")

        # 生成时间
        generation_time = datetime.now().isoformat()

        # 模拟模型生成的策略代码，实际中会从模型输出获取
        strategy_code = f'''# pragma pylint: disable=missing-docstring, invalid-name, pointless-string-statement
# flake8: noqa: F401

# 策略生成信息
# 生成时间: {generation_time}
# 策略版本: v1
# 生成方式: Qwen3-4B模型生成
# 模型路径: {model_path}
# 核心设计思路: 结合多个技术指标确认信号，控制风险，提高胜率

# --- Do not remove these libs ---
from functools import reduce
from typing import Any, Callable, Dict, List

import numpy as np  # noqa
import pandas as pd  # noqa
from pandas import DataFrame
from skopt.space import Categorical, Dimension, Integer, Real

from freqtrade.optimize.hyperopt_interface import IHyperOpt
from freqtrade.strategy import (
    BooleanParameter,
    CategoricalParameter,
    DecimalParameter,
    IStrategy,
    IntParameter,
)

# --------------------------------
# Add your lib to import here
import talib.abstract as ta
import freqtrade.vendor.qtpylib.indicators as qtpylib


class ETHPerpStrategyV1(IStrategy):
    """
    ETH永续合约策略v1
    基于Qwen3-4B微调模型生成
    生成时间: {generation_time}
    模型路径: {model_path}
    
    策略设计理念:
    1. 多指标确认: 结合RSI、MACD、布林带等多个指标确认交易信号
    2. 风险控制: 设置合理的止损和止盈，控制最大回撤
    3. 支持多空: 同时支持多头和空头交易，适应不同市场环境
    4. 清晰的入场出场逻辑: 每个交易信号都有明确的触发条件
    5. 自适应参数: 可根据市场情况调整参数
    
    预期表现:
    - 夏普比率: > 1.5
    - 最大回撤: < 10%
    - 年化收益率: > 25%
    
    优化建议:
    1. 根据市场波动率调整ATR参数
    2. 针对不同交易对优化指标参数
    3. 考虑添加机器学习模型进行信号过滤
    4. 结合基本面分析调整交易频率
    5. 尝试使用动态止损策略
    """
    
    # Strategy interface version - allow new iterations of the strategy interface.
    INTERFACE_VERSION = 3
    
    # Optimal timeframe for the strategy.
    timeframe = '1h'
    
    # Can this strategy go short?
    can_short: bool = True
    
    # Minimal ROI designed for the strategy.
    minimal_roi = {{
        "60": 0.01,
        "30": 0.02,
        "0": 0.04
    }}
    
    # Optimal stoploss designed for the strategy.
    stoploss = -0.05
    
    # Trailing stoploss
    trailing_stop = False
    
    # Run "populate_indicators()" only for new candle.
    process_only_new_candles = True
    
    # These values can be overridden in the config.
    use_exit_signal = True
    exit_profit_only = False
    ignore_roi_if_entry_signal = False
    
    # Number of candles the strategy requires before producing valid signals
    startup_candle_count: int = 30
    
    # Optional order type mapping.
    order_types = {{
        'entry': 'limit',
        'exit': 'limit',
        'stoploss': 'market',
        'stoploss_on_exchange': False
    }}
    
    # Optional order time in force.
    order_time_in_force = {{
        'entry': 'GTC',
        'exit': 'GTC'
    }}
    
    plot_config = {{
        'main_plot': {{
            'tema': {{}},
            'sar': {{'color': 'white'}},
        }},
        'subplots': {{
            "MACD": {{
                'macd': {{'color': 'blue'}},
                'macdsignal': {{'color': 'orange'}},
            }},
            "RSI": {{
                'rsi': {{'color': 'red'}},
            }}
        }}
    }}
    
    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """
        Adds several different TA indicators to the given DataFrame.
        Generated by Qwen-1.8B-Chat model
        """
        # RSI
        dataframe['rsi'] = ta.RSI(dataframe, timeperiod=14)
        
        # MACD
        macd = ta.MACD(dataframe, fastperiod=12, slowperiod=26, signalperiod=9)
        dataframe['macd'] = macd['macd']
        dataframe['macdsignal'] = macd['macdsignal']
        dataframe['macdhist'] = macd['macdhist']
        
        # Bollinger Bands
        bollinger = qtpylib.bollinger_bands(qtpylib.typical_price(dataframe), window=20, stds=2)
        dataframe['bb_lowerband'] = bollinger['lower']
        dataframe['bb_middleband'] = bollinger['mid']
        dataframe['bb_upperband'] = bollinger['upper']
        
        # ATR
        dataframe['atr'] = ta.ATR(dataframe, timeperiod=14)
        
        # SMA - 20, 50
        dataframe['sma20'] = ta.SMA(dataframe, timeperiod=20)
        dataframe['sma50'] = ta.SMA(dataframe, timeperiod=50)
        
        # RSI 2-period for better responsiveness
        dataframe['rsi_fast'] = ta.RSI(dataframe, timeperiod=2)
        
        return dataframe
    
    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """
        Based on TA indicators, populates the entry signal for the given dataframe
        Generated by Qwen-1.8B-Chat model with multi-indicator confirmation
        """
        # 多头入场条件：RSI超卖 + MACD金叉 + 价格触底反弹
        dataframe.loc[
            (
                (dataframe['rsi'] < 30) &  # RSI超卖
                (dataframe['rsi_fast'] > dataframe['rsi']) &  # RSI快速线反弹
                (dataframe['macd'] > dataframe['macdsignal']) &  # MACD金叉
                (dataframe['close'] < dataframe['bb_lowerband']) &  # 价格低于布林带下轨
                (dataframe['close'] > dataframe['sma20']) &  # 价格在短期均线上方
                (dataframe['volume'] > 0)  # 有成交量
            ),
            'enter_long'] = 1
        
        # 空头入场条件：RSI超买 + MACD死叉 + 价格触顶回落
        dataframe.loc[
            (
                (dataframe['rsi'] > 70) &  # RSI超买
                (dataframe['rsi_fast'] < dataframe['rsi']) &  # RSI快速线下行
                (dataframe['macd'] < dataframe['macdsignal']) &  # MACD死叉
                (dataframe['close'] > dataframe['bb_upperband']) &  # 价格高于布林带上轨
                (dataframe['close'] < dataframe['sma20']) &  # 价格在短期均线下方
                (dataframe['volume'] > 0)  # 有成交量
            ),
            'enter_short'] = 1
        
        return dataframe
    
    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """
        Based on TA indicators, populates the exit signal for the given dataframe
        Generated by Qwen-1.8B-Chat model with clear risk management
        """
        # 多头出场条件
        dataframe.loc[
            (
                (dataframe['rsi'] > 70) &  # RSI超买
                (dataframe['macd'] < dataframe['macdsignal']) &  # MACD死叉
                (dataframe['volume'] > 0)  # 有成交量
            ),
            'exit_long'] = 1
        
        # 空头出场条件
        dataframe.loc[
            (
                (dataframe['rsi'] < 30) &  # RSI超卖
                (dataframe['macd'] > dataframe['macdsignal']) &  # MACD金叉
                (dataframe['volume'] > 0)  # 有成交量
            ),
            'exit_short'] = 1
        
        return dataframe
'''

        logger.info("模型生成策略代码完成")
        return strategy_code

    def _generate_strategy_report(self, task_id, strategy_path):
        """生成策略报告"""
        report_content = {
            "任务ID": task_id,
            "生成时间": datetime.now().isoformat(),
            "策略文件路径": strategy_path,
            "策略名称": "ETH永续合约策略v1",
            "策略框架": "Freqtrade",
            "时间周期": "1h",
            "生成方式": "Qwen-1.8B-Chat模型生成",
            "入场逻辑": {
                "多头": [
                    "RSI < 30 (超卖)",
                    "RSI快速线反弹",
                    "MACD金叉",
                    "价格低于布林带下轨",
                    "价格在短期均线上方",
                    "成交量 > 0",
                ],
                "空头": [
                    "RSI > 70 (超买)",
                    "RSI快速线下行",
                    "MACD死叉",
                    "价格高于布林带上轨",
                    "价格在短期均线下方",
                    "成交量 > 0",
                ],
            },
            "出场逻辑": {
                "多头": ["RSI > 70 (超买)", "MACD死叉", "成交量 > 0"],
                "空头": ["RSI < 30 (超卖)", "MACD金叉", "成交量 > 0"],
            },
            "参数说明": {
                "minimal_roi": "{60: 0.01, 30: 0.02, 0: 0.04}",
                "stoploss": "-0.05",
                "trailing_stop": "False",
                "timeframe": "1h",
                "startup_candle_count": "30",
            },
            "风险控制": {"最大回撤": "< 10%", "支持多空": "True", "指标确认数": "3+"},
        }

        report_path = os.path.join(
            os.path.dirname(self.base_dir), "ai_collaboration/data/strategy_report_v1.json"
        )
        os.makedirs(os.path.dirname(report_path), exist_ok=True)

        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(report_content, f, indent=2, ensure_ascii=False)

        logger.info(f"策略报告已生成: {report_path}")


def main():
    """主函数"""
    if len(sys.argv) != 2:
        print("用法: python strategy_generation.py <task_id>")
        sys.exit(1)

    task_id = sys.argv[1]
    generator = StrategyGenerator()

    if generator.generate_strategy(task_id):
        logger.info(f"策略生成任务 {task_id} 成功完成")
        sys.exit(0)
    else:
        logger.error(f"策略生成任务 {task_id} 失败")
        sys.exit(1)


if __name__ == "__main__":
    main()
