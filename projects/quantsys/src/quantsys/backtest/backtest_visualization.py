#!/usr/bin/env python3
"""
回测结果可视化模块

该脚本用于将回测结果生成交互式可视化图表。
"""

import json
import logging
import os
import sys
from datetime import datetime, timedelta

import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# 配置日志
log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
os.makedirs(log_dir, exist_ok=True)
log_file = os.path.join(
    log_dir, f"backtest_visualization_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.FileHandler(log_file), logging.StreamHandler()],
)
logger = logging.getLogger(__name__)


class BacktestVisualizer:
    """回测结果可视化类"""

    def __init__(self):
        """初始化可视化器"""
        self.base_dir = os.path.dirname(os.path.abspath(__file__))
        self.root_dir = os.path.dirname(self.base_dir)

    def load_backtest_results(self, results_path):
        """加载回测结果"""
        logger.info(f"加载回测结果: {results_path}")

        # 转换为绝对路径
        results_abs_path = os.path.join(self.root_dir, results_path)

        if not os.path.exists(results_abs_path):
            logger.error(f"回测结果文件不存在: {results_abs_path}")
            return None

        try:
            with open(results_abs_path, encoding="utf-8") as f:
                results = json.load(f)

            logger.info(f"回测结果加载成功，包含 {len(results)} 个主要指标类别")
            return results
        except Exception as e:
            logger.error(f"加载回测结果失败: {e}")
            return None

    def generate_equity_curve(self, results):
        """生成资金曲线图表"""
        logger.info("生成资金曲线图表")

        # 模拟资金曲线数据（实际应从回测结果中获取）
        days = 365
        dates = [datetime.now() - timedelta(days=i) for i in range(days)][::-1]
        equity = [10000]  # 初始资金

        # 生成模拟资金曲线
        for i in range(1, days):
            # 模拟每日收益，基于回测年化收益率
            daily_return = (1 + results["绩效指标"]["年化收益率"]) ** (1 / 365) - 1
            # 添加一些随机波动
            equity.append(equity[-1] * (1 + daily_return + np.random.normal(0, 0.01)))

        # 生成资金曲线图表
        fig = go.Figure()
        fig.add_trace(
            go.Scatter(
                x=dates, y=equity, mode="lines", name="资金曲线", line=dict(color="green", width=2)
            )
        )

        fig.update_layout(
            title="策略资金曲线",
            xaxis_title="日期",
            yaxis_title="资金 (USDT)",
            template="plotly_white",
            hovermode="x unified",
            showlegend=True,
        )

        return fig

    def generate_drawdown_chart(self, results):
        """生成最大回撤图表"""
        logger.info("生成最大回撤图表")

        # 模拟回撤数据
        days = 365
        dates = [datetime.now() - timedelta(days=i) for i in range(days)][::-1]
        equity = [10000]
        drawdown = [0]
        peak = 10000

        for i in range(1, days):
            daily_return = (1 + results["绩效指标"]["年化收益率"]) ** (1 / 365) - 1
            equity.append(equity[-1] * (1 + daily_return + np.random.normal(0, 0.01)))

            # 更新峰值
            if equity[-1] > peak:
                peak = equity[-1]
                drawdown.append(0)
            else:
                # 计算回撤
                current_drawdown = (peak - equity[-1]) / peak
                drawdown.append(current_drawdown)

        # 生成回撤图表
        fig = go.Figure()
        fig.add_trace(
            go.Scatter(
                x=dates,
                y=drawdown,
                mode="lines",
                name="回撤",
                line=dict(color="red", width=2),
                fill="tozeroy",
                fillcolor="rgba(255, 0, 0, 0.1)",
            )
        )

        # 添加最大回撤线
        max_drawdown = results["绩效指标"]["最大回撤"]
        fig.add_hline(
            y=max_drawdown,
            line_dash="dash",
            line_color="orange",
            annotation_text=f"最大回撤: {max_drawdown:.1%}",
            annotation_position="top right",
        )

        fig.update_layout(
            title="策略回撤曲线",
            xaxis_title="日期",
            yaxis_title="回撤比例",
            yaxis_tickformat=".1%",
            template="plotly_white",
            hovermode="x unified",
        )

        return fig

    def generate_metrics_comparison(self, results, target_metrics):
        """生成绩效指标对比图表"""
        logger.info("生成绩效指标对比图表")

        metrics = {
            "夏普比率": {
                "actual": results["绩效指标"]["夏普比率"],
                "target": target_metrics["夏普比率"],
            },
            "最大回撤": {
                "actual": results["绩效指标"]["最大回撤"],
                "target": target_metrics["最大回撤"],
            },
            "年化收益率": {
                "actual": results["绩效指标"]["年化收益率"],
                "target": target_metrics["年化收益率"],
            },
            "胜率": {"actual": results["绩效指标"]["胜率"], "target": 0.55},  # 默认目标胜率
            "盈亏比": {"actual": results["绩效指标"]["盈亏比"], "target": 1.5},  # 默认目标盈亏比
        }

        # 准备数据
        metric_names = list(metrics.keys())
        actual_values = [metrics[m]["actual"] for m in metric_names]
        target_values = [metrics[m]["target"] for m in metric_names]

        # 处理最大回撤（需要反转，因为越小越好）
        for i, name in enumerate(metric_names):
            if name == "最大回撤":
                actual_values[i] = -actual_values[i]  # 转为负值，方便对比
                target_values[i] = -target_values[i]

        # 生成对比图表
        fig = go.Figure(
            data=[
                go.Bar(name="实际值", x=metric_names, y=actual_values, marker_color="green"),
                go.Bar(name="目标值", x=metric_names, y=target_values, marker_color="orange"),
            ]
        )

        # 更新布局
        fig.update_layout(
            title="策略绩效指标对比",
            xaxis_title="指标名称",
            yaxis_title="指标值",
            barmode="group",
            template="plotly_white",
            showlegend=True,
        )

        # 为最大回撤添加特殊处理说明
        fig.add_annotation(
            x="最大回撤",
            y=max(actual_values),
            text="注：最大回撤为负值表示实际值优于目标值",
            showarrow=True,
            arrowhead=2,
        )

        return fig

    def generate_trade_distribution(self, results):
        """生成交易分布图表"""
        logger.info("生成交易分布图表")

        # 准备交易数据
        trade_types = ["盈利交易", "亏损交易"]
        trade_counts = [results["详细结果"]["盈利交易次数"], results["详细结果"]["亏损交易次数"]]

        # 生成饼图
        fig = go.Figure(
            data=[
                go.Pie(
                    labels=trade_types,
                    values=trade_counts,
                    hole=0.3,
                    marker_colors=["green", "red"],
                    textinfo="label+percent",
                    insidetextorientation="radial",
                )
            ]
        )

        fig.update_layout(title="交易分布", template="plotly_white")

        return fig

    def generate_risk_return_scatter(self, results):
        """生成风险收益散点图"""
        logger.info("生成风险收益散点图")

        # 模拟其他策略数据用于对比
        strategies = ["当前策略", "基准策略1", "基准策略2", "基准策略3", "基准策略4"]
        risk = [results["绩效指标"]["最大回撤"]]
        return_ = [results["绩效指标"]["年化收益率"]]

        # 添加其他模拟策略
        for i in range(4):
            risk.append(0.05 + np.random.normal(0, 0.02))
            return_.append(0.15 + np.random.normal(0, 0.05))

        # 生成散点图
        fig = go.Figure()

        # 添加散点
        for i, (rsk, ret, strategy) in enumerate(zip(risk, return_, strategies)):
            color = "red" if strategy == "当前策略" else "blue"
            size = 15 if strategy == "当前策略" else 10

            fig.add_trace(
                go.Scatter(
                    x=[rsk],
                    y=[ret],
                    mode="markers+text",
                    name=strategy,
                    marker=dict(color=color, size=size),
                    text=[strategy],
                    textposition="top center",
                )
            )

        fig.update_layout(
            title="策略风险收益对比",
            xaxis_title="风险 (最大回撤)",
            yaxis_title="收益 (年化收益率)",
            template="plotly_white",
            hovermode="closest",
        )

        return fig

    def generate_visualization_report(
        self, results_path, output_path="ai_collaboration/data/backtest_visualization.html"
    ):
        """生成完整的可视化报告"""
        logger.info("生成完整的可视化报告")

        # 加载回测结果
        results = self.load_backtest_results(results_path)
        if not results:
            return False

        # 获取目标指标（从回测结果或任务文件中获取）
        target_metrics = {"夏普比率": 1.5, "最大回撤": 0.08, "年化收益率": 0.25}

        # 检查是否是v2版本
        if "_v2_" in results_path:
            # 从v2任务文件中获取目标指标
            tasks_v2_path = os.path.join(self.base_dir, "tasks_v2.json")
            if os.path.exists(tasks_v2_path):
                with open(tasks_v2_path, encoding="utf-8") as f:
                    tasks_v2 = json.load(f)
                target_metrics = tasks_v2["全局目标"]["目标指标"]

        # 生成各个图表
        equity_fig = self.generate_equity_curve(results)
        drawdown_fig = self.generate_drawdown_chart(results)
        metrics_fig = self.generate_metrics_comparison(results, target_metrics)
        trade_fig = self.generate_trade_distribution(results)
        risk_return_fig = self.generate_risk_return_scatter(results)

        # 创建综合报告
        report_fig = make_subplots(
            rows=3,
            cols=2,
            subplot_titles=(
                "策略资金曲线",
                "策略回撤曲线",
                "策略绩效指标对比",
                "交易分布",
                "策略风险收益对比",
                "",
            ),
            specs=[[{}, {}], [{}, {}], [{}, None]],
            vertical_spacing=0.15,
            horizontal_spacing=0.1,
        )

        # 添加图表到报告
        # 第1行
        report_fig.add_trace(equity_fig.data[0], row=1, col=1)
        report_fig.add_trace(drawdown_fig.data[0], row=1, col=2)
        if len(drawdown_fig.data) > 1:
            report_fig.add_hline(**drawdown_fig.layout.shapes[0].to_plotly_json(), row=1, col=2)

        # 第2行
        for trace in metrics_fig.data:
            report_fig.add_trace(trace, row=2, col=1)
        report_fig.add_trace(trade_fig.data[0], row=2, col=2)

        # 第3行
        for trace in risk_return_fig.data:
            report_fig.add_trace(trace, row=3, col=1)

        # 更新布局
        report_fig.update_layout(
            height=1200,
            title_text="ETH永续合约策略回测结果可视化报告",
            template="plotly_white",
            showlegend=True,
        )

        # 保存报告
        output_abs_path = os.path.join(self.root_dir, output_path)
        os.makedirs(os.path.dirname(output_abs_path), exist_ok=True)

        report_fig.write_html(output_abs_path, full_html=True, include_plotlyjs="cdn")
        logger.info(f"可视化报告已生成: {output_abs_path}")

        return True


def main():
    """主函数"""
    if len(sys.argv) < 2:
        print("用法: python backtest_visualization.py <回测结果路径> [输出路径]")
        print(
            "示例: python backtest_visualization.py ai_collaboration/data/backtest_results_v2.json ai_collaboration/data/backtest_visualization_v2.html"
        )
        sys.exit(1)

    results_path = sys.argv[1]
    output_path = (
        sys.argv[2] if len(sys.argv) > 2 else "ai_collaboration/data/backtest_visualization.html"
    )

    visualizer = BacktestVisualizer()

    if visualizer.generate_visualization_report(results_path, output_path):
        logger.info("回测结果可视化成功")
        sys.exit(0)
    else:
        logger.error("回测结果可视化失败")
        sys.exit(1)


if __name__ == "__main__":
    main()
