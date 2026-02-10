#!/usr/bin/env python3
"""
故障注入模块，用于模拟各种系统故障，验证系统的容错能力和安全降级机制
"""

import logging
import os
import random
from dataclasses import dataclass, field
from datetime import datetime, timedelta

# 配置日志
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


@dataclass
class FaultConfig:
    """
    故障配置类
    """

    enabled: bool = False
    probability: float = 0.0  # 故障触发概率（0.0-1.0）
    duration: int = 0  # 故障持续时间（秒）
    start_time: datetime | None = None  # 故障开始时间
    end_time: datetime | None = None  # 故障结束时间


@dataclass
class FaultStatus:
    """
    故障状态类
    """

    active: bool = False
    fault_type: str = ""
    start_time: datetime | None = None
    end_time: datetime | None = None
    triggered: bool = False
    details: dict[str, any] = field(default_factory=dict)


class FaultInjector:
    """
    故障注入器类，用于模拟各种系统故障
    """

    def __init__(self):
        """
        初始化故障注入器
        """
        self.fault_configs: dict[str, FaultConfig] = {
            "network_disconnect": FaultConfig(enabled=False, probability=0.0, duration=60),
            "http_429": FaultConfig(enabled=False, probability=0.0, duration=30),
            "partial_fill": FaultConfig(enabled=False, probability=0.0, duration=0),
            "api_timeout": FaultConfig(enabled=False, probability=0.0, duration=0),
            "time_drift": FaultConfig(enabled=False, probability=0.0, duration=300),
            "release_interruption": FaultConfig(enabled=False, probability=0.0, duration=120),
            "package_corruption": FaultConfig(enabled=False, probability=0.0, duration=60),
            "validation_failure": FaultConfig(enabled=False, probability=0.0, duration=0),
            "rollback_failure": FaultConfig(enabled=False, probability=0.0, duration=180),
            "feature_drift": FaultConfig(enabled=False, probability=0.0, duration=300),
            "market_gap": FaultConfig(enabled=False, probability=0.0, duration=120),
        }

        self.fault_status: dict[str, FaultStatus] = {
            fault_type: FaultStatus() for fault_type in self.fault_configs.keys()
        }

        self.current_time: datetime = datetime.now()

        logger.info("故障注入器初始化完成")

    def update_current_time(self, timestamp: datetime):
        """
        更新当前时间

        Args:
            timestamp: 当前时间戳
        """
        self.current_time = timestamp
        self._check_fault_duration()

    def enable_fault(self, fault_type: str, probability: float = 0.5, duration: int = 60):
        """
        启用特定故障

        Args:
            fault_type: 故障类型
            probability: 故障触发概率（0.0-1.0）
            duration: 故障持续时间（秒）
        """
        if fault_type in self.fault_configs:
            self.fault_configs[fault_type] = FaultConfig(
                enabled=True, probability=probability, duration=duration
            )
            logger.info(f"启用故障 {fault_type}，概率: {probability}, 持续时间: {duration}秒")
        else:
            logger.error(f"未知故障类型: {fault_type}")

    def disable_fault(self, fault_type: str):
        """
        禁用特定故障

        Args:
            fault_type: 故障类型
        """
        if fault_type in self.fault_configs:
            self.fault_configs[fault_type].enabled = False
            if self.fault_status[fault_type].active:
                self.fault_status[fault_type].active = False
                self.fault_status[fault_type].end_time = self.current_time
            logger.info(f"禁用故障 {fault_type}")
        else:
            logger.error(f"未知故障类型: {fault_type}")

    def disable_all_faults(self):
        """
        禁用所有故障
        """
        for fault_type in self.fault_configs.keys():
            self.disable_fault(fault_type)
        logger.info("禁用所有故障")

    def _check_fault_duration(self):
        """
        检查故障持续时间，自动结束过期故障
        """
        for fault_type, status in self.fault_status.items():
            if status.active and status.end_time and self.current_time >= status.end_time:
                status.active = False
                logger.info(f"故障 {fault_type} 已结束")

    def _should_trigger_fault(self, fault_type: str) -> bool:
        """
        判断是否应该触发故障

        Args:
            fault_type: 故障类型

        Returns:
            bool: 是否触发故障
        """
        config = self.fault_configs[fault_type]

        if not config.enabled:
            return False

        if self.fault_status[fault_type].active:
            return True

        # 根据概率判断是否触发故障
        if random.random() <= config.probability:
            return True

        return False

    def inject_network_disconnect(self) -> bool:
        """
        注入网络断开故障

        Returns:
            bool: 是否注入成功
        """
        if self._should_trigger_fault("network_disconnect"):
            if not self.fault_status["network_disconnect"].active:
                config = self.fault_configs["network_disconnect"]
                end_time = self.current_time + timedelta(seconds=config.duration)
                self.fault_status["network_disconnect"] = FaultStatus(
                    active=True,
                    fault_type="network_disconnect",
                    start_time=self.current_time,
                    end_time=end_time,
                    triggered=True,
                    details={"duration": config.duration},
                )
                logger.error("[故障注入] 网络断开")
            return True
        return False

    def inject_http_429(self) -> bool:
        """
        注入HTTP 429 Too Many Requests故障

        Returns:
            bool: 是否注入成功
        """
        if self._should_trigger_fault("http_429"):
            if not self.fault_status["http_429"].active:
                config = self.fault_configs["http_429"]
                end_time = self.current_time + timedelta(seconds=config.duration)
                self.fault_status["http_429"] = FaultStatus(
                    active=True,
                    fault_type="http_429",
                    start_time=self.current_time,
                    end_time=end_time,
                    triggered=True,
                    details={"duration": config.duration},
                )
                logger.error("[故障注入] HTTP 429 Too Many Requests")
            return True
        return False

    def inject_partial_fill(self) -> bool:
        """
        注入部分成交故障

        Returns:
            bool: 是否注入成功
        """
        if self._should_trigger_fault("partial_fill"):
            fill_ratio = random.uniform(0.1, 0.9)  # 随机成交比例（10%-90%）
            self.fault_status["partial_fill"] = FaultStatus(
                active=False,  # 部分成交是一次性故障
                fault_type="partial_fill",
                start_time=self.current_time,
                end_time=self.current_time,
                triggered=True,
                details={"fill_ratio": fill_ratio},
            )
            logger.error(f"[故障注入] 部分成交，成交比例: {fill_ratio:.2%}")
            return True
        return False

    def inject_api_timeout(self) -> bool:
        """
        注入API超时故障

        Returns:
            bool: 是否注入成功
        """
        if self._should_trigger_fault("api_timeout"):
            timeout_duration = random.uniform(5.0, 30.0)  # 随机超时时间（5-30秒）
            self.fault_status["api_timeout"] = FaultStatus(
                active=False,  # API超时是一次性故障
                fault_type="api_timeout",
                start_time=self.current_time,
                end_time=self.current_time,
                triggered=True,
                details={"timeout_duration": timeout_duration},
            )
            logger.error(f"[故障注入] API超时，超时时间: {timeout_duration:.1f}秒")
            return True
        return False

    def inject_time_drift(self) -> bool:
        """
        注入时间漂移故障

        Returns:
            bool: 是否注入成功
        """
        if self._should_trigger_fault("time_drift"):
            if not self.fault_status["time_drift"].active:
                config = self.fault_configs["time_drift"]
                end_time = self.current_time + timedelta(seconds=config.duration)
                drift_seconds = random.uniform(-300, 300)  # 随机时间漂移（-5分钟到+5分钟）
                self.fault_status["time_drift"] = FaultStatus(
                    active=True,
                    fault_type="time_drift",
                    start_time=self.current_time,
                    end_time=end_time,
                    triggered=True,
                    details={"drift_seconds": drift_seconds, "duration": config.duration},
                )
                logger.error(
                    f"[故障注入] 时间漂移，漂移量: {drift_seconds:.1f}秒，持续时间: {config.duration}秒"
                )
            return True
        return False

    def inject_release_interruption(self) -> bool:
        """
        注入发布中断故障

        Returns:
            bool: 是否注入成功
        """
        if self._should_trigger_fault("release_interruption"):
            if not self.fault_status["release_interruption"].active:
                config = self.fault_configs["release_interruption"]
                end_time = self.current_time + timedelta(seconds=config.duration)
                self.fault_status["release_interruption"] = FaultStatus(
                    active=True,
                    fault_type="release_interruption",
                    start_time=self.current_time,
                    end_time=end_time,
                    triggered=True,
                    details={"duration": config.duration},
                )
                logger.error(f"[故障注入] 发布中断，预计持续 {config.duration} 秒")
            return True
        return False

    def inject_package_corruption(self) -> bool:
        """
        注入包损坏故障

        Returns:
            bool: 是否注入成功
        """
        if self._should_trigger_fault("package_corruption"):
            if not self.fault_status["package_corruption"].active:
                config = self.fault_configs["package_corruption"]
                end_time = self.current_time + timedelta(seconds=config.duration)
                # 模拟包损坏，随机选择一个核心包
                corrupted_packages = [
                    "factor_engine",
                    "execution_engine",
                    "risk_control",
                    "data_source",
                ]
                corrupted_package = random.choice(corrupted_packages)
                self.fault_status["package_corruption"] = FaultStatus(
                    active=True,
                    fault_type="package_corruption",
                    start_time=self.current_time,
                    end_time=end_time,
                    triggered=True,
                    details={"duration": config.duration, "corrupted_package": corrupted_package},
                )
                logger.error(
                    f"[故障注入] 包损坏，损坏的包: {corrupted_package}，预计持续 {config.duration} 秒"
                )
            return True
        return False

    def inject_validation_failure(self) -> bool:
        """
        注入校验失败故障

        Returns:
            bool: 是否注入成功
        """
        if self._should_trigger_fault("validation_failure"):
            # 校验失败是一次性故障
            validation_types = [
                "data_validation",
                "model_validation",
                "config_validation",
                "dependency_validation",
            ]
            failed_validation = random.choice(validation_types)
            error_message = f"{failed_validation} failed: {random.choice(['invalid format', 'missing required fields', 'out of range', 'checksum mismatch'])}"
            self.fault_status["validation_failure"] = FaultStatus(
                active=False,
                fault_type="validation_failure",
                start_time=self.current_time,
                end_time=self.current_time,
                triggered=True,
                details={"validation_type": failed_validation, "error_message": error_message},
            )
            logger.error(f"[故障注入] 校验失败: {error_message}")
            return True
        return False

    def inject_rollback_failure(self) -> bool:
        """
        注入回滚失败故障

        Returns:
            bool: 是否注入成功
        """
        if self._should_trigger_fault("rollback_failure"):
            if not self.fault_status["rollback_failure"].active:
                config = self.fault_configs["rollback_failure"]
                end_time = self.current_time + timedelta(seconds=config.duration)
                # 模拟回滚失败原因
                failure_reasons = [
                    "backup corrupted",
                    "permission denied",
                    "resource locked",
                    "network timeout",
                ]
                failure_reason = random.choice(failure_reasons)
                self.fault_status["rollback_failure"] = FaultStatus(
                    active=True,
                    fault_type="rollback_failure",
                    start_time=self.current_time,
                    end_time=end_time,
                    triggered=True,
                    details={"duration": config.duration, "failure_reason": failure_reason},
                )
                logger.error(
                    f"[故障注入] 回滚失败，原因: {failure_reason}，预计持续 {config.duration} 秒"
                )
            return True
        return False

    def inject_feature_drift(self) -> bool:
        """
        注入特征漂移故障

        Returns:
            bool: 是否注入成功
        """
        if self._should_trigger_fault("feature_drift"):
            if not self.fault_status["feature_drift"].active:
                config = self.fault_configs["feature_drift"]
                end_time = self.current_time + timedelta(seconds=config.duration)
                # 模拟特征漂移，随机选择一个特征
                features = [
                    "volume_profile",
                    "price_momentum",
                    "volatility",
                    "liquidity",
                    "sentiment",
                ]
                drifted_feature = random.choice(features)
                drift_magnitude = random.uniform(0.2, 1.0)  # 漂移幅度（20%-100%）
                self.fault_status["feature_drift"] = FaultStatus(
                    active=True,
                    fault_type="feature_drift",
                    start_time=self.current_time,
                    end_time=end_time,
                    triggered=True,
                    details={
                        "duration": config.duration,
                        "drifted_feature": drifted_feature,
                        "drift_magnitude": drift_magnitude,
                    },
                )
                logger.error(
                    f"[故障注入] 特征漂移，特征: {drifted_feature}，漂移幅度: {drift_magnitude:.1%}，预计持续 {config.duration} 秒"
                )
            return True
        return False

    def inject_market_gap(self) -> bool:
        """
        注入行情缺口故障

        Returns:
            bool: 是否注入成功
        """
        if self._should_trigger_fault("market_gap"):
            if not self.fault_status["market_gap"].active:
                config = self.fault_configs["market_gap"]
                end_time = self.current_time + timedelta(seconds=config.duration)
                # 模拟行情缺口，随机选择方向和幅度
                gap_direction = random.choice(["up", "down"])
                gap_size = random.uniform(0.01, 0.1)  # 缺口大小（1%-10%）
                self.fault_status["market_gap"] = FaultStatus(
                    active=True,
                    fault_type="market_gap",
                    start_time=self.current_time,
                    end_time=end_time,
                    triggered=True,
                    details={
                        "duration": config.duration,
                        "gap_direction": gap_direction,
                        "gap_size": gap_size,
                    },
                )
                logger.error(
                    f"[故障注入] 行情缺口，方向: {gap_direction}，缺口大小: {gap_size:.1%}，预计持续 {config.duration} 秒"
                )
            return True
        return False

    def is_fault_active(self, fault_type: str) -> bool:
        """
        检查特定故障是否活跃

        Args:
            fault_type: 故障类型

        Returns:
            bool: 故障是否活跃
        """
        return fault_type in self.fault_status and self.fault_status[fault_type].active

    def get_active_faults(self) -> list[str]:
        """
        获取所有活跃的故障

        Returns:
            List[str]: 活跃故障类型列表
        """
        return [fault_type for fault_type, status in self.fault_status.items() if status.active]

    def get_fault_status(self, fault_type: str) -> FaultStatus | None:
        """
        获取特定故障的状态

        Args:
            fault_type: 故障类型

        Returns:
            Optional[FaultStatus]: 故障状态，未知故障类型返回None
        """
        return self.fault_status.get(fault_type)

    def get_all_fault_status(self) -> dict[str, FaultStatus]:
        """
        获取所有故障的状态

        Returns:
            Dict[str, FaultStatus]: 所有故障状态
        """
        return self.fault_status

    def reset_all_faults(self):
        """
        重置所有故障状态
        """
        for fault_type in self.fault_status.keys():
            self.fault_status[fault_type] = FaultStatus()
        logger.info("重置所有故障状态")

    def generate_drill_report(self) -> dict[str, any]:
        """
        生成故障演练报告

        Returns:
            Dict[str, any]: 演练报告字典
        """
        report = {
            "report_generated_at": datetime.now().isoformat(),
            "drill_overview": {
                "total_fault_types": len(self.fault_configs),
                "active_faults": len(self.get_active_faults()),
                "triggered_faults": sum(
                    1 for status in self.fault_status.values() if status.triggered
                ),
            },
            "fault_details": [],
            "system_response": {"blocked_reasons": []},
            "drill_conclusion": "",
        }

        # 收集故障详情
        for fault_type, status in self.fault_status.items():
            if status.triggered:
                fault_detail = {
                    "fault_type": fault_type,
                    "triggered": status.triggered,
                    "active": status.active,
                    "start_time": status.start_time.isoformat() if status.start_time else None,
                    "end_time": status.end_time.isoformat() if status.end_time else None,
                    "details": status.details,
                }
                report["fault_details"].append(fault_detail)

        # 收集系统响应信息
        active_faults = self.get_active_faults()
        if active_faults:
            report["system_response"]["status"] = "BLOCKED"
            report["system_response"]["blocked_reasons"] = active_faults
        else:
            report["system_response"]["status"] = "READY"

        # 生成演练结论
        if report["drill_overview"]["triggered_faults"] == 0:
            report["drill_conclusion"] = "未触发任何故障，无法评估系统响应"
        elif active_faults:
            report["drill_conclusion"] = "系统检测到故障并正确进入BLOCKED状态"
        else:
            report["drill_conclusion"] = "系统检测到故障后已恢复正常状态"

        logger.info(f"生成故障演练报告，共包含 {len(report['fault_details'])} 个触发的故障")
        return report

    def save_drill_report(self, file_path: str = "drill_report.json"):
        """
        保存故障演练报告到文件

        Args:
            file_path: 报告文件路径
        """
        import json

        report = self.generate_drill_report()

        # 确保目录存在
        os.makedirs(os.path.dirname(file_path), exist_ok=True)

        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)

        logger.info(f"故障演练报告已保存到: {file_path}")


class FaultAwareExecutionReadiness:
    """
    支持故障感知的执行就绪管理器
    """

    def __init__(self, fault_injector: FaultInjector):
        """
        初始化故障感知执行就绪管理器

        Args:
            fault_injector: 故障注入器实例
        """
        from src.quantsys.execution.readiness import ExecutionReadiness

        self.base_readiness = ExecutionReadiness()
        self.fault_injector = fault_injector

        logger.info("故障感知执行就绪管理器初始化完成")

    def check_readiness(self):
        """
        检查系统就绪状态，考虑故障注入情况

        Returns:
            ReadinessStatus: 系统就绪状态
        """
        base_status = self.base_readiness.check_readiness()

        # 如果基础状态已阻塞，直接返回
        if base_status.blocked:
            return base_status

        # 检查故障注入情况
        active_faults = self.fault_injector.get_active_faults()
        blocked_reasons = []

        # 检查活跃故障
        if active_faults:
            blocked_reasons.append(f"检测到活跃故障: {', '.join(active_faults)}")

            # 根据故障类型添加具体原因
            for fault_type in active_faults:
                fault_status = self.fault_injector.get_fault_status(fault_type)
                if fault_status and fault_status.details:
                    if fault_type == "network_disconnect":
                        blocked_reasons.append(
                            f"网络断开，预计持续 {fault_status.details.get('duration', 0)} 秒"
                        )
                    elif fault_type == "http_429":
                        blocked_reasons.append("HTTP 429 Too Many Requests")
                    elif fault_type == "time_drift":
                        drift_seconds = fault_status.details.get("drift_seconds", 0)
                        blocked_reasons.append(f"时间漂移 {drift_seconds:.1f} 秒")
                    elif fault_type == "release_interruption":
                        blocked_reasons.append(
                            f"发布中断，预计持续 {fault_status.details.get('duration', 0)} 秒"
                        )
                    elif fault_type == "package_corruption":
                        corrupted_package = fault_status.details.get("corrupted_package", "unknown")
                        blocked_reasons.append(
                            f"包损坏: {corrupted_package}，预计持续 {fault_status.details.get('duration', 0)} 秒"
                        )
                    elif fault_type == "rollback_failure":
                        failure_reason = fault_status.details.get("failure_reason", "unknown")
                        blocked_reasons.append(
                            f"回滚失败，原因: {failure_reason}，预计持续 {fault_status.details.get('duration', 0)} 秒"
                        )
                    elif fault_type == "feature_drift":
                        drifted_feature = fault_status.details.get("drifted_feature", "unknown")
                        drift_magnitude = fault_status.details.get("drift_magnitude", 0)
                        blocked_reasons.append(
                            f"特征漂移: {drifted_feature}，漂移幅度: {drift_magnitude:.1%}，预计持续 {fault_status.details.get('duration', 0)} 秒"
                        )
                    elif fault_type == "market_gap":
                        gap_direction = fault_status.details.get("gap_direction", "unknown")
                        gap_size = fault_status.details.get("gap_size", 0)
                        blocked_reasons.append(
                            f"行情缺口: {gap_direction}，缺口大小: {gap_size:.1%}，预计持续 {fault_status.details.get('duration', 0)} 秒"
                        )

        # 检查一次性故障（如validation_failure）
        validation_status = self.fault_injector.get_fault_status("validation_failure")
        if validation_status and validation_status.triggered:
            blocked_reasons.append(
                f"校验失败: {validation_status.details.get('error_message', '未知错误')}"
            )

        if blocked_reasons:
            # 检测到故障，系统进入BLOCKED状态
            from src.quantsys.execution.readiness import ReadinessStatus
            from src.quantsys.execution.reconciliation import RecommendedAction

            return ReadinessStatus(
                ok=False,
                blocked=True,
                reasons=blocked_reasons,
                recommended_action=RecommendedAction.BLOCK,
            )

        return base_status

    def is_ready(self) -> bool:
        """
        检查系统是否就绪

        Returns:
            bool: 系统是否就绪
        """
        status = self.check_readiness()
        return status.ok and not status.blocked

    def is_blocked(self) -> bool:
        """
        检查系统是否阻塞

        Returns:
            bool: 系统是否阻塞
        """
        status = self.check_readiness()
        return status.blocked

    def get_blocked_reasons(self) -> list[str]:
        """
        获取阻塞原因

        Returns:
            List[str]: 阻塞原因列表
        """
        status = self.check_readiness()
        return status.reasons
