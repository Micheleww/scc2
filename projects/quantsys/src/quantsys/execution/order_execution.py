#!/usr/bin/env python3
"""
订单执行模块
实现与交易所API的交互，处理订单的创建、取消和查询
"""

import hashlib
import hmac
import json
import logging
import time
from datetime import datetime
from typing import Any

import requests
from requests.exceptions import ConnectionError, Timeout

from src.quantsys.common.black_swan_mode import BlackSwanModeManager
from src.quantsys.common.risk_manager import RiskManager, RiskVerdict
from src.quantsys.execution.readiness import ExecutionReadiness
from src.quantsys.risk import RiskEngine

from .account_service import AccountService
from .exchange_adapter import ExchangeAdapterFactory
from .execution_context import ExecutionContext
from .guards.risk_guard import GuardBlockedError, OrderIntent, RiskGuard, RiskVerdict
from .order_executor import OrderExecutor

# 导入订单ID管理和状态机
from .order_ids import OrderIdManager
from .order_splitter import OrderSplitter
from .order_validator import OrderValidator
from .reconciliation import ReconciliationReport, reconcile
from .risk_gate import RiskGate

# 配置日志
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# 限制公开接口：只允许 execution wrapper 方法调用
__all__ = ["OrderExecution"]


class OrderExecution:
    """
    订单执行类，处理与交易所API的交互
    """

    def __init__(
        self,
        config: dict[str, Any],
        readiness: ExecutionReadiness | None = None,
        risk_engine: RiskEngine | None = None,
    ):
        """
        初始化订单执行模块

        Args:
            config: 配置信息，包含交易所API密钥等
            readiness: Execution Readiness manager instance
            risk_engine: Risk Engine instance for evaluating order intents
        """
        self.config = config
        self.exchange = config.get("exchange", "okx")

        # Risk Engine (optional, for evaluating order intents)
        self.risk_engine = risk_engine

        # 从环境变量读取交易所密钥，安全优先
        import os

        # 根据交易所类型构建环境变量名
        exchange_prefix = self.exchange.upper()
        self.api_key = os.environ.get(f"{exchange_prefix}_API_KEY", "")
        self.secret_key = os.environ.get(f"{exchange_prefix}_API_SECRET", "")
        self.passphrase = os.environ.get(f"{exchange_prefix}_PASSPHRASE", "")

        # 执行模式：live, dry_run, paper, drill, test
        self.trading_mode = config.get("trading_mode", "drill")

        # 检查密钥是否完整，测试模式下跳过
        if self.trading_mode != "test" and not all(
            [self.api_key, self.secret_key, self.passphrase]
        ):
            missing_keys = []
            if not self.api_key:
                missing_keys.append(f"{exchange_prefix}_API_KEY")
            if not self.secret_key:
                missing_keys.append(f"{exchange_prefix}_API_SECRET")
            if not self.passphrase:
                missing_keys.append(f"{exchange_prefix}_PASSPHRASE")

            error_msg = (
                f"缺失必要的交易所密钥: {', '.join(missing_keys)}。请通过环境变量设置完整的密钥。"
            )
            logger.error(error_msg)

            # 若readiness存在，记录缺失密钥信息但不调用block方法（该方法不存在）
            if readiness:
                logger.error("readiness对象存在但缺少block方法，无法将系统状态设置为BLOCKED")

            # 抛出异常，确保系统不会在缺密钥情况下运行
            raise ValueError(error_msg)

        # 执行就绪管理器
        self.readiness = readiness

        # 初始化风险管理器
        self.risk_manager = RiskManager(config.get("risk_params", {}))

        # 初始化账户服务（用于获取真实账户数据）
        self.account_service = AccountService(
            exchange=self.exchange, trading_mode=self.trading_mode
        )

        # 初始化统一风险门禁（统一风险检查入口）
        self.risk_gate = RiskGate(
            risk_manager=self.risk_manager, account_service=self.account_service
        )

        # 初始化订单ID管理器
        self.order_id_manager = OrderIdManager()

        # 创建交易所适配器（用于拆分后的模块）
        import os

        exchange_prefix = self.exchange.upper()
        api_key = os.environ.get(f"{exchange_prefix}_API_KEY", "")
        secret_key = os.environ.get(f"{exchange_prefix}_API_SECRET", "")
        passphrase = os.environ.get(f"{exchange_prefix}_PASSPHRASE", "")

        self.exchange_adapter = ExchangeAdapterFactory.create(
            exchange=self.exchange,
            api_key=api_key,
            secret_key=secret_key,
            passphrase=passphrase,
            trading_mode=self.trading_mode,
        )

        # 创建订单验证器
        self.order_validator = OrderValidator(config.get("order_validator", {}))

        # 创建订单执行器（用于拆分后的模块）
        self.order_executor = OrderExecutor(
            exchange_adapter=self.exchange_adapter,
            order_id_manager=self.order_id_manager,
            order_validator=self.order_validator,
        )

        # 初始化订单分拆管理器
        self.order_splitter = OrderSplitter(config.get("order_splitter", {}))

        # 初始化黑天鹅模式管理器
        self.black_swan_manager = BlackSwanModeManager(config.get("black_swan", {}))

        # 初始化 Runtime Guard
        risk_guard_config = config.get("risk_guard", {})
        risk_guard_enabled = risk_guard_config.get("enabled", True)
        self.risk_guard = RiskGuard(enabled=risk_guard_enabled)

        # 事件流日志（必须在 _record_startup_audit 之前初始化）
        self.event_log = []

        # Startup gates: Load runtime environment configuration
        self._load_runtime_env()

        # Startup gates: Validate risk_guard configuration
        self._validate_risk_guard_config()

        # Startup gates: Generate session_id
        self.session_id = self._generate_session_id()

        # Startup gates: Record startup audit events
        self._record_startup_audit()

        # 真单开关配置
        self.real_order_switch = config.get("real_order", {}).get(
            "enabled", False
        )  # 真单开关，默认关闭
        self.real_order_config = config.get("real_order", {})

        # 真单限制参数
        self.real_order_limits = {
            "single_order_max_usdt": self.real_order_config.get(
                "single_order_max_usdt", 3.3
            ),  # 单笔名义≤3.3u
            "total_budget_max_usdt": self.real_order_config.get(
                "total_budget_max_usdt", 10.0
            ),  # 总预算≤10u
            "max_positions": self.real_order_config.get("max_positions", 1),  # 最多1仓
        }

        # 止损配置
        self.stop_loss_config = {
            "enabled": self.real_order_config.get("stop_loss_enabled", True),  # 自动止损，默认开启
            "stop_loss_ratio": self.real_order_config.get("stop_loss_ratio", 0.01),  # 止损比例1%
        }

        # 真单状态
        self.real_order_status = {
            "enabled": self.real_order_switch,
            "current_positions": 0,
            "total_usdt_used": 0.0,
        }

        # 交易所API端点
        if self.exchange == "okx":
            self.base_url = "https://www.okx.com"
        else:
            raise ValueError(f"不支持的交易所: {self.exchange}")

        # 重试配置
        retry_config = config.get("retry", {})
        self.max_retries = retry_config.get("max_retries", 3)
        self.initial_retry_delay = retry_config.get(
            "initial_retry_delay", 1.0
        )  # 初始重试延迟（秒）
        self.max_retry_delay = retry_config.get("max_retry_delay", 30.0)  # 最大重试延迟（秒）
        self.backoff_factor = retry_config.get("backoff_factor", 2.0)  # 退避因子

        # 重试指标
        self.retry_metrics = {
            "total_attempts": 0,
            "successful_attempts": 0,
            "failed_attempts": 0,
            "retries": 0,
            "retry_success": 0,
            "retry_failure": 0,
            "error_types": {},
        }

        logger.info(
            f"订单执行模块初始化完成，交易所: {self.exchange}，交易模式: {self.trading_mode}"
        )
        logger.info(
            f"重试配置: 最大重试次数={self.max_retries}, 初始延迟={self.initial_retry_delay}s, 最大延迟={self.max_retry_delay}s, 退避因子={self.backoff_factor}"
        )

    def _load_runtime_env(self):
        """
        Load runtime environment configuration from configs/current/runtime_env.yaml
        Authority: see law/QCC-README.md
        """
        import os

        import yaml

        runtime_env_path = os.path.join(
            os.path.dirname(__file__), "..", "..", "..", "configs", "current", "runtime_env.yaml"
        )

        try:
            with open(runtime_env_path, encoding="utf-8") as f:
                self.runtime_env = yaml.safe_load(f)
            logger.info(f"Runtime environment loaded: {self.runtime_env.get('env', 'unknown')}")
        except FileNotFoundError:
            logger.warning(
                f"Runtime environment config not found at {runtime_env_path}, using defaults"
            )
            self.runtime_env = {"env": "backtest", "live_account_id": "", "real_broker": False}
        except Exception as e:
            logger.error(f"Failed to load runtime environment config: {e}")
            raise RuntimeError(f"Failed to load runtime environment config: {e}")

    def _validate_risk_guard_config(self):
        """
        Validate risk_guard configuration based on runtime environment
        Authority: see law/QCC-README.md

        Fail-fast if:
        - env=live and risk_guard.enabled=false
        - live_account_id is set and risk_guard.enabled=false
        - real_broker=true and risk_guard.enabled=false
        """
        env = self.runtime_env.get("env", "backtest")
        live_account_id = self.runtime_env.get("live_account_id", "")
        real_broker = self.runtime_env.get("real_broker", False)
        risk_guard_enabled = self.risk_guard.enabled

        # Check if environment is live
        is_live = env == "live" or (live_account_id and live_account_id.strip()) or real_broker

        if is_live and not risk_guard_enabled:
            error_msg = f"FAIL-FAST: Live environment detected (env={env}, live_account_id={live_account_id}, real_broker={real_broker}) but risk_guard.enabled=false. System will NOT start."
            logger.error(error_msg)

            # Record audit event
            self._record_audit_event(
                {
                    "event_type": "SYSTEM_START_BLOCKED",
                    "timestamp": time.time(),
                    "timestamp_ms": int(time.time() * 1000),
                    "session_id": "N/A",
                    "env": env,
                    "live_account_id": live_account_id,
                    "real_broker": real_broker,
                    "risk_guard_enabled": risk_guard_enabled,
                    "reason": "Live environment requires risk_guard.enabled=true",
                    "result": "BLOCKED",
                    "error_code": "STARTUP_GATE_FAILED",
                }
            )

            raise RuntimeError(error_msg)

        logger.info(
            f"Startup gate validation passed: env={env}, risk_guard.enabled={risk_guard_enabled}"
        )

    def _generate_session_id(self) -> str:
        """
        Generate unique session_id for this execution lifecycle
        Authority: see law/QCC-README.md

        Returns:
            session_id: Unique session identifier
        """
        import uuid

        session_id = f"sess_{int(time.time())}_{uuid.uuid4().hex[:8]}"
        logger.info(f"Generated session_id: {session_id}")
        return session_id

    def _record_startup_audit(self):
        """
        Record startup audit events
        Authority: see law/QCC-README.md
        """
        startup_event = {
            "event_type": "SYSTEM_START",
            "timestamp": time.time(),
            "timestamp_ms": int(time.time() * 1000),
            "session_id": self.session_id,
            "env": self.runtime_env.get("env", "unknown"),
            "live_account_id": self.runtime_env.get("live_account_id", ""),
            "real_broker": self.runtime_env.get("real_broker", False),
            "risk_guard_enabled": self.risk_guard.enabled,
            "exchange": self.exchange,
            "trading_mode": self.trading_mode,
            "result": "SUCCESS",
            "error_code": None,
        }

        self._record_audit_event(startup_event)

        # Also record SESSION_OPEN event
        session_event = {
            "event_type": "SESSION_OPEN",
            "timestamp": time.time(),
            "timestamp_ms": int(time.time() * 1000),
            "session_id": self.session_id,
            "env": self.runtime_env.get("env", "unknown"),
            "result": "SUCCESS",
            "error_code": None,
        }

        self._record_audit_event(session_event)

    def _record_audit_event(self, event: dict[str, Any]):
        """
        Record audit event to event log
        Authority: see law/QCC-README.md

        Args:
            event: Audit event dictionary
        """
        self.event_log.append(event)
        logger.info(f"Audit event recorded: {event.get('event_type')}")

    def _sign_request(
        self, method: str, endpoint: str, body: dict[str, Any] = None
    ) -> dict[str, str]:
        """
        生成请求签名

        Args:
            method: HTTP方法
            endpoint: API端点
            body: 请求体

        Returns:
            headers: 包含签名的请求头
        """
        body = body or {}

        # 获取当前时间戳
        timestamp = str(datetime.utcnow().isoformat()[:-3]) + "Z"

        # 构造签名字符串
        message = timestamp + method.upper() + endpoint + json.dumps(body)

        # 生成签名（OKX要求使用Base64编码）
        import base64

        signature = base64.b64encode(
            hmac.new(
                self.secret_key.encode("utf-8"), message.encode("utf-8"), hashlib.sha256
            ).digest()
        ).decode("utf-8")

        # 构造请求头
        headers = {
            "OK-ACCESS-KEY": self.api_key,
            "OK-ACCESS-SIGN": signature,
            "OK-ACCESS-TIMESTAMP": timestamp,
            "OK-ACCESS-PASSPHRASE": self.passphrase,
            "Content-Type": "application/json",
        }

        return headers

    def _send_request_with_retry(
        self,
        method: str,
        endpoint: str,
        body: dict[str, Any] = None,
        context: ExecutionContext | None = None,
    ) -> dict[str, Any]:
        """
        发送带重试机制的API请求（私有方法，仅由 execution wrapper 调用）

        Args:
            method: HTTP方法
            endpoint: API端点
            body: 请求体
            context: 执行上下文（用于调用源校验）

        Returns:
            result: API响应结果

        Raises:
            RuntimeError: If verdict is required but not provided or invalid
        """
        # 二次门禁：检查是否需要 verdict
        # 在 broker adapter 层面，所有真实发单请求必须通过 execution wrapper 调用
        # 这里我们通过检查调用栈来验证（简化实现）
        # 实际生产环境应该通过参数传入 verdict

        # 调用源校验：context.source 必须为 "execution"
        if context and context.source != "execution":
            error_msg = (
                f"BYPASS DETECTED: Invalid context.source '{context.source}', must be 'execution'"
            )
            logger.error(error_msg)
            raise RuntimeError(error_msg)

        self.retry_metrics["total_attempts"] += 1
        attempt = 0
        retry_delay = self.initial_retry_delay

        # 二次门禁：检查是否是从 execution wrapper 调用的
        import inspect

        caller_frame = inspect.currentframe().f_back
        caller_name = caller_frame.f_code.co_name if caller_frame else "unknown"
        caller_function = caller_frame.f_code.co_name if caller_frame else "unknown"

        # 允许的调用者列表（execution wrapper 方法）
        allowed_callers = [
            "place_order",
            "cancel_order",
            "cancel_all_orders",
            "modify_order",
            "_execute_single_order",
            "place_market_order",
            "place_limit_order",
        ]

        # 如果不是从允许的调用者调用，则拒绝
        is_allowed = any(caller in allowed_callers for caller in [caller_name, caller_function])

        if not is_allowed:
            error_msg = f"BYPASS DETECTED: Direct call to _send_request_with_retry from {caller_name}.{caller_function} is not allowed"
            logger.error(error_msg)
            raise RuntimeError(error_msg)

        # 记录事件流
        event = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "event_type": "request_start",
            "method": method,
            "endpoint": endpoint,
            "body": body,
        }
        self.event_log.append(event)

        while attempt <= self.max_retries:
            try:
                attempt += 1
                headers = self._sign_request(method, endpoint, body)

                # 发送请求
                if method == "GET":
                    response = requests.get(
                        f"{self.base_url}{endpoint}",
                        headers=headers,
                        params=body,  # GET请求使用params
                        timeout=10,  # 10秒超时
                    )
                else:
                    response = requests.request(
                        method,
                        f"{self.base_url}{endpoint}",
                        headers=headers,
                        json=body,
                        timeout=10,  # 10秒超时
                    )

                # 处理响应
                response.raise_for_status()  # 抛出HTTP错误
                result = response.json()

                # 记录成功事件
                success_event = {
                    "timestamp": datetime.utcnow().isoformat() + "Z",
                    "event_type": "request_success",
                    "method": method,
                    "endpoint": endpoint,
                    "attempt": attempt,
                    "status_code": response.status_code,
                    "result": result,
                }
                self.event_log.append(success_event)

                # 更新指标
                self.retry_metrics["successful_attempts"] += 1
                if attempt > 1:
                    self.retry_metrics["retries"] += attempt - 1
                    self.retry_metrics["retry_success"] += 1

                return result

            except (Timeout, ConnectionError) as e:
                # 网络超时或连接错误，重试
                error_type = type(e).__name__
                self._record_error(attempt, method, endpoint, error_type, str(e))

            except requests.exceptions.HTTPError as e:
                # HTTP错误处理
                status_code = e.response.status_code if hasattr(e, "response") else 0

                if status_code == 429:  # 限流错误
                    error_type = "HTTP_429_TOO_MANY_REQUESTS"
                    self._record_error(attempt, method, endpoint, error_type, str(e))
                elif 500 <= status_code < 600:  # 服务器错误
                    error_type = f"HTTP_{status_code}_SERVER_ERROR"
                    self._record_error(attempt, method, endpoint, error_type, str(e))
                else:
                    # 其他HTTP错误，不重试
                    error_type = f"HTTP_{status_code}_CLIENT_ERROR"
                    self._record_error(attempt, method, endpoint, error_type, str(e), retry=False)
                    break

            except Exception as e:
                # 其他异常，不重试
                error_type = type(e).__name__
                self._record_error(attempt, method, endpoint, error_type, str(e), retry=False)
                break

            # 检查是否需要重试
            if attempt <= self.max_retries:
                # 计算重试延迟
                logger.warning(
                    f"请求失败，将在 {retry_delay:.2f} 秒后重试 ({attempt}/{self.max_retries}): {method} {endpoint}"
                )

                # 记录重试事件
                retry_event = {
                    "timestamp": datetime.utcnow().isoformat() + "Z",
                    "event_type": "request_retry",
                    "method": method,
                    "endpoint": endpoint,
                    "attempt": attempt,
                    "retry_delay": retry_delay,
                }
                self.event_log.append(retry_event)

                time.sleep(retry_delay)

                # 更新重试延迟（指数退避）
                retry_delay = min(retry_delay * self.backoff_factor, self.max_retry_delay)

        # 所有重试都失败
        self.retry_metrics["failed_attempts"] += 1
        if attempt > 1:
            self.retry_metrics["retries"] += attempt - 1
            self.retry_metrics["retry_failure"] += 1

        # 记录最终失败事件
        final_failure_event = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "event_type": "request_final_failure",
            "method": method,
            "endpoint": endpoint,
            "attempts": attempt - 1,
            "max_retries": self.max_retries,
        }
        self.event_log.append(final_failure_event)

        # 返回失败结果
        return {"code": "1", "msg": f"请求失败，已重试 {self.max_retries} 次", "data": []}

    def _record_error(
        self,
        attempt: int,
        method: str,
        endpoint: str,
        error_type: str,
        error_msg: str,
        retry: bool = True,
    ):
        """
        记录错误信息和指标

        Args:
            attempt: 当前尝试次数
            method: HTTP方法
            endpoint: API端点
            error_type: 错误类型
            error_msg: 错误信息
            retry: 是否需要重试
        """
        # 记录错误事件
        error_event = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "event_type": "request_error",
            "method": method,
            "endpoint": endpoint,
            "attempt": attempt,
            "error_type": error_type,
            "error_msg": error_msg,
            "will_retry": retry,
        }
        self.event_log.append(error_event)

        # 更新错误类型指标
        if error_type not in self.retry_metrics["error_types"]:
            self.retry_metrics["error_types"][error_type] = 0
        self.retry_metrics["error_types"][error_type] += 1

        logger.error(
            f"请求失败 (尝试 {attempt}/{self.max_retries}): {method} {endpoint}, 错误类型: {error_type}, 错误信息: {error_msg}"
        )

    def set_leverage(self, symbol: str, leverage: int, pos_side: str = "long") -> dict[str, Any]:
        """
        设置杠杆

        Args:
            symbol: 交易对
            leverage: 杠杆倍数
            pos_side: 持仓方向

        Returns:
            result: 设置结果
        """
        # 使用新的ExchangeAdapter设置杠杆
        if hasattr(self.exchange_adapter, "set_leverage"):
            return self.exchange_adapter.set_leverage(symbol, leverage, pos_side)

        # 向后兼容：如果没有set_leverage方法，使用原有逻辑
        logger.warning("ExchangeAdapter不支持set_leverage，使用原有逻辑")
        return self._set_leverage_legacy(symbol, leverage, pos_side)

    def _set_leverage_legacy(
        self, symbol: str, leverage: int, pos_side: str = "long"
    ) -> dict[str, Any]:
        """
        设置合约杠杆

        Args:
            symbol: 交易对
            leverage: 杠杆倍数
            pos_side: 持仓方向，long 或 short

        Returns:
            result: 设置结果
        """
        logger.info(f"设置杠杆: {symbol} {leverage} 倍 {pos_side}")

        if self.exchange == "okx":
            endpoint = "/api/v5/account/set-leverage"
            body = {
                "instId": symbol,
                "lever": str(leverage),
                "mgnMode": "cross",  # 全仓模式
                "posSide": pos_side,
            }

            result = self._send_request_with_retry("POST", endpoint, body)
            logger.info(f"设置杠杆结果: {result}")
            return result

        return {}

    def _check_readiness(self) -> None:
        """
        检查执行就绪状态，若阻塞则抛出异常

        Raises:
            RuntimeError: If system is blocked
        """
        if self.readiness and self.readiness.is_blocked():
            reasons = self.readiness.get_blocked_reasons()
            error_msg = f"系统处于 BLOCKED 状态，禁止下单: {'; '.join(reasons)}"
            logger.error(error_msg)
            raise RuntimeError(error_msg)

    def _check_risk(self, symbol: str, side: str, amount: float, price: float) -> None:
        """
        检查风险，若不允许则抛出异常

        使用统一风险门禁进行风险检查

        Args:
            symbol: 交易对
            side: 买卖方向
            amount: 交易数量
            price: 交易价格

        Raises:
            RuntimeError: If risk check fails
        """
        # 使用统一风险门禁进行风险检查
        verdict = self.risk_gate.check_order(symbol=symbol, side=side, amount=amount, price=price)

        # 检查是否允许执行订单
        is_allowed = self.risk_gate.is_order_allowed(
            symbol=symbol, side=side, amount=amount, price=price
        )

        if not is_allowed:
            error_msg = f"风险检查失败，禁止下单: {'; '.join(verdict.blocked_reason)}"
            logger.error(error_msg)
            raise RuntimeError(error_msg)

    def _execute_single_order(
        self,
        symbol: str,
        side: str,
        order_type: str,
        amount: float,
        price: float | None = None,
        params: dict[str, Any] = None,
    ) -> dict[str, Any]:
        """
        执行单个订单（内部方法，不进行分拆检查）

        使用新的OrderExecutor执行订单

        Args:
            symbol: 交易对，如 ETH-USDT 或 ETH-USDT-SWAP
            side: 买卖方向，buy 或 sell
            order_type: 订单类型，market 或 limit
            amount: 交易数量
            price: 交易价格（限价单需要）
            params: 其他参数，应包含strategy_id

        Returns:
            result: 订单创建结果
        """
        # 使用新的OrderExecutor执行订单
        return self.order_executor.execute_order(
            symbol=symbol,
            side=side,
            order_type=order_type,
            amount=amount,
            price=price,
            params=params,
        )

    def place_order(
        self,
        symbol: str,
        side: str,
        order_type: str,
        amount: float,
        price: float | None = None,
        params: dict[str, Any] = None,
        verdict: RiskVerdict | None = None,
        context: ExecutionContext | None = None,
    ) -> dict[str, Any]:
        """
        下单

        Args:
            symbol: 交易对，如 ETH-USDT 或 ETH-USDT-SWAP
            side: 买卖方向，buy 或 sell
            order_type: 订单类型，market 或 limit
            amount: 交易数量
            price: 交易价格（限价单需要）
            params: 其他参数，应包含strategy_id
            verdict: 风控裁决（可选，由 runtime guard 验证）[DEPRECATED: Use context instead]
            context: 执行上下文（包含 session_id, trace_id, env, account_id, venue, strategy_id, strategy_version, risk_verdict）

        Returns:
            result: 订单创建结果

        Raises:
            RuntimeError: If system is in BLOCKED state or risk check fails
            GuardBlockedError: If runtime guard blocks the order
        """
        # Migration: Support both old verdict param and new context param
        # TODO: Remove verdict param in next major version
        if context is None and verdict is not None:
            # Legacy mode: Create context from params and verdict
            import uuid

            trace_id = f"trace_{int(time.time())}_{uuid.uuid4().hex[:8]}"
            context = ExecutionContext(
                session_id=self.session_id,
                trace_id=trace_id,
                env=self.runtime_env.get("env", "unknown"),
                account_id=params.get("account_id", "default") if params else "default",
                venue=self.exchange,
                strategy_id=params.get("strategy_id", "default") if params else "default",
                strategy_version=params.get("strategy_version", "v1.0.0") if params else "v1.0.0",
                risk_verdict=verdict,
            )
        elif context is None:
            # No context provided, create minimal context
            import uuid

            trace_id = f"trace_{int(time.time())}_{uuid.uuid4().hex[:8]}"
            context = ExecutionContext(
                session_id=self.session_id,
                trace_id=trace_id,
                env=self.runtime_env.get("env", "unknown"),
                account_id=params.get("account_id", "default") if params else "default",
                venue=self.exchange,
                strategy_id=params.get("strategy_id", "default") if params else "default",
                strategy_version=params.get("strategy_version", "v1.0.0") if params else "v1.0.0",
                risk_verdict=None,
            )

        # Runtime Guard: Validate verdict before reaching broker adapter
        # Extract context fields
        strategy_id = context.strategy_id
        strategy_version = context.strategy_version
        session_id = context.session_id
        account_id = context.account_id
        venue = context.venue

        # Create OrderIntent
        intent = OrderIntent(
            symbol=symbol,
            side=side,
            order_type=order_type,
            amount=amount,
            price=price,
            strategy_id=strategy_id,
            strategy_version=strategy_version,
            session_id=session_id,
            account_id=account_id,
            venue=venue,
        )

        # Record ORDER_SUBMIT_ATTEMPT audit event
        self._record_audit_event(
            {
                "event_type": "ORDER_SUBMIT_ATTEMPT",
                "timestamp": time.time(),
                "timestamp_ms": int(time.time() * 1000),
                "session_id": context.session_id,
                "trace_id": context.trace_id,
                "strategy_id": context.strategy_id,
                "strategy_version": context.strategy_version,
                "account_id": context.account_id,
                "venue": context.venue,
                "symbol": symbol,
                "side": side,
                "order_type": order_type,
                "amount": amount,
                "price": price,
                "verdict_id": context.get_verdict_id(),
                "decision": context.get_decision(),
                "policy_version": context.get_policy_version(),
                "result": "ATTEMPT",
                "error_code": None,
            }
        )

        # Risk Engine: Evaluate order intent if verdict is None and guard is enabled
        if (
            context.risk_verdict is None
            and self.risk_guard.enabled
            and self.risk_engine is not None
        ):
            try:
                logger.info(f"Calling risk_engine.evaluate for order: {symbol} {side} {amount}")
                evaluate_start_time = time.time()
                evaluate_result = self.risk_engine.evaluate(intent, context)
                evaluate_latency_ms = int((time.time() - evaluate_start_time) * 1000)

                # Update context with verdict
                context.risk_verdict = evaluate_result.verdict

                # Record RISK_EVALUATED audit event
                self._record_audit_event(
                    {
                        "event_type": "RISK_EVALUATED",
                        "timestamp": time.time(),
                        "timestamp_ms": int(time.time() * 1000),
                        "trace_id": context.trace_id,
                        "session_id": context.session_id,
                        "intent_hash": evaluate_result.verdict.intent_hash,
                        "verdict_id": evaluate_result.verdict.verdict_id,
                        "decision": evaluate_result.verdict.decision,
                        "policy_version": evaluate_result.verdict.policy_version,
                        "result": "SUCCESS",
                        "error_code": None,
                        "latency_ms": evaluate_latency_ms,
                    }
                )

                logger.info(
                    f"risk_engine.evaluate returned: {evaluate_result.verdict.decision}, verdict_id: {evaluate_result.verdict.verdict_id}"
                )
            except Exception as e:
                # Fail-closed: Convert exception to DENY decision
                logger.error(f"risk_engine.evaluate failed: {e}, fail-closed with DENY decision")

                # Record RISK_EVALUATED audit event (failure)
                self._record_audit_event(
                    {
                        "event_type": "RISK_EVALUATED",
                        "timestamp": time.time(),
                        "timestamp_ms": int(time.time() * 1000),
                        "trace_id": context.trace_id,
                        "session_id": context.session_id,
                        "intent_hash": self.risk_guard.calculate_intent_hash(intent),
                        "verdict_id": "N/A",
                        "decision": "DENY",
                        "policy_version": self.risk_engine.get_policy_version()
                        if self.risk_engine
                        else "N/A",
                        "result": "FAILURE",
                        "error_code": "EVAL_ERROR",
                        "latency_ms": 0,
                    }
                )

                # Record ORDER_SUBMIT_BLOCKED audit event
                self._record_audit_event(
                    {
                        "event_type": "ORDER_SUBMIT_BLOCKED",
                        "timestamp": time.time(),
                        "timestamp_ms": int(time.time() * 1000),
                        "trace_id": context.trace_id,
                        "session_id": context.session_id,
                        "strategy_id": context.strategy_id,
                        "strategy_version": context.strategy_version,
                        "account_id": context.account_id,
                        "venue": context.venue,
                        "intent_hash": self.risk_guard.calculate_intent_hash(intent),
                        "verdict_id": "N/A",
                        "decision": "DENY",
                        "reason_code": "EVAL_ERROR",
                        "result": "BLOCKED",
                        "error_code": "EVAL_ERROR",
                        "latency_ms": 0,
                    }
                )

                # Raise GuardBlockedError to prevent order execution
                raise GuardBlockedError(f"Risk engine evaluation failed: {e}")

        # Require valid verdict (raises GuardBlockedError if validation fails)
        self.risk_guard.require_verdict(context.risk_verdict, intent)

        # 检查执行就绪状态
        self._check_readiness()

        # 检查黑天鹅模式
        if self.black_swan_manager.is_reduce_only() or self.black_swan_manager.is_liquidate():
            # 黑天鹅模式：只允许卖出操作（减仓或清仓）
            if side != "sell":
                error_msg = f"黑天鹅模式 ({self.black_swan_manager.get_current_status_value()}) 下不允许买入操作"
                logger.error(error_msg)
                raise RuntimeError(error_msg)
            logger.warning(
                f"黑天鹅模式 ({self.black_swan_manager.get_current_status_value()}) 下执行卖出操作"
            )

        # 初始化params
        params = params or {}

        # 真单开关检查
        if self.real_order_switch:
            # 检查风险
            self._check_risk(symbol, side, amount, price or 0.0)

            # 真单限制检查
            self._check_real_order_limits(symbol, side, amount, price or 0.0)

            # 执行单个订单
            order_result = self._execute_single_order(
                symbol, side, order_type, amount, price, params
            )

            # 如果订单成功，挂止损单
            if order_result.get("code") == "0" and self.stop_loss_config["enabled"]:
                # 计算止损价格
                stop_loss_price = self._calculate_stop_loss_price(side, price or 0.0)

                # 挂止损单
                stop_loss_order = self._place_stop_loss_order(
                    symbol, side, amount, stop_loss_price, order_result
                )

                # 生成live_order_report
                self._generate_live_order_report(order_result, stop_loss_order)
            else:
                # 生成live_order_report（仅主订单）
                self._generate_live_order_report(order_result)

            return order_result
        else:
            # 非真单模式，使用原有逻辑
            # 检查风险
            self._check_risk(symbol, side, amount, price or 0.0)

            # 检查是否需要分拆订单（如果订单数量超过最大单笔订单数量）
            if amount > self.order_splitter.config.max_single_order_amount:
                logger.info(
                    f"订单数量 {amount} 超过最大单笔订单数量 {self.order_splitter.config.max_single_order_amount}，开始分拆"
                )

                # 使用订单分拆管理器执行分拆订单（使用新的order_executor）
                split_result = self.order_splitter.split_and_execute(
                    self.order_executor, symbol, side, order_type, amount, price, params
                )

                # 返回分拆结果的汇总信息
                return {
                    "code": "0" if split_result.status == "success" else "1",
                    "msg": f"Order split and executed, status: {split_result.status}",
                    "data": [
                        {
                            "original_order_id": split_result.original_order_id,
                            "status": split_result.status,
                            "split_count": len(split_result.split_orders),
                            "failed_count": sum(
                                1
                                for order in split_result.split_orders
                                if order["status"] == "failed"
                            ),
                        }
                    ],
                }

            # 直接执行单个订单
            return self._execute_single_order(symbol, side, order_type, amount, price, params)

    def cancel_order(
        self,
        symbol: str,
        order_id: str,
        verdict: RiskVerdict | None = None,
        context: ExecutionContext | None = None,
    ) -> dict[str, Any]:
        """
        撤单

        Args:
            symbol: 交易对
            order_id: 订单ID
            verdict: 风控裁决（可选，由 runtime guard 验证）[DEPRECATED: Use context instead]
            context: 执行上下文（包含 session_id, trace_id, env, account_id, venue, strategy_id, strategy_version, risk_verdict）

        Returns:
            result: 撤单结果

        Raises:
            GuardBlockedError: If runtime guard blocks cancel
        """
        # Migration: Support both old verdict param and new context param
        # TODO: Remove verdict param in next major version
        if context is None and verdict is not None:
            import uuid

            trace_id = f"trace_{int(time.time())}_{uuid.uuid4().hex[:8]}"
            context = ExecutionContext(
                session_id=self.session_id,
                trace_id=trace_id,
                env=self.runtime_env.get("env", "unknown"),
                account_id="default",
                venue=self.exchange,
                strategy_id="default",
                strategy_version="v1.0.0",
                risk_verdict=verdict,
            )
        elif context is None:
            import uuid

            trace_id = f"trace_{int(time.time())}_{uuid.uuid4().hex[:8]}"
            context = ExecutionContext(
                session_id=self.session_id,
                trace_id=trace_id,
                env=self.runtime_env.get("env", "unknown"),
                account_id="default",
                venue=self.exchange,
                strategy_id="default",
                strategy_version="v1.0.0",
                risk_verdict=None,
            )

        # Runtime Guard: Validate verdict for cancel operation
        intent = OrderIntent(
            symbol=symbol,
            side="cancel",
            order_type="cancel",
            amount=0.0,
            price=None,
            strategy_id="default",
            strategy_version="v1.0.0",
            session_id=context.session_id,
            account_id=context.account_id,
            venue=context.venue,
        )

        # Record ORDER_CANCEL_ATTEMPT audit event
        self._record_audit_event(
            {
                "event_type": "ORDER_CANCEL_ATTEMPT",
                "timestamp": time.time(),
                "timestamp_ms": int(time.time() * 1000),
                "session_id": context.session_id,
                "trace_id": context.trace_id,
                "strategy_id": context.strategy_id,
                "strategy_version": context.strategy_version,
                "account_id": context.account_id,
                "venue": context.venue,
                "symbol": symbol,
                "order_id": order_id,
                "verdict_id": context.get_verdict_id(),
                "decision": context.get_decision(),
                "policy_version": context.get_policy_version(),
                "result": "ATTEMPT",
                "error_code": None,
            }
        )

        # Risk Engine: Evaluate cancel intent if verdict is None and guard is enabled
        if (
            context.risk_verdict is None
            and self.risk_guard.enabled
            and self.risk_engine is not None
        ):
            try:
                logger.info(f"Calling risk_engine.evaluate for cancel: {symbol} {order_id}")
                evaluate_start_time = time.time()
                evaluate_result = self.risk_engine.evaluate(intent, context)
                evaluate_latency_ms = int((time.time() - evaluate_start_time) * 1000)

                # Update context with verdict
                context.risk_verdict = evaluate_result.verdict

                # Record RISK_EVALUATED audit event
                self._record_audit_event(
                    {
                        "event_type": "RISK_EVALUATED",
                        "timestamp": time.time(),
                        "timestamp_ms": int(time.time() * 1000),
                        "trace_id": context.trace_id,
                        "session_id": context.session_id,
                        "intent_hash": evaluate_result.verdict.intent_hash,
                        "verdict_id": evaluate_result.verdict.verdict_id,
                        "decision": evaluate_result.verdict.decision,
                        "policy_version": evaluate_result.verdict.policy_version,
                        "result": "SUCCESS",
                        "error_code": None,
                        "latency_ms": evaluate_latency_ms,
                    }
                )

                logger.info(
                    f"risk_engine.evaluate returned: {evaluate_result.verdict.decision}, verdict_id: {evaluate_result.verdict.verdict_id}"
                )
            except Exception as e:
                # Fail-closed: Convert exception to DENY decision
                logger.error(f"risk_engine.evaluate failed: {e}, fail-closed with DENY decision")

                # Record RISK_EVALUATED audit event (failure)
                self._record_audit_event(
                    {
                        "event_type": "RISK_EVALUATED",
                        "timestamp": time.time(),
                        "timestamp_ms": int(time.time() * 1000),
                        "trace_id": context.trace_id,
                        "session_id": context.session_id,
                        "intent_hash": self.risk_guard.calculate_intent_hash(intent),
                        "verdict_id": "N/A",
                        "decision": "DENY",
                        "policy_version": self.risk_engine.get_policy_version()
                        if self.risk_engine
                        else "N/A",
                        "result": "FAILURE",
                        "error_code": "EVAL_ERROR",
                        "latency_ms": 0,
                    }
                )

                # Record ORDER_CANCEL_BLOCKED audit event
                self._record_audit_event(
                    {
                        "event_type": "ORDER_CANCEL_BLOCKED",
                        "timestamp": time.time(),
                        "timestamp_ms": int(time.time() * 1000),
                        "trace_id": context.trace_id,
                        "session_id": context.session_id,
                        "strategy_id": context.strategy_id,
                        "strategy_version": context.strategy_version,
                        "account_id": context.account_id,
                        "venue": context.venue,
                        "intent_hash": self.risk_guard.calculate_intent_hash(intent),
                        "verdict_id": "N/A",
                        "decision": "DENY",
                        "reason_code": "EVAL_ERROR",
                        "result": "BLOCKED",
                        "error_code": "EVAL_ERROR",
                        "latency_ms": 0,
                    }
                )

                # Raise GuardBlockedError to prevent cancel execution
                raise GuardBlockedError(f"Risk engine evaluation failed: {e}")

        self.risk_guard.require_verdict(context.risk_verdict, intent)

        logger.info(f"撤单: {symbol} {order_id}")

        # 使用新的OrderExecutor撤单
        return self.order_executor.cancel_order(symbol, order_id)

    def cancel_all_orders(
        self,
        symbol: str,
        verdict: RiskVerdict | None = None,
        context: ExecutionContext | None = None,
    ) -> dict[str, Any]:
        """
        撤销所有订单

        Args:
            symbol: 交易对
            verdict: 风控裁决（可选，由 runtime guard 验证）[DEPRECATED: Use context instead]
            context: 执行上下文（包含 session_id, trace_id, env, account_id, venue, strategy_id, strategy_version, risk_verdict）

        Returns:
            result: 撤销结果

        Raises:
            GuardBlockedError: If runtime guard blocks operation
        """
        # Migration: Support both old verdict param and new context param
        # TODO: Remove verdict param in next major version
        if context is None and verdict is not None:
            import uuid

            trace_id = f"trace_{int(time.time())}_{uuid.uuid4().hex[:8]}"
            context = ExecutionContext(
                session_id=self.session_id,
                trace_id=trace_id,
                env=self.runtime_env.get("env", "unknown"),
                account_id="default",
                venue=self.exchange,
                strategy_id="default",
                strategy_version="v1.0.0",
                risk_verdict=verdict,
            )
        elif context is None:
            import uuid

            trace_id = f"trace_{int(time.time())}_{uuid.uuid4().hex[:8]}"
            context = ExecutionContext(
                session_id=self.session_id,
                trace_id=trace_id,
                env=self.runtime_env.get("env", "unknown"),
                account_id="default",
                venue=self.exchange,
                strategy_id="default",
                strategy_version="v1.0.0",
                risk_verdict=None,
            )

        # Runtime Guard: Validate verdict for batch cancel operation
        intent = OrderIntent(
            symbol=symbol,
            side="cancel_all",
            order_type="batch_cancel",
            amount=0.0,
            price=None,
            strategy_id="default",
            strategy_version="v1.0.0",
            session_id=context.session_id,
            account_id=context.account_id,
            venue=context.venue,
        )

        # Record ORDER_CANCEL_ALL_ATTEMPT audit event
        self._record_audit_event(
            {
                "event_type": "ORDER_CANCEL_ALL_ATTEMPT",
                "timestamp": time.time(),
                "timestamp_ms": int(time.time() * 1000),
                "session_id": context.session_id,
                "trace_id": context.trace_id,
                "strategy_id": context.strategy_id,
                "strategy_version": context.strategy_version,
                "account_id": context.account_id,
                "venue": context.venue,
                "symbol": symbol,
                "verdict_id": context.get_verdict_id(),
                "decision": context.get_decision(),
                "policy_version": context.get_policy_version(),
                "result": "ATTEMPT",
                "error_code": None,
            }
        )

        # Risk Engine: Evaluate cancel_all intent if verdict is None and guard is enabled
        if (
            context.risk_verdict is None
            and self.risk_guard.enabled
            and self.risk_engine is not None
        ):
            try:
                logger.info(f"Calling risk_engine.evaluate for cancel_all: {symbol}")
                evaluate_start_time = time.time()
                evaluate_result = self.risk_engine.evaluate(intent, context)
                evaluate_latency_ms = int((time.time() - evaluate_start_time) * 1000)

                # Update context with verdict
                context.risk_verdict = evaluate_result.verdict

                # Record RISK_EVALUATED audit event
                self._record_audit_event(
                    {
                        "event_type": "RISK_EVALUATED",
                        "timestamp": time.time(),
                        "timestamp_ms": int(time.time() * 1000),
                        "trace_id": context.trace_id,
                        "session_id": context.session_id,
                        "intent_hash": evaluate_result.verdict.intent_hash,
                        "verdict_id": evaluate_result.verdict.verdict_id,
                        "decision": evaluate_result.verdict.decision,
                        "policy_version": evaluate_result.verdict.policy_version,
                        "result": "SUCCESS",
                        "error_code": None,
                        "latency_ms": evaluate_latency_ms,
                    }
                )

                logger.info(
                    f"risk_engine.evaluate returned: {evaluate_result.verdict.decision}, verdict_id: {evaluate_result.verdict.verdict_id}"
                )
            except Exception as e:
                # Fail-closed: Convert exception to DENY decision
                logger.error(f"risk_engine.evaluate failed: {e}, fail-closed with DENY decision")

                # Record RISK_EVALUATED audit event (failure)
                self._record_audit_event(
                    {
                        "event_type": "RISK_EVALUATED",
                        "timestamp": time.time(),
                        "timestamp_ms": int(time.time() * 1000),
                        "trace_id": context.trace_id,
                        "session_id": context.session_id,
                        "intent_hash": self.risk_guard.calculate_intent_hash(intent),
                        "verdict_id": "N/A",
                        "decision": "DENY",
                        "policy_version": self.risk_engine.get_policy_version()
                        if self.risk_engine
                        else "N/A",
                        "result": "FAILURE",
                        "error_code": "EVAL_ERROR",
                        "latency_ms": 0,
                    }
                )

                # Record ORDER_CANCEL_ALL_BLOCKED audit event
                self._record_audit_event(
                    {
                        "event_type": "ORDER_CANCEL_ALL_BLOCKED",
                        "timestamp": time.time(),
                        "timestamp_ms": int(time.time() * 1000),
                        "trace_id": context.trace_id,
                        "session_id": context.session_id,
                        "strategy_id": context.strategy_id,
                        "strategy_version": context.strategy_version,
                        "account_id": context.account_id,
                        "venue": context.venue,
                        "intent_hash": self.risk_guard.calculate_intent_hash(intent),
                        "verdict_id": "N/A",
                        "decision": "DENY",
                        "reason_code": "EVAL_ERROR",
                        "result": "BLOCKED",
                        "error_code": "EVAL_ERROR",
                        "latency_ms": 0,
                    }
                )

                # Raise GuardBlockedError to prevent cancel_all execution
                raise GuardBlockedError(f"Risk engine evaluation failed: {e}")

        self.risk_guard.require_verdict(context.risk_verdict, intent)

        logger.info(f"撤销所有订单: {symbol}")

        if self.exchange == "okx":
            endpoint = "/api/v5/trade/cancel-batch-orders"
            body = {"instId": symbol}

            # 根据交易模式决定是否发送真实请求
            if self.trading_mode == "live":
                # LIVE模式：发送真实API请求
                result = self._send_request_with_retry("POST", endpoint, body)
            else:
                # DRY_RUN或PAPER模式：模拟撤销所有订单结果
                logger.info(f"{self.trading_mode}模式：模拟撤销所有订单，不发送真实API请求")
                # 获取所有未完成订单并模拟撤销结果
                order_ledger = self.order_id_manager.get_order_ledger()
                mock_results = []
                for order in order_ledger:
                    if order["symbol"] == symbol and order["status"] in ["OPEN", "PARTIAL"]:
                        mock_results.append(
                            {
                                "ordId": order.get(
                                    "exchange_order_id", f"mock_{order['clientOrderId'][:16]}"
                                ),
                                "clOrdId": order["clientOrderId"],
                                "sCode": "0",
                                "sMsg": "Cancel request processed",
                            }
                        )
                result = {
                    "code": "0",
                    "msg": f"{self.trading_mode} mode cancel all accepted",
                    "data": mock_results,
                }

            logger.info(f"撤销所有订单结果: {result}")

            # 更新本地订单状态
            if result.get("code") == "0" and result.get("data"):
                for data_item in result["data"]:
                    client_order_id = data_item.get("clOrdId", "")
                    if client_order_id:
                        # 更新订单状态为CANCELED
                        self.order_id_manager.update_order_status(
                            client_order_id, "CANCELED", data_item.get("ordId")
                        )

            return result

        return {}

    def get_order(self, symbol: str, order_id: str) -> dict[str, Any]:
        """
        查询订单状态

        Args:
            symbol: 交易对
            order_id: 订单ID

        Returns:
            result: 订单状态
        """
        logger.info(f"查询订单: {symbol} {order_id}")

        if self.exchange == "okx":
            endpoint = "/api/v5/trade/order"
            params = {"instId": symbol, "ordId": order_id}

            # 根据交易模式决定是否发送真实请求
            if self.trading_mode == "live":
                # LIVE模式：发送真实API请求
                result = self._send_request_with_retry("GET", endpoint, params)
            else:
                # DRY_RUN或PAPER模式：模拟查询订单结果
                logger.info(f"{self.trading_mode}模式：模拟查询订单，不发送真实API请求")
                result = {
                    "code": "0",
                    "msg": f"{self.trading_mode} mode order status",
                    "data": [
                        {
                            "ordId": order_id,
                            "clOrdId": order_id.replace("mock_", ""),
                            "instId": symbol,
                            "state": "filled" if self.trading_mode == "paper" else "pending",
                            "side": "buy",
                            "ordType": "market",
                            "sz": "1",
                            "px": "0",
                            "accFillSz": "1" if self.trading_mode == "paper" else "0",
                            "fillPx": "10000" if self.trading_mode == "paper" else "0",
                        }
                    ],
                }

            logger.info(f"订单状态: {result}")

            # 更新本地订单状态
            if result.get("code") == "0" and result.get("data"):
                order_data = result["data"][0]
                client_order_id = order_data.get("clOrdId", "")

                # 如果有client_order_id，更新本地订单状态
                if client_order_id:
                    # 映射OKX订单状态到本地订单状态
                    status_map = {
                        "pending": "SENT",
                        "live": "OPEN",
                        "partially_filled": "PARTIAL",
                        "filled": "FILLED",
                        "canceled": "CANCELED",
                        "rejected": "REJECTED",
                    }

                    # 获取交易所返回的状态
                    exchange_status = order_data.get("state", "pending")
                    # 映射到本地状态
                    local_status = status_map.get(exchange_status, "SENT")

                    # 获取成交信息
                    acc_fill_sz = float(order_data.get("accFillSz", "0"))
                    fill_px = float(order_data.get("fillPx", "0"))
                    total_sz = float(order_data.get("sz", "0"))

                    # 更新订单状态
                    self.order_id_manager.update_order_status(
                        client_order_id, local_status, order_id
                    )

                    # 更新成交信息
                    self.order_id_manager.update_order_fill(client_order_id, acc_fill_sz, fill_px)

            return result

        return {}

    def get_open_orders(self, symbol: str) -> dict[str, Any]:
        """
        查询所有未成交订单

        Args:
            symbol: 交易对

        Returns:
            result: 未成交订单列表
        """
        logger.info(f"查询未成交订单: {symbol}")

        if self.exchange == "okx":
            endpoint = "/api/v5/trade/orders-pending"
            params = {"instId": symbol}

            # 根据交易模式决定是否发送真实请求
            if self.trading_mode == "live":
                # LIVE模式：发送真实API请求
                result = self._send_request_with_retry("GET", endpoint, params)
            else:
                # DRY_RUN或PAPER模式：模拟未成交订单结果
                logger.info(f"{self.trading_mode}模式：模拟未成交订单，不发送真实API请求")
                result = {
                    "code": "0",
                    "msg": f"{self.trading_mode} mode open orders",
                    "data": [],  # PAPER模式下订单通常立即成交，所以返回空列表
                }

            logger.info(f"未成交订单: {result}")
            return result

        return {}

    def modify_order(
        self,
        symbol: str,
        order_id: str,
        new_price: float,
        new_amount: float | None = None,
        verdict: RiskVerdict | None = None,
        context: ExecutionContext | None = None,
    ) -> dict[str, Any]:
        """
        改价/重挂订单：取消现有订单并创建新订单

        Args:
            symbol: 交易对
            order_id: 原订单ID
            new_price: 新价格
            new_amount: 新数量（可选，默认使用原订单数量）
            verdict: 风控裁决（可选，由 runtime guard 验证）[DEPRECATED: Use context instead]
            context: 执行上下文（包含 session_id, trace_id, env, account_id, venue, strategy_id, strategy_version, risk_verdict）

        Returns:
            result: 包含撤单结果和新订单结果的字典

        Raises:
            GuardBlockedError: If runtime guard blocks operation
        """
        # Migration: Support both old verdict param and new context param
        # TODO: Remove verdict param in next major version
        if context is None and verdict is not None:
            import uuid

            trace_id = f"trace_{int(time.time())}_{uuid.uuid4().hex[:8]}"
            context = ExecutionContext(
                session_id=self.session_id,
                trace_id=trace_id,
                env=self.runtime_env.get("env", "unknown"),
                account_id="default",
                venue=self.exchange,
                strategy_id="default",
                strategy_version="v1.0.0",
                risk_verdict=verdict,
            )
        elif context is None:
            import uuid

            trace_id = f"trace_{int(time.time())}_{uuid.uuid4().hex[:8]}"
            context = ExecutionContext(
                session_id=self.session_id,
                trace_id=trace_id,
                env=self.runtime_env.get("env", "unknown"),
                account_id="default",
                venue=self.exchange,
                strategy_id="default",
                strategy_version="v1.0.0",
                risk_verdict=None,
            )

        # Runtime Guard: Validate verdict for modify operation
        intent = OrderIntent(
            symbol=symbol,
            side="modify",
            order_type="modify",
            amount=new_amount or 0.0,
            price=new_price,
            strategy_id="default",
            strategy_version="v1.0.0",
            session_id=context.session_id,
            account_id=context.account_id,
            venue=context.venue,
        )

        # Record ORDER_MODIFY_ATTEMPT audit event
        self._record_audit_event(
            {
                "event_type": "ORDER_MODIFY_ATTEMPT",
                "timestamp": time.time(),
                "timestamp_ms": int(time.time() * 1000),
                "session_id": context.session_id,
                "trace_id": context.trace_id,
                "strategy_id": context.strategy_id,
                "strategy_version": context.strategy_version,
                "account_id": context.account_id,
                "venue": context.venue,
                "symbol": symbol,
                "order_id": order_id,
                "new_price": new_price,
                "new_amount": new_amount,
                "verdict_id": context.get_verdict_id(),
                "decision": context.get_decision(),
                "policy_version": context.get_policy_version(),
                "result": "ATTEMPT",
                "error_code": None,
            }
        )

        # Risk Engine: Evaluate modify intent if verdict is None and guard is enabled
        if (
            context.risk_verdict is None
            and self.risk_guard.enabled
            and self.risk_engine is not None
        ):
            try:
                logger.info(f"Calling risk_engine.evaluate for modify: {symbol} {order_id}")
                evaluate_start_time = time.time()
                evaluate_result = self.risk_engine.evaluate(intent, context)
                evaluate_latency_ms = int((time.time() - evaluate_start_time) * 1000)

                # Update context with verdict
                context.risk_verdict = evaluate_result.verdict

                # Record RISK_EVALUATED audit event
                self._record_audit_event(
                    {
                        "event_type": "RISK_EVALUATED",
                        "timestamp": time.time(),
                        "timestamp_ms": int(time.time() * 1000),
                        "trace_id": context.trace_id,
                        "session_id": context.session_id,
                        "intent_hash": evaluate_result.verdict.intent_hash,
                        "verdict_id": evaluate_result.verdict.verdict_id,
                        "decision": evaluate_result.verdict.decision,
                        "policy_version": evaluate_result.verdict.policy_version,
                        "result": "SUCCESS",
                        "error_code": None,
                        "latency_ms": evaluate_latency_ms,
                    }
                )

                logger.info(
                    f"risk_engine.evaluate returned: {evaluate_result.verdict.decision}, verdict_id: {evaluate_result.verdict.verdict_id}"
                )
            except Exception as e:
                # Fail-closed: Convert exception to DENY decision
                logger.error(f"risk_engine.evaluate failed: {e}, fail-closed with DENY decision")

                # Record RISK_EVALUATED audit event (failure)
                self._record_audit_event(
                    {
                        "event_type": "RISK_EVALUATED",
                        "timestamp": time.time(),
                        "timestamp_ms": int(time.time() * 1000),
                        "trace_id": context.trace_id,
                        "session_id": context.session_id,
                        "intent_hash": self.risk_guard.calculate_intent_hash(intent),
                        "verdict_id": "N/A",
                        "decision": "DENY",
                        "policy_version": self.risk_engine.get_policy_version()
                        if self.risk_engine
                        else "N/A",
                        "result": "FAILURE",
                        "error_code": "EVAL_ERROR",
                        "latency_ms": 0,
                    }
                )

                # Record ORDER_MODIFY_BLOCKED audit event
                self._record_audit_event(
                    {
                        "event_type": "ORDER_MODIFY_BLOCKED",
                        "timestamp": time.time(),
                        "timestamp_ms": int(time.time() * 1000),
                        "trace_id": context.trace_id,
                        "session_id": context.session_id,
                        "strategy_id": context.strategy_id,
                        "strategy_version": context.strategy_version,
                        "account_id": context.account_id,
                        "venue": context.venue,
                        "intent_hash": self.risk_guard.calculate_intent_hash(intent),
                        "verdict_id": "N/A",
                        "decision": "DENY",
                        "reason_code": "EVAL_ERROR",
                        "result": "BLOCKED",
                        "error_code": "EVAL_ERROR",
                        "latency_ms": 0,
                    }
                )

                # Raise GuardBlockedError to prevent modify execution
                raise GuardBlockedError(f"Risk engine evaluation failed: {e}")

        self.risk_guard.require_verdict(context.risk_verdict, intent)

        logger.info(f"改价/重挂订单: {symbol} {order_id} -> 新价格: {new_price}")

        # 1. 获取原订单信息
        original_order = None
        order_ledger = self.order_id_manager.get_order_ledger()
        for order in order_ledger:
            if order["exchange_order_id"] == order_id or order["clientOrderId"] == order_id:
                original_order = order
                break

        if not original_order:
            logger.error(f"原订单不存在: {order_id}")
            return {
                "code": "1",
                "msg": f"Original order not found: {order_id}",
                "cancel_result": None,
                "new_order_result": None,
            }

        # 2. 取消原订单
        cancel_result = self.cancel_order(symbol, order_id)

        # 3. 创建新订单（使用新价格）
        if cancel_result.get("code") == "0":
            # 使用原订单的其他参数，只修改价格
            new_amount = new_amount or original_order["amount"]

            # 获取策略ID
            strategy_id = (
                original_order.get("clientOrderId", "").split("-")[0]
                if "-" in original_order.get("clientOrderId", "")
                else "default"
            )

            # 发送新订单
            new_order_result = self.place_order(
                symbol=symbol,
                side=original_order["side"],
                order_type=original_order["order_type"],
                amount=new_amount,
                price=new_price,
                params={"strategy_id": strategy_id},
            )

            # 从结果中获取新订单ID
            new_client_order_id = None
            if new_order_result.get("code") == "0" and new_order_result.get("data"):
                new_client_order_id = new_order_result["data"][0].get("clOrdId")

            logger.info(
                f"改价/重挂成功: 取消原订单 {order_id}，创建新订单 {new_client_order_id} 价格: {new_price}"
            )

            return {
                "code": "0",
                "msg": "Order modified successfully",
                "cancel_result": cancel_result,
                "new_order_result": new_order_result,
                "new_client_order_id": new_client_order_id,
            }
        else:
            logger.error(f"取消原订单失败，无法完成改价/重挂: {cancel_result}")
            return {
                "code": "1",
                "msg": "Failed to cancel original order",
                "cancel_result": cancel_result,
                "new_order_result": None,
            }

    def get_positions(self, symbol: str = None) -> dict[str, Any]:
        """
        查询持仓

        Args:
            symbol: 交易对（可选）

        Returns:
            result: 持仓信息
        """
        logger.info(f"查询持仓: {symbol}")

        # 使用新的ExchangeAdapter查询持仓
        return self.exchange_adapter.get_positions(symbol)

    def get_balance(self) -> dict[str, Any]:
        """
        查询账户余额

        Returns:
            result: 账户余额信息
        """
        logger.info("查询账户余额")

        # 使用新的ExchangeAdapter查询余额
        return self.exchange_adapter.get_balance()

    def place_market_order(
        self, symbol: str, side: str, amount: float, params: dict[str, Any] = None
    ) -> dict[str, Any]:
        """
        下市价单

        Args:
            symbol: 交易对
            side: 买卖方向
            amount: 交易数量
            params: 其他参数，应包含strategy_id

        Returns:
            result: 订单创建结果
        """
        return self.place_order(symbol, side, "market", amount, None, params)

    def place_limit_order(
        self, symbol: str, side: str, amount: float, price: float, params: dict[str, Any] = None
    ) -> dict[str, Any]:
        """
        下限价单

        Args:
            symbol: 交易对
            side: 买卖方向
            amount: 交易数量
            price: 交易价格
            params: 其他参数，应包含strategy_id

        Returns:
            result: 订单创建结果
        """
        return self.place_order(symbol, side, "limit", amount, price, params)

    def reconcile(
        self,
        local_state: dict[str, Any],
        symbol_map: dict[str, str],
        now_ts: int,
        config: dict[str, Any],
    ) -> ReconciliationReport:
        """
        执行交易所与本地状态的对账

        Args:
            local_state: 本地状态字典，包含balance、positions、orders和fills
            symbol_map: 本地符号到交易所符号的映射
            now_ts: 当前时间戳（毫秒）
            config: 对账配置

        Returns:
            ReconciliationReport: 对账结果报告
        """
        logger.info("执行交易所与本地状态对账")

        # 直接调用reconcile函数，使用当前实例作为exchange_client
        return reconcile(self, local_state, symbol_map, now_ts, config)

    def get_retry_metrics(self) -> dict[str, Any]:
        """
        获取重试指标

        Returns:
            retry_metrics: 重试指标字典
        """
        return self.retry_metrics

    def fetch_balance(self) -> dict[str, Any]:
        """
        获取账户余额（为了兼容reconcile函数）

        Returns:
            balance: 账户余额信息
        """
        return self.get_balance()

    def fetch_positions(self) -> list[dict[str, Any]]:
        """
        获取持仓信息（为了兼容reconcile函数）

        Returns:
            positions: 持仓信息列表
        """
        return self.get_positions()

    def fetch_open_orders(self) -> list[dict[str, Any]]:
        """
        获取未成交订单（为了兼容reconcile函数）

        Returns:
            orders: 未成交订单列表
        """
        return self.get_open_orders("") if callable(getattr(self, "get_open_orders", None)) else []

    def fetch_my_trades(self) -> list[dict[str, Any]]:
        """
        获取成交记录（为了兼容reconcile函数）

        Returns:
            trades: 成交记录列表
        """
        # 简化实现，返回空列表
        return []

    def _check_real_order_limits(self, symbol: str, side: str, amount: float, price: float) -> None:
        """
        检查真单限制条件（OrderGate）

        Args:
            symbol: 交易对
            side: 买卖方向
            amount: 交易数量
            price: 交易价格

        Raises:
            RuntimeError: If any limit is exceeded
        """
        logger.info("执行OrderGate检查...")

        # 计算订单价值
        order_value = amount * price

        # 收集阻塞问题
        blocking_issues = {"timestamp": datetime.now().isoformat(), "issues": []}

        # 1. 单笔订单最大名义价值检查（≤3.3u）
        if order_value > self.real_order_limits["single_order_max_usdt"]:
            blocking_issues["issues"].append(
                {
                    "category": "ORDER_GATE",
                    "code": "ORDER_GATE_001",
                    "message": f"单笔订单价值 {order_value}u 超出限制 {self.real_order_limits['single_order_max_usdt']}u",
                    "evidence_paths": [
                        "configs/live_config.json",
                        "taskhub/index/live_config.json",
                        "logs/order_execution.log",
                    ],
                }
            )

        # 2. 总预算检查（≤10u）
        if (
            self.real_order_status["total_usdt_used"] + order_value
            > self.real_order_limits["total_budget_max_usdt"]
        ):
            blocking_issues["issues"].append(
                {
                    "category": "ORDER_GATE",
                    "code": "ORDER_GATE_002",
                    "message": f"总预算超出限制，当前已使用 {self.real_order_status['total_usdt_used']}u，本次订单 {order_value}u，总预算 {self.real_order_limits['total_budget_max_usdt']}u",
                    "evidence_paths": [
                        "configs/live_config.json",
                        "taskhub/index/live_config.json",
                        "logs/order_execution.log",
                    ],
                }
            )

        # 3. 最多1仓检查（买开时检查）
        if (
            side == "buy"
            and self.real_order_status["current_positions"]
            >= self.real_order_limits["max_positions"]
        ):
            blocking_issues["issues"].append(
                {
                    "category": "ORDER_GATE",
                    "code": "ORDER_GATE_003",
                    "message": f"当前已有 {self.real_order_status['current_positions']} 个仓位，超出最大允许 {self.real_order_limits['max_positions']} 个仓位",
                    "evidence_paths": [
                        "configs/live_config.json",
                        "taskhub/index/live_config.json",
                        "logs/order_execution.log",
                    ],
                }
            )

        # 4. 止损存在检查
        if not self.stop_loss_config["enabled"]:
            blocking_issues["issues"].append(
                {
                    "category": "ORDER_GATE",
                    "code": "ORDER_GATE_004",
                    "message": "止损未开启，禁止下单",
                    "evidence_paths": [
                        "configs/live_config.json",
                        "taskhub/index/live_config.json",
                        "logs/order_execution.log",
                    ],
                }
            )

        # 如果有阻塞问题，写入文件并抛出异常
        if blocking_issues["issues"]:
            # 写入blocking_issues.json
            self._write_blocking_issues(blocking_issues)

            # 生成错误信息
            error_msg = "OrderGate检查失败："
            for issue in blocking_issues["issues"]:
                error_msg += f"[{issue['code']}] {issue['message']}; "

            logger.error(error_msg)
            raise RuntimeError(error_msg)

        logger.info("OrderGate检查通过")

    def _calculate_stop_loss_price(self, side: str, entry_price: float) -> float:
        """
        计算止损价格

        Args:
            side: 买卖方向
            entry_price: 入场价格

        Returns:
            float: 止损价格
        """
        if side == "buy":
            # 买单止损：低于入场价格
            stop_loss_price = entry_price * (1 - self.stop_loss_config["stop_loss_ratio"])
        else:
            # 卖单止损：高于入场价格
            stop_loss_price = entry_price * (1 + self.stop_loss_config["stop_loss_ratio"])

        logger.info(
            f"计算止损价格：入场价格 {entry_price}，止损比例 {self.stop_loss_config['stop_loss_ratio']}，止损价格 {stop_loss_price}"
        )
        return stop_loss_price

    def _write_blocking_issues(self, blocking_issues: dict) -> None:
        """
        写入阻塞问题到文件

        Args:
            blocking_issues: 包含阻塞问题的字典
        """
        import os

        # 写入到data目录
        data_dir = os.path.join(self.config.get("system", {}).get("data_dir", "data"))
        blocking_path = os.path.join(data_dir, "blocking_issues.json")

        try:
            # 确保data目录存在
            os.makedirs(data_dir, exist_ok=True)

            # 读取现有问题
            existing_issues = {"timestamp": datetime.now().isoformat(), "issues": []}

            if os.path.exists(blocking_path):
                with open(blocking_path, encoding="utf-8") as f:
                    existing_issues = json.load(f)

            # 添加新问题，避免重复
            existing_issue_keys = {
                (issue["category"], issue["code"]) for issue in existing_issues["issues"]
            }
            for new_issue in blocking_issues["issues"]:
                new_issue_key = (new_issue["category"], new_issue["code"])
                if new_issue_key not in existing_issue_keys:
                    existing_issues["issues"].append(new_issue)

            # 更新时间戳
            existing_issues["timestamp"] = datetime.now().isoformat()

            # 写入文件
            with open(blocking_path, "w", encoding="utf-8") as f:
                json.dump(existing_issues, f, indent=2, ensure_ascii=False)

            logger.info(f"已写入 {len(blocking_issues['issues'])} 个阻塞问题到 {blocking_path}")
        except Exception as e:
            logger.error(f"写入阻塞问题失败: {e}")

    def _place_stop_loss_order(
        self,
        symbol: str,
        side: str,
        amount: float,
        stop_loss_price: float,
        main_order_result: dict[str, Any],
    ) -> dict[str, Any]:
        """
        挂止损单

        Args:
            symbol: 交易对
            side: 主订单买卖方向
            amount: 交易数量
            stop_loss_price: 止损价格
            main_order_result: 主订单结果

        Returns:
            Dict[str, Any]: 止损订单结果
        """
        # 止损单方向与主订单相反
        stop_side = "sell" if side == "buy" else "buy"

        logger.info(f"挂止损单：{stop_side} {symbol} {amount} {stop_loss_price}")

        # 使用限价单作为止损单
        stop_order_result = self._execute_single_order(
            symbol=symbol,
            side=stop_side,
            order_type="limit",
            amount=amount,
            price=stop_loss_price,
            params={
                "strategy_id": "stop_loss",
                "main_order_id": main_order_result.get("data", [{}])[0].get("ordId"),
            },
        )

        logger.info(f"止损单结果：{stop_order_result}")
        return stop_order_result

    def _generate_live_order_report(
        self, main_order_result: dict[str, Any], stop_order_result: dict[str, Any] | None = None
    ) -> None:
        """
        生成live_order_report.json

        Args:
            main_order_result: 主订单结果
            stop_order_result: 止损订单结果（可选）
        """
        import json
        import os
        from datetime import datetime

        logger.info("生成live_order_report.json")

        # 确保data目录存在
        data_dir = "data"
        os.makedirs(data_dir, exist_ok=True)

        # 生成报告
        report = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "real_order_switch": self.real_order_switch,
            "trading_mode": self.trading_mode,
            "main_order": main_order_result,
            "stop_order": stop_order_result,
            "real_order_limits": self.real_order_limits,
            "real_order_status": self.real_order_status,
            "stop_loss_config": self.stop_loss_config,
        }

        # 保存报告
        report_path = os.path.join(data_dir, "live_order_report.json")
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, ensure_ascii=False)

        logger.info(f"live_order_report.json 已生成：{report_path}")

    def get_event_log(self) -> list[dict[str, Any]]:
        """
        获取事件日志

        Returns:
            event_log: 事件日志列表
        """
        return self.event_log

    def clear_event_log(self) -> None:
        """
        清空事件日志
        """
        self.event_log = []

    def place_order_with_flow_report(
        self,
        symbol: str,
        side: str,
        order_type: str,
        amount: float,
        price: float | None = None,
        params: dict[str, Any] = None,
    ) -> dict[str, Any]:
        """
        最小下单链路，带订单流报告生成

        Args:
            symbol: 交易对
            side: 买卖方向
            order_type: 订单类型
            amount: 交易数量
            price: 交易价格
            params: 其他参数

        Returns:
            Dict[str, Any]: 下单结果
        """
        logger.info("开始执行最小下单链路...")

        import json
        import os
        from datetime import datetime

        # 初始化订单流报告
        flow_report = {
            "flow_id": f"flow_{int(datetime.utcnow().timestamp() * 1000)}",
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "datetime": datetime.now().isoformat(),
            "exchange": self.exchange,
            "trading_mode": self.trading_mode,
            "symbol": symbol,
            "side": side,
            "order_type": order_type,
            "requested_amount": amount,
            "requested_price": price,
            "steps": [],
            "final_status": "PENDING",
            "final_result": None,
        }

        try:
            # Step 1: 信号接收
            step1 = {
                "step": "signal_received",
                "timestamp": datetime.utcnow().isoformat() + "Z",
                "status": "SUCCESS",
                "details": {"symbol": symbol, "side": side, "amount": amount, "price": price},
            }
            flow_report["steps"].append(step1)

            # Step 2: 风控预算检查
            step2 = {
                "step": "risk_check",
                "timestamp": datetime.utcnow().isoformat() + "Z",
                "status": "PENDING",
                "details": None,
            }

            # 计算订单价值（USDT）
            if not price:
                # 市价单，使用模拟价格（实际应该从市场数据获取）
                mock_prices = {"ETH-USDT": 2000, "BTC-USDT": 40000, "SOL-USDT": 100}
                price = mock_prices.get(symbol, 1000)  # 默认模拟价格

            order_value_usdt = amount * price

            # 风控预算检查：总预算≤10u
            risk_config = self.config.get("risk", {})
            max_total_usdt = risk_config.get("max_total_usdt", 10.0)

            if order_value_usdt > max_total_usdt:
                step2["status"] = "BLOCKED"
                step2["details"] = {
                    "order_value_usdt": order_value_usdt,
                    "max_total_usdt": max_total_usdt,
                    "reason": f"订单价值 {order_value_usdt}u 超出最大总预算 {max_total_usdt}u",
                }
                flow_report["steps"].append(step2)
                flow_report["final_status"] = "BLOCKED"
                flow_report["final_result"] = {
                    "code": "1",
                    "msg": f"订单被风控拦截: {step2['details']['reason']}",
                }

                logger.error(f"订单被风控拦截: {step2['details']['reason']}")
            else:
                step2["status"] = "PASS"
                step2["details"] = {
                    "order_value_usdt": order_value_usdt,
                    "max_total_usdt": max_total_usdt,
                    "reason": "订单价值在预算范围内",
                }
                flow_report["steps"].append(step2)

                # Step 3: 执行就绪检查
                step3 = {
                    "step": "readiness_check",
                    "timestamp": datetime.utcnow().isoformat() + "Z",
                    "status": "PENDING",
                    "details": None,
                }

                try:
                    self._check_readiness()
                    step3["status"] = "PASS"
                    step3["details"] = {"reason": "系统处于就绪状态"}
                    flow_report["steps"].append(step3)

                    # Step 4: 下单请求
                    step4 = {
                        "step": "order_placed",
                        "timestamp": datetime.utcnow().isoformat() + "Z",
                        "status": "PENDING",
                        "details": None,
                    }

                    # 执行下单
                    order_result = self.place_order(symbol, side, order_type, amount, price, params)
                    step4["status"] = "SUCCESS"
                    step4["details"] = order_result
                    flow_report["steps"].append(step4)

                    # Step 5: 订单回执
                    step5 = {
                        "step": "order_acknowledged",
                        "timestamp": datetime.utcnow().isoformat() + "Z",
                        "status": "PENDING",
                        "details": None,
                    }

                    if order_result.get("code") == "0":
                        step5["status"] = "SUCCESS"
                        step5["details"] = {
                            "order_id": order_result.get("data", [{}])[0].get("clOrdId"),
                            "exchange_order_id": order_result.get("data", [{}])[0].get("ordId"),
                        }
                        flow_report["final_status"] = "SUCCESS"
                        flow_report["final_result"] = order_result
                    else:
                        step5["status"] = "FAILURE"
                        step5["details"] = {"error": order_result.get("msg", "Unknown error")}
                        flow_report["final_status"] = "FAILURE"
                        flow_report["final_result"] = order_result

                    flow_report["steps"].append(step5)

                    # Step 6: 订单状态查询
                    step6 = {
                        "step": "order_status_checked",
                        "timestamp": datetime.utcnow().isoformat() + "Z",
                        "status": "PENDING",
                        "details": None,
                    }

                    # 模拟订单状态查询，实际应该根据订单ID查询
                    if order_result.get("code") == "0":
                        mock_order_status = "FILLED" if self.trading_mode == "paper" else "PENDING"
                        step6["status"] = "SUCCESS"
                        step6["details"] = {"status": mock_order_status}
                    else:
                        step6["status"] = "SKIPPED"
                        step6["details"] = {"reason": "订单创建失败，跳过状态查询"}

                    flow_report["steps"].append(step6)

                except RuntimeError as e:
                    step3["status"] = "BLOCKED"
                    step3["details"] = {"reason": str(e)}
                    flow_report["steps"].append(step3)
                    flow_report["final_status"] = "BLOCKED"
                    flow_report["final_result"] = {
                        "code": "1",
                        "msg": f"执行就绪检查失败: {str(e)}",
                    }

            # 生成订单流报告文件
            report_dir = os.path.join(os.getcwd(), "reports")
            os.makedirs(report_dir, exist_ok=True)
            report_path = os.path.join(report_dir, "order_flow_report.json")

            with open(report_path, "w", encoding="utf-8") as f:
                json.dump(flow_report, f, indent=2, ensure_ascii=False)

            logger.info(f"订单流报告已生成: {report_path}")
            logger.info(f"下单链路最终状态: {flow_report['final_status']}")

            return flow_report["final_result"]

        except Exception as e:
            logger.error(f"下单链路执行失败: {str(e)}")

            # 更新报告状态
            flow_report["final_status"] = "FAILURE"
            flow_report["final_result"] = {"code": "1", "msg": f"下单链路执行异常: {str(e)}"}

            # 确保报告生成
            report_dir = os.path.join(os.getcwd(), "reports")
            os.makedirs(report_dir, exist_ok=True)
            report_path = os.path.join(report_dir, "order_flow_report.json")

            with open(report_path, "w", encoding="utf-8") as f:
                json.dump(flow_report, f, indent=2, ensure_ascii=False)

            return flow_report["final_result"]

    def connectivity_check(self) -> dict[str, Any]:
        """
        执行连通性验证，拉取账户信息并生成报告

        Returns:
            Dict[str, Any]: 连通性验证结果
        """
        logger.info("开始执行连通性验证...")

        # 初始化报告
        import json
        import os
        from datetime import datetime

        report = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "datetime": datetime.now().isoformat(),
            "exchange": self.exchange,
            "trading_mode": self.trading_mode,
            "environment": {
                "api_key_present": bool(self.api_key),
                "secret_key_present": bool(self.secret_key),
                "passphrase_present": bool(self.passphrase),
            },
            "checks": [],
            "status": "SUCCESS",
            "failure_reason": None,
        }

        try:
            # 执行多项检查，按优先级顺序
            checks_to_perform = [
                ("balance", self.get_balance),
                ("positions", self.get_positions),
                ("open_orders", lambda: self.get_open_orders("ETH-USDT")),
            ]

            for check_name, check_func in checks_to_perform:
                check_result = {
                    "name": check_name,
                    "status": "SUCCESS",
                    "timestamp": datetime.utcnow().isoformat() + "Z",
                    "data": None,
                    "error": None,
                }

                try:
                    result = check_func()
                    check_result["data"] = result

                    # 检查API返回码
                    if result.get("code") != "0":
                        check_result["status"] = "FAILURE"
                        check_result["error"] = result.get("msg", "Unknown error")
                        report["status"] = "FAILURE"
                        report["failure_reason"] = (
                            f"{check_name} check failed: {check_result['error']}"
                        )

                    report["checks"].append(check_result)

                    # 只要有一项成功，就认为连通性验证通过
                    if report["status"] == "SUCCESS" and check_result["status"] == "SUCCESS":
                        break

                except Exception as e:
                    check_result["status"] = "FAILURE"
                    check_result["error"] = str(e)
                    report["checks"].append(check_result)
                    report["status"] = "FAILURE"
                    report["failure_reason"] = f"{check_name} check failed: {str(e)}"

            # 生成报告文件
            report_dir = os.path.join(os.getcwd(), "reports")
            os.makedirs(report_dir, exist_ok=True)
            report_path = os.path.join(report_dir, "connectivity_report.json")

            with open(report_path, "w", encoding="utf-8") as f:
                json.dump(report, f, indent=2, ensure_ascii=False)

            logger.info(f"连通性验证报告已生成: {report_path}")
            logger.info(f"连通性验证结果: {report['status']}")

            return report

        except Exception as e:
            logger.error(f"连通性验证失败: {str(e)}")
            report["status"] = "FAILURE"
            report["failure_reason"] = str(e)

            # 确保即使发生异常也生成报告
            report_dir = os.path.join(os.getcwd(), "reports")
            os.makedirs(report_dir, exist_ok=True)
            report_path = os.path.join(report_dir, "connectivity_report.json")

            with open(report_path, "w", encoding="utf-8") as f:
                json.dump(report, f, indent=2, ensure_ascii=False)

            return report
