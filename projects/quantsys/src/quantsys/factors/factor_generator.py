import logging

import numpy as np
import pandas as pd
from tqdm import tqdm

# 配置日志
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class FactorGenerator:
    """
    搭积木式量化因子生成器
    按照5层流程生成多样化的量化因子
    """

    def __init__(self):
        """
        初始化因子生成器
        """
        # 基础数据字段
        self.data_fields = ["open", "high", "low", "close", "volume"]

        # 时间序列算子
        self.ts_operators = [
            "ts_rank",  # 时间序列排名
            "ts_mean",  # 时间序列均值
            "ts_std",  # 时间序列标准差
            "ts_corr",  # 时间序列相关系数
            "ts_cov",  # 时间序列协方差
            "ts_min",  # 时间序列最小值
            "ts_max",  # 时间序列最大值
            "ts_sum",  # 时间序列求和
            "ts_diff",  # 时间序列差分
            "ts_delay",  # 时间序列延迟
            "ts_quantile",  # 时间序列分位数
            "ts_median",  # 时间序列中位数
            "ts_skew",  # 时间序列偏度
            "ts_kurt",  # 时间序列峰度
            "ts_returns",  # 时间序列收益率
            "ts_volatility",  # 时间序列波动率
            "ts_autocorr",  # 时间序列自相关
        ]

        # 截面算子
        self.cross_section_operators = [
            "group_rank",  # 截面排名
            "group_zscore",  # 截面Z-score标准化
            "group_quantile",  # 截面分位数
            "group_median",  # 截面中位数
            "group_std",  # 截面标准差
            "group_skew",  # 截面偏度
            "group_kurt",  # 截面峰度
            "group_corr",  # 截面相关性
            "group_volatility",  # 截面波动率
        ]

        # 非线性算子
        self.nonlinear_operators = [
            "log",  # 对数变换
            "exp",  # 指数变换
            "sqrt",  # 平方根变换
            "square",  # 平方变换
            "abs",  # 绝对值
            "sign",  # 符号函数
            "inv",  # 倒数
            "pow2",  # 平方
            "pow3",  # 立方
            "sqrt_abs",  # 绝对值的平方根
        ]

        # 条件算子
        self.conditional_operators = [
            "greater_than",  # 大于
            "less_than",  # 小于
            "equal",  # 等于
            "between",  # 介于之间
            "if_else",  # 条件判断
            "where_positive",  # 仅保留正值
            "where_negative",  # 仅保留负值
            "clip",  # 截断
            "rank_greater_than",  # 排名大于阈值
        ]

        # 常用参数
        self.ts_windows = [5, 10, 20, 30, 60]
        self.quantiles = [0.25, 0.5, 0.75]
        self.clip_limits = [(0, 1), (-1, 1), (0, 100)]
        self.thresholds = [0, 0.25, 0.5, 0.75, 1]

        # 已生成的因子，用于去重
        self.generated_factors = []

        logger.info("因子生成器初始化完成")

    def _calculate_ic(self, factor_values, returns):
        """
        计算因子的信息系数(IC)

        Args:
            factor_values: 因子值序列
            returns: 未来收益序列

        Returns:
            float: IC值
        """
        # 计算秩相关系数
        return factor_values.rank().corr(returns)

    def _pseudo_evaluate(self, factors, data):
        """
        伪评估器：计算因子的IC值

        Args:
            factors: 因子表达式列表
            data: 测试数据

        Returns:
            list: 因子及其IC值的元组列表，按IC值降序排序
        """
        logger.info(f"开始伪评估 {len(factors)} 个因子")

        # 计算未来1日收益
        data["next_ret"] = data["close"].pct_change().shift(-1)

        results = []
        for factor_expr in tqdm(factors, desc="伪评估因子", unit="因子", ncols=80):
            try:
                # 计算因子值，将pd和np都导入到eval环境中
                data["factor"] = eval(factor_expr, {"data": data, "np": np, "pd": pd})

                # 计算IC值
                ic = self._calculate_ic(data["factor"], data["next_ret"])

                # 只保留有效的IC值
                if not np.isnan(ic):
                    results.append((factor_expr, ic))
            except Exception as e:
                logger.error(f"计算因子 {factor_expr} 失败: {e}")
                continue

        # 按IC值降序排序
        results.sort(key=lambda x: abs(x[1]), reverse=True)

        logger.info(f"伪评估完成，有效因子数量: {len(results)}")
        return results

    def _generate_layer1_factors(self):
        """
        生成第1层因子：基础因子

        Returns:
            list: 第1层因子表达式列表
        """
        logger.info("开始生成第1层因子")

        layer1_factors = []

        # 1. 基础价格统计
        for field in self.data_fields:
            for window in self.ts_windows:
                # 基本统计量
                layer1_factors.append(f"data['{field}'].rolling(window={window}).mean()")
                layer1_factors.append(f"data['{field}'].rolling(window={window}).std()")
                layer1_factors.append(
                    f"data['{field}'].rolling(window={window}).max() - data['{field}'].rolling(window={window}).min()"
                )
                layer1_factors.append(f"data['{field}'].rolling(window={window}).median()")
                layer1_factors.append(f"data['{field}'].rolling(window={window}).skew()")
                layer1_factors.append(f"data['{field}'].rolling(window={window}).kurt()")

        # 2. 价格变化率
        for window in self.ts_windows:
            layer1_factors.append(f"(data['close'] / data['close'].shift({window}) - 1)")
            layer1_factors.append(f"(data['volume'] / data['volume'].shift({window}) - 1)")
            # 添加收益率的非线性变换
            returns_expr = f"(data['close'] / data['close'].shift({window}) - 1)"
            for op in self.nonlinear_operators[:5]:  # 使用部分非线性算子
                if op == "log":
                    layer1_factors.append(f"np.log(1 + {returns_expr})")
                elif op == "sqrt":
                    layer1_factors.append(
                        f"np.sqrt(np.abs({returns_expr})) * np.sign({returns_expr})"
                    )
                elif op == "square":
                    layer1_factors.append(f"np.square({returns_expr})")
                elif op == "abs":
                    layer1_factors.append(f"np.abs({returns_expr})")
                elif op == "sign":
                    layer1_factors.append(f"np.sign({returns_expr})")

        # 3. 量价关系
        layer1_factors.append("data['volume'] * data['close']")
        layer1_factors.append("data['volume'] / (data['high'] - data['low'])")
        layer1_factors.append(
            "(data['volume'] * data['close']) / data['volume'].rolling(window=20).mean()"
        )

        # 4. 日内强度
        layer1_factors.append("(data['close'] - data['open']) / (data['high'] - data['low'])")
        layer1_factors.append("(data['close'] - data['low']) / (data['high'] - data['low'])")
        layer1_factors.append("(data['high'] - data['close']) / (data['high'] - data['low'])")

        # 5. 非线性变换因子
        for field in self.data_fields[:3]:  # 仅对价格字段应用非线性变换
            for op in self.nonlinear_operators[:5]:
                if op == "log":
                    layer1_factors.append(f"np.log(data['{field}'])")
                elif op == "sqrt":
                    layer1_factors.append(f"np.sqrt(data['{field}'])")
                elif op == "square":
                    layer1_factors.append(f"np.square(data['{field}'])")
                elif op == "abs":
                    layer1_factors.append(f"np.abs(data['{field}'] - data['{field}'].shift(1))")
                elif op == "inv":
                    layer1_factors.append(f"1 / (data['{field}'] + 1e-8)")

        # 6. 条件因子
        for window in self.ts_windows[:3]:  # 使用部分窗口
            # 当价格高于MA时的强度
            layer1_factors.append(
                f"np.where(data['close'] > data['close'].rolling(window={window}).mean(), data['close'] - data['close'].rolling(window={window}).mean(), 0)"
            )
            # 当成交量高于平均成交量时的变化
            layer1_factors.append(
                f"np.where(data['volume'] > data['volume'].rolling(window={window}).mean(), data['volume'] / data['volume'].rolling(window={window}).mean() - 1, 0)"
            )

        logger.info(f"第1层因子生成完成，共 {len(layer1_factors)} 个因子")
        return layer1_factors

    def _generate_layer2_factors(self, layer1_top50):
        """
        生成第2层因子：复杂度提升

        Args:
            layer1_top50: 第1层筛选出的50个优质因子

        Returns:
            list: 第2层因子表达式列表
        """
        logger.info("开始生成第2层因子")

        layer2_factors = []

        # 对第1层因子应用时间序列算子
        for factor_expr in layer1_top50:
            for ts_op in ["ts_rank", "ts_mean", "ts_std"]:
                for window in self.ts_windows[:3]:  # 使用部分窗口，避免因子数量过多
                    if ts_op == "ts_rank":
                        # 使用lambda函数来处理嵌套计算
                        new_expr = f"({factor_expr}).rolling(window={window}).rank(pct=True)"
                    elif ts_op == "ts_mean":
                        new_expr = f"({factor_expr}).rolling(window={window}).mean()"
                    elif ts_op == "ts_std":
                        new_expr = f"({factor_expr}).rolling(window={window}).std()"

                    layer2_factors.append(new_expr)

        # 对第1层因子应用截面算子
        for factor_expr in layer1_top50:
            for cs_op in self.cross_section_operators:
                if cs_op == "group_rank":
                    new_expr = f"({factor_expr}).rank(pct=True)"
                elif cs_op == "group_zscore":
                    new_expr = f"(({factor_expr}) - ({factor_expr}).mean()) / ({factor_expr}).std()"
                elif cs_op == "group_quantile":
                    new_expr = f"pd.qcut({factor_expr}, 4, labels=False)"

                layer2_factors.append(new_expr)

        logger.info(f"第2层因子生成完成，共 {len(layer2_factors)} 个因子")
        return layer2_factors

    def _generate_layer3_factors(self, layer1_top50, layer2_top50):
        """
        生成第3层因子：相关性增强

        Args:
            layer1_top50: 第1层筛选出的50个优质因子
            layer2_top50: 第2层筛选出的50个优质因子

        Returns:
            list: 第3层因子表达式列表
        """
        logger.info("开始生成第3层因子")

        layer3_factors = []

        # 合并前两层的优质因子
        prev_factors = layer1_top50 + layer2_top50

        # 计算因子间的相关性
        for i in range(len(prev_factors)):
            for j in range(i + 1, len(prev_factors)):
                for window in self.ts_windows[:3]:
                    # 时间序列相关系数
                    new_expr = (
                        f"({prev_factors[i]}).rolling(window={window}).corr({prev_factors[j]})"
                    )
                    layer3_factors.append(new_expr)

                    # 时间序列协方差
                    new_expr = (
                        f"({prev_factors[i]}).rolling(window={window}).cov({prev_factors[j]})"
                    )
                    layer3_factors.append(new_expr)

        logger.info(f"第3层因子生成完成，共 {len(layer3_factors)} 个因子")
        return layer3_factors

    def _generate_layer4_factors(self, layer1_top50, layer2_top50, layer3_top50):
        """
        生成第4层因子：专家级因子

        Args:
            layer1_top50: 第1层筛选出的50个优质因子
            layer2_top50: 第2层筛选出的50个优质因子
            layer3_top50: 第3层筛选出的50个优质因子

        Returns:
            list: 第4层因子表达式列表
        """
        logger.info("开始生成第4层因子")

        layer4_factors = []

        # 合并前三层的优质因子
        prev_factors = layer1_top50 + layer2_top50 + layer3_top50

        # 嵌套逻辑：截面排名 + 时间序列排名
        for factor_expr in prev_factors:
            for window in self.ts_windows[:2]:
                new_expr = f"({factor_expr}).rank(pct=True).rolling(window={window}).rank(pct=True)"
                layer4_factors.append(new_expr)

        # 条件表达式：基于因子值的条件处理
        for factor_expr in prev_factors:
            # 当因子值大于均值时
            new_expr = f"np.where({factor_expr} > ({factor_expr}).mean(), {factor_expr}, 0)"
            layer4_factors.append(new_expr)

            # 当因子值小于均值时
            new_expr = f"np.where({factor_expr} < ({factor_expr}).mean(), {factor_expr}, 0)"
            layer4_factors.append(new_expr)

        # 双重时间序列处理
        for factor_expr in prev_factors:
            for window1 in self.ts_windows[:2]:
                for window2 in self.ts_windows[:2]:
                    if window1 != window2:
                        new_expr = f"({factor_expr}).rolling(window={window1}).mean().rolling(window={window2}).std()"
                        layer4_factors.append(new_expr)

        logger.info(f"第4层因子生成完成，共 {len(layer4_factors)} 个因子")
        return layer4_factors

    def _generate_layer5_factors(self, layer4_top50):
        """
        生成第5层因子：终极复杂因子

        Args:
            layer4_top50: 第4层筛选出的50个优质因子

        Returns:
            list: 第5层因子表达式列表
        """
        logger.info("开始生成第5层因子")

        layer5_factors = []

        # 在第4层基础上再叠加一层组合逻辑
        for i in range(len(layer4_top50)):
            for j in range(i + 1, len(layer4_top50)):
                # 因子乘积
                new_expr = f"({layer4_top50[i]}) * ({layer4_top50[j]})"
                layer5_factors.append(new_expr)

                # 因子差值
                new_expr = f"({layer4_top50[i]}) - ({layer4_top50[j]})"
                layer5_factors.append(new_expr)

                # 因子比率
                new_expr = f"({layer4_top50[i]}) / (({layer4_top50[j]}) + 1e-8)"
                layer5_factors.append(new_expr)

        logger.info(f"第5层因子生成完成，共 {len(layer5_factors)} 个因子")
        return layer5_factors

    def generate_factors(self, test_data, output_path=None):
        """
        生成5层因子

        Args:
            test_data: 测试数据，用于伪评估
            output_path: 因子输出路径，默认None

        Returns:
            list: 最终生成的250个因子
        """
        logger.info("开始生成5层因子")

        final_factors = []

        # 使用tqdm跟踪5层因子生成过程
        for layer in tqdm(range(1, 6), desc="生成5层因子", unit="层", ncols=80):
            logger.info(f"=== 生成第{layer}层因子 ===")

            if layer == 1:
                layer_factors = self._generate_layer1_factors()
            elif layer == 2:
                layer_factors = self._generate_layer2_factors(layer1_top50)
            elif layer == 3:
                layer_factors = self._generate_layer3_factors(layer1_top50, layer2_top50)
            elif layer == 4:
                layer_factors = self._generate_layer4_factors(
                    layer1_top50, layer2_top50, layer3_top50
                )
            else:  # layer == 5
                layer_factors = self._generate_layer5_factors(layer4_top50)

            layer_eval = self._pseudo_evaluate(layer_factors, test_data)
            layer_top50 = [factor for factor, ic in layer_eval[:50]]
            final_factors.extend(layer_top50)
            logger.info(f"第{layer}层筛选出 {len(layer_top50)} 个优质因子")

            # 保存当前层的top50因子，用于下一层生成
            if layer == 1:
                layer1_top50 = layer_top50
            elif layer == 2:
                layer2_top50 = layer_top50
            elif layer == 3:
                layer3_top50 = layer_top50
            elif layer == 4:
                layer4_top50 = layer_top50

        # 去重
        final_factors = list(set(final_factors))
        logger.info(f"去重后最终因子数量: {len(final_factors)}")

        # 保存因子
        if output_path:
            with open(output_path, "w") as f:
                for i, factor in enumerate(final_factors):
                    f.write(f"FACTOR_{i + 1}: {factor}\n")
            logger.info(f"因子已保存到: {output_path}")

        logger.info("5层因子生成完成")
        return final_factors


# 测试脚本
if __name__ == "__main__":
    # 创建测试数据
    import numpy as np
    import pandas as pd

    # 创建日期范围
    dates = pd.date_range(start="2023-01-01", end="2023-12-31", freq="D")

    # 创建随机价格数据
    np.random.seed(42)
    price = 100.0
    prices = []
    for _ in range(len(dates)):
        change = np.random.normal(0, 2, 1)[0]
        price += change
        prices.append(price)

    # 创建数据框
    test_data = pd.DataFrame(
        {
            "timestamp": dates,
            "open": [p + np.random.normal(0, 1) for p in prices],
            "high": [p + np.random.normal(1, 1.5) for p in prices],
            "low": [p + np.random.normal(-1.5, 1) for p in prices],
            "close": prices,
            "volume": [np.random.normal(1000000, 500000) for _ in range(len(dates))],
        }
    )

    # 设置索引
    test_data.set_index("timestamp", inplace=True)

    # 创建因子生成器
    generator = FactorGenerator()

    # 生成因子
    factors = generator.generate_factors(test_data, output_path="generated_factors.txt")

    print(f"因子生成完成，共生成 {len(factors)} 个因子")
    print("前10个因子示例:")
    for i, factor in enumerate(factors[:10]):
        print(f"{i + 1}. {factor}")
