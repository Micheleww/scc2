import json
import logging
import os
from datetime import datetime

import pandas as pd
import talib
from sklearn.feature_selection import mutual_info_regression
from sklearn.preprocessing import StandardScaler

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(
            f"d:/quantsys/ai_collaboration/logs/crypto_task_20260105_002_feature_ai_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
        ),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)


# 读取任务配置
def read_task_config():
    with open("d:/quantsys/ai_collaboration/tasks.json", encoding="utf-8") as f:
        tasks_config = json.load(f)
    for task in tasks_config["tasks"]:
        if task["任务ID"] == "crypto_task_20260105_002":
            return task
    return None


# 更新任务状态
def update_status(status, progress, output_path="", error=None, feedback=""):
    with open("d:/quantsys/ai_collaboration/status.json", encoding="utf-8") as f:
        status_config = json.load(f)

    status_config["任务状态"]["crypto_task_20260105_002"].update(
        {
            "状态": status,
            "进度": progress,
            "最后更新时间": datetime.now().isoformat(),
            "输出路径": output_path,
            "异常信息": error,
            "反馈信息": feedback,
        }
    )

    # 更新全局状态
    active_tasks = sum(
        1 for t in status_config["任务状态"].values() if t["状态"] in ["in_progress", "执行中"]
    )
    completed_tasks = sum(
        1 for t in status_config["任务状态"].values() if t["状态"] in ["completed", "完成"]
    )
    failed_tasks = sum(
        1 for t in status_config["任务状态"].values() if t["状态"] in ["failed", "失败"]
    )

    status_config["全局状态"].update(
        {
            "当前迭代周期": 1,
            "总体进度": sum(t["进度"] for t in status_config["任务状态"].values())
            / len(status_config["任务状态"]),
            "状态": "running"
            if active_tasks > 0
            else "completed"
            if completed_tasks > 0
            else "idle",
            "最后更新时间": datetime.now().isoformat(),
            "活跃任务数": active_tasks,
            "已完成任务数": completed_tasks,
            "失败任务数": failed_tasks,
        }
    )

    with open("d:/quantsys/ai_collaboration/status.json", "w", encoding="utf-8") as f:
        json.dump(status_config, f, indent=2, ensure_ascii=False)


# 计算RSI
def calculate_rsi(df, timeperiod=14):
    df[f"RSI_{timeperiod}"] = talib.RSI(df["close"], timeperiod=timeperiod)
    return df


# 计算MACD
def calculate_macd(df, fastperiod=12, slowperiod=26, signalperiod=9):
    df["MACD"], df["MACD_signal"], df["MACD_hist"] = talib.MACD(
        df["close"], fastperiod=fastperiod, slowperiod=slowperiod, signalperiod=signalperiod
    )
    return df


# 计算移动平均线
def calculate_ma(df, timeperiods=[5, 10, 20, 50, 100, 200]):
    for period in timeperiods:
        df[f"MA_{period}"] = talib.SMA(df["close"], timeperiod=period)
    return df


# 计算布林带
def calculate_bollinger_bands(df, timeperiod=20, nbdevup=2, nbdevdn=2):
    df["BB_upper"], df["BB_middle"], df["BB_lower"] = talib.BBANDS(
        df["close"], timeperiod=timeperiod, nbdevup=nbdevup, nbdevdn=nbdevdn
    )
    df["BB_width"] = (df["BB_upper"] - df["BB_lower"]) / df["BB_middle"]
    return df


# 计算ATR
def calculate_atr(df, timeperiod=14):
    df[f"ATR_{timeperiod}"] = talib.ATR(df["high"], df["low"], df["close"], timeperiod=timeperiod)
    return df


# 计算特征重要性
def calculate_feature_importance(df):
    # 准备特征和目标变量
    # 使用未来1小时的收益率作为目标变量
    df["target"] = df["close"].shift(-1) / df["close"] - 1

    # 删除最后一行，因为没有目标值
    df = df.dropna()

    # 提取特征和目标
    features = df.columns.drop(["open", "high", "low", "close", "volume", "target"])
    X = df[features]
    y = df["target"]

    # 标准化特征
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)

    # 计算互信息
    mi = mutual_info_regression(X_scaled, y)

    # 生成特征重要性字典
    feature_importance = {feature: float(mi[i]) for i, feature in enumerate(features)}

    # 按重要性排序
    sorted_importance = dict(sorted(feature_importance.items(), key=lambda x: x[1], reverse=True))

    return sorted_importance


# 计算特征相关性
def calculate_feature_correlation(df):
    # 提取特征
    features = df.columns.drop(["open", "high", "low", "close", "volume"])
    X = df[features]

    # 计算相关矩阵
    correlation_matrix = X.corr()

    # 转换为字典格式
    correlation_dict = correlation_matrix.to_dict()

    return correlation_dict


# 生成特征重要性报告
def generate_importance_report(sorted_importance, correlation_dict, output_path):
    logger.info("开始生成特征重要性报告")

    report = {
        "特征重要性排序": sorted_importance,
        "特征相关性分析": correlation_dict,
        "生成时间": datetime.now().isoformat(),
        "报告说明": {
            "特征重要性计算方法": "互信息回归",
            "目标变量": "未来1小时收益率",
            "相关性计算方法": "皮尔逊相关系数",
        },
    }

    # 保存报告
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False, default=str)

    logger.info(f"特征重要性报告已保存到: {output_path}")
    return report


# 主函数
def main():
    try:
        # 读取任务配置
        task_config = read_task_config()
        if not task_config:
            logger.error("任务配置未找到")
            return

        # 更新任务状态为执行中
        update_status("in_progress", 10, feedback="开始执行特征工程任务")

        # 提取任务参数
        input_file = task_config["输入资源"]["数据文件路径"]
        factors = task_config["输入资源"]["需要计算的因子"]
        output_file = task_config["输出要求"]["文件路径"]

        # 检查输入文件是否存在
        if not os.path.exists(input_file):
            logger.error(f"输入文件不存在: {input_file}")
            update_status(
                "failed", 0, error=f"输入文件不存在: {input_file}", feedback="任务执行失败"
            )
            return

        # 读取输入数据
        update_status("in_progress", 20, feedback="正在读取输入数据")
        df = pd.read_csv(input_file, index_col=0, parse_dates=True)
        logger.info(f"读取数据成功，共 {len(df)} 条记录")

        # 计算各种因子
        update_status("in_progress", 40, feedback="正在计算量化因子")

        # 计算RSI
        if "RSI" in factors:
            df = calculate_rsi(df, timeperiod=14)
            logger.info("RSI计算完成")

        # 计算MACD
        if "MACD" in factors:
            df = calculate_macd(df)
            logger.info("MACD计算完成")

        # 计算移动平均线
        if "MA" in factors:
            df = calculate_ma(df)
            logger.info("移动平均线计算完成")

        # 计算布林带
        if "Bollinger Bands" in factors:
            df = calculate_bollinger_bands(df)
            logger.info("布林带计算完成")

        # 计算ATR
        if "ATR" in factors:
            df = calculate_atr(df)
            logger.info("ATR计算完成")

        # 删除含有缺失值的行
        df = df.dropna()
        logger.info(f"因子计算完成，处理后共 {len(df)} 条记录")

        # 保存特征数据
        update_status("in_progress", 70, feedback="正在保存特征数据")
        df.to_csv(output_file)
        logger.info(f"特征数据已保存到: {output_file}")

        # 计算特征重要性和相关性
        update_status("in_progress", 80, feedback="正在计算特征重要性和相关性")
        feature_importance = calculate_feature_importance(df)
        correlation_dict = calculate_feature_correlation(df)

        # 生成特征重要性报告
        importance_report_path = output_file.replace(".csv", "_importance_report.json")
        report = generate_importance_report(
            feature_importance, correlation_dict, importance_report_path
        )

        # 更新任务状态为完成
        update_status(
            "completed", 100, output_path=output_file, feedback="特征工程与因子计算任务完成"
        )

        logger.info("任务完成")

    except Exception as e:
        logger.error(f"任务执行失败: {e}")
        update_status("failed", 0, error=str(e), feedback="任务执行失败")
        raise


if __name__ == "__main__":
    main()
