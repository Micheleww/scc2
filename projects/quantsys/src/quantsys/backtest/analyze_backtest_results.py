#!/usr/bin/env python3
"""
分析回测结果统计信息
"""

import pandas as pd

# 读取回测结果文件
df = pd.read_csv("d:/quantsys/ai_collaboration/backtest_results/strategy_summary.csv")

# 打印统计结果
print("=== 1000个BTC日线策略回测结果统计 ===")
print(f"总策略数: {len(df)}")
print(f"有交易的策略数: {len(df[df['total_trades'] > 0])}")
print(f"盈利策略数: {len(df[df['total_profit'] > 0])}")
print(f"亏损策略数: {len(df[df['total_profit'] < 0])}")
print(f"盈利策略占比: {len(df[df['total_profit'] > 0]) / len(df) * 100:.2f}%")
print(f"平均总收益率: {df['total_profit'].mean():.2f} USDT")
print(f"平均每策略交易次数: {df['total_trades'].mean():.2f}")
print(f"平均胜率: {df['win_rate'].mean() * 100:.2f}%")

# 最大和最小收益率
max_profit_idx = df["total_profit"].idxmax()
min_profit_idx = df["total_profit"].idxmin()
print(
    f"最大收益率: {df['total_profit'].max():.2f} USDT (策略: {df.loc[max_profit_idx, 'strategy_name']})"
)
print(
    f"最大亏损: {df['total_profit'].min():.2f} USDT (策略: {df.loc[min_profit_idx, 'strategy_name']})"
)

# 收益率分布
print("\n=== 收益率分布 ===")
print(f"收益率>10 USDT的策略数: {len(df[df['total_profit'] > 10])}")
print(f"收益率>5 USDT的策略数: {len(df[df['total_profit'] > 5])}")
print(
    f"收益率在0-5 USDT之间的策略数: {len(df[(df['total_profit'] > 0) & (df['total_profit'] <= 5)])}"
)
print(f"收益率为0的策略数: {len(df[df['total_profit'] == 0])}")
print(f"收益率<-5 USDT的策略数: {len(df[df['total_profit'] < -5])}")

# 交易次数分布
print("\n=== 交易次数分布 ===")
print(f"交易次数>10次的策略数: {len(df[df['total_trades'] > 10])}")
print(f"交易次数5-10次的策略数: {len(df[(df['total_trades'] >= 5) & (df['total_trades'] <= 10)])}")
print(f"交易次数1-4次的策略数: {len(df[(df['total_trades'] >= 1) & (df['total_trades'] < 5)])}")
print(f"没有交易的策略数: {len(df[df['total_trades'] == 0])}")

# 按收益率排序，显示前10个最佳策略
print("\n=== 前10个最佳策略 ===")
top_10 = df.nlargest(10, "total_profit")[
    ["strategy_name", "total_profit", "total_trades", "win_rate", "avg_profit_per_trade"]
]
top_10["win_rate"] = top_10["win_rate"] * 100  # 转换为百分比
print(top_10.to_string(index=False, float_format="%.2f"))

# 按亏损排序，显示前5个最差策略
print("\n=== 前5个最差策略 ===")
worst_5 = df.nsmallest(5, "total_profit")[
    ["strategy_name", "total_profit", "total_trades", "win_rate"]
]
worst_5["win_rate"] = worst_5["win_rate"] * 100  # 转换为百分比
print(worst_5.to_string(index=False, float_format="%.2f"))
