#!/usr/bin/env python3
"""
LiveConfigFreeze - 配置冻结与版本回滚模块

用于防止实盘漂移，实现配置冻结和回滚功能
"""

import json
import logging
import os
import subprocess
from datetime import datetime
from typing import Any

# 配置日志
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class LiveConfigFreeze:
    """
    配置冻结与版本回滚类，用于防止实盘漂移
    """

    def __init__(
        self,
        config_dir: str = "configs",
        frozen_config_path: str = "frozen_config.json",
        rollback_plan_path: str = "rollback_plan.json",
    ):
        """
        初始化配置冻结与版本回滚模块

        Args:
            config_dir: 配置文件目录
            frozen_config_path: 冻结配置文件路径
            rollback_plan_path: 回滚计划文件路径
        """
        self.config_dir = config_dir
        self.frozen_config_path = frozen_config_path
        self.rollback_plan_path = rollback_plan_path

        # 确保配置目录存在
        os.makedirs(config_dir, exist_ok=True)

    def get_git_hash(self) -> str:
        """
        获取当前git commit hash

        Returns:
            str: 当前git commit hash，如果不是git仓库则返回空字符串
        """
        try:
            result = subprocess.run(
                ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True
            )
            return result.stdout.strip()
        except subprocess.CalledProcessError:
            logger.warning("不是git仓库，无法获取git hash")
            return ""
        except FileNotFoundError:
            logger.warning("未安装git，无法获取git hash")
            return ""

    def freeze_config(
        self, config: dict[str, Any], reason: str = "进入Live前冻结"
    ) -> dict[str, Any]:
        """
        冻结当前配置

        Args:
            config: 要冻结的配置
            reason: 冻结原因

        Returns:
            Dict[str, Any]: 冻结后的配置信息
        """
        logger.info(f"开始冻结配置，原因：{reason}")

        # 获取当前时间戳
        timestamp = datetime.utcnow().isoformat() + "Z"

        # 获取git hash
        git_hash = self.get_git_hash()

        # 构建冻结配置
        frozen_config = {
            "timestamp": timestamp,
            "git_hash": git_hash,
            "reason": reason,
            "config": config,
        }

        # 保存冻结配置到文件
        with open(self.frozen_config_path, "w", encoding="utf-8") as f:
            json.dump(frozen_config, f, indent=2, ensure_ascii=False)

        logger.info(f"配置已冻结到 {self.frozen_config_path}")
        return frozen_config

    def load_frozen_config(self) -> dict[str, Any] | None:
        """
        加载冻结配置

        Returns:
            Optional[Dict[str, Any]]: 冻结的配置，如果文件不存在则返回None
        """
        if not os.path.exists(self.frozen_config_path):
            logger.warning(f"冻结配置文件 {self.frozen_config_path} 不存在")
            return None

        with open(self.frozen_config_path, encoding="utf-8") as f:
            frozen_config = json.load(f)

        logger.info(f"已加载冻结配置 {self.frozen_config_path}")
        return frozen_config

    def check_config_changes(self, current_config: dict[str, Any]) -> dict[str, Any]:
        """
        检查当前配置与冻结配置的变化

        Args:
            current_config: 当前配置

        Returns:
            Dict[str, Any]: 配置变化信息，包含是否变化、变化项等
        """
        logger.info("检查配置变化")

        # 加载冻结配置
        frozen_config = self.load_frozen_config()
        if not frozen_config:
            return {"changed": False, "reason": "没有冻结配置", "changes": []}

        # 比较配置
        changes = self._compare_dicts(frozen_config["config"], current_config)

        result = {
            "changed": len(changes) > 0,
            "frozen_timestamp": frozen_config["timestamp"],
            "current_timestamp": datetime.utcnow().isoformat() + "Z",
            "changes": changes,
        }

        if result["changed"]:
            logger.warning(f"配置已变化，共 {len(changes)} 处变化")
            for change in changes:
                logger.warning(
                    f"  - {change['path']}: {change['old_value']} -> {change['new_value']}"
                )
        else:
            logger.info("配置未变化")

        return result

    def _compare_dicts(
        self, old_dict: dict[str, Any], new_dict: dict[str, Any], path: str = ""
    ) -> list[dict[str, Any]]:
        """
        递归比较两个字典的差异

        Args:
            old_dict: 旧字典
            new_dict: 新字典
            path: 当前路径

        Returns:
            List[Dict[str, Any]]: 差异列表
        """
        changes = []

        # 检查旧字典中的键
        for key in old_dict:
            current_path = f"{path}.{key}" if path else key

            if key not in new_dict:
                # 键被删除
                changes.append(
                    {
                        "path": current_path,
                        "old_value": old_dict[key],
                        "new_value": "[DELETED]",
                        "type": "deleted",
                    }
                )
            else:
                old_value = old_dict[key]
                new_value = new_dict[key]

                if isinstance(old_value, dict) and isinstance(new_value, dict):
                    # 递归比较字典
                    changes.extend(self._compare_dicts(old_value, new_value, current_path))
                elif isinstance(old_value, list) and isinstance(new_value, list):
                    # 比较列表
                    if old_value != new_value:
                        changes.append(
                            {
                                "path": current_path,
                                "old_value": old_value,
                                "new_value": new_value,
                                "type": "list_changed",
                            }
                        )
                else:
                    # 比较基本类型
                    if old_value != new_value:
                        changes.append(
                            {
                                "path": current_path,
                                "old_value": old_value,
                                "new_value": new_value,
                                "type": "value_changed",
                            }
                        )

        # 检查新字典中的键
        for key in new_dict:
            if key not in old_dict:
                current_path = f"{path}.{key}" if path else key
                # 键被添加
                changes.append(
                    {
                        "path": current_path,
                        "old_value": "[ADDED]",
                        "new_value": new_dict[key],
                        "type": "added",
                    }
                )

        return changes

    def create_rollback_plan(self, reason: str = "创建回滚计划") -> dict[str, Any]:
        """
        创建回滚计划

        Args:
            reason: 回滚计划创建原因

        Returns:
            Dict[str, Any]: 回滚计划
        """
        logger.info(f"开始创建回滚计划，原因：{reason}")

        # 加载冻结配置
        frozen_config = self.load_frozen_config()
        if not frozen_config:
            logger.error("没有冻结配置，无法创建回滚计划")
            return {}

        # 获取当前时间戳
        timestamp = datetime.utcnow().isoformat() + "Z"

        # 构建回滚计划
        rollback_plan = {
            "timestamp": timestamp,
            "reason": reason,
            "target_frozen_timestamp": frozen_config["timestamp"],
            "target_git_hash": frozen_config["git_hash"],
            "target_config": frozen_config["config"],
        }

        # 保存回滚计划到文件
        with open(self.rollback_plan_path, "w", encoding="utf-8") as f:
            json.dump(rollback_plan, f, indent=2, ensure_ascii=False)

        logger.info(f"回滚计划已创建到 {self.rollback_plan_path}")
        return rollback_plan

    def rollback_to_frozen(self) -> dict[str, Any]:
        """
        回滚到最近一次冻结的配置

        Returns:
            Dict[str, Any]: 回滚结果
        """
        logger.info("开始回滚到最近一次冻结的配置")

        # 加载冻结配置
        frozen_config = self.load_frozen_config()
        if not frozen_config:
            logger.error("没有冻结配置，无法回滚")
            return {"success": False, "reason": "没有冻结配置"}

        # 创建回滚计划
        self.create_rollback_plan(reason="回滚到最近一次冻结配置")

        logger.info(f"已回滚到 {frozen_config['timestamp']} 冻结的配置")
        return {
            "success": True,
            "timestamp": frozen_config["timestamp"],
            "git_hash": frozen_config["git_hash"],
            "config": frozen_config["config"],
        }

    def check_and_handle_config_changes(
        self, current_config: dict[str, Any], block_on_change: bool = True
    ) -> dict[str, Any]:
        """
        检查配置变化并处理

        Args:
            current_config: 当前配置
            block_on_change: 如果配置变化是否阻止执行

        Returns:
            Dict[str, Any]: 处理结果
        """
        # 检查配置变化
        change_result = self.check_config_changes(current_config)

        if change_result["changed"]:
            # 配置已变化
            result = {
                "blocked": block_on_change,
                "reason": f"配置已变化，共 {len(change_result['changes'])} 处变化",
                "changes": change_result["changes"],
                "frozen_timestamp": change_result["frozen_timestamp"],
            }

            if block_on_change:
                logger.error(f"配置已变化，阻止执行：{result['reason']}")
            else:
                logger.warning(f"配置已变化，允许执行：{result['reason']}")
        else:
            # 配置未变化
            result = {"blocked": False, "reason": "配置未变化", "changes": []}
            logger.info("配置未变化，允许执行")

        return result


if __name__ == "__main__":
    # 测试代码
    config = {
        "system": {"name": "quantsys", "version": "1.0.0", "live_trading": True},
        "strategy": {"param1": 1.0, "param2": 2.0},
        "risk": {"max_position": 10000, "max_leverage": 10},
    }

    config_freeze = LiveConfigFreeze()

    # 测试冻结配置
    frozen = config_freeze.freeze_config(config, reason="测试冻结")
    print(f"冻结配置：{json.dumps(frozen, indent=2, ensure_ascii=False)}")

    # 测试加载冻结配置
    loaded = config_freeze.load_frozen_config()
    print(f"加载冻结配置：{json.dumps(loaded, indent=2, ensure_ascii=False)}")

    # 测试配置变化检查
    changed_config = config.copy()
    changed_config["strategy"]["param1"] = 1.5
    changed_config["strategy"]["param3"] = 3.0
    change_result = config_freeze.check_config_changes(changed_config)
    print(f"配置变化检查：{json.dumps(change_result, indent=2, ensure_ascii=False)}")

    # 测试创建回滚计划
    rollback_plan = config_freeze.create_rollback_plan(reason="测试回滚计划")
    print(f"回滚计划：{json.dumps(rollback_plan, indent=2, ensure_ascii=False)}")

    # 测试配置变化处理
    handle_result = config_freeze.check_and_handle_config_changes(
        changed_config, block_on_change=True
    )
    print(f"配置变化处理：{json.dumps(handle_result, indent=2, ensure_ascii=False)}")

    # 测试回滚
    rollback_result = config_freeze.rollback_to_frozen()
    print(f"回滚结果：{json.dumps(rollback_result, indent=2, ensure_ascii=False)}")
