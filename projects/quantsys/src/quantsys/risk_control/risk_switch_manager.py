#!/usr/bin/env python3
"""
风控分层开关管理器
支持global/strategy/symbol三层开关配置，热加载和审计事件记录
"""

import json
import logging
import os
import time
from datetime import datetime
from typing import Any

import yaml

# 配置日志
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class RiskSwitchManager:
    """风控开关管理器"""

    def __init__(self, config_path: str):
        """初始化风控开关管理器

        Args:
            config_path: 配置文件路径
        """
        self.config_path = config_path
        self.config = self._load_config()
        self.last_mtime = os.path.getmtime(self.config_path)
        self.audit_log_path = os.path.join(os.path.dirname(config_path), "risk_switch_audit.log")
        self.audit_events = []
        self._load_audit_events()

    def _load_config(self) -> dict[str, Any]:
        """加载配置文件

        Returns:
            配置字典
        """
        with open(self.config_path, encoding="utf-8") as f:
            config = yaml.safe_load(f)

        # 确保配置结构完整
        if not config:
            config = {"global": {}, "strategy": {}, "symbol": {}}
        else:
            if "global" not in config:
                config["global"] = {}
            if "strategy" not in config:
                config["strategy"] = {}
            if "symbol" not in config:
                config["symbol"] = {}

        logger.info(f"加载配置文件: {self.config_path}")
        return config

    def _load_audit_events(self) -> None:
        """加载审计事件"""
        if os.path.exists(self.audit_log_path):
            with open(self.audit_log_path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        self.audit_events.append(json.loads(line))
        logger.info(f"加载审计事件: {len(self.audit_events)} 条")

    def _write_audit_event(self, event: dict[str, Any]) -> None:
        """写入审计事件

        Args:
            event: 审计事件
        """
        event["timestamp"] = time.time()
        event["event_time"] = datetime.now().isoformat()

        # 写入日志文件
        with open(self.audit_log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(event, ensure_ascii=False) + "\n")

        # 内存中保存
        self.audit_events.append(event)
        logger.info(f"写入审计事件: {event['event_type']} - {event['key']}")

    def check_reload(self) -> bool:
        """检查配置文件是否需要重新加载

        Returns:
            是否重新加载
        """
        current_mtime = os.path.getmtime(self.config_path)
        if current_mtime > self.last_mtime:
            logger.info(f"配置文件已更新，重新加载: {self.config_path}")
            self.config = self._load_config()
            self.last_mtime = current_mtime

            # 写入配置重载审计事件
            self._write_audit_event(
                {
                    "event_type": "config_reloaded",
                    "key": "all",
                    "previous_value": None,
                    "new_value": None,
                    "updated_by": "system",
                    "description": "配置文件自动重载",
                }
            )
            return True
        return False

    def get_switch_value(
        self, key: str, strategy: str | None = None, symbol: str | None = None, default: Any = None
    ) -> Any:
        """获取开关值，支持层级优先级：symbol > strategy > global

        Args:
            key: 开关名称
            strategy: 策略名称
            symbol: 交易对
            default: 默认值

        Returns:
            开关值
        """
        # 检查是否需要重新加载配置
        self.check_reload()

        # 1. 检查交易对级开关
        if (
            strategy
            and symbol
            and strategy in self.config["symbol"]
            and symbol in self.config["symbol"][strategy]
        ):
            if (
                key in self.config["symbol"][strategy][symbol]
                and self.config["symbol"][strategy][symbol][key]["enabled"]
            ):
                logger.debug(f"从交易对级获取开关值: {key} - {strategy}/{symbol}")
                return self.config["symbol"][strategy][symbol][key]["value"]

        # 2. 检查策略级开关
        if strategy and strategy in self.config["strategy"]:
            if (
                key in self.config["strategy"][strategy]
                and self.config["strategy"][strategy][key]["enabled"]
            ):
                logger.debug(f"从策略级获取开关值: {key} - {strategy}")
                return self.config["strategy"][strategy][key]["value"]

        # 3. 检查全局开关
        if key in self.config["global"] and self.config["global"][key]["enabled"]:
            logger.debug(f"从全局获取开关值: {key}")
            return self.config["global"][key]["value"]

        logger.debug(f"未找到开关值: {key}，返回默认值: {default}")
        return default

    def update_switch(
        self,
        key: str,
        value: Any,
        level: str,
        strategy: str | None = None,
        symbol: str | None = None,
        enabled: bool = True,
        updated_by: str = "system",
        description: str = "",
    ) -> bool:
        """更新开关值

        Args:
            key: 开关名称
            value: 开关值
            level: 开关层级 (global/strategy/symbol)
            strategy: 策略名称
            symbol: 交易对
            enabled: 是否启用
            updated_by: 更新人
            description: 描述

        Returns:
            是否更新成功
        """
        # 检查参数
        if level == "strategy" and not strategy:
            logger.error("更新策略级开关必须提供策略名称")
            return False
        if level == "symbol" and (not strategy or not symbol):
            logger.error("更新交易对级开关必须提供策略名称和交易对")
            return False

        # 获取之前的值
        previous_value = self.get_switch_value(key, strategy, symbol)

        # 更新配置
        update_ts = time.time()
        switch_config = {
            "enabled": enabled,
            "value": value,
            "description": description,
            "create_ts": update_ts,
            "update_ts": update_ts,
            "updated_by": updated_by,
        }

        if level == "global":
            self.config["global"][key] = switch_config
        elif level == "strategy":
            if strategy not in self.config["strategy"]:
                self.config["strategy"][strategy] = {}
            self.config["strategy"][strategy][key] = switch_config
        elif level == "symbol":
            if strategy not in self.config["symbol"]:
                self.config["symbol"][strategy] = {}
            if symbol not in self.config["symbol"][strategy]:
                self.config["symbol"][strategy][symbol] = {}
            self.config["symbol"][strategy][symbol][key] = switch_config
        else:
            logger.error(f"无效的开关层级: {level}")
            return False

        # 保存配置
        with open(self.config_path, "w", encoding="utf-8") as f:
            yaml.dump(self.config, f, indent=2, allow_unicode=True)

        # 更新mtime
        self.last_mtime = os.path.getmtime(self.config_path)

        # 写入审计事件
        self._write_audit_event(
            {
                "event_type": "switch_updated",
                "key": key,
                "level": level,
                "strategy": strategy,
                "symbol": symbol,
                "previous_value": previous_value,
                "new_value": value,
                "enabled": enabled,
                "updated_by": updated_by,
                "description": description,
            }
        )

        logger.info(f"更新开关: {key} - {level} - {strategy}/{symbol} - {value}")
        return True

    def delete_switch(
        self,
        key: str,
        level: str,
        strategy: str | None = None,
        symbol: str | None = None,
        updated_by: str = "system",
        description: str = "",
    ) -> bool:
        """删除开关

        Args:
            key: 开关名称
            level: 开关层级 (global/strategy/symbol)
            strategy: 策略名称
            symbol: 交易对
            updated_by: 更新人
            description: 描述

        Returns:
            是否删除成功
        """
        # 检查参数
        if level == "strategy" and not strategy:
            logger.error("删除策略级开关必须提供策略名称")
            return False
        if level == "symbol" and (not strategy or not symbol):
            logger.error("删除交易对级开关必须提供策略名称和交易对")
            return False

        # 获取之前的值
        previous_value = self.get_switch_value(key, strategy, symbol)

        # 删除开关
        success = False
        if level == "global":
            if key in self.config["global"]:
                del self.config["global"][key]
                success = True
        elif level == "strategy":
            if strategy in self.config["strategy"] and key in self.config["strategy"][strategy]:
                del self.config["strategy"][strategy][key]
                success = True
        elif level == "symbol":
            if (
                strategy in self.config["symbol"]
                and symbol in self.config["symbol"][strategy]
                and key in self.config["symbol"][strategy][symbol]
            ):
                del self.config["symbol"][strategy][symbol][key]
                success = True
        else:
            logger.error(f"无效的开关层级: {level}")
            return False

        if success:
            # 保存配置
            with open(self.config_path, "w", encoding="utf-8") as f:
                yaml.dump(self.config, f, indent=2, allow_unicode=True)

            # 更新mtime
            self.last_mtime = os.path.getmtime(self.config_path)

            # 写入审计事件
            self._write_audit_event(
                {
                    "event_type": "switch_deleted",
                    "key": key,
                    "level": level,
                    "strategy": strategy,
                    "symbol": symbol,
                    "previous_value": previous_value,
                    "new_value": None,
                    "enabled": None,
                    "updated_by": updated_by,
                    "description": description,
                }
            )

            logger.info(f"删除开关: {key} - {level} - {strategy}/{symbol}")

        return success

    def get_audit_events(self, limit: int = 100) -> list[dict[str, Any]]:
        """获取审计事件

        Args:
            limit: 返回事件数量限制

        Returns:
            审计事件列表
        """
        return self.audit_events[-limit:]

    def self_test(self) -> dict[str, Any]:
        """自测

        Returns:
            自测结果
        """
        test_result = {"timestamp": time.time(), "tests": [], "passed": True}

        # 测试1: 配置加载
        try:
            config = self._load_config()
            test_result["tests"].append(
                {"test_name": "config_load", "result": "passed", "description": "配置加载成功"}
            )
        except Exception as e:
            test_result["tests"].append(
                {
                    "test_name": "config_load",
                    "result": "failed",
                    "description": f"配置加载失败: {str(e)}",
                }
            )
            test_result["passed"] = False

        # 测试2: 开关查询
        try:
            value = self.get_switch_value("max_order_amount", "strategy_1", "BTC-USDT")
            test_result["tests"].append(
                {
                    "test_name": "switch_query",
                    "result": "passed",
                    "description": f"开关查询成功，值: {value}",
                }
            )
        except Exception as e:
            test_result["tests"].append(
                {
                    "test_name": "switch_query",
                    "result": "failed",
                    "description": f"开关查询失败: {str(e)}",
                }
            )
            test_result["passed"] = False

        # 测试3: 审计事件记录
        try:
            # 创建一个临时开关进行测试
            self.update_switch(
                "test_switch", 100, "global", updated_by="self_test", description="测试开关"
            )
            # 删除测试开关
            self.delete_switch(
                "test_switch", "global", updated_by="self_test", description="删除测试开关"
            )
            test_result["tests"].append(
                {"test_name": "audit_event", "result": "passed", "description": "审计事件记录成功"}
            )
        except Exception as e:
            test_result["tests"].append(
                {
                    "test_name": "audit_event",
                    "result": "failed",
                    "description": f"审计事件记录失败: {str(e)}",
                }
            )
            test_result["passed"] = False

        return test_result

    def save_evidence(self, evidence_dir: str = "evidence") -> str:
        """保存证据

        Args:
            evidence_dir: 证据目录

        Returns:
            证据文件路径
        """
        # 创建证据目录
        evidence_path = os.path.join(evidence_dir, datetime.now().strftime("%Y%m%d"))
        os.makedirs(evidence_path, exist_ok=True)

        # 保存自测结果
        test_result = self.self_test()
        evidence_file = os.path.join(
            evidence_path, f"risk_switch_self_test_{datetime.now().strftime('%H%M%S')}.json"
        )
        with open(evidence_file, "w", encoding="utf-8") as f:
            json.dump(test_result, f, indent=2, ensure_ascii=False)

        # 保存当前配置
        config_file = os.path.join(
            evidence_path, f"risk_switch_config_{datetime.now().strftime('%H%M%S')}.yaml"
        )
        with open(config_file, "w", encoding="utf-8") as f:
            yaml.dump(self.config, f, indent=2, allow_unicode=True)

        # 保存审计事件
        audit_file = os.path.join(
            evidence_path, f"risk_switch_audit_{datetime.now().strftime('%H%M%S')}.json"
        )
        with open(audit_file, "w", encoding="utf-8") as f:
            json.dump(self.audit_events, f, indent=2, ensure_ascii=False)

        logger.info(f"保存证据文件: {evidence_file}, {config_file}, {audit_file}")
        return evidence_file
