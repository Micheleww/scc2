#!/usr/bin/env python3
"""
加密量化策略迭代体系 - 任务看板管理脚本

该脚本用于管理加密量化策略迭代体系的任务看板，实现任务状态的更新和查询。
"""

import datetime
import json
import logging
import os

# 配置日志
log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
os.makedirs(log_dir, exist_ok=True)
log_file = os.path.join(log_dir, "task_board.log")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.FileHandler(log_file), logging.StreamHandler()],
)
logger = logging.getLogger(__name__)


class TaskBoardManager:
    """任务看板管理器"""

    def __init__(self, board_path="ai_collaboration/crypto_task_board.json"):
        """初始化任务看板管理器"""
        self.board_path = board_path
        self.ensure_board_exists()

    def ensure_board_exists(self):
        """确保任务看板文件存在"""
        if not os.path.exists(self.board_path):
            self.init_task_board()

    def init_task_board(self):
        """初始化任务看板"""
        # 导入统一task_id管理模块
        try:
            import sys
            sys.path.insert(0, str(os.path.join(os.path.dirname(__file__), '..', '..', 'tools', 'mcp_bus', 'server')))
            from task_id_manager import get_task_id_manager
            task_id_manager = get_task_id_manager()
        except Exception as e:
            logger.error(f"Failed to initialize task_id_manager: {e}")
            task_id_manager = None
        
        board = {
            "全局目标": {
                "策略名称": "ETH永续合约策略",
                "版本": "v1",
                "目标指标": {"夏普比率": 1.2, "最大回撤": 0.1, "年化收益率": 0.2},
            },
            "当前迭代周期": 1,
            "任务清单": [
                {
                    "任务ID": "QSYS-20260105-001" if task_id_manager else "crypto_task_20260105_001",
                    "旧任务ID": "crypto_task_20260105_001",
                    "任务类型": "数据采集与预处理",
                    "负责人": "data_ai",
                    "状态": "待执行",
                    "进度": 0,
                    "输出路径": "",
                    "异常信息": "",
                },
                {
                    "任务ID": "QSYS-20260105-002" if task_id_manager else "crypto_task_20260105_002",
                    "旧任务ID": "crypto_task_20260105_002",
                    "任务类型": "特征工程与因子计算",
                    "负责人": "feature_ai",
                    "状态": "待执行",
                    "进度": 0,
                    "输出路径": "",
                    "异常信息": "",
                },
                {
                    "任务ID": "QSYS-20260105-003" if task_id_manager else "crypto_task_20260105_003",
                    "旧任务ID": "crypto_task_20260105_003",
                    "任务类型": "模型训练与微调",
                    "负责人": "training_ai",
                    "状态": "待执行",
                    "进度": 0,
                    "输出路径": "",
                    "异常信息": "",
                },
                {
                    "任务ID": "QSYS-20260105-004" if task_id_manager else "crypto_task_20260105_004",
                    "旧任务ID": "crypto_task_20260105_004",
                    "任务类型": "策略生成与优化",
                    "负责人": "strategy_ai",
                    "状态": "待执行",
                    "进度": 0,
                    "输出路径": "",
                    "异常信息": "",
                },
                {
                    "任务ID": "QSYS-20260105-005" if task_id_manager else "crypto_task_20260105_005",
                    "旧任务ID": "crypto_task_20260105_005",
                    "任务类型": "策略回测与验证",
                    "负责人": "backtest_ai",
                    "状态": "待执行",
                    "进度": 0,
                    "输出路径": "",
                    "异常信息": "",
                },
                {
                    "任务ID": "QSYS-20260105-006" if task_id_manager else "crypto_task_20260105_006",
                    "旧任务ID": "crypto_task_20260105_006",
                    "任务类型": "回测结果分析与迭代",
                    "负责人": "iteration_ai",
                    "状态": "待执行",
                    "进度": 0,
                    "输出路径": "",
                    "异常信息": "",
                },
            ],
        }

        # 确保目录存在
        os.makedirs(os.path.dirname(self.board_path), exist_ok=True)

        with open(self.board_path, "w", encoding="utf-8") as f:
            json.dump(board, f, indent=2, ensure_ascii=False)

        logger.info(f"任务看板已初始化: {self.board_path}")

    def update_task_board(self, task_id, status, progress, output_path="", error=""):
        """更新任务看板状态

        Args:
            task_id: 任务ID
            status: 任务状态（待执行、执行中、完成、失败）
            progress: 任务进度（0-100）
            output_path: 输出文件路径
            error: 错误信息

        Returns:
            更新后的任务看板
        """
        self.ensure_board_exists()

        with open(self.board_path, encoding="utf-8") as f:
            board = json.load(f)

        task_found = False
        for task in board["任务清单"]:
            if task["任务ID"] == task_id:
                task["状态"] = status
                task["进度"] = progress
                task["输出路径"] = output_path
                task["异常信息"] = error
                task["最后更新时间"] = datetime.datetime.now().isoformat()
                task_found = True
                break

        if not task_found:
            logger.warning(f"任务ID {task_id} 未找到")
            return board

        # 更新全局状态
        active_tasks = sum(1 for t in board["任务清单"] if t["状态"] in ["执行中", "in_progress"])
        completed_tasks = sum(1 for t in board["任务清单"] if t["状态"] in ["完成", "completed"])
        failed_tasks = sum(1 for t in board["任务清单"] if t["状态"] in ["失败", "failed"])

        board["全局状态"] = {
            "当前迭代周期": board.get("当前迭代周期", 1),
            "总体进度": sum(t["进度"] for t in board["任务清单"]) / len(board["任务清单"]),
            "状态": "运行中" if active_tasks > 0 else "完成" if completed_tasks > 0 else "待开始",
            "最后更新时间": datetime.datetime.now().isoformat(),
            "活跃任务数": active_tasks,
            "已完成任务数": completed_tasks,
            "失败任务数": failed_tasks,
        }

        with open(self.board_path, "w", encoding="utf-8") as f:
            json.dump(board, f, indent=2, ensure_ascii=False)

        logger.info(f"任务 {task_id} 状态已更新: {status}, 进度: {progress}%")
        return board

    def get_task_status(self, task_id):
        """获取指定任务的状态

        Args:
            task_id: 任务ID

        Returns:
            任务状态信息，或None
        """
        self.ensure_board_exists()

        with open(self.board_path, encoding="utf-8") as f:
            board = json.load(f)

        for task in board["任务清单"]:
            if task["任务ID"] == task_id:
                return task

        logger.warning(f"任务ID {task_id} 未找到")
        return None

    def check_dependencies(self, task_id):
        """检查任务依赖是否完成

        Args:
            task_id: 任务ID

        Returns:
            bool: 依赖是否完成
        """
        # 读取任务配置文件
        tasks_config_path = "ai_collaboration/tasks.json"
        if not os.path.exists(tasks_config_path):
            logger.warning(f"任务配置文件 {tasks_config_path} 未找到")
            return False

        with open(tasks_config_path, encoding="utf-8") as f:
            tasks_config = json.load(f)

        # 查找当前任务
        current_task = None
        for task in tasks_config["tasks"]:
            if task["任务ID"] == task_id:
                current_task = task
                break

        if not current_task:
            logger.warning(f"任务ID {task_id} 在配置文件中未找到")
            return False

        # 检查依赖
        dependencies = current_task.get("dependencies", [])
        for dep_id in dependencies:
            dep_status = self.get_task_status(dep_id)
            if not dep_status or dep_status["状态"] not in ["完成", "completed"]:
                logger.info(
                    f"任务 {task_id} 的依赖 {dep_id} 未完成，当前状态: {dep_status['状态'] if dep_status else '未知'}"
                )
                return False

        logger.info(f"任务 {task_id} 的所有依赖已完成")
        return True

    def get_board_summary(self):
        """获取任务看板摘要

        Returns:
            任务看板摘要
        """
        self.ensure_board_exists()

        with open(self.board_path, encoding="utf-8") as f:
            board = json.load(f)

        summary = {
            "全局目标": board["全局目标"],
            "当前迭代周期": board.get("当前迭代周期", 1),
            "全局状态": board.get("全局状态", {}),
            "任务概览": [
                {
                    "任务ID": task["任务ID"],
                    "任务类型": task["任务类型"],
                    "负责人": task["负责人"],
                    "状态": task["状态"],
                    "进度": task["进度"],
                }
                for task in board["任务清单"]
            ],
        }

        return summary


if __name__ == "__main__":
    # 示例用法
    manager = TaskBoardManager()

    # 示例1: 更新数据采集任务状态
    manager.update_task_board(
        task_id="crypto_task_20260105_001", status="执行中", progress=50, output_path="", error=""
    )

    # 示例2: 检查任务依赖
    if manager.check_dependencies("crypto_task_20260105_002"):
        print("所有依赖已完成，可以开始执行任务")
    else:
        print("依赖未完成，等待中...")

    # 示例3: 获取任务状态
    task_status = manager.get_task_status("crypto_task_20260105_001")
    print(f"任务状态: {task_status}")

    # 示例4: 获取看板摘要
    summary = manager.get_board_summary()
    print(f"看板摘要: {json.dumps(summary, indent=2, ensure_ascii=False)}")
