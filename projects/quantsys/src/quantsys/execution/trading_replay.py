#!/usr/bin/env python3
"""
实盘回放/复盘工具
从ledger+evidence重放某日交易，输出复盘报告（信号→目标仓位→订单→成交→PNL），用于事故调查。
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from src.quantsys.execution.trade_ledger import EventType, LedgerEvent, TradeLedger


@dataclass
class ReplayEvent:
    """
    重放事件类，扩展LedgerEvent，包含更多上下文信息"""

    ledger_event: LedgerEvent
    context: dict[str, Any] = field(default_factory=dict)
    sequence_number: int = 0


@dataclass
class ReplayStep:
    """
    复盘步骤类，记录从信号到PNL的完整链路"""

    step_id: str
    timestamp: float
    signal: dict[str, Any] | None = None
    target_position: dict[str, Any] | None = None
    order: dict[str, Any] | None = None
    fill: dict[str, Any] | None = None
    position: dict[str, Any] | None = None
    pnl: dict[str, Any] | None = None
    status: str = "COMPLETED"
    notes: list[str] = field(default_factory=list)


class TradingReplayManager:
    """
    实盘回放/复盘管理器"""

    def __init__(self, config: dict[str, Any] | None = None):
        """
        初始化回放管理器

        Args:
            config: 配置信息
        """
        self.config = config or {
            "ledger_path": "data/trade_ledger.json",
            "evidence_path": "data/evidence",
            "reports_path": "reports/replay_reports",
            "signal_path": "data/signals",
            "position_target_path": "data/position_targets",
        }

        # 初始化组件
        self.ledger = TradeLedger(self.config["ledger_path"])

        # 创建报告目录
        self.reports_dir = Path(self.config["reports_path"])
        self.reports_dir.mkdir(parents=True, exist_ok=True)

        # 初始化状态
        self.replay_date: date | None = None
        self.filtered_events: list[LedgerEvent] = []
        self.replay_steps: list[ReplayStep] = []
        self.final_state: dict[str, Any] = {}

    def _get_events_for_date(self, replay_date: date) -> list[LedgerEvent]:
        """
        获取指定日期的所有事件

        Args:
            replay_date: 要重放的日期

        Returns:
            List[LedgerEvent]: 过滤后的事件列表
        """
        # 转换日期为时间戳范围
        start_ts = time.mktime(replay_date.timetuple())
        end_ts = start_ts + 86400  # 一天后的时间戳

        # 过滤事件
        filtered_events = [
            event for event in self.ledger.events if start_ts <= event.timestamp < end_ts
        ]

        # 按时间排序
        filtered_events.sort(key=lambda x: x.timestamp)

        return filtered_events

    def _load_evidence_for_date(self, replay_date: date) -> dict[str, Any]:
        """
        加载指定日期的证据文件

        Args:
            replay_date: 要加载证据的日期

        Returns:
            Dict[str, Any]: 证据数据
        """
        evidence_data = {"signals": [], "position_targets": [], "other_evidence": []}

        # 加载信号数据
        signal_dir = Path(self.config["signal_path"])
        if signal_dir.exists():
            # 查找当日的信号文件
            signal_files = list(signal_dir.glob(f"*{replay_date.strftime('%Y%m%d')}*.json"))
            for signal_file in signal_files:
                try:
                    with open(signal_file, encoding="utf-8") as f:
                        signal_data = json.load(f)
                        if isinstance(signal_data, list):
                            evidence_data["signals"].extend(signal_data)
                        else:
                            evidence_data["signals"].append(signal_data)
                except Exception as e:
                    print(f"加载信号文件失败 {signal_file}: {e}")

        # 加载目标仓位数据
        position_target_dir = Path(self.config["position_target_path"])
        if position_target_dir.exists():
            # 查找当日的目标仓位文件
            target_files = list(
                position_target_dir.glob(f"*{replay_date.strftime('%Y%m%d')}*.json")
            )
            for target_file in target_files:
                try:
                    with open(target_file, encoding="utf-8") as f:
                        target_data = json.load(f)
                        if isinstance(target_data, list):
                            evidence_data["position_targets"].extend(target_data)
                        else:
                            evidence_data["position_targets"].append(target_data)
                except Exception as e:
                    print(f"加载目标仓位文件失败 {target_file}: {e}")

        # 按时间排序
        evidence_data["signals"].sort(key=lambda x: x.get("timestamp", 0))
        evidence_data["position_targets"].sort(key=lambda x: x.get("timestamp", 0))

        return evidence_data

    def _create_replay_steps(
        self, events: list[LedgerEvent], evidence: dict[str, Any]
    ) -> list[ReplayStep]:
        """
        创建复盘步骤，将事件和证据关联起来

        Args:
            events: 事件列表
            evidence: 证据数据

        Returns:
            List[ReplayStep]: 复盘步骤列表
        """
        replay_steps = []

        # 创建步骤映射，用于关联相关事件
        step_map: dict[str, ReplayStep] = {}

        # 首先处理信号和目标仓位，创建初始步骤
        all_context = []
        all_context.extend(evidence["signals"])
        all_context.extend(evidence["position_targets"])
        all_context.sort(key=lambda x: x.get("timestamp", 0))

        for ctx in all_context:
            timestamp = ctx.get("timestamp", 0)
            step = ReplayStep(
                step_id=f"step_{int(timestamp)}_{len(replay_steps)}",
                timestamp=timestamp,
                status="PENDING",
            )

            # 根据类型设置相应字段
            if "signal_strength" in ctx or "confidence" in ctx:
                # 这是一个信号
                step.signal = ctx
            elif "target_position" in ctx or "target_amount" in ctx:
                # 这是一个目标仓位
                step.target_position = ctx

            replay_steps.append(step)
            step_map[step.step_id] = step

        # 处理ledger事件，将它们关联到相应的步骤
        for event in events:
            event_data = event.event_data
            timestamp = event.timestamp

            # 查找最近的步骤
            matching_step = None
            for step in reversed(replay_steps):
                if step.timestamp <= timestamp:
                    matching_step = step
                    break

            if not matching_step:
                # 如果没有匹配的步骤，创建一个新步骤
                matching_step = ReplayStep(
                    step_id=f"step_{int(timestamp)}_{len(replay_steps)}", timestamp=timestamp
                )
                replay_steps.append(matching_step)
                step_map[matching_step.step_id] = matching_step

            # 根据事件类型更新步骤
            if event.event_type == EventType.ORDER_CREATED:
                matching_step.order = event_data
            elif event.event_type == EventType.FILL_CREATED:
                matching_step.fill = event_data
            elif event.event_type == EventType.POSITION_UPDATED:
                matching_step.position = event_data
            elif event.event_type == EventType.PNL_CALCULATED:
                matching_step.pnl = event_data

            # 更新步骤状态
            matching_step.status = "COMPLETED"

        # 按时间排序所有步骤
        replay_steps.sort(key=lambda x: x.timestamp)

        # 为每个步骤添加序号
        for i, step in enumerate(replay_steps):
            step.sequence_number = i + 1

        return replay_steps

    def run_replay(self, replay_date: date) -> dict[str, Any]:
        """
        运行实盘回放

        Args:
            replay_date: 要回放的日期

        Returns:
            Dict[str, Any]: 回放结果
        """
        print(f"开始回放 {replay_date.strftime('%Y-%m-%d')} 的交易...")

        # 保存回放日期
        self.replay_date = replay_date

        # 步骤1: 加载当日事件
        print("步骤1: 加载当日事件...")
        self.filtered_events = self._get_events_for_date(replay_date)
        print(f"✓ 加载了 {len(self.filtered_events)} 个事件")

        # 步骤2: 加载当日证据
        print("步骤2: 加载当日证据...")
        evidence = self._load_evidence_for_date(replay_date)
        print(
            f"✓ 加载了 {len(evidence['signals'])} 个信号，{len(evidence['position_targets'])} 个目标仓位"
        )

        # 步骤3: 重放ledger事件
        print("步骤3: 重放ledger事件...")
        replay_result = self.ledger.replay()
        print(f"✓ 事件重放完成，共处理 {replay_result['total_events']} 个事件")

        # 保存最终状态
        self.final_state = replay_result["final_state"]

        # 步骤4: 创建复盘步骤
        print("步骤4: 创建复盘步骤...")
        self.replay_steps = self._create_replay_steps(self.filtered_events, evidence)
        print(f"✓ 创建了 {len(self.replay_steps)} 个复盘步骤")

        # 步骤5: 生成并保存报告
        print("步骤5: 生成并保存报告...")
        report = self.generate_replay_report()
        report_path = self.save_replay_report(report)
        print(f"✓ 报告已保存到: {report_path}")

        # 步骤6: 保存证据
        print("步骤6: 保存证据...")
        evidence_path = self.save_replay_evidence(report)
        print(f"✓ 证据已保存到: {evidence_path}")

        print("\n=== 回放完成 ===")
        print(f"日期: {replay_date.strftime('%Y-%m-%d')}")
        print(f"事件数: {len(self.filtered_events)}")
        print(f"步骤数: {len(self.replay_steps)}")
        print(f"最终PNL: {sum(pnl['total_pnl'] for pnl in self.final_state['pnl'].values()):.2f}")

        return {
            "status": "SUCCESS",
            "date": replay_date.isoformat(),
            "total_events": len(self.filtered_events),
            "total_steps": len(self.replay_steps),
            "final_pnl": sum(pnl["total_pnl"] for pnl in self.final_state["pnl"].values()),
            "report_path": str(report_path),
            "evidence_path": str(evidence_path),
        }

    def generate_replay_report(self) -> dict[str, Any]:
        """
        生成复盘报告

        Returns:
            Dict[str, Any]: 复盘报告
        """
        if not self.replay_date:
            raise ValueError("请先运行run_replay方法")

        # 统计数据
        total_signals = sum(1 for step in self.replay_steps if step.signal)
        total_targets = sum(1 for step in self.replay_steps if step.target_position)
        total_orders = sum(1 for step in self.replay_steps if step.order)
        total_fills = sum(1 for step in self.replay_steps if step.fill)
        total_pnl_updates = sum(1 for step in self.replay_steps if step.pnl)

        # 生成报告
        report = {
            "report_id": f"replay_report_{self.replay_date.strftime('%Y%m%d')}_{int(time.time())}",
            "generated_at": time.time(),
            "replay_date": self.replay_date.isoformat(),
            "statistics": {
                "total_events": len(self.filtered_events),
                "total_steps": len(self.replay_steps),
                "total_signals": total_signals,
                "total_target_positions": total_targets,
                "total_orders": total_orders,
                "total_fills": total_fills,
                "total_pnl_updates": total_pnl_updates,
                "final_pnl": sum(pnl["total_pnl"] for pnl in self.final_state["pnl"].values()),
                "final_positions": len(self.final_state["positions"]),
                "final_orders": len(self.final_state["orders"]),
                "final_fills": len(self.final_state["fills"]),
            },
            "replay_steps": [
                {
                    "step_id": step.step_id,
                    "sequence_number": step.sequence_number,
                    "timestamp": step.timestamp,
                    "datetime": datetime.fromtimestamp(step.timestamp).strftime(
                        "%Y-%m-%d %H:%M:%S"
                    ),
                    "signal": step.signal,
                    "target_position": step.target_position,
                    "order": step.order,
                    "fill": step.fill,
                    "position": step.position,
                    "pnl": step.pnl,
                    "status": step.status,
                    "notes": step.notes,
                }
                for step in self.replay_steps
            ],
            "final_state": self.final_state,
            "replay_summary": "\n".join(
                [
                    f"=== {self.replay_date.strftime('%Y-%m-%d')} 交易复盘报告 ===",
                    f"总事件数: {len(self.filtered_events)}",
                    f"复盘步骤数: {len(self.replay_steps)}",
                    f"信号数量: {total_signals}",
                    f"目标仓位数量: {total_targets}",
                    f"订单数量: {total_orders}",
                    f"成交数量: {total_fills}",
                    f"PNL更新数量: {total_pnl_updates}",
                    f"最终PNL: {sum(pnl['total_pnl'] for pnl in self.final_state['pnl'].values()):.2f}",
                    f"最终持仓数量: {len(self.final_state['positions'])}",
                ]
            ),
        }

        return report

    def save_replay_report(self, report: dict[str, Any]) -> Path:
        """
        保存复盘报告到文件

        Args:
            report: 要保存的报告

        Returns:
            Path: 报告文件路径
        """
        if not self.replay_date:
            raise ValueError("请先运行run_replay方法")

        # 创建每日报告目录
        daily_report_dir = self.reports_dir / self.replay_date.strftime("%Y%m%d")
        daily_report_dir.mkdir(exist_ok=True)

        # 保存JSON格式报告
        report_path = daily_report_dir / f"replay_report_{report['report_id']}.json"
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, ensure_ascii=False, default=str)

        # 保存MD格式报告
        md_report_path = daily_report_dir / f"replay_report_{report['report_id']}.md"
        self._generate_md_report(report, md_report_path)

        return report_path

    def _generate_md_report(self, report: dict[str, Any], output_path: Path):
        """
        生成Markdown格式的复盘报告

        Args:
            report: 报告数据
            output_path: 输出路径
        """
        with open(output_path, "w", encoding="utf-8") as f:
            # 写入报告标题
            f.write("# 实盘回放复盘报告\n\n")
            f.write("## 基本信息\n\n")
            f.write(f"- **报告ID**: {report['report_id']}\n")
            f.write(
                f"- **生成时间**: {datetime.fromtimestamp(report['generated_at']).strftime('%Y-%m-%d %H:%M:%S')}\n"
            )
            f.write(f"- **回放日期**: {report['replay_date']}\n\n")

            # 写入统计信息
            f.write("## 统计信息\n\n")
            stats = report["statistics"]
            f.write("| 指标 | 数值 |\n")
            f.write("|------|------|\n")
            f.write(f"| 总事件数 | {stats['total_events']} |\n")
            f.write(f"| 复盘步骤数 | {stats['total_steps']} |\n")
            f.write(f"| 信号数量 | {stats['total_signals']} |\n")
            f.write(f"| 目标仓位数量 | {stats['total_target_positions']} |\n")
            f.write(f"| 订单数量 | {stats['total_orders']} |\n")
            f.write(f"| 成交数量 | {stats['total_fills']} |\n")
            f.write(f"| PNL更新数量 | {stats['total_pnl_updates']} |\n")
            f.write(f"| 最终PNL | {stats['final_pnl']:.2f} |\n")
            f.write(f"| 最终持仓数量 | {stats['final_positions']} |\n")
            f.write(f"| 最终订单数量 | {stats['final_orders']} |\n")
            f.write(f"| 最终成交数量 | {stats['final_fills']} |\n\n")

            # 写入复盘步骤
            f.write("## 复盘步骤\n\n")
            f.write("| 序号 | 时间 | 信号 | 目标仓位 | 订单 | 成交 | 持仓 | PNL | 状态 |\n")
            f.write("|------|------|------|----------|------|------|------|------|------|\n")

            for step in report["replay_steps"]:
                has_signal = "✓" if step["signal"] else ""
                has_target = "✓" if step["target_position"] else ""
                has_order = "✓" if step["order"] else ""
                has_fill = "✓" if step["fill"] else ""
                has_position = "✓" if step["position"] else ""
                has_pnl = "✓" if step["pnl"] else ""

                f.write(
                    f"| {step['sequence_number']} | {step['datetime']} | {has_signal} | {has_target} | {has_order} | {has_fill} | {has_position} | {has_pnl} | {step['status']} |\n"
                )

            # 写入最终状态
            f.write("\n## 最终状态\n\n")
            f.write("### 持仓情况\n\n")
            for symbol, position in report["final_state"]["positions"].items():
                f.write(
                    f"- **{symbol}**: 数量={position['total_amount']:.4f}, 均价={position['avg_price']:.2f}, 浮动盈亏={position['unrealized_pnl']:.2f}\n"
                )

            f.write("\n### PNL情况\n\n")
            for symbol, pnl in report["final_state"]["pnl"].items():
                f.write(
                    f"- **{symbol}**: 浮动盈亏={pnl['unrealized_pnl']:.2f}, 已实现盈亏={pnl['realized_pnl']:.2f}, 总盈亏={pnl['total_pnl']:.2f}\n"
                )

    def save_replay_evidence(self, report: dict[str, Any]) -> Path:
        """
        保存回放证据

        Args:
            report: 回放报告

        Returns:
            Path: 证据文件路径
        """
        if not self.replay_date:
            raise ValueError("请先运行run_replay方法")

        # 创建证据目录
        evidence_dir = Path("data/evidence/replay") / self.replay_date.strftime("%Y%m%d")
        evidence_dir.mkdir(parents=True, exist_ok=True)

        # 保存证据文件
        evidence_data = {
            "report_id": report["report_id"],
            "generated_at": time.time(),
            "replay_date": report["replay_date"],
            "filtered_events": [event.to_dict() for event in self.filtered_events],
            "replay_steps": [
                {
                    "step_id": step.step_id,
                    "sequence_number": step.sequence_number,
                    "timestamp": step.timestamp,
                    "signal": step.signal,
                    "target_position": step.target_position,
                    "order": step.order,
                    "fill": step.fill,
                    "position": step.position,
                    "pnl": step.pnl,
                    "status": step.status,
                    "notes": step.notes,
                }
                for step in self.replay_steps
            ],
            "final_state": self.final_state,
        }

        evidence_path = evidence_dir / f"replay_evidence_{report['report_id']}.json"
        with open(evidence_path, "w", encoding="utf-8") as f:
            json.dump(evidence_data, f, indent=2, ensure_ascii=False, default=str)

        return evidence_path

    def run_self_test(self) -> dict[str, Any]:
        """
        运行自测

        Returns:
            Dict[str, Any]: 自测结果
        """
        print("开始运行实盘回放工具自测...")

        test_result = {
            "test_name": "TradingReplayManager Self Test",
            "timestamp": time.time(),
            "tests": [],
            "overall_result": "PASS",
        }

        # 测试1: 初始化测试
        try:
            manager = TradingReplayManager()
            test_result["tests"].append(
                {
                    "test_id": "init_test",
                    "test_name": "初始化测试",
                    "result": "PASS",
                    "message": "TradingReplayManager初始化成功",
                }
            )
            print("✓ 测试1通过: 初始化测试")
        except Exception as e:
            test_result["tests"].append(
                {
                    "test_id": "init_test",
                    "test_name": "初始化测试",
                    "result": "FAIL",
                    "message": f"初始化失败: {str(e)}",
                }
            )
            test_result["overall_result"] = "FAIL"
            print(f"✗ 测试1失败: 初始化测试 - {str(e)}")

        # 测试2: 日期过滤测试
        try:
            manager = TradingReplayManager()
            today = date.today()
            events = manager._get_events_for_date(today)
            test_result["tests"].append(
                {
                    "test_id": "date_filter_test",
                    "test_name": "日期过滤测试",
                    "result": "PASS",
                    "message": f"日期过滤成功，返回 {len(events)} 个事件",
                }
            )
            print(f"✓ 测试2通过: 日期过滤测试 - 返回 {len(events)} 个事件")
        except Exception as e:
            test_result["tests"].append(
                {
                    "test_id": "date_filter_test",
                    "test_name": "日期过滤测试",
                    "result": "FAIL",
                    "message": f"日期过滤失败: {str(e)}",
                }
            )
            test_result["overall_result"] = "FAIL"
            print(f"✗ 测试2失败: 日期过滤测试 - {str(e)}")

        # 测试3: 报告生成测试
        try:
            manager = TradingReplayManager()
            today = date.today()

            # 模拟一些数据
            manager.replay_date = today
            manager.filtered_events = []
            manager.replay_steps = [
                ReplayStep(step_id="test_step_1", timestamp=time.time(), status="COMPLETED")
            ]
            manager.final_state = {
                "positions": {},
                "pnl": {},
                "orders": {},
                "fills": {},
                "last_event_time": time.time(),
            }

            report = manager.generate_replay_report()
            test_result["tests"].append(
                {
                    "test_id": "report_generation_test",
                    "test_name": "报告生成测试",
                    "result": "PASS",
                    "message": "报告生成成功",
                }
            )
            print("✓ 测试3通过: 报告生成测试")
        except Exception as e:
            test_result["tests"].append(
                {
                    "test_id": "report_generation_test",
                    "test_name": "报告生成测试",
                    "result": "FAIL",
                    "message": f"报告生成失败: {str(e)}",
                }
            )
            test_result["overall_result"] = "FAIL"
            print(f"✗ 测试3失败: 报告生成测试 - {str(e)}")

        # 保存自测结果
        test_result_path = Path("reports") / f"replay_self_test_{int(time.time())}.json"
        with open(test_result_path, "w", encoding="utf-8") as f:
            json.dump(test_result, f, indent=2, ensure_ascii=False)

        print("\n=== 自测完成 ===")
        print(f"总体结果: {test_result['overall_result']}")
        print(f"测试数量: {len(test_result['tests'])}")
        print(f"通过数量: {sum(1 for test in test_result['tests'] if test['result'] == 'PASS')}")
        print(f"自测结果已保存到: {test_result_path}")

        return test_result


if __name__ == "__main__":
    # 测试代码
    replay_manager = TradingReplayManager()

    # 运行自测
    test_result = replay_manager.run_self_test()

    # 如果自测通过，运行一次回放
    if test_result["overall_result"] == "PASS":
        print("\n=== 运行实盘回放测试 ===")
        # 回放昨天的交易
        yesterday = date.today() - timedelta(days=1)
        replay_result = replay_manager.run_replay(yesterday)
        print("\n回放结果:")
        print(json.dumps(replay_result, indent=2, ensure_ascii=False))
    else:
        print("\n自测失败，无法运行实盘回放")
