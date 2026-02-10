#!/usr/bin/env python3
"""
多策略对比分析模块

该脚本用于对比不同策略的回测结果，生成对比分析报告。
"""

import json
import logging
import os
import sys
from datetime import datetime

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# 配置日志
log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
os.makedirs(log_dir, exist_ok=True)
log_file = os.path.join(
    log_dir, f"multi_strategy_comparison_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.FileHandler(log_file), logging.StreamHandler()],
)
logger = logging.getLogger(__name__)


class MultiStrategyComparator:
    """多策略对比分析类"""

    def __init__(self):
        """初始化对比分析器"""
        self.base_dir = os.path.dirname(os.path.abspath(__file__))
        self.root_dir = os.path.dirname(self.base_dir)

    def load_strategy_results(self, results_paths):
        """加载多个策略的回测结果"""
        logger.info(f"加载 {len(results_paths)} 个策略的回测结果")

        all_results = {}

        for path in results_paths:
            # 转换为绝对路径
            abs_path = os.path.join(self.root_dir, path)

            if not os.path.exists(abs_path):
                logger.error(f"策略回测结果文件不存在: {abs_path}")
                continue

            try:
                with open(abs_path, encoding="utf-8") as f:
                    results = json.load(f)

                # 提取策略名称
                strategy_name = results.get("回测基本信息", {}).get(
                    "策略名称", f"策略_{len(all_results) + 1}"
                )
                all_results[strategy_name] = results
                logger.info(f"成功加载策略: {strategy_name}")

            except Exception as e:
                logger.error(f"加载策略回测结果失败: {abs_path}, 错误: {e}")
                continue

        logger.info(f"共成功加载 {len(all_results)} 个策略的回测结果")
        return all_results

    def compare_metrics(self, all_results):
        """对比策略绩效指标"""
        logger.info("开始对比策略绩效指标")

        # 准备对比数据
        metrics_to_compare = ["夏普比率", "最大回撤", "年化收益率", "胜率", "盈亏比", "交易次数"]

        comparison_data = {}

        for strategy_name, results in all_results.items():
            comparison_data[strategy_name] = {}

            for metric in metrics_to_compare:
                if metric in results["绩效指标"]:
                    comparison_data[strategy_name][metric] = results["绩效指标"][metric]
                else:
                    comparison_data[strategy_name][metric] = None

        return comparison_data

    def generate_metrics_comparison_chart(self, comparison_data):
        """生成指标对比图表"""
        logger.info("生成指标对比图表")

        # 转换为DataFrame以便处理
        df = pd.DataFrame(comparison_data).T
        df = df.dropna(axis=1, how="all")  # 删除所有值都为None的列

        # 生成对比图表
        fig = make_subplots(
            rows=2,
            cols=3,
            subplot_titles=tuple(df.columns),
            vertical_spacing=0.15,
            horizontal_spacing=0.1,
        )

        # 为每个指标创建子图
        row = 1
        col = 1

        for metric in df.columns:
            fig.add_trace(
                go.Bar(
                    x=df.index,
                    y=df[metric],
                    name=metric,
                    marker_color=plotly.colors.qualitative.Set1[: len(df.index)],
                ),
                row=row,
                col=col,
            )

            # 更新坐标轴标签
            fig.update_xaxes(title_text="策略名称", row=row, col=col)
            fig.update_yaxes(title_text=metric, row=row, col=col)

            # 处理下一个位置
            col += 1
            if col > 3:
                col = 1
                row += 1

        # 更新整体布局
        fig.update_layout(
            height=800, title_text="多策略绩效指标对比", template="plotly_white", showlegend=False
        )

        return fig

    def generate_risk_return_scatter(self, all_results):
        """生成风险收益散点图"""
        logger.info("生成风险收益散点图")

        # 准备数据
        strategy_names = list(all_results.keys())
        risk = [all_results[s]["绩效指标"]["最大回撤"] for s in strategy_names]
        return_ = [all_results[s]["绩效指标"]["年化收益率"] for s in strategy_names]
        sharpe = [all_results[s]["绩效指标"]["夏普比率"] for s in strategy_names]

        # 生成散点图
        fig = go.Figure()

        # 添加散点
        for name, rsk, ret, shp in zip(strategy_names, risk, return_, sharpe):
            fig.add_trace(
                go.Scatter(
                    x=[rsk],
                    y=[ret],
                    mode="markers+text",
                    name=name,
                    marker=dict(
                        size=shp * 10,  # 用大小表示夏普比率
                        color=shp,  # 用颜色表示夏普比率
                        colorscale="Viridis",
                        showscale=True,
                        colorbar_title="夏普比率",
                    ),
                    text=[f"{name}<br>夏普: {shp:.2f}"],
                    textposition="top center",
                    hovertemplate="策略: %{text}<br>风险: %{x:.2%}<br>收益: %{y:.2%}",
                )
            )

        # 更新布局
        fig.update_layout(
            title="多策略风险收益对比",
            xaxis_title="风险 (最大回撤)",
            yaxis_title="收益 (年化收益率)",
            xaxis_tickformat=".1%",
            yaxis_tickformat=".1%",
            template="plotly_white",
            hovermode="closest",
        )

        return fig

    def generate_comparison_report(
        self, all_results, output_path="ai_collaboration/data/multi_strategy_comparison.md"
    ):
        """生成对比分析报告"""
        logger.info("生成多策略对比分析报告")

        # 生成指标对比数据
        comparison_data = self.compare_metrics(all_results)

        # 生成Markdown报告
        report_content = "# 多策略对比分析报告\n\n"
        report_content += f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        report_content += f"参与对比的策略数量: {len(all_results)}\n\n"

        # 1. 策略基本信息
        report_content += "## 1. 策略基本信息\n\n"
        report_content += "| 策略名称 | 回测时间范围 | 初始资金 | 时间周期 | 交易次数 |\n"
        report_content += "|---------|-------------|---------|---------|---------|\n"

        for strategy_name, results in all_results.items():
            basic_info = results["回测基本信息"]
            report_content += f"| {strategy_name} | {basic_info.get('回测时间范围', 'N/A')} | {basic_info.get('初始资金', 'N/A')} | {basic_info.get('时间周期', 'N/A')} | {results['绩效指标'].get('交易次数', 'N/A')} |\n"

        # 2. 绩效指标对比
        report_content += "\n## 2. 绩效指标对比\n\n"
        report_content += "| 策略名称 | 夏普比率 | 最大回撤 | 年化收益率 | 胜率 | 盈亏比 |\n"
        report_content += "|---------|---------|---------|-----------|------|--------|\n"

        for strategy_name, metrics in comparison_data.items():
            report_content += f"| {strategy_name} | "
            report_content += f"{metrics.get('夏普比率', 'N/A'):.2f} | "
            report_content += f"{metrics.get('最大回撤', 'N/A'):.2%} | "
            report_content += f"{metrics.get('年化收益率', 'N/A'):.2%} | "
            report_content += f"{metrics.get('胜率', 'N/A'):.2%} | "
            report_content += f"{metrics.get('盈亏比', 'N/A'):.2f} |\n"

        # 3. 综合评价
        report_content += "\n## 3. 综合评价\n\n"

        # 找出各个指标的最优策略
        best_sharpe = max(all_results.items(), key=lambda x: x[1]["绩效指标"]["夏普比率"])[0]
        best_return = max(all_results.items(), key=lambda x: x[1]["绩效指标"]["年化收益率"])[0]
        best_risk = min(all_results.items(), key=lambda x: x[1]["绩效指标"]["最大回撤"])[0]
        best_winrate = max(all_results.items(), key=lambda x: x[1]["绩效指标"]["胜率"])[0]

        report_content += f"- **最佳夏普比率**: {best_sharpe} ({all_results[best_sharpe]['绩效指标']['夏普比率']:.2f})\n"
        report_content += f"- **最高年化收益**: {best_return} ({all_results[best_return]['绩效指标']['年化收益率']:.2%})\n"
        report_content += f"- **最低最大回撤**: {best_risk} ({all_results[best_risk]['绩效指标']['最大回撤']:.2%})\n"
        report_content += f"- **最高胜率**: {best_winrate} ({all_results[best_winrate]['绩效指标']['胜率']:.2%})\n\n"

        # 4. 策略对比建议
        report_content += "## 4. 策略对比建议\n\n"

        # 基于不同投资目标的建议
        report_content += "### 4.1 基于不同投资目标的建议\n\n"
        report_content += "- **追求高收益**: 推荐选择年化收益率最高的策略，但需注意控制风险\n"
        report_content += "- **风险厌恶型**: 推荐选择最大回撤最低的策略，牺牲部分收益换取稳定性\n"
        report_content += "- **平衡型**: 推荐选择夏普比率最高的策略，兼顾收益和风险\n\n"

        # 5. 策略优化方向
        report_content += "## 5. 策略优化方向\n\n"
        report_content += "### 5.1 各策略优化建议\n\n"

        for strategy_name, results in all_results.items():
            report_content += f"#### {strategy_name}\n\n"

            # 基于指标提出优化建议
            if results["绩效指标"]["夏普比率"] < 1.0:
                report_content += "- 夏普比率较低，建议优化风险控制机制\n"

            if results["绩效指标"]["最大回撤"] > 0.15:
                report_content += "- 最大回撤较大，建议改进止损策略\n"

            if results["绩效指标"]["胜率"] < 0.5:
                report_content += "- 胜率较低，建议优化入场信号\n"

            if results["绩效指标"]["盈亏比"] < 1.5:
                report_content += "- 盈亏比较低，建议改进出场策略，让利润奔跑\n"

            report_content += "\n"

        # 6. 可视化结果
        report_content += "## 6. 可视化结果\n\n"
        report_content += "![风险收益对比](backtest_visualization.html#risk-return-comparison)\n\n"
        report_content += "![绩效指标对比](backtest_visualization.html#metrics-comparison)\n\n"

        # 保存报告
        output_abs_path = os.path.join(self.root_dir, output_path)
        os.makedirs(os.path.dirname(output_abs_path), exist_ok=True)

        with open(output_abs_path, "w", encoding="utf-8") as f:
            f.write(report_content)

        logger.info(f"多策略对比分析报告已生成: {output_abs_path}")
        return report_content

    def generate_comparison_charts(
        self, all_results, output_path="ai_collaboration/data/multi_strategy_comparison.html"
    ):
        """生成对比图表HTML文件"""
        logger.info("生成多策略对比图表HTML文件")

        # 生成指标对比图表
        comparison_data = self.compare_metrics(all_results)
        metrics_fig = self.generate_metrics_comparison_chart(comparison_data)

        # 生成风险收益散点图
        risk_return_fig = self.generate_risk_return_scatter(all_results)

        # 创建综合报告
        report_fig = make_subplots(
            rows=2,
            cols=1,
            subplot_titles=("多策略绩效指标对比", "多策略风险收益对比"),
            vertical_spacing=0.15,
        )

        # 添加图表到报告
        # 由于指标对比图表是多个子图，我们需要单独处理
        # 这里我们直接使用两个独立的图表

        # 保存为HTML
        output_abs_path = os.path.join(self.root_dir, output_path)
        os.makedirs(os.path.dirname(output_abs_path), exist_ok=True)

        # 创建HTML内容
        html_content = """
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>多策略对比分析</title>
    <script src="https://cdn.plot.ly/plotly-latest.min.js"></script>
    <style>
        body {
            font-family: Arial, sans-serif;
            margin: 20px;
            background-color: #f5f5f5;
        }
        .container {
            max-width: 1200px;
            margin: 0 auto;
            background-color: white;
            padding: 20px;
            border-radius: 8px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        }
        h1 {
            color: #333;
            text-align: center;
        }
        .chart-container {
            margin: 20px 0;
            border: 1px solid #e0e0e0;
            border-radius: 4px;
            padding: 10px;
        }
        .chart-title {
            font-size: 18px;
            font-weight: bold;
            margin-bottom: 10px;
            color: #555;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>多策略对比分析</h1>
        
        <div class="chart-container" id="metrics-comparison">
            <div class="chart-title">绩效指标对比</div>
        </div>
        
        <div class="chart-container" id="risk-return-comparison">
            <div class="chart-title">风险收益对比</div>
        </div>
    </div>
    
    <script>
        // 指标对比图表数据
        var metricsChartData = %s;
        Plotly.newPlot('metrics-comparison', metricsChartData.data, metricsChartData.layout);
        
        // 风险收益对比图表数据
        var riskReturnChartData = %s;
        Plotly.newPlot('risk-return-comparison', riskReturnChartData.data, riskReturnChartData.layout);
    </script>
</body>
</html>
        """

        # 将图表转换为JSON
        metrics_json = metrics_fig.to_json()
        risk_return_json = risk_return_fig.to_json()

        # 填充HTML内容
        html_content = html_content % (metrics_json, risk_return_json)

        # 保存HTML文件
        with open(output_abs_path, "w", encoding="utf-8") as f:
            f.write(html_content)

        logger.info(f"多策略对比图表HTML已生成: {output_abs_path}")
        return output_abs_path

    def run_comparison(
        self,
        results_paths,
        output_report_path="ai_collaboration/data/multi_strategy_comparison.md",
        output_chart_path="ai_collaboration/data/multi_strategy_comparison.html",
    ):
        """运行完整的多策略对比分析"""
        logger.info("开始完整的多策略对比分析")

        # 加载策略回测结果
        all_results = self.load_strategy_results(results_paths)

        if not all_results:
            logger.error("没有成功加载任何策略的回测结果，无法进行对比分析")
            return False

        # 生成对比报告
        report_content = self.generate_comparison_report(all_results, output_report_path)

        # 生成对比图表
        chart_path = self.generate_comparison_charts(all_results, output_chart_path)

        logger.info("多策略对比分析完成")
        return {
            "report_path": output_report_path,
            "chart_path": chart_path,
            "strategy_count": len(all_results),
        }


def main():
    """主函数"""
    if len(sys.argv) < 3:
        print(
            "用法: python multi_strategy_comparison.py <结果路径1> <结果路径2> [结果路径3...] [输出报告路径] [输出图表路径]"
        )
        print(
            "示例: python multi_strategy_comparison.py ai_collaboration/data/backtest_results_v1.json ai_collaboration/data/backtest_results_v2.json"
        )
        sys.exit(1)

    # 解析命令行参数
    results_paths = sys.argv[1:-2] if len(sys.argv) > 3 else sys.argv[1:]
    output_report_path = (
        sys.argv[-2] if len(sys.argv) > 3 else "ai_collaboration/data/multi_strategy_comparison.md"
    )
    output_chart_path = (
        sys.argv[-1]
        if len(sys.argv) > 4
        else "ai_collaboration/data/multi_strategy_comparison.html"
    )

    comparator = MultiStrategyComparator()
    result = comparator.run_comparison(results_paths, output_report_path, output_chart_path)

    if result:
        logger.info("多策略对比分析成功完成")
        logger.info(f"对比报告: {result['report_path']}")
        logger.info(f"对比图表: {result['chart_path']}")
        logger.info(f"参与对比的策略数量: {result['strategy_count']}")
        sys.exit(0)
    else:
        logger.error("多策略对比分析失败")
        sys.exit(1)


if __name__ == "__main__":
    # 确保plotly可用
    try:
        import plotly
        import plotly.colors
    except ImportError:
        logger.error("缺少plotly库，请先安装: pip install plotly")
        sys.exit(1)

    main()
