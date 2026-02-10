import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any


class AuditLogger:
    def __init__(self, log_dir: str, repo_root: str):
        self.log_dir = Path(repo_root) / log_dir
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.repo_root = repo_root

    def _get_log_path(self) -> Path:
        today = datetime.now().strftime("%Y-%m-%d")
        return self.log_dir / f"{today}.jsonl"

    def _truncate(self, value: Any, max_length: int = 200) -> str:
        if value is None:
            return ""
        str_value = str(value)
        if len(str_value) > max_length:
            return str_value[:max_length] + "..."
        return str_value

    def _generate_client_hash(self, caller: str, user_agent: str | None = None) -> str:
        """Generate a unique hash for the client based on caller and user agent"""
        client_info = f"{caller}:{user_agent or 'unknown'}"
        return hashlib.md5(client_info.encode()).hexdigest()

    def _sanitize_params(self, params: dict[str, Any]) -> dict[str, Any]:
        """Sanitize parameters to remove any sensitive information like tokens or auth headers"""
        sanitized = {}
        # Fields that may contain sensitive content (messages, payloads, text)
        sensitive_content_fields = ["text", "payload", "message", "content", "body", "data"]
        # Fields that indicate authentication/authorization
        sensitive_key_fields = [
            "auth",
            "token",
            "secret",
            "password",
            "key",
            "credential",
            "api_key",
        ]

        for key, value in params.items():
            lower_key = key.lower()

            # Check if key indicates sensitive authentication data
            if any(sensitive in lower_key for sensitive in sensitive_key_fields):
                sanitized[key] = "******"
            # Check if key indicates potentially sensitive content
            elif any(sensitive in lower_key for sensitive in sensitive_content_fields):
                # Truncate and mask content fields
                if isinstance(value, str):
                    if len(value) > 50:
                        sanitized[key] = value[:50] + "...[REDACTED]"
                    else:
                        sanitized[key] = "[REDACTED]"
                elif isinstance(value, dict):
                    sanitized[key] = "[REDACTED_DICT]"
                else:
                    sanitized[key] = "[REDACTED]"
            else:
                sanitized[key] = value
        return sanitized

    def log(
        self,
        timestamp: str,
        tool: str,
        client_hash: str,
        scope: str,
        trace_id: str,
        result: bool,
        reason_code: int,
        latency_ms: int,
        params: dict[str, Any] | None = None,
        error: str | None = None,
    ):
        log_entry = {
            "timestamp": timestamp,
            "tool": tool,
            "client_hash": client_hash,
            "scope": scope,
            "trace_id": trace_id,
            "result": result,
            "reason_code": reason_code,
            "latency_ms": latency_ms,
            "params_summary": self._truncate(
                json.dumps(self._sanitize_params(params or {}), default=str)
            )
            if params
            else "",
            "error": error,
        }

        log_path = self._get_log_path()
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")

    def log_tool_call(
        self,
        tool_name: str,
        caller: str,
        params: dict[str, Any],
        success: bool,
        result: Any = None,
        error: str | None = None,
        start_time: datetime | None = None,
        user_agent: str | None = None,
        trace_id: str | None = None,
        scope: str = "default",
    ):
        end_time = datetime.now()
        timestamp = end_time.isoformat()

        # Calculate latency
        if start_time:
            latency_ms = int((end_time - start_time).total_seconds() * 1000)
        else:
            latency_ms = 0

        # Generate client hash
        client_hash = self._generate_client_hash(caller, user_agent)

        # Set reason code based on result
        reason_code = 0 if success else 1

        self.log(
            timestamp=timestamp,
            tool=tool_name,
            client_hash=client_hash,
            scope=scope,
            trace_id=trace_id or "unknown",
            result=success,
            reason_code=reason_code,
            latency_ms=latency_ms,
            params=params,
            error=error,
        )
