#!/usr/bin/env python3
"""
统一异常处理
定义统一的异常类，提供异常处理装饰器
"""

import logging
from functools import wraps
from typing import Any

# 配置日志
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class TradingException(Exception):
    """交易系统基础异常"""

    def __init__(
        self, message: str, error_code: str | None = None, details: dict[str, Any] | None = None
    ):
        self.message = message
        self.error_code = error_code
        self.details = details or {}
        super().__init__(self.message)


class OrderRejectedException(TradingException):
    """订单被拒绝异常"""

    def __init__(
        self, reason: str, order: dict[str, Any] | None = None, error_code: str = "ORDER_REJECTED"
    ):
        self.reason = reason
        self.order = order
        super().__init__(
            message=f"Order rejected: {reason}",
            error_code=error_code,
            details={"order": order, "reason": reason},
        )


class ExecutionException(TradingException):
    """执行异常"""

    def __init__(
        self,
        message: str,
        order: dict[str, Any] | None = None,
        cause: Exception | None = None,
        error_code: str = "EXECUTION_ERROR",
    ):
        self.order = order
        self.cause = cause
        super().__init__(
            message=message,
            error_code=error_code,
            details={
                "order": order,
                "cause": str(cause) if cause else None,
                "cause_type": type(cause).__name__ if cause else None,
            },
        )


class RiskCheckException(TradingException):
    """风险检查异常"""

    def __init__(
        self,
        reason: str,
        order: dict[str, Any] | None = None,
        error_code: str = "RISK_CHECK_FAILED",
    ):
        self.reason = reason
        self.order = order
        super().__init__(
            message=f"Risk check failed: {reason}",
            error_code=error_code,
            details={"order": order, "reason": reason},
        )


class ExchangeException(TradingException):
    """交易所异常"""

    def __init__(
        self,
        message: str,
        exchange: str,
        api_response: dict[str, Any] | None = None,
        error_code: str = "EXCHANGE_ERROR",
    ):
        self.exchange = exchange
        self.api_response = api_response
        super().__init__(
            message=message,
            error_code=error_code,
            details={"exchange": exchange, "api_response": api_response},
        )


class ValidationException(TradingException):
    """验证异常"""

    def __init__(
        self,
        errors: list,
        order: dict[str, Any] | None = None,
        error_code: str = "VALIDATION_FAILED",
    ):
        self.errors = errors
        self.order = order
        super().__init__(
            message=f"Validation failed: {', '.join(errors)}",
            error_code=error_code,
            details={"order": order, "errors": errors},
        )


def handle_execution_errors(func):
    """
    异常处理装饰器
    统一处理执行相关的异常
    """

    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except OrderRejectedException as e:
            logger.warning(f"Order rejected: {e.reason}", extra={"order": e.order})
            return {
                "success": False,
                "status": "REJECTED",
                "reason": e.reason,
                "error_code": e.error_code,
                "order": e.order,
            }
        except RiskCheckException as e:
            logger.warning(f"Risk check failed: {e.reason}", extra={"order": e.order})
            return {
                "success": False,
                "status": "BLOCKED",
                "reason": e.reason,
                "error_code": e.error_code,
                "order": e.order,
            }
        except ExecutionException as e:
            logger.error(
                f"Execution failed: {e.message}", exc_info=e.cause, extra={"order": e.order}
            )
            return {
                "success": False,
                "status": "ERROR",
                "error": e.message,
                "error_code": e.error_code,
                "order": e.order,
            }
        except ExchangeException as e:
            logger.error(
                f"Exchange error: {e.message}",
                extra={"exchange": e.exchange, "api_response": e.api_response},
            )
            return {
                "success": False,
                "status": "EXCHANGE_ERROR",
                "error": e.message,
                "error_code": e.error_code,
                "exchange": e.exchange,
            }
        except ValidationException as e:
            logger.warning(f"Validation failed: {', '.join(e.errors)}", extra={"order": e.order})
            return {
                "success": False,
                "status": "VALIDATION_FAILED",
                "errors": e.errors,
                "error_code": e.error_code,
                "order": e.order,
            }
        except Exception as e:
            logger.error(f"Unexpected error in {func.__name__}: {e}", exc_info=True)
            return {
                "success": False,
                "status": "UNEXPECTED_ERROR",
                "error": str(e),
                "error_code": "UNEXPECTED_ERROR",
            }

    return wrapper
