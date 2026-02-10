#!/usr/bin/env python3
"""
Execution Context - Unified context for order execution
Authority: see law/QCC-README.md
"""

import time
import uuid
from dataclasses import dataclass
from typing import Any

from .guards.risk_guard import RiskVerdict


@dataclass
class ExecutionContext:
    """
    Unified execution context for order operations
    Converges session_id, trace_id, env, account_id, venue, strategy_id, strategy_version, and risk_verdict
    Authority: see law/QCC-README.md
    """

    session_id: str
    trace_id: str
    env: str
    account_id: str
    venue: str
    strategy_id: str
    strategy_version: str
    risk_verdict: RiskVerdict | None = None
    source: str = "execution"

    def __post_init__(self):
        """Auto-generate trace_id if not provided"""
        if not self.trace_id or self.trace_id.strip() == "":
            self.trace_id = f"trace_{int(time.time())}_{uuid.uuid4().hex[:8]}"

    def to_dict(self) -> dict[str, Any]:
        """Convert context to dictionary for logging/auditing"""
        return {
            "session_id": self.session_id,
            "trace_id": self.trace_id,
            "env": self.env,
            "account_id": self.account_id,
            "venue": self.venue,
            "strategy_id": self.strategy_id,
            "strategy_version": self.strategy_version,
            "risk_verdict": self.risk_verdict.to_dict() if self.risk_verdict else None,
            "source": self.source,
        }

    def get_verdict_id(self) -> str:
        """Get verdict ID if verdict exists, otherwise return 'N/A'"""
        return self.risk_verdict.verdict_id if self.risk_verdict else "N/A"

    def get_decision(self) -> str:
        """Get decision if verdict exists, otherwise return 'N/A'"""
        return self.risk_verdict.decision if self.risk_verdict else "N/A"

    def get_policy_version(self) -> str:
        """Get policy version if verdict exists, otherwise return 'N/A'"""
        return self.risk_verdict.policy_version if self.risk_verdict else "N/A"
