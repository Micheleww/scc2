#!/usr/bin/env python3
"""
Risk Engine Contract
Authority: see law/QCC-README.md
"""

import time
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from ..execution.execution_context import ExecutionContext
from ..execution.guards.risk_guard import OrderIntent, RiskVerdict


@dataclass
class EvaluateResult:
    """Result of risk engine evaluation"""

    verdict: RiskVerdict
    latency_ms: int
    error_code: str | None = None
    error_message: str | None = None


class RiskEngine(ABC):
    """
    Risk Engine Contract (Protocol)

    Defines the interface for evaluating order intents and generating risk verdicts.
    All implementations must follow fail-closed principle: any error or exception
    must result in DENY decision.

    Authority: see law/QCC-README.md
    """

    @abstractmethod
    def evaluate(self, intent: OrderIntent, context: ExecutionContext) -> EvaluateResult:
        """
        Evaluate order intent and return risk verdict

        Args:
            intent: OrderIntent object containing order details
            context: ExecutionContext containing session, trace, and other metadata

        Returns:
            EvaluateResult: Contains RiskVerdict, latency_ms, and optional error details

        Raises:
            Exception: Any exception must be caught by caller and converted to DENY decision
                      with error_code=EVAL_ERROR and reason_code=EVAL_ERROR

        Fail-Closed Rules:
            - If evaluation fails, must return DENY decision
            - If exception is raised, caller must convert to DENY with error_code=EVAL_ERROR
            - Never return ALLOW on error
            - Always set error_code and error_message on failure

        Verdict Generation Requirements:
            - verdict_id: Must be unique (e.g., "rv_{timestamp}_{uuid}")
            - decision: Must be ALLOW/DENY/REQUIRE_REVIEW (QCC-S v1.1)
            - timestamp_ms: Current UTC timestamp in milliseconds
            - ttl_ms: Time-to-live in milliseconds (e.g., 30000 for 30 seconds)
            - policy_version: Must follow v{major}.{minor}.{patch} format
            - risk_rule_version: Risk rule version (can be same as policy_version)
            - session_id: Must match context.session_id
            - strategy_id: Must match context.strategy_id
            - strategy_version: Must match context.strategy_version
            - intent_hash: Must match RiskGuard.calculate_intent_hash(intent)
            - account_id: Must match context.account_id
            - venue: Must match context.venue
            - reason_codes: List of reason codes (required for DENY)
            - limits: Optional limits dictionary (for ALLOW decisions)
        """
        pass

    @abstractmethod
    def get_engine_version(self) -> str:
        """
        Get the engine version

        Returns:
            str: Engine version string (e.g., "v1.0.0")
        """
        pass

    @abstractmethod
    def get_policy_version(self) -> str:
        """
        Get the policy version

        Returns:
            str: Policy version string (e.g., "v1.1.0")
        """
        pass


class BaseRiskEngine(RiskEngine):
    """
    Base implementation of RiskEngine with common utilities
    Authority: see law/QCC-README.md
    """

    def __init__(self, policy_version: str = "v1.1.0"):
        """
        Initialize BaseRiskEngine

        Args:
            policy_version: Policy version string
        """
        self.policy_version = policy_version

    def get_engine_version(self) -> str:
        """Get engine version"""
        return "v1.0.0"

    def get_policy_version(self) -> str:
        """Get policy version"""
        return self.policy_version

    def _generate_verdict_id(self) -> str:
        """Generate unique verdict ID"""
        return f"rv_{int(time.time())}_{uuid.uuid4().hex[:8]}"

    def _create_allow_verdict(
        self,
        intent: OrderIntent,
        context: ExecutionContext,
        intent_hash: str,
        ttl_ms: int = 30000,
        limits: dict[str, Any] | None = None,
    ) -> RiskVerdict:
        """
        Create ALLOW verdict

        Args:
            intent: OrderIntent object
            context: ExecutionContext object
            intent_hash: Calculated intent hash
            ttl_ms: Time-to-live in milliseconds
            limits: Optional limits dictionary

        Returns:
            RiskVerdict: ALLOW verdict
        """
        return RiskVerdict(
            verdict_id=self._generate_verdict_id(),
            decision="ALLOW",
            timestamp_ms=int(time.time() * 1000),
            ttl_ms=ttl_ms,
            policy_version=self.policy_version,
            risk_rule_version=self.policy_version,
            session_id=context.session_id,
            strategy_id=context.strategy_id,
            strategy_version=context.strategy_version,
            intent_hash=intent_hash,
            account_id=context.account_id,
            venue=context.venue,
            reason_codes=[],
            limits=limits,
        )

    def _create_deny_verdict(
        self,
        intent: OrderIntent,
        context: ExecutionContext,
        intent_hash: str,
        reason_codes: list,
        ttl_ms: int = 30000,
    ) -> RiskVerdict:
        """
        Create DENY verdict

        Args:
            intent: OrderIntent object
            context: ExecutionContext object
            intent_hash: Calculated intent hash
            reason_codes: List of reason codes
            ttl_ms: Time-to-live in milliseconds

        Returns:
            RiskVerdict: DENY verdict
        """
        return RiskVerdict(
            verdict_id=self._generate_verdict_id(),
            decision="DENY",
            timestamp_ms=int(time.time() * 1000),
            ttl_ms=ttl_ms,
            policy_version=self.policy_version,
            risk_rule_version=self.policy_version,
            session_id=context.session_id,
            strategy_id=context.strategy_id,
            strategy_version=context.strategy_version,
            intent_hash=intent_hash,
            account_id=context.account_id,
            venue=context.venue,
            reason_codes=reason_codes,
            limits=None,
        )
