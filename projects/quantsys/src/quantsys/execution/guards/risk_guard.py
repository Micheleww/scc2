#!/usr/bin/env python3
"""
Runtime Guard Implementation

Authority: see law/QCC-README.md
"""

import hashlib
import json
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class RiskDecision(Enum):
    """Risk decision enumeration (QCC-S v1.1 aligned)"""

    ALLOW = "ALLOW"
    DENY = "DENY"
    REQUIRE_REVIEW = "REQUIRE_REVIEW"


@dataclass
class RiskVerdict:
    """Risk verdict data structure (aligned with contracts/risk_verdict.md v0.2, QCC-S v1.1)"""

    verdict_id: str
    decision: str
    timestamp_ms: int
    ttl_ms: int
    policy_version: str
    risk_rule_version: str
    session_id: str
    strategy_id: str
    strategy_version: str
    intent_hash: str
    account_id: str
    venue: str
    reason_codes: list[str] = field(default_factory=list)
    limits: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert RiskVerdict to dictionary"""
        return {
            "verdict_id": self.verdict_id,
            "decision": self.decision,
            "timestamp_ms": self.timestamp_ms,
            "ttl_ms": self.ttl_ms,
            "policy_version": self.policy_version,
            "risk_rule_version": self.risk_rule_version,
            "session_id": self.session_id,
            "strategy_id": self.strategy_id,
            "strategy_version": self.strategy_version,
            "intent_hash": self.intent_hash,
            "account_id": self.account_id,
            "venue": self.venue,
            "reason_codes": self.reason_codes,
            "limits": self.limits,
        }


@dataclass
class OrderIntent:
    """Order intent for hash calculation (aligned with contracts/risk_verdict.md)"""

    symbol: str
    side: str
    order_type: str
    amount: float
    price: float | None
    strategy_id: str
    strategy_version: str
    session_id: str
    account_id: str
    venue: str


class GuardBlockedError(Exception):
    """Exception raised when guard blocks an operation"""

    pass


class RiskGuard:
    """Runtime guard for validating risk verdicts"""

    def __init__(self, enabled: bool = True):
        """
        Initialize RiskGuard

        Args:
            enabled: Whether the guard is enabled (read-only after initialization)
        """
        self._enabled = enabled  # 使用私有变量，防止外部修改
        logger.info(f"RiskGuard initialized (enabled={enabled})")

    @property
    def enabled(self) -> bool:
        """Read-only property for enabled state"""
        return self._enabled

    @staticmethod
    def calculate_intent_hash(intent: OrderIntent) -> str:
        """
        Calculate intent hash

        Args:
            intent: OrderIntent object

        Returns:
            str: 64-character hex string
        """
        hash_string = (
            f"{intent.symbol}:{intent.side}:{intent.order_type}:"
            f"{intent.amount}:{intent.price}:{intent.strategy_id}:"
            f"{intent.strategy_version}:{intent.session_id}:"
            f"{intent.account_id}:{intent.venue}"
        )
        return hashlib.sha256(hash_string.encode("utf-8")).hexdigest()

    def validate(
        self, verdict: RiskVerdict | None, intent: OrderIntent, context: dict[str, Any]
    ) -> tuple[bool, str | None]:
        """
        Validate risk verdict

        Args:
            verdict: RiskVerdict object or None
            intent: OrderIntent object
            context: Additional context (e.g., current_time_ms)

        Returns:
            tuple: (is_valid, error_message)
        """
        if not self.enabled:
            return True, None

        # Check 1: Verdict existence
        if verdict is None:
            return False, "RiskVerdict is required but not provided"

        # Check 2: Required fields existence (QCC-S v1.1 aligned)
        required_fields = [
            "verdict_id",
            "decision",
            "timestamp_ms",
            "ttl_ms",
            "policy_version",
            "risk_rule_version",
            "session_id",
            "strategy_id",
            "strategy_version",
            "intent_hash",
            "account_id",
            "venue",
        ]
        for field in required_fields:
            if not hasattr(verdict, field) or getattr(verdict, field) is None:
                return False, f"Required field '{field}' is missing or None"

        # Check 3: Decision validation (QCC-S v1.1 aligned)
        # Map REJECT to DENY for backward compatibility
        decision_value = verdict.decision
        if decision_value == "REJECT":
            decision_value = "DENY"

        # REQUIRE_REVIEW is treated as DENY for now (no manual review channel in this version)
        if decision_value not in [
            RiskDecision.ALLOW.value,
            RiskDecision.DENY.value,
            RiskDecision.REQUIRE_REVIEW.value,
        ]:
            return False, f"Decision is {verdict.decision}, must be ALLOW/DENY/REQUIRE_REVIEW"

        # Only ALLOW is permitted for execution
        if decision_value != RiskDecision.ALLOW.value:
            return False, f"Decision is {verdict.decision}, only ALLOW is permitted"

        # Check 4: TTL validation
        # SECURITY: Always use server time, never trust client-provided time
        current_time_ms = int(time.time() * 1000)  # 始终使用服务器时间，防止时间操纵攻击
        expiry_time_ms = verdict.timestamp_ms + verdict.ttl_ms
        if current_time_ms > expiry_time_ms:
            return False, f"Verdict expired (current={current_time_ms}, expiry={expiry_time_ms})"

        # Check 5: Binding consistency
        if verdict.session_id != intent.session_id:
            return (
                False,
                f"Session ID mismatch (verdict={verdict.session_id}, intent={intent.session_id})",
            )
        if verdict.account_id != intent.account_id:
            return (
                False,
                f"Account ID mismatch (verdict={verdict.account_id}, intent={intent.account_id})",
            )
        if verdict.venue != intent.venue:
            return False, f"Venue mismatch (verdict={verdict.venue}, intent={intent.venue})"
        if verdict.strategy_id != intent.strategy_id:
            return (
                False,
                f"Strategy ID mismatch (verdict={verdict.strategy_id}, intent={intent.strategy_id})",
            )
        if verdict.strategy_version != intent.strategy_version:
            return (
                False,
                f"Strategy version mismatch (verdict={verdict.strategy_version}, intent={intent.strategy_version})",
            )

        # Check 6: Intent hash validation
        calculated_hash = self.calculate_intent_hash(intent)
        if verdict.intent_hash != calculated_hash:
            return (
                False,
                f"Intent hash mismatch (verdict={verdict.intent_hash}, calculated={calculated_hash})",
            )

        # Check 7: Limits validation (if provided)
        if verdict.limits:
            if "amount" in verdict.limits:
                max_amount = verdict.limits["amount"]
                if intent.amount > max_amount:
                    return False, f"Amount {intent.amount} exceeds limit {max_amount}"
            if "price_range" in verdict.limits and intent.price is not None:
                price_range = verdict.limits["price_range"]
                min_price = price_range.get("min", 0)
                max_price = price_range.get("max", float("inf"))
                if not (min_price <= intent.price <= max_price):
                    return False, f"Price {intent.price} outside range [{min_price}, {max_price}]"

        return True, None

    def require_verdict(
        self,
        verdict: RiskVerdict | None,
        intent: OrderIntent,
        context: dict[str, Any] | None = None,
    ) -> None:
        """
        Require valid verdict, raise GuardBlockedError if validation fails

        Args:
            verdict: RiskVerdict object or None
            intent: OrderIntent object
            context: Additional context

        Raises:
            GuardBlockedError: If validation fails
        """
        context = context or {}
        context["current_time_ms"] = int(time.time() * 1000)

        is_valid, error_msg = self.validate(verdict, intent, context)

        if not is_valid:
            # Log blocked event
            self._log_blocked_event(verdict, intent, error_msg)
            raise GuardBlockedError(error_msg)

    def _log_blocked_event(
        self, verdict: RiskVerdict | None, intent: OrderIntent, reason: str
    ) -> None:
        """
        Log blocked event (aligned with docs/ARCH/runtime-guard-v0.1.md)

        Args:
            verdict: RiskVerdict object (may be None)
            intent: OrderIntent object
            reason: Blocking reason
        """
        import uuid

        trace_id = str(uuid.uuid4())
        verdict_id = verdict.verdict_id if verdict else "N/A"
        decision = verdict.decision if verdict else "N/A"
        intent_hash = self.calculate_intent_hash(intent)

        blocked_event = {
            "event_type": "ORDER_SUBMIT_BLOCKED",
            "timestamp": time.time(),
            "timestamp_ms": int(time.time() * 1000),
            "trace_id": trace_id,
            "session_id": intent.session_id,
            "strategy_id": intent.strategy_id,
            "version": intent.strategy_version,
            "account_id": intent.account_id,
            "venue": intent.venue,
            "intent_hash": intent_hash,
            "verdict_id": verdict_id,
            "decision": decision,
            "reason_code": reason,
            "result": "BLOCKED",
            "error_code": "GUARD_BLOCKED",
            "latency_ms": 0,
        }

        logger.warning(f"Guard blocked order: {json.dumps(blocked_event, indent=2)}")
