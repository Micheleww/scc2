#!/usr/bin/env python3
"""
Exchange Server Prototype

Provides:
1. JSON-RPC over HTTP: POST /mcp (supports tools/list and tools/call)
2. SSE: GET /sse and GET /mcp/messages

Internal tools:
- ata.search(query)
- ata.fetch(task_code)
"""

import asyncio
import glob
import hashlib
import json
import os
import time
import uuid
from collections import defaultdict, deque
from datetime import datetime, timedelta
from pathlib import Path

import jsonschema
import requests
from aiohttp import web
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization
from jose import jwt


def hash_client_id(client_id: str) -> str:
    """
    Generate irreversible hash for client_id for privacy in logs and metrics
    """
    return hashlib.sha256(client_id.encode()).hexdigest()[:16]


# Project root directory
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
ATA_LEDGER_PATH = os.path.join(PROJECT_ROOT, "docs", "REPORT", "_index", "ATA_LEDGER__STATIC.json")
TOOLSET_VERSION = "v0.1"
EXCHANGE_TOOL_SCHEMA_PATH = os.path.join(
    PROJECT_ROOT, "tools", "exchange_server", "schemas", "exchange_tool_contract.schema.json"
)


class RateLimiter:
    """Scope and Client ID based rate limiter with sliding window algorithm"""

    def __init__(self, window_size=60, max_requests=100, scope_limits=None):
        """
        Initialize rate limiter

        Args:
            window_size: Time window in seconds
            max_requests: Maximum requests allowed per window (global default)
            scope_limits: Dict mapping scope to max requests, e.g. {"a2a:create": 50, "ata:fetch": 100}
        """
        self.window_size = window_size
        self.max_requests = max_requests
        self.scope_limits = scope_limits or {}
        # {client_id_hash: {scope: deque([timestamp1, timestamp2, ...])}}
        self.requests = defaultdict(lambda: defaultdict(deque))

    def is_allowed(self, client_id_hash, scope="global"):
        """Check if request is allowed for given client_id_hash and scope"""
        now = time.time()

        # Get the max requests for this scope, default to global limit
        max_requests = self.scope_limits.get(scope, self.max_requests)

        # Clean up old requests for this client_id_hash and scope
        while (
            self.requests[client_id_hash][scope]
            and now - self.requests[client_id_hash][scope][0] > self.window_size
        ):
            self.requests[client_id_hash][scope].popleft()

        # Check if within limit
        if len(self.requests[client_id_hash][scope]) < max_requests:
            self.requests[client_id_hash][scope].append(now)
            return True

        return False

    def get_remaining(self, client_id_hash, scope="global"):
        """Get remaining requests for given client_id_hash and scope"""
        now = time.time()

        # Get the max requests for this scope, default to global limit
        max_requests = self.scope_limits.get(scope, self.max_requests)

        # Clean up old requests for this client_id_hash and scope
        while (
            self.requests[client_id_hash][scope]
            and now - self.requests[client_id_hash][scope][0] > self.window_size
        ):
            self.requests[client_id_hash][scope].popleft()

        return max(0, max_requests - len(self.requests[client_id_hash][scope]))

    def get_reset_time(self):
        """Get reset time in seconds"""
        return self.window_size

    def get_max_requests(self, scope="global"):
        """Get max requests for a given scope"""
        return self.scope_limits.get(scope, self.max_requests)


class SSEClient:
    """SSE client connection with idle tracking and backpressure support"""

    def __init__(self, response, ip, trace_id, client_id, max_queue_size=100, heartbeat_interval=2):
        self.response = response
        self.ip = ip
        self.trace_id = trace_id
        self.client_id = client_id
        self.last_activity = time.time()
        self.connected_at = time.time()
        self.buffer_size = 0
        self.max_buffer_size = 1048576  # 1MB default buffer size
        self.backpressure_active = False

        # Message queue with max size
        self.message_queue = deque(maxlen=max_queue_size)
        self.max_queue_size = max_queue_size
        self.queue_overflow = False

        # Heartbeat tracking for buffering detection
        self.last_heartbeat_sent = time.time()
        self.heartbeat_delay = 0
        self.heartbeat_delay_anomaly = False
        self.heartbeat_interval = heartbeat_interval  # Store the actual heartbeat interval
        self.heartbeat_count = 0  # Track heartbeat tick count

        # Proxy buffering risk detection
        self.proxy_buffering_risk = False
        self.last_buffer_flush = time.time()

    def update_activity(self):
        """Update last activity timestamp"""
        self.last_activity = time.time()

    def is_idle(self, idle_timeout):
        """Check if client is idle"""
        return time.time() - self.last_activity > idle_timeout

    def update_buffer_size(self, data_size):
        """Update buffer size and check if backpressure should be applied"""
        self.buffer_size += data_size

        # Check if backpressure should be applied
        if self.buffer_size >= self.max_buffer_size and not self.backpressure_active:
            self.backpressure_active = True
            return True

        # Check if backpressure should be released
        if self.buffer_size < self.max_buffer_size * 0.8 and self.backpressure_active:
            self.backpressure_active = False
            return False

        return None

    def is_backpressure_active(self):
        """Check if backpressure is active"""
        return self.backpressure_active

    def add_message(self, message, event_type="message", is_critical=False):
        """Add message to queue, handle overflow based on message criticality"""
        msg = {
            "event_type": event_type,
            "message": message,
            "timestamp": time.time(),
            "is_critical": is_critical,
        }

        # Check if queue is full
        queue_full = len(self.message_queue) >= self.max_queue_size

        if queue_full:
            self.queue_overflow = True

            # If message is critical, remove oldest non-critical message to make space
            if is_critical:
                # Find and remove oldest non-critical message
                for i, queued_msg in enumerate(self.message_queue):
                    if not queued_msg["is_critical"]:
                        removed_msg = self.message_queue[i]
                        self.message_queue.remove(removed_msg)
                        self.message_queue.append(msg)
                        return {
                            "status": "added",
                            "action": "removed_oldest_non_critical",
                            "removed_msg": removed_msg["event_type"],
                        }

            # If queue is full and message is non-critical, discard
            return {"status": "discarded", "action": "queue_full_non_critical_discarded"}

        # Queue is not full, add message
        self.message_queue.append(msg)
        return {"status": "added", "action": "queue_added"}

    def get_queue_size(self):
        """Get current queue size"""
        return len(self.message_queue)

    def is_queue_full(self):
        """Check if queue is full"""
        return len(self.message_queue) >= self.max_queue_size

    def update_heartbeat_sent(self):
        """Update last heartbeat sent time"""
        current_time = time.time()
        if self.last_heartbeat_sent > 0:
            self.heartbeat_delay = current_time - self.last_heartbeat_sent
        self.last_heartbeat_sent = current_time
        self.heartbeat_count += 1  # Increment heartbeat tick count

        # Detect heartbeat delay anomalies (delay > 2x expected interval)
        self.heartbeat_delay_anomaly = self.heartbeat_delay > (
            2 * self.heartbeat_interval
        )  # Use actual heartbeat interval

    def detect_proxy_buffering(self):
        """Detect potential proxy buffering"""
        current_time = time.time()
        time_since_flush = current_time - self.last_buffer_flush

        # If no buffer flush for a long time but we're sending messages, it might be proxy buffering
        if time_since_flush > 60 and len(self.message_queue) > 0:
            self.proxy_buffering_risk = True
        else:
            self.proxy_buffering_risk = False

        return self.proxy_buffering_risk


class Logger:
    """Structured logger for exchange server"""

    def __init__(self):
        """Initialize logger with audit log functionality"""
        # Set up audit log directory
        self.audit_log_path = os.getenv(
            "EXCHANGE_AUDIT_LOG_PATH", os.path.join(os.path.dirname(__file__), "logs")
        )
        os.makedirs(self.audit_log_path, exist_ok=True)

        # Log rotation settings
        self.rotation_mode = os.getenv("EXCHANGE_AUDIT_LOG_ROTATION_MODE", "daily")
        self.max_size = self._parse_size(os.getenv("EXCHANGE_AUDIT_LOG_MAX_SIZE", "100MB"))
        self.rotation_time = os.getenv("EXCHANGE_AUDIT_LOG_ROTATION_TIME", "00:00")
        self.retention_days = int(os.getenv("EXCHANGE_AUDIT_LOG_RETENTION_DAYS", "30"))

        # Current log file info
        self.current_log_file = None
        self.current_log_size = 0
        self.current_log_date = None

        # Open initial log file
        self._rotate_log()

    def _parse_size(self, size_str):
        """Parse size string to bytes"""
        size_str = size_str.strip().upper()
        if size_str.endswith("GB"):
            return int(size_str[:-2]) * 1024 * 1024 * 1024
        elif size_str.endswith("MB"):
            return int(size_str[:-2]) * 1024 * 1024
        elif size_str.endswith("KB"):
            return int(size_str[:-2]) * 1024
        else:
            return int(size_str)

    def _get_log_filename(self):
        """Generate log filename based on current datetime"""
        now = datetime.now()
        return os.path.join(self.audit_log_path, f"audit_{now.strftime('%Y%m%d_%H%M%S')}.jsonl")

    def _rotate_log(self):
        """Rotate log file"""
        # Close current log file if open
        if self.current_log_file:
            self.current_log_file.close()

        # Open new log file in append mode
        filename = self._get_log_filename()
        self.current_log_file = open(filename, "a")
        self.current_log_size = os.path.getsize(filename) if os.path.exists(filename) else 0
        self.current_log_date = datetime.now().date()

    def _should_rotate(self):
        """Check if log rotation is needed"""
        # Check by date
        if self.rotation_mode == "daily":
            if datetime.now().date() != self.current_log_date:
                return True

        # Check by size
        if self.rotation_mode == "size" or self.rotation_mode == "daily":
            if self.current_log_size >= self.max_size:
                return True

        return False

    def _cleanup_old_logs(self):
        """Clean up old logs beyond retention period"""
        import glob
        import shutil

        # Create archive directory if it doesn't exist
        archive_dir = os.path.join(self.audit_log_path, "archive")
        os.makedirs(archive_dir, exist_ok=True)

        # Get all log files
        log_files = glob.glob(os.path.join(self.audit_log_path, "audit_*.jsonl"))

        # Sort by modification time (oldest first)
        log_files.sort(key=os.path.getmtime)

        # Calculate cutoff date
        cutoff_date = datetime.now() - timedelta(days=self.retention_days)

        # Archive old files
        for log_file in log_files:
            if os.path.getmtime(log_file) < cutoff_date.timestamp():
                # Move to archive directory
                archive_file = os.path.join(archive_dir, os.path.basename(log_file))
                shutil.move(log_file, archive_file)

    def audit_log(
        self,
        ts=None,
        trace_id=None,
        task_code=None,
        route=None,
        auth_mode=None,
        auth_result=None,
        gate_result=None,
        reason_code=None,
        ruleset_sha256=None,
        client_id=None,
        client_ip=None,
        request_method=None,
        response_status=None,
        tool_name=None,
        tool_params=None,
        duration_ms=None,
        error_message=None,
        idempotency_key_hash=None,
    ):
        """Log audit event in JSON line format"""
        # Check if rotation is needed
        if self._should_rotate():
            self._rotate_log()
            self._cleanup_old_logs()

        # Create audit log entry
        audit_entry = {
            "ts": ts or datetime.now().isoformat(),
            "trace_id": trace_id,
            "task_code": task_code,
            "route": route,
            "auth_mode": auth_mode,
            "auth_result": auth_result,
            "gate_result": gate_result,
            "reason_code": reason_code,
            "ruleset_sha256": ruleset_sha256,
            "client_id": client_id,
            "client_ip": client_ip,
            "request_method": request_method,
            "response_status": response_status,
            "tool_name": tool_name,
            "tool_params": tool_params,
            "duration_ms": duration_ms,
            "error_message": error_message,
            "idempotency_key_hash": idempotency_key_hash,
        }

        # Filter out None values
        audit_entry = {k: v for k, v in audit_entry.items() if v is not None}

        # Write to file
        log_line = json.dumps(audit_entry) + "\n"
        self.current_log_file.write(log_line)
        self.current_log_file.flush()  # Ensure immediate write
        self.current_log_size += len(log_line)

        # Also print to stdout for debugging
        print(log_line.strip())

    @staticmethod
    def log(
        ts=None,
        trace_id=None,
        task_code=None,
        route=None,
        status=None,
        reason=None,
        message=None,
        ruleset_sha256=None,
        client_id=None,
        final_queue_size=None,
        queue_overflow=None,
        proxy_buffering_risk=None,
        heartbeat_delay_anomaly=None,
        heartbeat_count=None,
        heartbeat_lag_ms=None,
        queue_size=None,
    ):
        """Log structured message"""
        log_entry = {
            "ts": ts or datetime.now().isoformat(),
            "trace_id": trace_id,
            "task_code": task_code,
            "route": route,
            "status": status,
            "reason": reason,
            "message": message,
            "ruleset_sha256": ruleset_sha256,
            "client_id": client_id,
            "final_queue_size": final_queue_size,
            "queue_overflow": queue_overflow,
            "proxy_buffering_risk": proxy_buffering_risk,
            "heartbeat_delay_anomaly": heartbeat_delay_anomaly,
            "heartbeat_count": heartbeat_count,
            "heartbeat_lag_ms": heartbeat_lag_ms,
            "queue_size": queue_size,
        }
        # Filter out None values
        log_entry = {k: v for k, v in log_entry.items() if v is not None}
        print(json.dumps(log_entry))

    @staticmethod
    def log_rejection(ip, route, reason, details, trace_id=None):
        """Log rejection event in JSON line format"""
        rejection_entry = {
            "ts": datetime.now().isoformat(),
            "trace_id": trace_id or str(uuid.uuid4()),
            "route": route,
            "ip": ip,
            "status": 429,
            "reason": reason,
            "details": details,
            "type": "RATE_LIMIT_REJECTION",
        }
        print(json.dumps(rejection_entry))


logger = Logger()


class ExchangeServer:
    """Exchange Server class"""

    def __init__(self, auth_mode=None):
        self.app = web.Application()
        self.setup_routes()
        self.sse_clients = set()

        # Files module initialization
        from files import FilesModule

        self.files_module = FilesModule()

        # Replay protection store - per client_id
        self.nonce_store = defaultdict(dict)  # {client_id_hash: {nonce: timestamp}}
        self.max_nonce_age = 300  # 5 minutes in seconds

        # Calculate RULESET_SHA256 on server start
        self.RULESET_SHA256 = self.calculate_ruleset_sha256()

        # Metrics counters
        self.metrics = {
            "requests_total": 0,
            "auth_fail_total": 0,
            "gate_fail_total": 0,
            "sse_connections": 0,
            "latency_ms_bucket": defaultdict(int),
            "reconnect_attempts_total": defaultdict(int),
            "reconnect_success_total": defaultdict(int),
            "reconnect_time_ms_bucket": defaultdict(int),
            "heartbeat_lag_ms_bucket": defaultdict(int),
            "recent_fail_reasons": deque(maxlen=10),  # Keep last 10 failure reasons
            "request_timestamps": deque(
                maxlen=60
            ),  # Keep timestamps for last 60 seconds for QPS calculation
        }

        # Client ID extraction configuration
        self.client_id_config = {
            "source": os.getenv("EXCHANGE_CLIENT_ID_SOURCE", "token"),  # token|header|explicit
            "header_name": os.getenv("EXCHANGE_CLIENT_ID_HEADER", "X-Client-ID"),
        }

        # Parse scope limits from environment variable
        def parse_scope_limits():
            scope_limits_env = os.getenv("EXCHANGE_RATE_LIMIT_SCOPES", "{}")
            try:
                return json.loads(scope_limits_env)
            except json.JSONDecodeError:
                logger.log(
                    reason="INVALID_SCOPE_LIMITS_CONFIG",
                    message=f"Failed to parse EXCHANGE_RATE_LIMIT_SCOPES: {scope_limits_env}",
                )
                return {}

        # 读取配置，可通过环境变量或配置文件
        self.config = {
            "auth": {
                "jsonrpc": {
                    "type": os.getenv("EXCHANGE_JSONRPC_AUTH_TYPE", "bearer"),  # bearer|oauth
                    "tokens": self._parse_tokens(),
                    "revoked_tokens": self._parse_revoked_tokens(),
                    "token_versions": {
                        "current": 1,
                        "supported": [1],  # List of supported token versions
                    },
                    "oauth": {
                        "enabled": os.getenv("EXCHANGE_JSONRPC_OAUTH_ENABLED", "false").lower()
                        == "true",
                        "issuer": os.getenv("EXCHANGE_OAUTH_ISSUER", ""),
                        "audience": os.getenv("EXCHANGE_OAUTH_AUDIENCE", ""),
                        "client_id": os.getenv("EXCHANGE_OAUTH_CLIENT_ID", ""),
                        "public_key": os.getenv("EXCHANGE_OAUTH_PUBLIC_KEY", ""),
                        "public_key_file": os.getenv("EXCHANGE_OAUTH_PUBLIC_KEY_FILE", ""),
                        "jwks_url": os.getenv("EXCHANGE_OAUTH_JWKS_URL", ""),
                        "algorithms": os.getenv("EXCHANGE_OAUTH_ALGORITHMS", "RS256").split(","),
                        "revoked_tokens": self._parse_revoked_tokens(
                            prefix="EXCHANGE_JSONRPC_OAUTH_REVOKED_TOKENS"
                        ),
                        "token_expiry": int(
                            os.getenv("EXCHANGE_JSONRPC_OAUTH_TOKEN_EXPIRY", "3600")
                        ),  # Default 1 hour in seconds
                    },
                },
                "sse": {
                    "mode": os.getenv("EXCHANGE_SSE_AUTH_MODE", "none"),  # none|oauth
                    "oauth": {
                        "enabled": os.getenv("EXCHANGE_SSE_OAUTH_ENABLED", "false").lower()
                        == "true",
                        "issuer": os.getenv("EXCHANGE_OAUTH_ISSUER", ""),
                        "audience": os.getenv("EXCHANGE_OAUTH_AUDIENCE", ""),
                        "client_id": os.getenv("EXCHANGE_OAUTH_CLIENT_ID", ""),
                        "public_key": os.getenv("EXCHANGE_OAUTH_PUBLIC_KEY", ""),
                        "public_key_file": os.getenv("EXCHANGE_OAUTH_PUBLIC_KEY_FILE", ""),
                        "jwks_url": os.getenv("EXCHANGE_OAUTH_JWKS_URL", ""),
                        "algorithms": os.getenv("EXCHANGE_OAUTH_ALGORITHMS", "RS256").split(","),
                        "tokens": self._parse_oauth2_tokens(),
                        "revoked_tokens": self._parse_revoked_tokens(
                            prefix="EXCHANGE_OAUTH_REVOKED_TOKENS"
                        ),
                        "token_expiry": int(
                            os.getenv("EXCHANGE_OAUTH_TOKEN_EXPIRY", "3600")
                        ),  # Default 1 hour in seconds
                    },
                },
            },
            "sse": {
                "heartbeat_interval": int(
                    os.getenv("EXCHANGE_SSE_HEARTBEAT_INTERVAL", "60")
                ),  # 心跳间隔（秒） - normal production value
                "max_idle_time": int(
                    os.getenv("EXCHANGE_SSE_MAX_IDLE_TIME", "30")
                ),  # 最大空闲时间（秒）
                "initial_backoff": float(
                    os.getenv("EXCHANGE_SSE_INITIAL_BACKOFF", "1")
                ),  # 初始重连延迟（秒）
                "max_backoff": float(
                    os.getenv("EXCHANGE_SSE_MAX_BACKOFF", "30")
                ),  # 最大重连延迟（秒）
                "backoff_factor": float(
                    os.getenv("EXCHANGE_SSE_BACKOFF_FACTOR", "2")
                ),  # 重连延迟乘数
                "max_connections": int(
                    os.getenv("EXCHANGE_SSE_MAX_CONNECTIONS", "10")
                ),  # 全局最大连接数
                "max_connections_per_client": int(
                    os.getenv("EXCHANGE_SSE_MAX_CONNECTIONS_PER_CLIENT", "5")
                ),  # 每个client_id的最大连接数
                "max_queue": int(
                    os.getenv("EXCHANGE_SSE_MAX_QUEUE", "5")
                ),  # 单连接发送队列上限 - smaller for testing
            },
            "rate_limit": {
                "window_size": int(
                    os.getenv("EXCHANGE_RATE_LIMIT_WINDOW", "60")
                ),  # 限流窗口大小（秒）
                "max_requests": int(
                    os.getenv("EXCHANGE_RATE_LIMIT_MAX", "100")
                ),  # 窗口内最大请求数（全局默认）
                "scope_limits": parse_scope_limits(),  # Scope特定限流配置
            },
        }

        # Override auth mode if provided
        if auth_mode == "none":
            # Set both JSON-RPC and SSE auth to none
            self.config["auth"]["jsonrpc"]["type"] = "none"
            self.config["auth"]["sse"]["mode"] = "none"

        # Initialize rate limiter with scope support
        self.rate_limiter = RateLimiter(
            window_size=self.config["rate_limit"]["window_size"],
            max_requests=self.config["rate_limit"]["max_requests"],
            scope_limits=self.config["rate_limit"]["scope_limits"],
        )

        # Initialize SSE idle timeout
        self.sse_idle_timeout = self.config["sse"]["max_idle_time"]

        # Track SSE connections per client_id
        self.sse_connections_per_client = defaultdict(int)  # {client_id_hash: connection_count}

        # Storage for idempotent requests: {client_id: {idempotency_key: task_id}}
        self.idempotent_requests = defaultdict(dict)

        # ATA ledger cache initialization
        self.ata_ledger_cache = None
        self.ata_ledger_last_update = 0
        self.ata_ledger_path = os.path.join(
            PROJECT_ROOT, "docs", "REPORT", "_index", "ATA_LEDGER__STATIC.json"
        )
        # Load ATA ledger cache on startup - commented out for now
        # self.refresh_ata_ledger_cache()

    def _parse_tokens(self):
        """Parse tokens from environment variable"""
        # Support multiple tokens separated by commas
        token_env = os.getenv("EXCHANGE_BEARER_TOKEN", "default_secret_token")
        tokens = [token.strip() for token in token_env.split(",") if token.strip()]
        return tokens

    def calculate_ruleset_sha256(self):
        """Calculate SHA256 hash of the ruleset"""
        # For now, return a dummy SHA256 value
        # In a real implementation, this would calculate the hash of actual ruleset files
        return "dummy_ruleset_sha256_value_1234567890abcdef"

    def refresh_ata_ledger_cache(self):
        """Refresh the ATA ledger cache from the static ledger file"""
        try:
            if os.path.exists(self.ata_ledger_path):
                with open(self.ata_ledger_path, encoding="utf-8") as f:
                    ledger_data = json.load(f)
                self.ata_ledger_cache = ledger_data
                self.ata_ledger_last_update = time.time()
                # Store the file modification time for future checks
                self.ata_ledger_file_mtime = os.path.getmtime(self.ata_ledger_path)
                logger.log(
                    task_code="ata.search",
                    status="completed",
                    message=f"ATA ledger cache refreshed from {self.ata_ledger_path}, containing {ledger_data.get('total_entries', 0)} entries",
                )
            else:
                logger.log(
                    task_code="ata.search",
                    status="warning",
                    reason="LEDGER_FILE_MISSING",
                    message=f"ATA ledger file not found at {self.ata_ledger_path}, cache not refreshed",
                )
        except Exception as e:
            logger.log(
                task_code="ata.search",
                status="error",
                reason="CACHE_REFRESH_ERROR",
                message=f"Error refreshing ATA ledger cache: {str(e)}",
            )

    def check_and_refresh_ata_ledger(self):
        """Check if ATA ledger file has changed and refresh cache if needed"""
        try:
            if os.path.exists(self.ata_ledger_path):
                current_mtime = os.path.getmtime(self.ata_ledger_path)
                # Check if we have stored mtime and if file has changed
                if hasattr(self, "ata_ledger_file_mtime"):
                    if current_mtime > self.ata_ledger_file_mtime:
                        logger.log(
                            task_code="ata.search",
                            status="processing",
                            message="ATA ledger file has changed, refreshing cache",
                        )
                        self.refresh_ata_ledger_cache()
                else:
                    # First time checking, just refresh
                    self.refresh_ata_ledger_cache()
        except Exception as e:
            logger.log(
                task_code="ata.search",
                status="error",
                reason="LEDGER_CHECK_ERROR",
                message=f"Error checking ATA ledger file: {str(e)}",
            )

    def _parse_oauth2_tokens(self):
        """Parse OAuth2 tokens from environment variable"""
        # Support multiple tokens with format: token|expiry_timestamp
        token_env = os.getenv("EXCHANGE_OAUTH2_TOKENS", "test_token|0")
        tokens = {}

        for token_entry in token_env.split(","):
            if "|" in token_entry:
                token, expiry_str = token_entry.strip().split("|", 1)
                try:
                    expiry = int(expiry_str)
                except ValueError:
                    expiry = 0  # Invalid expiry becomes permanent token
            else:
                token = token_entry.strip()
                expiry = 0  # 0 means permanent token

            if token:
                tokens[token] = expiry

        return tokens

    def _parse_revoked_tokens(self, prefix="EXCHANGE_REVOKED_TOKENS"):
        """Parse revoked tokens from environment variable"""
        # Support multiple revoked tokens separated by commas
        revoked_env = os.getenv(prefix, "")
        if not revoked_env:
            return []

        revoked_tokens = [token.strip() for token in revoked_env.split(",") if token.strip()]
        return revoked_tokens

    def _load_public_key(self, oauth_config):
        """Load public key from config (env var, file, or JWKS URL)"""
        # Try env var first
        public_key = oauth_config.get("public_key")
        if public_key:
            return self._parse_public_key(public_key)

        # Try file next
        public_key_file = oauth_config.get("public_key_file")
        if public_key_file and os.path.exists(public_key_file):
            with open(public_key_file) as f:
                public_key = f.read()
            return self._parse_public_key(public_key)

        # Try JWKS URL last
        jwks_url = oauth_config.get("jwks_url")
        if jwks_url:
            return self._fetch_jwks_public_key(jwks_url)

        return None

    def _parse_public_key(self, public_key):
        """Parse PEM formatted public key"""
        try:
            if "BEGIN PUBLIC KEY" not in public_key:
                # Add PEM headers if missing
                public_key = f"-----BEGIN PUBLIC KEY-----\n{public_key}\n-----END PUBLIC KEY-----"

            return serialization.load_pem_public_key(
                public_key.encode("utf-8"), backend=default_backend()
            )
        except Exception as e:
            logger.log(reason="INVALID_PUBLIC_KEY", message=f"Failed to parse public key: {str(e)}")
            return None

    def _fetch_jwks_public_key(self, jwks_url):
        """Fetch public key from JWKS URL"""
        try:
            response = requests.get(jwks_url)
            response.raise_for_status()
            jwks = response.json()

            # For simplicity, use the first key in JWKS
            if "keys" in jwks and len(jwks["keys"]) > 0:
                first_key = jwks["keys"][0]
                jwk_data = json.dumps(first_key)
                # Use python-jose to process JWK
                from jose import jwt

                return jwt.algorithms.RSAAlgorithm.from_jwk(jwk_data)
        except Exception as e:
            logger.log(reason="JWKS_FETCH_FAILED", message=f"Failed to fetch JWKS: {str(e)}")
        return None

    def validate_jwt_token(self, token, oauth_config):
        """Validate JWT token with signature, exp, aud, and iss checks"""
        try:
            # Check if token is revoked
            if token in oauth_config.get("revoked_tokens", []):
                return False, "TOKEN_REVOKED", None

            # Load public key
            public_key = self._load_public_key(oauth_config)
            if not public_key:
                return False, "MISSING_PUBLIC_KEY", None

            # Validate token
            payload = jwt.decode(
                token,
                public_key,
                algorithms=oauth_config.get("algorithms", ["RS256"]),
                audience=oauth_config.get("audience"),
                issuer=oauth_config.get("issuer"),
            )

            return True, "VALID_TOKEN", payload

        except jwt.ExpiredSignatureError:
            return False, "TOKEN_EXPIRED", None
        except jwt.InvalidAudienceError:
            return False, "INVALID_AUDIENCE", None
        except jwt.InvalidIssuerError:
            return False, "INVALID_ISSUER", None
        except jwt.JWTError as e:
            return False, f"INVALID_TOKEN: {str(e)}", None
        except Exception as e:
            return False, f"VALIDATION_ERROR: {str(e)}", None

    def check_scope(self, payload, required_scope):
        """Check if the token has the required scope"""
        # Get scopes from token payload
        token_scopes = payload.get("scope", "").split()

        # Check if required scope is in token scopes
        return required_scope in token_scopes

    def generate_error_response(
        self, status_code, error_code, error_message, reason_code, trace_id
    ):
        """Generate standardized error response for both JSON-RPC and SSE"""
        # Standardized error structure
        error_response = {
            "error_code": error_code,
            "error_message": error_message,
            "reason_code": reason_code,
            "trace_id": trace_id,
        }

        return web.Response(
            status=status_code,
            text=json.dumps(error_response),
            content_type="application/json",
            headers={"X-Trace-ID": trace_id},
        )

    def get_required_scope(self, tool_name):
        """Map tool name to required scope"""
        scope_map = {
            "ata.search": "ata:search",
            "ata.fetch": "ata:fetch",
            "a2a.task_create": "a2a:create",
            "a2a.task_status": "a2a:status",
            "a2a.task_result": "a2a:result",
            "files.generate_presigned_url": "files:generate",
            "files.revoke": "files:revoke",
            "files.check_access": "files:check",
            "planner.inbox": "planner:inbox",
        }

        return scope_map.get(tool_name)

    async def cleanup_idle_clients(self):
        """Periodically clean up idle SSE clients"""
        while True:
            await asyncio.sleep(60)  # Check every minute

            now = time.time()
            idle_clients = []

            # Find idle clients
            for client in self.sse_clients:
                if client.is_idle(self.sse_idle_timeout):
                    idle_clients.append(client)

            # Disconnect idle clients
            for client in idle_clients:
                try:
                    await client.response.write(
                        b'event: disconnect\ndata: {"reason": "idle_timeout"}\n\n'
                    )
                    await client.response.write_eof()
                    self.sse_clients.remove(client)
                    # Decrement connection count for this token
                    if hasattr(client, "token"):
                        self.sse_connections_per_token[client.token] -= 1
                        if self.sse_connections_per_token[client.token] <= 0:
                            del self.sse_connections_per_token[client.token]
                    logger.log_rejection(
                        client.ip,
                        "sse",
                        "SSE_IDLE_TIMEOUT",
                        f"Client idle for {self.sse_idle_timeout} seconds",
                        client.trace_id,
                    )
                except Exception as e:
                    logger.log(
                        trace_id=client.trace_id,
                        route="sse",
                        status="error",
                        reason="IDLE_CLEANUP_FAILED",
                        message=f"Failed to clean up idle client: {str(e)}",
                    )

    def _cleanup_nonces(self, client_id_hash=None):
        """Cleanup expired nonces, optionally for a specific client_id_hash"""
        current_time = datetime.now().timestamp()

        if client_id_hash:
            # Cleanup only for this client_id_hash
            if client_id_hash in self.nonce_store:
                expired_nonces = [
                    nonce
                    for nonce, timestamp in self.nonce_store[client_id_hash].items()
                    if current_time - timestamp > self.max_nonce_age
                ]
                for nonce in expired_nonces:
                    del self.nonce_store[client_id_hash][nonce]
        else:
            # Cleanup all clients
            for client_id_hash in list(self.nonce_store.keys()):
                self._cleanup_nonces(client_id_hash)

    def _is_nonce_valid(self, nonce, client_id_hash):
        """Check if nonce is valid for the given client_id_hash"""
        # Cleanup expired nonces for this client first
        self._cleanup_nonces(client_id_hash)

        # Check if nonce is already used for this client
        if client_id_hash in self.nonce_store and nonce in self.nonce_store[client_id_hash]:
            return False

        # Add nonce to client's store with current timestamp
        if client_id_hash not in self.nonce_store:
            self.nonce_store[client_id_hash] = {}
        self.nonce_store[client_id_hash][nonce] = datetime.now().timestamp()
        return True

    def _extract_client_id(self, request, token=None, auth_payload=None):
        """
        Extract client_id from different sources based on configuration

        Args:
            request: HTTP request object
            token: Authentication token
            auth_payload: OAuth token payload

        Returns:
            str: client_id
        """
        source = self.client_id_config["source"]

        if source == "token":
            # Extract from token (last 8 chars of token as client_id for simplicity)
            if token:
                return token[-8:] if len(token) >= 8 else token
            return str(uuid.uuid4())[:8]  # Fallback to random client_id

        elif source == "header":
            # Extract from custom header
            client_id = request.headers.get(self.client_id_config["header_name"])
            if client_id:
                return client_id
            return str(uuid.uuid4())[:8]  # Fallback to random client_id

        elif source == "explicit":
            # Extract from auth payload (OAuth client_id claim)
            if auth_payload and "client_id" in auth_payload:
                return auth_payload["client_id"]
            return str(uuid.uuid4())[:8]  # Fallback to random client_id

        # Default fallback
        return str(uuid.uuid4())[:8]

    def setup_routes(self):
        """Set up HTTP routes"""
        # JSON-RPC over HTTP endpoint for Trae
        self.app.router.add_post("/mcp", self.handle_jsonrpc)

        # SSE endpoints for ChatGPT
        self.app.router.add_get("/sse", self.handle_sse)
        self.app.router.add_get("/mcp/messages", self.handle_sse)  # ChatGPT compatible

        # Version endpoint
        self.app.router.add_get("/version", self.handle_version)

        # Metrics endpoint (Prometheus format)
        self.app.router.add_get("/metrics", self.handle_metrics)

        # Status endpoint (JSON format)
        self.app.router.add_get("/status", self.handle_status)

    async def handle_metrics(self, request):
        """Handle metrics requests and return Prometheus format"""
        # Generate Prometheus format metrics
        metrics_text = []

        # Counter metrics
        metrics_text.append("# HELP exchange_requests_total Total number of requests")
        metrics_text.append("# TYPE exchange_requests_total counter")
        metrics_text.append(f"exchange_requests_total {self.metrics['requests_total']}")

        metrics_text.append(
            "# HELP exchange_auth_fail_total Total number of authentication failures"
        )
        metrics_text.append("# TYPE exchange_auth_fail_total counter")
        metrics_text.append(f"exchange_auth_fail_total {self.metrics['auth_fail_total']}")

        metrics_text.append("# HELP exchange_gate_fail_total Total number of gate check failures")
        metrics_text.append("# TYPE exchange_gate_fail_total counter")
        metrics_text.append(f"exchange_gate_fail_total {self.metrics['gate_fail_total']}")

        # Gauge metrics
        metrics_text.append("# HELP exchange_sse_connections Current number of SSE connections")
        metrics_text.append("# TYPE exchange_sse_connections gauge")
        metrics_text.append(f"exchange_sse_connections {len(self.sse_clients)}")

        # Histogram metrics
        metrics_text.append("# HELP exchange_latency_ms_bucket Request latency in milliseconds")
        metrics_text.append("# TYPE exchange_latency_ms_bucket histogram")
        for bucket, count in sorted(self.metrics["latency_ms_bucket"].items()):
            metrics_text.append(f'exchange_latency_ms_bucket{{le="{bucket}"}} {count}')

        # Add sum and count for histogram
        total_count = sum(self.metrics["latency_ms_bucket"].values())
        metrics_text.append(f"exchange_latency_ms_count {total_count}")

        # Reconnect metrics
        metrics_text.append(
            "# HELP exchange_reconnect_attempts_total Total number of reconnect attempts"
        )
        metrics_text.append("# TYPE exchange_reconnect_attempts_total counter")
        for client_id_hash, count in self.metrics["reconnect_attempts_total"].items():
            metrics_text.append(
                f'exchange_reconnect_attempts_total{{client_id="{client_id_hash}"}} {count}'
            )

        metrics_text.append(
            "# HELP exchange_reconnect_success_total Total number of successful reconnects"
        )
        metrics_text.append("# TYPE exchange_reconnect_success_total counter")
        for client_id_hash, count in self.metrics["reconnect_success_total"].items():
            metrics_text.append(
                f'exchange_reconnect_success_total{{client_id="{client_id_hash}"}} {count}'
            )

        metrics_text.append(
            "# HELP exchange_reconnect_time_ms_bucket Reconnect time in milliseconds"
        )
        metrics_text.append("# TYPE exchange_reconnect_time_ms_bucket histogram")
        for client_id_hash, bucket_counts in self.metrics["reconnect_time_ms_bucket"].items():
            for bucket, count in sorted(bucket_counts.items()):
                metrics_text.append(
                    f'exchange_reconnect_time_ms_bucket{{client_id="{client_id_hash}", le="{bucket}"}} {count}'
                )

        metrics_text.append("# HELP exchange_heartbeat_lag_ms_bucket Heartbeat lag in milliseconds")
        metrics_text.append("# TYPE exchange_heartbeat_lag_ms_bucket histogram")
        for client_id_hash, bucket_counts in self.metrics["heartbeat_lag_ms_bucket"].items():
            for bucket, count in sorted(bucket_counts.items()):
                metrics_text.append(
                    f'exchange_heartbeat_lag_ms_bucket{{client_id="{client_id_hash}", le="{bucket}"}} {count}'
                )

        return web.Response(text="\n".join(metrics_text), content_type="text/plain")

    async def handle_status(self, request):
        """Handle status requests and return JSON format"""
        # Calculate QPS: number of requests in the last 60 seconds
        now = time.time()
        recent_requests = [ts for ts in self.metrics["request_timestamps"] if now - ts <= 60]
        qps = len(recent_requests) / 60 if recent_requests else 0.0

        # Calculate P95 latency
        total_requests = sum(self.metrics["latency_ms_bucket"].values())
        p95 = 0.0
        if total_requests > 0:
            p95_threshold = int(total_requests * 0.95)
            cumulative = 0
            # Sort buckets to calculate percentiles
            sorted_buckets = sorted(
                [
                    (int(bucket), count)
                    for bucket, count in self.metrics["latency_ms_bucket"].items()
                ]
            )
            for bucket, count in sorted_buckets:
                cumulative += count
                if cumulative >= p95_threshold:
                    p95 = bucket
                    break

        # Get recent failure reasons (unique values)
        recent_fail_reasons = list(set(self.metrics["recent_fail_reasons"]))

        # Status response
        status = {
            "version": TOOLSET_VERSION,
            "ruleset_sha256": self.RULESET_SHA256,
            "sse_connections": len(self.sse_clients),
            "qps": round(qps, 2),
            "p95": p95,
            "recent_fail_reasons": recent_fail_reasons,
            "top_dlq_depth": 0,  # Placeholder since DLQ is not implemented
        }

        return web.Response(text=json.dumps(status), content_type="application/json")

    async def handle_jsonrpc(self, request):
        """Handle JSON-RPC requests with Bearer Token authentication"""
        # Start timing for latency calculation
        start_time = time.time()

        # Increment total requests counter
        self.metrics["requests_total"] += 1

        # Add request timestamp for QPS calculation
        self.metrics["request_timestamps"].append(time.time())

        # Generate or extract Trace ID
        trace_id = request.headers.get("X-Trace-ID", str(uuid.uuid4()))
        client_ip = request.remote  # Get client IP from request

        # Default task_code (can be overridden later)
        task_code = "GENERAL_OPERATION"

        # Default client_id extraction (will be updated after authentication)
        client_id = "anonymous"
        client_id_hash = hash_client_id(client_id)

        # Debug: Print config
        import sys

        sys.stderr.write(f"DEBUG: self.config = {self.config}\n")

        # Rate limiting check - JSON-RPC endpoints
        if not self.rate_limiter.is_allowed(client_id_hash):
            remaining = self.rate_limiter.get_remaining(client_id_hash)
            reset_time = self.rate_limiter.get_reset_time()

            logger.log_rejection(
                client_ip, "/mcp", "RATE_LIMIT_EXCEEDED", "JSON-RPC rate limit exceeded", trace_id
            )

            # Audit log for rate limit rejection
            logger.audit_log(
                trace_id=trace_id,
                task_code=task_code,
                route="/mcp",
                auth_mode=self.config["auth"]["jsonrpc"]["type"],
                auth_result="SUCCESS",
                gate_result="FAIL",
                reason_code="RATE_LIMIT_EXCEEDED",
                ruleset_sha256=self.RULESET_SHA256,
                client_id=client_id_hash,  # Use hashed client_id
                client_ip=client_ip,
                request_method=request.method,
                response_status=429,
            )

            # Generate standardized error response for rate limit exceeded
            error_response = {
                "error_code": "RATE_LIMITED",
                "error_message": "Rate limit exceeded",
                "reason_code": "RATE_LIMIT_EXCEEDED",
                "trace_id": trace_id,
                "remaining": remaining,
                "reset_time": reset_time,
            }
            return web.Response(
                status=429,
                text=json.dumps(error_response),
                content_type="application/json",
                headers={
                    "X-RateLimit-Remaining": str(remaining),
                    "X-RateLimit-Reset": str(int(time.time() + reset_time)),
                    "X-Trace-ID": trace_id,
                },
            )

        try:
            # 1. Replay protection: X-Request-Nonce + X-Request-Ts + TTL
            nonce = request.headers.get("X-Request-Nonce")
            request_ts = request.headers.get("X-Request-Ts")

            # Check if nonce is provided
            if not nonce:
                logger.log(
                    trace_id=trace_id,
                    route="/mcp",
                    status=401,
                    reason="REPLAY_PROTECTION_FAILED",
                    message="Missing X-Request-Nonce header",
                )
                return self.generate_error_response(
                    status_code=401,
                    error_code="INVALID_REQUEST",
                    error_message="Missing X-Request-Nonce header",
                    reason_code="MISSING_NONCE",
                    trace_id=trace_id,
                )

            # Check if request timestamp is provided
            if not request_ts:
                logger.log(
                    trace_id=trace_id,
                    route="/mcp",
                    status=401,
                    reason="REPLAY_PROTECTION_FAILED",
                    message="Missing X-Request-Ts header",
                )
                return web.Response(
                    status=401,
                    text=json.dumps({"error": "Missing X-Request-Ts header"}),
                    content_type="application/json",
                    headers={"X-Trace-ID": trace_id},
                )

            # Validate request timestamp format and TTL
            try:
                req_time = int(request_ts)
                current_time = int(datetime.now().timestamp())
                ttl = 300  # 5 minutes in seconds

                if abs(current_time - req_time) > ttl:
                    logger.log(
                        trace_id=trace_id,
                        route="/mcp",
                        status=401,
                        reason="REPLAY_PROTECTION_FAILED",
                        message="X-Request-Ts expired",
                    )
                    return self.generate_error_response(
                        status_code=401,
                        error_code="INVALID_REQUEST",
                        error_message="X-Request-Ts expired",
                        reason_code="EXPIRED_TIMESTAMP",
                        trace_id=trace_id,
                    )
            except ValueError:
                logger.log(
                    trace_id=trace_id,
                    route="/mcp",
                    status=400,
                    reason="REPLAY_PROTECTION_FAILED",
                    message="Invalid X-Request-Ts format",
                )
                return self.generate_error_response(
                    status_code=400,
                    error_code="INVALID_REQUEST",
                    error_message="Invalid X-Request-Ts format",
                    reason_code="INVALID_TIMESTAMP_FORMAT",
                    trace_id=trace_id,
                )

            # Check if nonce is valid for this client
            if not self._is_nonce_valid(nonce, client_id_hash):
                logger.log(
                    trace_id=trace_id,
                    route="/mcp",
                    status=409,
                    reason="REPLAY_PROTECTION_FAILED",
                    message="Invalid or expired X-Request-Nonce",
                )
                return self.generate_error_response(
                    status_code=409,
                    error_code="INVALID_REQUEST",
                    error_message="Invalid or expired X-Request-Nonce",
                    reason_code="INVALID_NONCE",
                    trace_id=trace_id,
                )

            # 2. Authentication based on configured type (none|bearer|oauth)
            auth_header = request.headers.get("Authorization")
            auth_mode = self.config["auth"]["jsonrpc"]["type"]
            auth_result = "FAIL"

            # Debug: Print auth_mode details
            print(f"DEBUG: auth_mode = {auth_mode}")
            print(
                f"DEBUG: self.config['auth']['jsonrpc']['type'] = {self.config['auth']['jsonrpc']['type']}"
            )
            print(
                f"DEBUG: self.config['auth']['sse']['mode'] = {self.config['auth']['sse']['mode']}"
            )
            print(f"DEBUG: Authorization header = {auth_header}")
            print(
                f"DEBUG: Command line auth_mode parameter = {self.auth_mode if hasattr(self, 'auth_mode') else 'not set'}"
            )
            print(f"DEBUG: auth_mode == 'none' = {auth_mode == 'none'}")

            # Skip authentication if auth_mode is 'none'
            if auth_mode == "none":
                auth_result = "SUCCESS"
                client_id = "anonymous"
                client_id_hash = hash_client_id(client_id)
                auth_type = "none"  # Define auth_type for none mode
                logger.log(
                    trace_id=trace_id,
                    route="/mcp",
                    status="authorized",
                    reason="NO_AUTH_REQUIRED",
                    message="Authentication skipped (auth_mode=none)",
                    client_id=client_id_hash,
                )
            else:
                # Normal authentication flow for bearer or oauth
                if not auth_header or not auth_header.startswith("Bearer "):
                    reason_code = "MISSING_AUTH_HEADER"
                    # Increment authentication failure counter
                    self.metrics["auth_fail_total"] += 1
                    logger.log(
                        trace_id=trace_id,
                        route="/mcp",
                        status=401,
                        reason=reason_code,
                        message="Missing or invalid Authorization header",
                    )

                    # Audit log for authentication failure
                    logger.audit_log(
                        trace_id=trace_id,
                        task_code=task_code,
                        route="/mcp",
                        auth_mode=auth_mode,
                        auth_result=auth_result,
                        gate_result="FAIL",
                        reason_code=reason_code,
                        ruleset_sha256=self.RULESET_SHA256,
                        client_ip=client_ip,
                        request_method=request.method,
                        response_status=401,
                    )

                    return self.generate_error_response(
                        status_code=401,
                        error_code="AUTHENTICATION_FAILED",
                        error_message="Missing or invalid Authorization header",
                        reason_code="MISSING_AUTH_HEADER",
                        trace_id=trace_id,
                    )

                token = auth_header[7:]
                auth_type = auth_mode.lower()

            # OAuth authentication flow - only if auth_type is not 'none'
            if auth_type != "none" and (
                auth_type == "oauth"
                or (auth_type == "bearer" and self.config["auth"]["jsonrpc"]["oauth"]["enabled"])
            ):
                # OAuth authentication
                oauth_config = self.config["auth"]["jsonrpc"]["oauth"]
                is_valid, reason_code, payload = self.validate_jwt_token(token, oauth_config)

                if not is_valid:
                    # Increment authentication failure counter
                    self.metrics["auth_fail_total"] += 1
                    logger.log(
                        trace_id=trace_id,
                        route="/mcp",
                        status=401,
                        reason=reason_code,
                        message=f"OAuth validation failed: {reason_code}",
                    )

                    # Audit log for authentication failure
                    logger.audit_log(
                        trace_id=trace_id,
                        task_code=task_code,
                        route="/mcp",
                        auth_mode=auth_mode,
                        auth_result=auth_result,
                        gate_result="FAIL",
                        reason_code=reason_code,
                        ruleset_sha256=self.RULESET_SHA256,
                        client_ip=client_ip,
                        request_method=request.method,
                        response_status=401,
                    )

                    return self.generate_error_response(
                        status_code=401,
                        error_code="AUTHENTICATION_FAILED",
                        error_message="OAuth validation failed",
                        reason_code=reason_code,
                        trace_id=trace_id,
                    )

                auth_result = "SUCCESS"

                # Extract client_id after successful OAuth authentication
                client_id = self._extract_client_id(request, token, payload)
                client_id_hash = hash_client_id(client_id)

                logger.log(
                    trace_id=trace_id,
                    route="/mcp",
                    status="authorized",
                    reason="VALID_TOKEN",
                    message="OAuth authentication successful",
                    client_id=client_id_hash,
                )
            # Bearer Token authentication flow - only if auth_type is not 'none'
            elif auth_type != "none" and auth_type == "bearer":
                # Bearer Token authentication with version support
                token_with_version = token

                # Extract token and version (format: token|v1, default to v1 if no version)
                if "|v" in token_with_version:
                    token, version_str = token_with_version.rsplit("|v", 1)
                    try:
                        version = int(version_str)
                    except ValueError:
                        reason_code = "INVALID_TOKEN_VERSION"
                        # Increment authentication failure counter
                        self.metrics["auth_fail_total"] += 1
                        logger.log(
                            trace_id=trace_id,
                            route="/mcp",
                            status=401,
                            reason=reason_code,
                            message="Invalid token version format",
                        )

                        # Audit log for authentication failure
                        logger.audit_log(
                            trace_id=trace_id,
                            task_code=task_code,
                            route="/mcp",
                            auth_mode=auth_mode,
                            auth_result=auth_result,
                            gate_result="FAIL",
                            reason_code=reason_code,
                            ruleset_sha256=self.RULESET_SHA256,
                            client_ip=client_ip,
                            request_method=request.method,
                            response_status=401,
                        )

                        return self.generate_error_response(
                            status_code=401,
                            error_code="AUTHENTICATION_FAILED",
                            error_message="Invalid token version format",
                            reason_code=reason_code,
                            trace_id=trace_id,
                        )
                else:
                    token = token_with_version
                    version = 1  # Default to version 1

                # Check if version is supported
                if version not in self.config["auth"]["jsonrpc"]["token_versions"]["supported"]:
                    reason_code = "UNSUPPORTED_TOKEN_VERSION"
                    # Increment authentication failure counter
                    self.metrics["auth_fail_total"] += 1
                    logger.log(
                        trace_id=trace_id,
                        route="/mcp",
                        status=401,
                        reason=reason_code,
                        message=f"Invalid token version: {version}, supported versions: {self.config['auth']['jsonrpc']['token_versions']['supported']}",
                    )

                    # Audit log for authentication failure
                    logger.audit_log(
                        trace_id=trace_id,
                        task_code=task_code,
                        route="/mcp",
                        auth_mode=auth_mode,
                        auth_result=auth_result,
                        gate_result="FAIL",
                        reason_code=reason_code,
                        ruleset_sha256=self.RULESET_SHA256,
                        client_ip=client_ip,
                        request_method=request.method,
                        response_status=401,
                    )

                    return self.generate_error_response(
                        status_code=401,
                        error_code="AUTHENTICATION_FAILED",
                        error_message=f"Invalid token version: {version}, supported versions: {self.config['auth']['jsonrpc']['token_versions']['supported']}",
                        reason_code=reason_code,
                        trace_id=trace_id,
                    )

                # Check if token is in revoked list
                revoked_tokens = self.config["auth"]["jsonrpc"]["revoked_tokens"]
                if token in revoked_tokens:
                    reason_code = "TOKEN_REVOKED"
                    # Increment authentication failure counter
                    self.metrics["auth_fail_total"] += 1
                    logger.log(
                        trace_id=trace_id,
                        route="/mcp",
                        status=401,
                        reason=reason_code,
                        message="Token has been revoked",
                    )

                    # Audit log for authentication failure
                    logger.audit_log(
                        trace_id=trace_id,
                        task_code=task_code,
                        route="/mcp",
                        auth_mode=auth_mode,
                        auth_result=auth_result,
                        gate_result="FAIL",
                        reason_code=reason_code,
                        ruleset_sha256=self.RULESET_SHA256,
                        client_ip=client_ip,
                        request_method=request.method,
                        response_status=401,
                    )

                    return self.generate_error_response(
                        status_code=401,
                        error_code="AUTHENTICATION_FAILED",
                        error_message="Token has been revoked",
                        reason_code=reason_code,
                        trace_id=trace_id,
                    )

                # Check if token is valid
                tokens = self.config["auth"]["jsonrpc"]["tokens"]
                if token not in tokens:
                    reason_code = "INVALID_TOKEN"
                    # Increment authentication failure counter
                    self.metrics["auth_fail_total"] += 1
                    logger.log(
                        trace_id=trace_id,
                        route="/mcp",
                        status=401,
                        reason=reason_code,
                        message="Invalid token",
                    )

                    # Audit log for authentication failure
                    logger.audit_log(
                        trace_id=trace_id,
                        task_code=task_code,
                        route="/mcp",
                        auth_mode=auth_mode,
                        auth_result=auth_result,
                        gate_result="FAIL",
                        reason_code=reason_code,
                        ruleset_sha256=self.RULESET_SHA256,
                        client_ip=client_ip,
                        request_method=request.method,
                        response_status=401,
                    )

                    return self.generate_error_response(
                        status_code=401,
                        error_code="AUTHENTICATION_FAILED",
                        error_message="Invalid token",
                        reason_code=reason_code,
                        trace_id=trace_id,
                    )

                auth_result = "SUCCESS"
                reason_code = "VALID_TOKEN"

                # Extract client_id after successful authentication
                client_id = self._extract_client_id(request, token, None)
                client_id_hash = hash_client_id(client_id)

                logger.log(
                    trace_id=trace_id,
                    route="/mcp",
                    status="authorized",
                    reason=reason_code,
                    message="Bearer token authentication successful",
                    client_id=client_id_hash,
                )

            # Parse JSON-RPC request
            data = await request.json()
            method = data.get("method")
            params = data.get("params", {})

            logger.log(
                trace_id=trace_id,
                route="/mcp",
                status="processing",
                message=f"Received JSON-RPC request: {method}",
                client_id=client_id_hash,
            )

            response_status = 200

            # Handle tools/list
            if method == "tools/list":
                tools = self.get_available_tools()
                response = {
                    "jsonrpc": "2.0",
                    "id": data.get("id"),
                    "result": {
                        "toolset_version": TOOLSET_VERSION,
                        "RULESET_SHA256": self.RULESET_SHA256,
                        "tools": tools,
                    },
                }
                logger.log(
                    trace_id=trace_id,
                    route="/mcp",
                    status=200,
                    message="Successfully processed tools/list request",
                )

                # Audit log for successful tools/list
                logger.audit_log(
                    trace_id=trace_id,
                    task_code=task_code,
                    route="/mcp",
                    auth_mode=auth_mode,
                    auth_result=auth_result,
                    gate_result="PASS",
                    reason_code="TOOLS_LIST_SUCCESS",
                    ruleset_sha256=self.RULESET_SHA256,
                    client_ip=client_ip,
                    request_method=request.method,
                    response_status=response_status,
                    duration_ms=int((time.time() - start_time) * 1000),
                )

            # Handle tools/call
            elif method == "tools/call":
                # Validate input parameters
                if "tool_call" not in params:
                    result = {
                        "success": False,
                        "error_code": "INVALID_REQUEST",
                        "error_message": "Missing required parameter: tool_call",
                        "reason_code": "INVALID_PARAMETER",
                        "trace_id": trace_id,
                    }
                    logger.log(
                        trace_id=trace_id,
                        route="/mcp",
                        status=400,
                        reason="INVALID_PARAMETER",
                        message="Missing required parameter: tool_call",
                    )
                    response_status = 400

                    # Audit log for invalid parameter
                    logger.audit_log(
                        trace_id=trace_id,
                        task_code=task_code,
                        route="/mcp",
                        auth_mode=auth_mode,
                        auth_result=auth_result,
                        gate_result="PASS",
                        reason_code="INVALID_PARAMETER",
                        ruleset_sha256=self.RULESET_SHA256,
                        client_ip=client_ip,
                        request_method=request.method,
                        response_status=response_status,
                        duration_ms=int((time.time() - start_time) * 1000),
                    )
                else:
                    tool_call = params.get("tool_call", {})
                    tool_name = tool_call.get("name")
                    tool_params = tool_call.get("params", {})

                    # Extract Idempotency-Key header if present
                    idempotency_key = request.headers.get("Idempotency-Key")

                    # Validate tool_call structure
                    if not isinstance(tool_call, dict):
                        result = {
                            "success": False,
                            "error_code": "INVALID_REQUEST",
                            "error_message": "Invalid parameter type: tool_call must be an object",
                            "reason_code": "INVALID_PARAMETER",
                            "trace_id": trace_id,
                        }
                        logger.log(
                            trace_id=trace_id,
                            route="/mcp",
                            status=400,
                            reason="INVALID_PARAMETER",
                            message="Invalid parameter type: tool_call must be an object",
                        )
                        response_status = 400

                        # Audit log for invalid parameter type
                        logger.audit_log(
                            trace_id=trace_id,
                            task_code=task_code,
                            route="/mcp",
                            auth_mode=auth_mode,
                            auth_result=auth_result,
                            gate_result="PASS",
                            reason_code="INVALID_PARAMETER",
                            ruleset_sha256=self.RULESET_SHA256,
                            client_ip=client_ip,
                            request_method=request.method,
                            response_status=response_status,
                            duration_ms=int((time.time() - start_time) * 1000),
                        )
                    elif not tool_name:
                        result = {
                            "success": False,
                            "error_code": "INVALID_REQUEST",
                            "error_message": "Missing required parameter: tool_call.name",
                            "reason_code": "INVALID_PARAMETER",
                            "trace_id": trace_id,
                        }
                        logger.log(
                            trace_id=trace_id,
                            route="/mcp",
                            status=400,
                            reason="INVALID_PARAMETER",
                            message="Missing required parameter: tool_call.name",
                        )
                        response_status = 400

                        # Audit log for missing tool name
                        logger.audit_log(
                            trace_id=trace_id,
                            task_code=task_code,
                            route="/mcp",
                            auth_mode=auth_mode,
                            auth_result=auth_result,
                            gate_result="PASS",
                            reason_code="INVALID_PARAMETER",
                            ruleset_sha256=self.RULESET_SHA256,
                            client_ip=client_ip,
                            request_method=request.method,
                            response_status=response_status,
                            duration_ms=int((time.time() - start_time) * 1000),
                        )
                    else:
                        logger.log(
                            trace_id=trace_id,
                            route="/mcp",
                            status="processing",
                            message=f"Calling tool: {tool_name} with params: {json.dumps(tool_params)}",
                        )

                        # Extract task_code from tool_params if available
                        if isinstance(tool_params, dict):
                            task_code = tool_params.get("task_code", task_code)

                        scope_check_passed = True

                        # Check scope based on tool name
                        required_scope = self.get_required_scope(tool_name)
                        if required_scope:
                            # Get the token payload from authentication result
                            if auth_type == "oauth" or (
                                auth_type == "bearer"
                                and self.config["auth"]["jsonrpc"]["oauth"]["enabled"]
                            ):
                                # OAuth authentication - payload is available from earlier validation
                                token_payload = payload
                            else:
                                # Bearer token authentication - create a mock payload with default scope for testing
                                # In production, scopes should be stored in the token or in a database
                                token_payload = {
                                    "scope": "ata:search ata:fetch a2a:create a2a:status a2a:result planner:inbox"
                                }

                            # Check if the token has the required scope
                            if not self.check_scope(token_payload, required_scope):
                                result = {
                                    "success": False,
                                    "error_code": "PERMISSION_DENIED",
                                    "error_message": f"Insufficient scope: requires {required_scope}",
                                    "reason_code": "INSUFFICIENT_SCOPE",
                                    "trace_id": trace_id,
                                }
                                logger.log(
                                    trace_id=trace_id,
                                    route="/mcp",
                                    status=403,
                                    reason="INSUFFICIENT_SCOPE",
                                    message=f"Insufficient scope for tool {tool_name}: requires {required_scope}",
                                )
                                response_status = 403
                                scope_check_passed = False

                                # Audit log for insufficient scope
                                logger.audit_log(
                                    trace_id=trace_id,
                                    task_code=task_code,
                                    route="/mcp",
                                    auth_mode=auth_mode,
                                    auth_result=auth_result,
                                    gate_result="PASS",
                                    reason_code="INSUFFICIENT_SCOPE",
                                    ruleset_sha256=self.RULESET_SHA256,
                                    client_ip=client_ip,
                                    request_method=request.method,
                                    response_status=response_status,
                                    tool_name=tool_name,
                                    tool_params=tool_params,
                                    duration_ms=int((time.time() - start_time) * 1000),
                                )

                        if scope_check_passed:
                            # Get client_id for idempotency key tracking
                            if auth_type == "oauth" or (
                                auth_type == "bearer"
                                and self.config["auth"]["jsonrpc"]["oauth"]["enabled"]
                            ):
                                client_id = payload.get("client_id", "unknown")
                            else:
                                client_id = "bearer_token_client"

                            # Tool calls with scope validation
                            if tool_name == "ata.search":
                                result = await self.ata_search(
                                    tool_params.get("query", ""), trace_id
                                )
                            elif tool_name == "ata.fetch":
                                result = await self.ata_fetch(
                                    tool_params.get("task_code", ""), trace_id
                                )
                            elif tool_name == "a2a.task_create":
                                result = await self.a2a_task_create(
                                    tool_params.get("payload", {}),
                                    trace_id,
                                    idempotency_key,
                                    client_id,
                                )
                            elif tool_name == "a2a.task_status":
                                result = await self.a2a_task_status(
                                    tool_params.get("task_id", ""), trace_id
                                )
                            elif tool_name == "a2a.task_result":
                                result = await self.a2a_task_result(
                                    tool_params.get("task_id", ""), trace_id
                                )
                            # Files module tools
                            elif tool_name == "files.generate_presigned_url":
                                result = self.files_module.generate_presigned_url(
                                    file_id=tool_params.get("file_id"),
                                    operation=tool_params.get("operation"),
                                    client_id=tool_params.get("client_id"),
                                )
                            elif tool_name == "files.revoke":
                                result = self.files_module.revoke(
                                    file_id=tool_params.get("file_id")
                                )
                            elif tool_name == "planner.inbox":
                                result = await self.planner_inbox(trace_id)
                            else:
                                result = {
                                    "success": False,
                                    "error": f"Unknown tool: {tool_name}",
                                    "REASON_CODE": "INVALID_TOOL",
                                    "trace_id": trace_id,
                                }
                                logger.log(
                                    trace_id=trace_id,
                                    route="/mcp",
                                    status=400,
                                    reason="INVALID_TOOL",
                                    message=f"Unknown tool: {tool_name}",
                                )
                                response_status = 400

                        # Add toolset version and ruleset sha256 to result
                        if isinstance(result, dict):
                            result["toolset_version"] = TOOLSET_VERSION
                            if "RULESET_SHA256" not in result:
                                result["RULESET_SHA256"] = self.RULESET_SHA256

                        response = {
                            "jsonrpc": "2.0",
                            "id": data.get("id"),
                            "result": {"tool_result": result},
                        }

                        # Determine reason_code for audit log
                        if scope_check_passed and response_status == 200:
                            if isinstance(result, dict) and result.get("success"):
                                reason_code = "TOOL_CALL_SUCCESS"
                            else:
                                reason_code = "TOOL_CALL_FAILED"
                        elif not scope_check_passed:
                            reason_code = "INSUFFICIENT_SCOPE"
                        else:
                            reason_code = "INVALID_TOOL"

                        logger.log(
                            trace_id=trace_id,
                            route="/mcp",
                            status=response_status,
                            message=f"Successfully processed tool call: {tool_name}",
                        )

                        if scope_check_passed:
                            # Calculate idempotency_key_hash if idempotency_key is provided
                            idempotency_key_hash = None
                            if idempotency_key:
                                import hashlib

                                idempotency_key_hash = hashlib.sha256(
                                    idempotency_key.encode()
                                ).hexdigest()

                            # Audit log for tool call
                            logger.audit_log(
                                trace_id=trace_id,
                                task_code=task_code,
                                route="/mcp",
                                auth_mode=auth_mode,
                                auth_result=auth_result,
                                gate_result="PASS",
                                reason_code=reason_code,
                                ruleset_sha256=self.RULESET_SHA256,
                                client_ip=client_ip,
                                request_method=request.method,
                                response_status=response_status,
                                tool_name=tool_name,
                                tool_params=tool_params,
                                duration_ms=int((time.time() - start_time) * 1000),
                                idempotency_key_hash=idempotency_key_hash,
                            )

                # Add toolset version and ruleset sha256 to result
                if isinstance(result, dict):
                    result["toolset_version"] = TOOLSET_VERSION
                    if "RULESET_SHA256" not in result:
                        result["RULESET_SHA256"] = self.RULESET_SHA256

                response = {
                    "jsonrpc": "2.0",
                    "id": data.get("id"),
                    "result": {"tool_result": result},
                }

            # Handle invalid method
            else:
                logger.log(
                    trace_id=trace_id,
                    route="/mcp",
                    status=400,
                    reason="INVALID_METHOD",
                    message=f"Method not found: {method}",
                )
                response = {
                    "jsonrpc": "2.0",
                    "id": data.get("id"),
                    "error": {"code": -32601, "message": f"Method not found: {method}"},
                }
                response_status = 400

                # Audit log for invalid method
                logger.audit_log(
                    trace_id=trace_id,
                    task_code=task_code,
                    route="/mcp",
                    auth_mode=auth_mode,
                    auth_result=auth_result,
                    gate_result="PASS",
                    reason_code="INVALID_METHOD",
                    ruleset_sha256=self.RULESET_SHA256,
                    client_ip=client_ip,
                    request_method=request.method,
                    response_status=response_status,
                    duration_ms=int((time.time() - start_time) * 1000),
                )

        except Exception as e:
            logger.log(
                trace_id=trace_id,
                route="/mcp",
                status=500,
                reason="INTERNAL_ERROR",
                message=f"Internal error: {str(e)}",
            )
            response = {
                "jsonrpc": "2.0",
                "id": data.get("id") if "data" in locals() else None,
                "error": {"code": -32603, "message": f"Internal error: {str(e)}"},
            }
            response_status = 500

            # Audit log for internal error
            logger.audit_log(
                trace_id=trace_id,
                task_code=task_code,
                route="/mcp",
                auth_mode=auth_mode
                if "auth_mode" in locals()
                else self.config["auth"]["jsonrpc"]["type"],
                auth_result=auth_result if "auth_result" in locals() else "UNKNOWN",
                gate_result="PASS",
                reason_code="INTERNAL_ERROR",
                ruleset_sha256=self.RULESET_SHA256,
                client_ip=client_ip,
                request_method=request.method,
                response_status=response_status,
                error_message=str(e),
                duration_ms=int((time.time() - start_time) * 1000),
            )

        # Calculate latency and update histogram
        end_time = time.time()
        latency_ms = int((end_time - start_time) * 1000)

        # Determine latency bucket
        if latency_ms < 10:
            bucket = 10
        elif latency_ms < 50:
            bucket = 50
        elif latency_ms < 100:
            bucket = 100
        elif latency_ms < 500:
            bucket = 500
        elif latency_ms < 1000:
            bucket = 1000
        else:
            bucket = "+Inf"

        self.metrics["latency_ms_bucket"][bucket] += 1

        return web.Response(
            text=json.dumps(response),
            content_type="application/json",
            headers={"X-Trace-ID": trace_id},
        )

    async def handle_sse(self, request):
        """Handle SSE connections with configurable authentication, idle tracking, and backpressure"""
        # Increment total requests counter
        self.metrics["requests_total"] += 1

        # Generate or extract Trace ID
        trace_id = request.headers.get("X-Trace-ID", str(uuid.uuid4()))
        client_id = str(uuid.uuid4())  # Generate client ID for logging

        # Default task_code
        task_code = "SSE_CONNECTION"

        # Get client IP
        client_ip = request.remote

        # SSE authentication based on configured mode
        sse_auth_mode = self.config["auth"]["sse"]["mode"]
        auth_result = "SUCCESS"
        reason_code = "VALID_MODE"
        gate_result = "PASS"
        response_status = 200

        if sse_auth_mode == "oauth":
            try:
                # OAuth authentication mode
                # Extract token from Authorization header
                auth_header = request.headers.get("Authorization")
                logger.log(
                    ts=datetime.now().isoformat(),
                    trace_id=trace_id,
                    client_id=client_id,
                    route=request.path,
                    status="processing",
                    reason="AUTHENTICATING",
                    message=f"OAuth authentication: auth_header={auth_header}",
                )

                if not auth_header or not auth_header.startswith("Bearer "):
                    reason_code = "MISSING_AUTH_HEADER"
                    auth_result = "FAIL"
                    gate_result = "FAIL"
                    response_status = 401
                    # Increment authentication failure counter
                    self.metrics["auth_fail_total"] += 1
                    logger.log(
                        ts=datetime.now().isoformat(),
                        trace_id=trace_id,
                        client_id=client_id,
                        route=request.path,
                        status="401",
                        reason=reason_code,
                        message="Missing or invalid Authorization header",
                    )

                    # Audit log for authentication failure
                    logger.audit_log(
                        trace_id=trace_id,
                        task_code=task_code,
                        route=request.path,
                        auth_mode=sse_auth_mode,
                        auth_result=auth_result,
                        gate_result=gate_result,
                        reason_code=reason_code,
                        ruleset_sha256=self.RULESET_SHA256,
                        client_id=client_id,
                        client_ip=client_ip,
                        request_method=request.method,
                        response_status=response_status,
                    )

                    return web.Response(
                        status=response_status,
                        text=json.dumps(
                            {
                                "error": "Missing or invalid Authorization header",
                                "AUTH_MODE": sse_auth_mode,
                                "REASON_CODE": reason_code,
                            }
                        ),
                        content_type="application/json",
                        headers={"X-Trace-ID": trace_id},
                    )

                token = auth_header[7:]
                logger.log(
                    ts=datetime.now().isoformat(),
                    trace_id=trace_id,
                    client_id=client_id,
                    route=request.path,
                    status="processing",
                    reason="VALIDATING_TOKEN",
                    message=f"OAuth authentication: extracted token={token[:10]}...",
                )

                # Use JWT validation for OAuth
                oauth_config = self.config["auth"]["sse"]["oauth"]
                is_valid, reason_code, payload = self.validate_jwt_token(token, oauth_config)

                if not is_valid:
                    auth_result = "FAIL"
                    gate_result = "FAIL"
                    response_status = 401
                    # Increment authentication failure counter
                    self.metrics["auth_fail_total"] += 1
                    logger.log(
                        ts=datetime.now().isoformat(),
                        trace_id=trace_id,
                        client_id=client_id,
                        route=request.path,
                        status="401",
                        reason=reason_code,
                        message=f"OAuth validation failed: {reason_code}",
                    )

                    # Audit log for authentication failure
                    logger.audit_log(
                        trace_id=trace_id,
                        task_code=task_code,
                        route=request.path,
                        auth_mode=sse_auth_mode,
                        auth_result=auth_result,
                        gate_result=gate_result,
                        reason_code=reason_code,
                        ruleset_sha256=self.RULESET_SHA256,
                        client_id=client_id,
                        client_ip=client_ip,
                        request_method=request.method,
                        response_status=response_status,
                    )

                    return self.generate_error_response(
                        status_code=response_status,
                        error_code="AUTHENTICATION_FAILED",
                        error_message="OAuth validation failed",
                        reason_code=reason_code,
                        trace_id=trace_id,
                    )

                logger.log(
                    ts=datetime.now().isoformat(),
                    trace_id=trace_id,
                    client_id=client_id,
                    route=request.path,
                    status="authorized",
                    reason="AUTH_SUCCESS",
                    message="OAuth authentication successful",
                )
            except Exception as e:
                auth_result = "FAIL"
                gate_result = "FAIL"
                response_status = 500
                reason_code = "INTERNAL_ERROR"
                logger.log(
                    ts=datetime.now().isoformat(),
                    trace_id=trace_id,
                    client_id=client_id,
                    route=request.path,
                    status="500",
                    reason=reason_code,
                    message=f"OAuth authentication failed with exception: {str(e)}",
                )

                # Audit log for authentication exception
                logger.audit_log(
                    trace_id=trace_id,
                    task_code=task_code,
                    route=request.path,
                    auth_mode=sse_auth_mode,
                    auth_result=auth_result,
                    gate_result=gate_result,
                    reason_code=reason_code,
                    ruleset_sha256=self.RULESET_SHA256,
                    client_id=client_id,
                    client_ip=client_ip,
                    request_method=request.method,
                    response_status=response_status,
                    error_message=str(e),
                )

                return web.Response(
                    status=response_status,
                    text=json.dumps(
                        {
                            "error": f"OAuth authentication failed: {str(e)}",
                            "AUTH_MODE": sse_auth_mode,
                            "REASON_CODE": reason_code,
                        }
                    ),
                    content_type="application/json",
                    headers={"X-Trace-ID": trace_id},
                )
        elif sse_auth_mode != "none":
            # Invalid mode - return error
            auth_result = "FAIL"
            gate_result = "FAIL"
            response_status = 500
            reason_code = "INVALID_AUTH_MODE"
            logger.log(
                ts=datetime.now().isoformat(),
                trace_id=trace_id,
                client_id=client_id,
                route=request.path,
                status="500",
                reason=reason_code,
                message=f"Invalid SSE authentication mode: {sse_auth_mode}",
            )

            # Audit log for invalid auth mode
            logger.audit_log(
                trace_id=trace_id,
                task_code=task_code,
                route=request.path,
                auth_mode=sse_auth_mode,
                auth_result=auth_result,
                gate_result=gate_result,
                reason_code=reason_code,
                ruleset_sha256=self.RULESET_SHA256,
                client_id=client_id,
                client_ip=client_ip,
                request_method=request.method,
                response_status=response_status,
            )

            return self.generate_error_response(
                status_code=response_status,
                error_code="INVALID_AUTH_MODE",
                error_message=f"Invalid SSE authentication mode: {sse_auth_mode}",
                reason_code=reason_code,
                trace_id=trace_id,
            )

        # Get client IP
        client_ip = request.remote

        # Check connection limit
        max_connections = self.config["sse"]["max_connections"]
        if len(self.sse_clients) >= max_connections:
            gate_result = "FAIL"
            response_status = 429
            reason_code = "SSE_CONNECTION_LIMIT_EXCEEDED"
            logger.log(
                ts=datetime.now().isoformat(),
                trace_id=trace_id,
                client_id=client_id,
                route=request.path,
                status="429",
                reason=reason_code,
                message=f"Max SSE connections ({max_connections}) exceeded",
            )

            # Audit log for connection limit exceeded
            logger.audit_log(
                trace_id=trace_id,
                task_code=task_code,
                route=request.path,
                auth_mode=sse_auth_mode,
                auth_result=auth_result,
                gate_result=gate_result,
                reason_code=reason_code,
                ruleset_sha256=self.RULESET_SHA256,
                client_id=client_id,
                client_ip=client_ip,
                request_method=request.method,
                response_status=response_status,
            )

            return self.generate_error_response(
                status_code=response_status,
                error_code="RATE_LIMITED",
                error_message="SSE connection limit exceeded",
                reason_code=reason_code,
                trace_id=trace_id,
            )

        # Get token from authentication result or use 'anonymous' for none auth mode
        token = token if "token" in locals() else "anonymous"

        # Check connection limit per token
        max_connections_per_token = self.config["sse"]["max_connections_per_token"]
        if self.sse_connections_per_token[token] >= max_connections_per_token:
            logger.log(
                ts=datetime.now().isoformat(),
                trace_id=trace_id,
                client_id=client_id,
                route=request.path,
                status="429",
                reason="SSE_CONNECTION_LIMIT_PER_TOKEN_EXCEEDED",
                message=f"Max SSE connections per token ({max_connections_per_token}) exceeded for token: {token[:10]}...",
            )
            # Generate standardized error response for per-token connection limit exceeded
            error_response = {
                "error_code": "RATE_LIMITED",
                "error_message": "SSE connection limit exceeded",
                "reason_code": "SSE_CONNECTION_LIMIT_PER_TOKEN_EXCEEDED",
                "trace_id": trace_id,
                "max_connections": max_connections_per_token,
                "current_connections": self.sse_connections_per_token[token],
            }
            return web.Response(
                status=429,
                text=json.dumps(error_response),
                content_type="application/json",
                headers={"X-Trace-ID": trace_id},
            )

        # Authentication passed or disabled
        logger.log(
            ts=datetime.now().isoformat(),
            trace_id=trace_id,
            client_id=client_id,
            route=request.path,
            status="connected",
            reason="CONNECTED",
            message=f"SSE client connected, current clients: {len(self.sse_clients) + 1}, connections for token {token[:10]}...: {self.sse_connections_per_token[token] + 1}/{max_connections_per_token}",
        )

        # Audit log for successful connection
        logger.audit_log(
            trace_id=trace_id,
            task_code=task_code,
            route=request.path,
            auth_mode=sse_auth_mode,
            auth_result=auth_result,
            gate_result=gate_result,
            reason_code=reason_code,
            ruleset_sha256=self.RULESET_SHA256,
            client_id=client_id,
            client_ip=client_ip,
            request_method=request.method,
            response_status=response_status,
        )

        # Increment connection count for this token
        self.sse_connections_per_token[token] += 1

        # Set up SSE response with proper headers for ChatGPT UI compatibility
        response = web.StreamResponse(
            status=200,
            headers={
                "Content-Type": "text/event-stream",
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",  # Disable buffering for SSE
                "X-Trace-ID": trace_id,
                "X-Client-ID": client_id,
            },
        )
        await response.prepare(request)

        # Create SSE client object with max queue size and heartbeat interval from config
        max_queue_size = self.config["sse"]["max_queue"]
        heartbeat_interval = self.config["sse"]["heartbeat_interval"]
        client = SSEClient(
            response, client_ip, trace_id, client_id, max_queue_size, heartbeat_interval
        )
        # Store token in client object for cleanup
        client.token = token
        self.sse_clients.add(client)

        # Update reconnect metrics
        import hashlib

        client_id_hash = hashlib.sha256(client_id.encode()).hexdigest()[:16]

        # Initialize start_time for reconnect metrics
        start_time = time.time()

        # Increment reconnect attempts total for this client
        self.metrics["reconnect_attempts_total"][client_id_hash] += 1

        # Increment reconnect success total for this client (assuming successful connection)
        self.metrics["reconnect_success_total"][client_id_hash] += 1

        # Update reconnect_time_ms_bucket metric (using connection time as proxy for reconnect time)
        # This is a simplified implementation - in real scenarios, we would track the actual reconnect time
        reconnect_time_ms = int((time.time() - start_time) * 1000)
        buckets = [0, 10, 50, 100, 200, 500, 1000, 5000, float("inf")]
        for bucket in buckets:
            if reconnect_time_ms <= bucket:
                if client_id_hash not in self.metrics["reconnect_time_ms_bucket"]:
                    self.metrics["reconnect_time_ms_bucket"][client_id_hash] = defaultdict(int)
                self.metrics["reconnect_time_ms_bucket"][client_id_hash][bucket] += 1
                break

        try:
            # Get SSE configuration
            heartbeat_interval = self.config["sse"]["heartbeat_interval"]
            max_idle_time = self.config["sse"]["max_idle_time"]
            max_queue_size = self.config["sse"]["max_queue"]

            # Send initial connection event in ChatGPT UI compatible format
            initial_msg = {
                "type": "connection",
                "message": "Connected to exchange server",
                "auth_mode": sse_auth_mode,
                "trace_id": trace_id,
                "client_id": client_id,
                "connection_count": len(self.sse_clients),
                "max_queue_size": max_queue_size,
            }

            # Send initial message immediately (not through queue) to ensure fast connection feedback
            initial_sse_data = f"event: connection\ndata: {json.dumps(initial_msg)}\n\n".encode()
            await response.write(initial_sse_data)
            await response.drain()  # Ensure immediate flush

            # Update buffer size
            client.update_buffer_size(len(initial_sse_data))

            # Send periodic heartbeat with proper event type for at least 60 seconds
            start_time = time.time()
            while time.time() - start_time < 70:  # Keep connection alive for at least 70 seconds
                await asyncio.sleep(0.1)  # Check more frequently for queue processing

                # Process message queue
                messages_sent = 0
                while client.message_queue:
                    queued_msg = client.message_queue.popleft()

                    # Format message for SSE
                    sse_data = f"event: {queued_msg['event_type']}\ndata: {json.dumps(queued_msg['message'])}\n\n".encode()

                    try:
                        await response.write(sse_data)
                        # Flush after each write to ensure no buffering
                        await response.drain()
                        messages_sent += 1

                        # Update buffer size and check for backpressure events
                        backpressure_event = client.update_buffer_size(len(sse_data))
                        if backpressure_event is True:
                            logger.log(
                                ts=datetime.now().isoformat(),
                                trace_id=trace_id,
                                client_id=client_id,
                                route=request.path,
                                status="backpressure",
                                reason="BACKPRESSURE_APPLIED",
                                message="Backpressure applied to client due to full buffer",
                            )
                        elif backpressure_event is False:
                            logger.log(
                                ts=datetime.now().isoformat(),
                                trace_id=trace_id,
                                client_id=client_id,
                                route=request.path,
                                status="normal",
                                reason="BACKPRESSURE_RELEASED",
                                message="Backpressure released for client",
                            )
                    except Exception as e:
                        logger.log(
                            ts=datetime.now().isoformat(),
                            trace_id=trace_id,
                            client_id=client_id,
                            route=request.path,
                            status="error",
                            reason="MESSAGE_SEND_FAILED",
                            message=f"Failed to send message: {str(e)}",
                        )
                        break

                # Update last buffer flush time if messages were sent
                if messages_sent > 0:
                    client.last_buffer_flush = time.time()

                # Check if client is idle
                if client.is_idle(max_idle_time):
                    # Send disconnect event before closing
                    disconnect_msg = {
                        "type": "disconnect",
                        "reason": "idle_timeout",
                        "message": f"Client idle for more than {max_idle_time} seconds",
                    }
                    disconnect_data = (
                        f"event: disconnect\ndata: {json.dumps(disconnect_msg)}\n\n".encode()
                    )
                    await response.write(disconnect_data)

                    logger.log(
                        ts=datetime.now().isoformat(),
                        trace_id=trace_id,
                        client_id=client_id,
                        route=request.path,
                        status="disconnected",
                        reason="IDLE_TIMEOUT",
                        message=f"Client idle for more than {max_idle_time} seconds",
                    )
                    break

                # Send heartbeat if backpressure is not active and time for heartbeat
                current_time = time.time()
                if (
                    not client.is_backpressure_active()
                    and current_time - client.last_heartbeat_sent >= heartbeat_interval
                ):
                    # Calculate heartbeat lag (actual delay from expected interval)
                    heartbeat_lag_ms = int(
                        (current_time - client.last_heartbeat_sent - heartbeat_interval) * 1000
                    )

                    # Hash client_id for privacy in metrics
                    import hashlib

                    client_id_hash = hashlib.sha256(client_id.encode()).hexdigest()[:16]

                    # Update heartbeat_lag_ms_bucket metric
                    # Define histogram buckets: 0, 10, 50, 100, 200, 500, 1000, 5000, +Inf
                    buckets = [0, 10, 50, 100, 200, 500, 1000, 5000, float("inf")]

                    # Find the appropriate bucket for this heartbeat lag
                    for bucket in buckets:
                        if heartbeat_lag_ms <= bucket:
                            if client_id_hash not in self.metrics["heartbeat_lag_ms_bucket"]:
                                self.metrics["heartbeat_lag_ms_bucket"][client_id_hash] = (
                                    defaultdict(int)
                                )
                            self.metrics["heartbeat_lag_ms_bucket"][client_id_hash][bucket] += 1
                            break

                    heartbeat_msg = {
                        "type": "heartbeat",
                        "timestamp": datetime.now().isoformat(),
                        "trace_id": trace_id,
                        "client_id": client_id,
                        "queue_size": client.get_queue_size(),
                        "queue_overflow": client.queue_overflow,
                        "heartbeat_delay": client.heartbeat_delay,
                        "heartbeat_lag_ms": heartbeat_lag_ms,  # Add heartbeat lag statistics
                        "heartbeat_delay_anomaly": client.heartbeat_delay_anomaly,
                        "proxy_buffering_risk": client.proxy_buffering_risk,
                        "heartbeat_count": client.heartbeat_count,  # Add heartbeat tick count
                    }

                    # Format and send heartbeat immediately to ensure timing accuracy
                    sse_data = f"event: heartbeat\ndata: {json.dumps(heartbeat_msg)}\n\n".encode()
                    try:
                        await response.write(sse_data)
                        await response.drain()  # Flush immediately after sending heartbeat

                        # Update buffer size and check for backpressure events
                        client.update_buffer_size(len(sse_data))
                    except Exception as e:
                        logger.log(
                            ts=datetime.now().isoformat(),
                            trace_id=trace_id,
                            client_id=client_id,
                            route=request.path,
                            status="error",
                            reason="HEARTBEAT_SEND_FAILED",
                            message=f"Failed to send heartbeat: {str(e)}",
                        )

                    # Log heartbeat with lag and tick count information
                    logger.log(
                        ts=datetime.now().isoformat(),
                        trace_id=trace_id,
                        client_id=client_id,
                        route=request.path,
                        status="heartbeat",
                        reason="HEARTBEAT_SENT",
                        message=f"Heartbeat sent, tick: {client.heartbeat_count}, lag: {heartbeat_lag_ms}ms, queue_size: {client.get_queue_size()}",
                        heartbeat_count=client.heartbeat_count,
                        heartbeat_lag_ms=heartbeat_lag_ms,
                        queue_size=client.get_queue_size(),
                    )

                    # Update heartbeat tracking
                    client.update_heartbeat_sent()
                    client.heartbeat_count += 1  # Increment heartbeat tick count
                    # Update last buffer flush time
                    client.last_buffer_flush = time.time()

                # Detect proxy buffering risk
                proxy_buffering = client.detect_proxy_buffering()
                if proxy_buffering:
                    logger.log(
                        ts=datetime.now().isoformat(),
                        trace_id=trace_id,
                        client_id=client_id,
                        route=request.path,
                        status="warning",
                        reason="PROXY_BUFFERING_RISK",
                        message="Potential proxy buffering detected",
                        time_since_flush=current_time - client.last_buffer_flush,
                        queue_size=client.get_queue_size(),
                    )

                # Detect heartbeat delay anomalies
                if client.heartbeat_delay_anomaly:
                    logger.log(
                        ts=datetime.now().isoformat(),
                        trace_id=trace_id,
                        client_id=client_id,
                        route=request.path,
                        status="warning",
                        reason="HEARTBEAT_DELAY_ANOMALY",
                        message="Heartbeat delay anomaly detected",
                        heartbeat_delay=client.heartbeat_delay,
                        expected_interval=heartbeat_interval,
                    )

                # Update activity timestamp
                client.update_activity()

            # If we exited the loop after 60 seconds, log normal disconnection
            if time.time() - start_time >= 60:
                logger.log(
                    ts=datetime.now().isoformat(),
                    trace_id=trace_id,
                    client_id=client_id,
                    route=request.path,
                    status="disconnected",
                    reason="NORMAL_DISCONNECT",
                    message="Connection closed after 60 seconds test",
                )

        except asyncio.CancelledError:
            logger.log(
                ts=datetime.now().isoformat(),
                trace_id=trace_id,
                client_id=client_id,
                route=request.path,
                status="disconnected",
                reason="CLIENT_CANCELLED",
                message="SSE connection cancelled by client",
            )
        except ConnectionResetError:
            logger.log(
                ts=datetime.now().isoformat(),
                trace_id=trace_id,
                client_id=client_id,
                route=request.path,
                status="disconnected",
                reason="CONNECTION_RESET",
                message="SSE connection reset by client",
            )
        except Exception as e:
            logger.log(
                ts=datetime.now().isoformat(),
                trace_id=trace_id,
                client_id=client_id,
                route=request.path,
                status="error",
                reason="INTERNAL_ERROR",
                message=f"SSE connection error: {str(e)}",
            )
        finally:
            # Remove client from set
            if client in self.sse_clients:
                self.sse_clients.remove(client)
                logger.log(
                    ts=datetime.now().isoformat(),
                    trace_id=trace_id,
                    client_id=client_id,
                    route=request.path,
                    status="disconnected",
                    reason="CLEANUP",
                    message=f"SSE client disconnected, remaining clients: {len(self.sse_clients)}",
                    final_queue_size=client.get_queue_size(),
                    queue_overflow=client.queue_overflow,
                    proxy_buffering_risk=client.proxy_buffering_risk,
                    heartbeat_delay_anomaly=client.heartbeat_delay_anomaly,
                )

    def get_available_tools(self):
        """Get list of available tools"""
        return [
            {
                "name": "ata.search",
                "description": "Search for tasks in ATA ledger",
                "parameters": {
                    "query": {
                        "type": "string",
                        "description": "Search query for TaskCode/owner_role/goal",
                    }
                },
            },
            {
                "name": "ata.fetch",
                "description": "Fetch task details by TaskCode",
                "parameters": {
                    "task_code": {"type": "string", "description": "TaskCode to fetch details for"}
                },
            },
            {
                "name": "a2a.task_create",
                "description": "Create a task in A2A Hub",
                "parameters": {
                    "payload": {"type": "object", "description": "Task payload for A2A Hub"}
                },
            },
            {
                "name": "a2a.task_status",
                "description": "Get status of an A2A task",
                "parameters": {
                    "task_id": {"type": "string", "description": "Task ID to get status for"}
                },
            },
            {
                "name": "a2a.task_result",
                "description": "Get result of an A2A task",
                "parameters": {
                    "task_id": {"type": "string", "description": "Task ID to get result for"}
                },
            },
            {
                "name": "planner.inbox",
                "description": "Get tasks that need planner attention",
                "parameters": {},
            },
        ]

    async def ata_search(self, query, trace_id):
        """Search ATA ledger for tasks"""
        logger.log(
            trace_id=trace_id,
            task_code="ata.search",
            status="processing",
            message=f"Searching ATA ledger with query: {query}",
        )

        try:
            results = []

            # Check if ledger file has changed and refresh cache if needed
            self.check_and_refresh_ata_ledger()

            # Refresh cache if still not available after checking
            if not self.ata_ledger_cache:
                self.refresh_ata_ledger_cache()

            if self.ata_ledger_cache:
                # Use cached ledger entries for faster search
                ledger_entries = self.ata_ledger_cache.get("entries", [])

                for entry in ledger_entries:
                    try:
                        task_code = entry.get("task_code", "")
                        context_path = entry.get("context_path", "")

                        if not task_code or not context_path:
                            continue

                        # Convert context_path to absolute path
                        absolute_context_path = os.path.join(
                            PROJECT_ROOT, context_path.replace("\\", "/")
                        )
                        if not os.path.exists(absolute_context_path):
                            continue

                        # Get directory structure
                        context_path_obj = Path(absolute_context_path)
                        ata_path = context_path_obj.parent  # docs/REPORT/.../artifacts/.../ata
                        artifacts_path = ata_path.parent  # docs/REPORT/.../artifacts/...

                        # Read context.json to get additional details
                        with open(absolute_context_path, encoding="utf-8") as f:
                            context = json.load(f)

                        # Determine report_path
                        report_path = context.get("report_path", "")
                        if not report_path:
                            # Infer report_path from context_path
                            report_dir = artifacts_path.parent.parent  # docs/REPORT/area
                            area = report_dir.name
                            report_files = glob.glob(
                                os.path.join(report_dir, f"**/REPORT__{task_code}*.md"),
                                recursive=True,
                            )
                            if report_files:
                                # Use the first found report file
                                report_path = os.path.relpath(report_files[0], PROJECT_ROOT)

                        # Get summary from context.json and REPORT title
                        summary = context.get("description", "")

                        # Try to extract REPORT title from report file
                        if report_path and os.path.exists(os.path.join(PROJECT_ROOT, report_path)):
                            with open(
                                os.path.join(PROJECT_ROOT, report_path), encoding="utf-8"
                            ) as f:
                                for line in f:
                                    if line.startswith("# "):
                                        # Extract title and add to summary
                                        report_title = line.strip("# ").strip()
                                        if summary:
                                            summary = f"{report_title}: {summary}"
                                        else:
                                            summary = report_title
                                        break

                        # Ensure summary is ≤200 characters
                        if len(summary) > 200:
                            summary = summary[:197] + "..."

                        # Convert paths to relative paths for output
                        rel_ata_path = os.path.relpath(ata_path, PROJECT_ROOT)

                        # Gate check: Verify paths exist and are readable
                        gate_passed = True

                        # Check report_path exists and is readable
                        if report_path:
                            full_report_path = os.path.join(PROJECT_ROOT, report_path)
                            if not os.path.exists(full_report_path) or not os.access(
                                full_report_path, os.R_OK
                            ):
                                gate_passed = False

                        # Check ata_path exists and is readable
                        if not os.access(ata_path, os.R_OK):
                            gate_passed = False

                        # Check context.json exists and is readable
                        if not os.access(absolute_context_path, os.R_OK):
                            gate_passed = False

                        # Only add to results if gate check passes and query matches
                        if gate_passed:
                            # Check if query matches
                            if (
                                query.lower() in task_code.lower()
                                or query.lower() in summary.lower()
                                or query.lower() in str(context).lower()
                            ):
                                results.append(
                                    {
                                        "task_code": task_code,
                                        "report_path": report_path,
                                        "ata_path": rel_ata_path,
                                        "summary": summary,
                                    }
                                )

                    except Exception as e:
                        logger.log(
                            trace_id=trace_id,
                            task_code="ata.search",
                            status="warning",
                            reason="SEARCH_CACHE_ERROR",
                            message=f"Error processing entry {entry.get('task_code', 'unknown')}: {str(e)}",
                        )
                        continue
            else:
                # Fallback to original implementation if cache unavailable
                logger.log(
                    trace_id=trace_id,
                    task_code="ata.search",
                    status="warning",
                    reason="CACHE_UNAVAILABLE",
                    message="ATA ledger cache unavailable, falling back to file search",
                )

                # Search all context.json files in docs/REPORT/**/artifacts/**/ata/
                search_pattern = os.path.join(
                    PROJECT_ROOT, "docs", "REPORT", "**", "artifacts", "**", "ata", "context.json"
                )
                context_files = glob.glob(search_pattern, recursive=True)

                # Search through each context.json file
                for context_file in context_files:
                    try:
                        # Get the directory structure
                        context_path = Path(context_file)
                        ata_path = context_path.parent  # docs/REPORT/.../artifacts/.../ata
                        artifacts_path = ata_path.parent  # docs/REPORT/.../artifacts/...

                        # Extract task_code from directory name or context.json
                        with open(context_file, encoding="utf-8") as f:
                            context = json.load(f)

                        task_code = context.get("task_code", artifacts_path.name)

                        # Determine report_path
                        report_path = context.get("report_path", "")
                        if not report_path:
                            # Infer report_path from context_file path
                            report_dir = artifacts_path.parent.parent  # docs/REPORT/area
                            area = report_dir.name
                            report_files = glob.glob(
                                os.path.join(report_dir, f"**/REPORT__{task_code}*.md"),
                                recursive=True,
                            )
                            if report_files:
                                # Use the first found report file
                                report_path = os.path.relpath(report_files[0], PROJECT_ROOT)

                        # Get summary from context.json and REPORT title
                        summary = context.get("description", "")

                        # Try to extract REPORT title from report file
                        if report_path and os.path.exists(os.path.join(PROJECT_ROOT, report_path)):
                            with open(
                                os.path.join(PROJECT_ROOT, report_path), encoding="utf-8"
                            ) as f:
                                for line in f:
                                    if line.startswith("# "):
                                        # Extract title and add to summary
                                        report_title = line.strip("# ").strip()
                                        if summary:
                                            summary = f"{report_title}: {summary}"
                                        else:
                                            summary = report_title
                                        break

                        # Ensure summary is ≤200 characters
                        if len(summary) > 200:
                            summary = summary[:197] + "..."

                        # Convert paths to relative paths for output
                        rel_ata_path = os.path.relpath(ata_path, PROJECT_ROOT)

                        # Gate check: Verify paths exist and are readable
                        gate_passed = True

                        # Check report_path exists and is readable
                        if report_path:
                            full_report_path = os.path.join(PROJECT_ROOT, report_path)
                            if not os.path.exists(full_report_path) or not os.access(
                                full_report_path, os.R_OK
                            ):
                                gate_passed = False

                        # Check ata_path exists and is readable
                        if not os.access(ata_path, os.R_OK):
                            gate_passed = False

                        # Check context.json exists and is readable
                        if not os.access(context_file, os.R_OK):
                            gate_passed = False

                        # Only add to results if gate check passes and query matches
                        if gate_passed:
                            # Check if query matches
                            if (
                                query.lower() in task_code.lower()
                                or query.lower() in summary.lower()
                                or query.lower() in str(context).lower()
                            ):
                                results.append(
                                    {
                                        "task_code": task_code,
                                        "report_path": report_path,
                                        "ata_path": rel_ata_path,
                                        "summary": summary,
                                    }
                                )

                    except Exception as e:
                        logger.log(
                            trace_id=trace_id,
                            task_code="ata.search",
                            status="warning",
                            reason="SEARCH_FILE_ERROR",
                            message=f"Error processing {context_file}: {str(e)}",
                        )
                        continue

            # Sort results by task_code
            results.sort(key=lambda x: x["task_code"])

            # Return topK results (default: 10)
            topK = 10
            results = results[:topK]

            logger.log(
                trace_id=trace_id,
                task_code="ata.search",
                status="completed",
                message=f"Found {len(results)} results for query: {query}",
            )

            return {"success": True, "results": results, "trace_id": trace_id}

        except Exception as e:
            logger.log(
                trace_id=trace_id,
                task_code="ata.search",
                status="error",
                reason="SEARCH_FAILED",
                message=f"ATA search failed: {str(e)}",
            )
            return {"success": False, "error": str(e), "trace_id": trace_id}

    async def planner_inbox(self, trace_id):
        """Get tasks that need planner attention"""
        logger.log(
            trace_id=trace_id,
            task_code="planner.inbox",
            status="processing",
            message="Fetching planner inbox tasks",
        )

        try:
            # Import taskctl module
            import sys
            from pathlib import Path

            sys.path.insert(0, str(Path(__file__).parent.parent))
            from taskctl import TaskRegistry

            # Initialize task registry
            # Use project root for tasks directory, not tools directory
            registry_path = Path(Path(__file__).parent.parent.parent, "tasks", "registry.yaml")
            registry = TaskRegistry(registry_path)

            # Get all tasks
            all_tasks = registry.get_all_tasks()

            # Filter tasks that need planner attention
            inbox_tasks = []

            for task in all_tasks:
                # Check if task needs planner attention
                # Tasks that need planner: needs_planner=true or status=blocked
                if task.get("needs_planner") == True or task.get("status") == "BLOCKED":
                    # Create task entry with required fields
                    task_entry = {
                        "task_code": task["id"],
                        "area": task.get("area", "general"),  # Area from task or default
                        "priority": task.get("priority", "medium"),  # Priority from task or default
                        "trace_id": trace_id,
                        "report_path": task.get("report_path", ""),  # Report path if available
                        "ata_path": task.get("ata_path", ""),  # ATA path if available
                        "last_update": task.get("updated_at", task.get("created_at", "")),
                    }

                    # Validate paths exist
                    if task_entry["report_path"] and not Path(task_entry["report_path"]).exists():
                        return {
                            "success": False,
                            "error": f"Invalid report_path for task {task_entry['task_code']}",
                            "REASON_CODE": "PATH_NOT_FOUND",
                            "trace_id": trace_id,
                        }

                    if task_entry["ata_path"] and not Path(task_entry["ata_path"]).exists():
                        return {
                            "success": False,
                            "error": f"Invalid ata_path for task {task_entry['task_code']}",
                            "REASON_CODE": "PATH_NOT_FOUND",
                            "trace_id": trace_id,
                        }

                    inbox_tasks.append(task_entry)

            result = {
                "success": True,
                "tasks": inbox_tasks,
                "total": len(inbox_tasks),
                "trace_id": trace_id,
            }

            logger.log(
                trace_id=trace_id,
                task_code="planner.inbox",
                status="completed",
                message=f"Found {len(inbox_tasks)} planner inbox tasks",
            )

            return result
        except Exception as e:
            logger.log(
                trace_id=trace_id,
                task_code="planner.inbox",
                status="error",
                reason="INTERNAL_ERROR",
                message=f"Error fetching planner inbox: {str(e)}",
            )
            return {
                "success": False,
                "error": f"Error fetching planner inbox: {str(e)}",
                "REASON_CODE": "INTERNAL_ERROR",
                "trace_id": trace_id,
            }

    async def ata_fetch(self, task_code, trace_id):
        """Fetch task details by TaskCode"""
        logger.log(
            trace_id=trace_id,
            task_code="ata.fetch",
            status="processing",
            message=f"Fetching task details for TaskCode: {task_code}",
        )

        try:
            # 1. Verify gate checks before returning result
            is_valid, reason_code, ruleset_sha256 = await self.verify_gate_checks(task_code)
            if not is_valid:
                logger.log(
                    trace_id=trace_id,
                    task_code="ata.fetch",
                    status="failed",
                    reason=reason_code,
                    message=f"Gate verification failed for TaskCode: {task_code}",
                )
                return {
                    "success": False,
                    "error": "Gate verification failed",
                    "REASON_CODE": reason_code,
                    "RULESET_SHA256": ruleset_sha256,
                    "trace_id": trace_id,
                }

            # 2. Get task area
            task_area = self.get_task_area(task_code)

            # 3. Construct absolute paths
            artifacts_dir = os.path.join(
                PROJECT_ROOT, "docs", "REPORT", task_area, "artifacts", task_code
            )
            submit_txt_path = os.path.join(artifacts_dir, "SUBMIT.txt")
            context_json_path = os.path.join(artifacts_dir, "ata", "context.json")

            # 4. Check if files exist
            has_submit_txt = os.path.exists(submit_txt_path)
            has_context_json = os.path.exists(context_json_path)

            # 5. Construct relative paths for response
            rel_artifacts_dir = f"docs/REPORT/{task_area}/artifacts/{task_code}"
            rel_submit_txt = f"{rel_artifacts_dir}/SUBMIT.txt" if has_submit_txt else None
            rel_context_json = f"{rel_artifacts_dir}/ata/context.json" if has_context_json else None

            result = {
                "success": True,
                "task_code": task_code,
                "files": {"submit_txt": rel_submit_txt, "context_json": rel_context_json},
                "RULESET_SHA256": ruleset_sha256,
                "trace_id": trace_id,
            }

            # 6. Add content if files exist
            if has_submit_txt:
                with open(submit_txt_path, encoding="utf-8") as f:
                    result["submit_txt_content"] = f.read()

            if has_context_json:
                with open(context_json_path, encoding="utf-8") as f:
                    result["context_json_content"] = json.load(f)
                    # Add trace_id to context.json if it doesn't exist
                    if "trace_id" not in result["context_json_content"]:
                        result["context_json_content"]["trace_id"] = trace_id

            logger.log(
                trace_id=trace_id,
                task_code="ata.fetch",
                status="completed",
                message=f"Successfully fetched task details for TaskCode: {task_code}",
                ruleset_sha256=ruleset_sha256,
            )

            return result

        except Exception as e:
            logger.log(
                trace_id=trace_id,
                task_code="ata.fetch",
                status="error",
                reason="FETCH_FAILED",
                message=f"Failed to fetch task details: {str(e)}",
            )
            return {"success": False, "error": str(e), "trace_id": trace_id}

    def get_task_goal(self, task_code):
        """Get task goal from context.json"""
        try:
            # Try to get area from ATA ledger
            area = self.get_task_area(task_code)
            context_path = os.path.join(
                PROJECT_ROOT, "docs", "REPORT", area, "artifacts", task_code, "ata", "context.json"
            )

            if os.path.exists(context_path):
                with open(context_path, encoding="utf-8") as f:
                    context = json.load(f)
                    return context.get("goal", "")
        except Exception as e:
            print(f"[WARNING] Failed to get task goal for {task_code}: {str(e)}")

        return ""

    def calculate_sha256(self, file_path):
        """Calculate SHA256 hash of a file"""
        sha256_hash = hashlib.sha256()
        with open(file_path, "rb") as f:
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256_hash.update(byte_block)
        return sha256_hash.hexdigest()

    def calculate_ruleset_sha256(self):
        """Calculate SHA256 hash of the ruleset"""
        # Calculate SHA256 of all relevant schema files
        sha256_hash = hashlib.sha256()

        # List of schema files to include in the ruleset hash
        schema_files = [
            # Exchange tool contract schema
            os.path.join(
                PROJECT_ROOT,
                "tools",
                "exchange_server",
                "schemas",
                "exchange_tool_contract.schema.json",
            ),
            # Gatekeeper ATA context schema
            os.path.join(PROJECT_ROOT, "tools", "gatekeeper", "schemas", "ata_context.schema.json"),
        ]

        for file_path in schema_files:
            if os.path.exists(file_path):
                # Read and update hash for each schema file
                try:
                    with open(file_path, "rb") as f:
                        for byte_block in iter(lambda: f.read(4096), b""):
                            sha256_hash.update(byte_block)
                except Exception as e:
                    print(f"[ERROR] Failed to read schema file {file_path}: {str(e)}")

        return sha256_hash.hexdigest()

    def load_ata_schema(self):
        """Load ATA schema"""
        schema_path = os.path.join(
            PROJECT_ROOT, "tools", "gatekeeper", "schemas", "ata_context.schema.json"
        )
        try:
            with open(schema_path, encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"[ERROR] Failed to load ATA schema: {str(e)}")
            return None

    def validate_ata_schema(self, context_data):
        """Validate ATA context against schema"""
        schema = self.load_ata_schema()
        if not schema:
            return False, "SCHEMA_LOAD_FAILED"

        try:
            jsonschema.validate(instance=context_data, schema=schema)
            return True, "SCHEMA_VALID"
        except jsonschema.exceptions.ValidationError as e:
            print(f"[ERROR] ATA schema validation failed: {str(e)}")
            return False, "SCHEMA_VALIDATION_FAILED"

    async def verify_gate_checks(self, task_code):
        """Verify gate checks before returning task result"""
        try:
            # Calculate RULESET_SHA256 first for consistent return value
            ruleset_path = os.path.join(
                PROJECT_ROOT, "tools", "gatekeeper", "schemas", "ata_context.schema.json"
            )
            ruleset_sha256 = (
                self.calculate_sha256(ruleset_path) if os.path.exists(ruleset_path) else "N/A"
            )

            # 1. Get task area and construct paths
            task_area = self.get_task_area(task_code)
            artifacts_dir = os.path.join(
                PROJECT_ROOT, "docs", "REPORT", task_area, "artifacts", task_code
            )

            # 2. Check 三件套存在 (three-piece set)
            submit_txt_path = os.path.join(artifacts_dir, "SUBMIT.txt")
            context_json_path = os.path.join(artifacts_dir, "ata", "context.json")

            if not os.path.exists(submit_txt_path):
                return False, "MISSING_SUBMIT_TXT", ruleset_sha256

            if not os.path.exists(context_json_path):
                return False, "MISSING_CONTEXT_JSON", ruleset_sha256

            # 3. Validate ATA schema
            with open(context_json_path, encoding="utf-8") as f:
                context_data = json.load(f)

            is_schema_valid, schema_result = self.validate_ata_schema(context_data)
            if not is_schema_valid:
                return False, schema_result, ruleset_sha256

            # 4. Check evidence_paths 全部存在
            evidence_paths = context_data.get("evidence_paths", [])
            if not evidence_paths:
                return False, "MISSING_EVIDENCE_PATHS", ruleset_sha256

            for path in evidence_paths:
                full_path = os.path.join(PROJECT_ROOT, path)
                if not os.path.exists(full_path):
                    return False, "EVIDENCE_PATH_NOT_EXIST", ruleset_sha256

            # 5. Check ledger sha alignment
            ledger_updated = False
            ledger_sha_matched = False

            with open(ATA_LEDGER_PATH, encoding="utf-8") as f:
                ledger = json.load(f)

            # Calculate current context.json sha
            context_sha = self.calculate_sha256(context_json_path)

            for entry in ledger.get("entries", []):
                if entry.get("task_code") == task_code:
                    ledger_updated = True
                    # Check if ledger has the correct sha for context.json
                    if entry.get("context_sha") == context_sha:
                        ledger_sha_matched = True
                    break

            if not ledger_updated:
                return False, "LEDGER_NOT_UPDATED", ruleset_sha256

            if not ledger_sha_matched:
                return False, "SHA_MISMATCH", ruleset_sha256

            # 6. Check selftest.log EXIT_CODE!=0
            selftest_log_path = None
            # Find selftest.log in evidence_paths
            for path in evidence_paths:
                if "selftest.log" in path:
                    selftest_log_path = os.path.join(PROJECT_ROOT, path)
                    break

            if selftest_log_path and os.path.exists(selftest_log_path):
                with open(selftest_log_path, encoding="utf-8") as f:
                    selftest_content = f.read()

                # Check if EXIT_CODE=0 is present at the end
                if "EXIT_CODE=0" not in selftest_content.splitlines()[-10:]:
                    return False, "SELFTEST_FAILED", ruleset_sha256

            return True, "GATE_PASS", ruleset_sha256

        except Exception as e:
            print(f"[ERROR] Gate verification failed: {str(e)}")
            # Calculate RULESET_SHA256 even on exception
            ruleset_path = os.path.join(
                PROJECT_ROOT, "tools", "gatekeeper", "schemas", "ata_context.schema.json"
            )
            ruleset_sha256 = (
                self.calculate_sha256(ruleset_path) if os.path.exists(ruleset_path) else "N/A"
            )
            return False, "GATE_VERIFICATION_FAILED", ruleset_sha256

    def get_task_area(self, task_code):
        """Get task area from ATA ledger"""
        try:
            with open(ATA_LEDGER_PATH, encoding="utf-8") as f:
                ledger = json.load(f)

            for entry in ledger.get("entries", []):
                if entry.get("task_code") == task_code:
                    return entry.get("area", "ata")
        except Exception as e:
            print(f"[WARNING] Failed to get task area for {task_code}: {str(e)}")

        return "ata"

    async def a2a_task_create(self, payload, trace_id, idempotency_key=None, client_id=None):
        """Create a task in A2A Hub with idempotency support"""
        # Calculate idempotency_key_hash if idempotency_key is provided
        idempotency_key_hash = None
        if idempotency_key:
            idempotency_key_hash = hashlib.sha256(idempotency_key.encode()).hexdigest()

        logger.log(
            trace_id=trace_id,
            task_code="a2a.task_create",
            status="processing",
            message=f"Creating task with payload: {json.dumps(payload)}, idempotency_key: {idempotency_key_hash}",
        )

        try:
            # Check if idempotency_key is provided and we've already processed this request
            if idempotency_key and client_id:
                if (
                    client_id in self.idempotent_requests
                    and idempotency_key in self.idempotent_requests[client_id]
                ):
                    # Return the existing task_id for idempotent requests
                    existing_task_id = self.idempotent_requests[client_id][idempotency_key]
                    logger.log(
                        trace_id=trace_id,
                        task_code="a2a.task_create",
                        status="completed",
                        message=f"Returning existing task for idempotent request: {existing_task_id}",
                    )
                    return {
                        "success": True,
                        "task_id": existing_task_id,
                        "trace_id": trace_id,
                        "idempotency_reused": True,
                    }

            # Mock implementation for A2A Hub create
            # In real implementation, this would call the actual A2A Hub API
            # Generate unique task_id with random component for absolute uniqueness
            task_id = f"task_{time.time():.6f}_{uuid.uuid4().hex[:8]}".replace(".", "")

            # Store task information (in real implementation, this would be in a database)
            if not hasattr(self, "a2a_tasks"):
                self.a2a_tasks = {}

            self.a2a_tasks[task_id] = {
                "status": "pending",
                "payload": payload,
                "trace_id": trace_id,
                "created_at": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat(),
                "client_id": client_id,
                "idempotency_key": idempotency_key,
                "idempotency_key_hash": idempotency_key_hash,
            }

            # Store the idempotent request mapping if applicable
            if idempotency_key and client_id:
                self.idempotent_requests[client_id][idempotency_key] = task_id

            logger.log(
                trace_id=trace_id,
                task_code="a2a.task_create",
                status="completed",
                message=f"Successfully created task: {task_id}",
            )

            return {
                "success": True,
                "task_id": task_id,
                "trace_id": trace_id,
                "idempotency_reused": False,
            }

        except Exception as e:
            logger.log(
                trace_id=trace_id,
                task_code="a2a.task_create",
                status="error",
                reason="A2A_CREATE_FAILED",
                message=f"Failed to create task: {str(e)}",
            )
            return {
                "success": False,
                "error": str(e),
                "REASON_CODE": "A2A_CREATE_FAILED",
                "trace_id": trace_id,
            }

    async def a2a_task_status(self, task_id, trace_id):
        """Get status of an A2A task"""
        logger.log(
            trace_id=trace_id,
            task_code="a2a.task_status",
            status="processing",
            message=f"Getting status for task: {task_id}",
        )

        try:
            # Mock implementation for A2A Hub status
            if not hasattr(self, "a2a_tasks") or task_id not in self.a2a_tasks:
                logger.log(
                    trace_id=trace_id,
                    task_code="a2a.task_status",
                    status="error",
                    reason="A2A_TASK_NOT_FOUND",
                    message=f"Task not found: {task_id}",
                )
                return {
                    "success": False,
                    "error": f"Task not found: {task_id}",
                    "REASON_CODE": "A2A_TASK_NOT_FOUND",
                    "trace_id": trace_id,
                }

            task = self.a2a_tasks[task_id]

            # Simulate task progression
            if task["status"] == "pending":
                # Randomly move to running state for demo purposes
                if datetime.now().timestamp() - float(task_id.split("_")[1]) > 5:
                    task["status"] = "running"
                    task["updated_at"] = datetime.now().isoformat()
                    logger.log(
                        trace_id=task.get("trace_id", trace_id),
                        task_code="a2a.task_status",
                        status="updated",
                        message=f"Task {task_id} moved to running state",
                    )
            elif task["status"] == "running":
                # Randomly move to completed state for demo purposes
                if datetime.now().timestamp() - float(task_id.split("_")[1]) > 10:
                    task["status"] = "completed"
                    task["updated_at"] = datetime.now().isoformat()
                    # Mock result with task_code for ATA integration
                    task["result"] = {
                        "task_code": "EXCHANGE-A2A-BRIDGE-v0.1__20260115",
                        "artifact_url": "docs/REPORT/ci/artifacts/EXCHANGE-A2A-BRIDGE-v0.1__20260115",
                        "trace_id": task.get("trace_id", trace_id),
                    }
                    logger.log(
                        trace_id=task.get("trace_id", trace_id),
                        task_code="a2a.task_status",
                        status="completed",
                        message=f"Task {task_id} completed",
                    )

            logger.log(
                trace_id=trace_id,
                task_code="a2a.task_status",
                status="completed",
                message=f"Successfully got status for task: {task_id}, status: {task['status']}",
            )

            return {
                "success": True,
                "status": task["status"],
                "created_at": task["created_at"],
                "updated_at": task["updated_at"],
                "trace_id": trace_id,
            }

        except Exception as e:
            logger.log(
                trace_id=trace_id,
                task_code="a2a.task_status",
                status="error",
                reason="A2A_STATUS_FAILED",
                message=f"Failed to get task status: {str(e)}",
            )
            return {
                "success": False,
                "error": str(e),
                "REASON_CODE": "A2A_STATUS_FAILED",
                "trace_id": trace_id,
            }

    async def a2a_task_result(self, task_id, trace_id):
        """Get result of an A2A task and verify with ATA ledger"""
        logger.log(
            trace_id=trace_id,
            task_code="a2a.task_result",
            status="processing",
            message=f"Getting result for task: {task_id}",
        )

        try:
            # Mock implementation for A2A Hub result
            if not hasattr(self, "a2a_tasks") or task_id not in self.a2a_tasks:
                logger.log(
                    trace_id=trace_id,
                    task_code="a2a.task_result",
                    status="error",
                    reason="A2A_TASK_NOT_FOUND",
                    message=f"Task not found: {task_id}",
                )
                return {
                    "success": False,
                    "error": f"Task not found: {task_id}",
                    "REASON_CODE": "A2A_TASK_NOT_FOUND",
                    "trace_id": trace_id,
                }

            task = self.a2a_tasks[task_id]

            if task["status"] != "completed":
                logger.log(
                    trace_id=trace_id,
                    task_code="a2a.task_result",
                    status="error",
                    reason="A2A_TASK_NOT_COMPLETED",
                    message=f"Task not completed: {task_id}",
                )
                return {
                    "success": False,
                    "error": f"Task not completed: {task_id}",
                    "REASON_CODE": "A2A_TASK_NOT_COMPLETED",
                    "trace_id": trace_id,
                }

            if "result" not in task:
                logger.log(
                    trace_id=trace_id,
                    task_code="a2a.task_result",
                    status="error",
                    reason="A2A_RESULT_NOT_AVAILABLE",
                    message=f"Task result not available: {task_id}",
                )
                return {
                    "success": False,
                    "error": f"Task result not available: {task_id}",
                    "REASON_CODE": "A2A_RESULT_NOT_AVAILABLE",
                    "trace_id": trace_id,
                }

            result = task["result"]
            task_code = result["task_code"]

            # 1. Verify gate checks before returning result
            is_valid, reason_code, ruleset_sha256 = await self.verify_gate_checks(task_code)
            if not is_valid:
                logger.log(
                    trace_id=trace_id,
                    task_code="a2a.task_result",
                    status="error",
                    reason=reason_code,
                    message=f"Gate verification failed for TaskCode: {task_code}",
                    ruleset_sha256=ruleset_sha256,
                )
                return {
                    "success": False,
                    "error": "Gate verification failed",
                    "REASON_CODE": reason_code,
                    "RULESET_SHA256": ruleset_sha256,
                    "trace_id": trace_id,
                }

            # 2. Verify with ATA ledger
            try:
                with open(ATA_LEDGER_PATH, encoding="utf-8") as f:
                    ledger = json.load(f)

                # Check if task exists in ledger
                task_found = False
                for entry in ledger.get("entries", []):
                    if entry.get("task_code") == task_code:
                        task_found = True
                        break

                if not task_found:
                    logger.log(
                        trace_id=trace_id,
                        task_code="a2a.task_result",
                        status="error",
                        reason="ATA_LEDGER_TASK_NOT_FOUND",
                        message=f"Task not found in ATA ledger: {task_code}",
                        ruleset_sha256=ruleset_sha256,
                    )
                    return {
                        "success": False,
                        "error": f"Task not found in ATA ledger: {task_code}",
                        "REASON_CODE": "ATA_LEDGER_TASK_NOT_FOUND",
                        "RULESET_SHA256": ruleset_sha256,
                        "trace_id": trace_id,
                    }

                # Check if files exist and are accessible via ata.fetch
                test_fetch = await self.ata_fetch(task_code, trace_id)
                if not test_fetch["success"]:
                    logger.log(
                        trace_id=trace_id,
                        task_code="a2a.task_result",
                        status="error",
                        reason="ATA_FETCH_FAILED",
                        message=f"Failed to fetch task details from ATA: {test_fetch['error']}",
                        ruleset_sha256=ruleset_sha256,
                    )
                    return {
                        "success": False,
                        "error": f"Failed to fetch task details from ATA: {test_fetch['error']}",
                        "REASON_CODE": "ATA_FETCH_FAILED",
                        "RULESET_SHA256": ruleset_sha256,
                        "trace_id": trace_id,
                    }

                # Verify required files exist
                if not test_fetch["files"]["submit_txt"] or not test_fetch["files"]["context_json"]:
                    logger.log(
                        trace_id=trace_id,
                        task_code="a2a.task_result",
                        status="error",
                        reason="ATA_FILES_MISSING",
                        message=f"Required files not found in ATA: submit_txt={test_fetch['files']['submit_txt']}, context_json={test_fetch['files']['context_json']}",
                        ruleset_sha256=ruleset_sha256,
                    )
                    return {
                        "success": False,
                        "error": f"Required files not found in ATA: submit_txt={test_fetch['files']['submit_txt']}, context_json={test_fetch['files']['context_json']}",
                        "REASON_CODE": "ATA_FILES_MISSING",
                        "RULESET_SHA256": ruleset_sha256,
                        "trace_id": trace_id,
                    }
            except Exception as e:
                logger.log(
                    trace_id=trace_id,
                    task_code="a2a.task_result",
                    status="error",
                    reason="ATA_VERIFICATION_FAILED",
                    message=f"ATA ledger verification failed: {str(e)}",
                    ruleset_sha256=ruleset_sha256,
                )
                return {
                    "success": False,
                    "error": f"ATA ledger verification failed: {str(e)}",
                    "REASON_CODE": "ATA_VERIFICATION_FAILED",
                    "RULESET_SHA256": ruleset_sha256,
                    "trace_id": trace_id,
                }

            logger.log(
                trace_id=trace_id,
                task_code="a2a.task_result",
                status="completed",
                message=f"Successfully got result for task: {task_id}",
                ruleset_sha256=ruleset_sha256,
            )

            return {
                "success": True,
                "result": result,
                "task_code": task_code,
                "RULESET_SHA256": ruleset_sha256,
                "trace_id": trace_id,
            }

        except Exception as e:
            logger.log(
                trace_id=trace_id,
                task_code="a2a.task_result",
                status="error",
                reason="A2A_RESULT_FAILED",
                message=f"Failed to get task result: {str(e)}",
            )
            return {
                "success": False,
                "error": str(e),
                "REASON_CODE": "A2A_RESULT_FAILED",
                "trace_id": trace_id,
            }

    async def handle_version(self, request):
        """Handle version requests"""
        import subprocess

        # Get git SHA
        try:
            git_sha = subprocess.check_output(
                ["git", "rev-parse", "HEAD"], cwd=PROJECT_ROOT, universal_newlines=True
            ).strip()
        except (subprocess.CalledProcessError, FileNotFoundError):
            git_sha = "unknown"

        # Get build time (current time)
        build_time = datetime.utcnow().isoformat() + "Z"

        # Return version information
        version_info = {
            "git_sha": git_sha,
            "build_time": build_time,
            "toolset_version": TOOLSET_VERSION,
            "RULESET_SHA256": self.RULESET_SHA256,
        }

        return web.Response(text=json.dumps(version_info), content_type="application/json")

    def run(self, host="0.0.0.0", port=8080):
        """Run the server"""
        web.run_app(self.app, host=host, port=port)


def main():
    """Main function"""
    import sys

    # Check if running in unified server mode
    import os
    if os.getenv('UNIFIED_SERVER_MODE') == '1':
        print("Exchange Server: Running in unified server mode - independent startup disabled")
        return 0

    # Check required secrets before starting the server
    check_required_secrets()

    # Check if --version flag is provided
    if "--version" in sys.argv:
        import subprocess

        # Get git SHA
        try:
            git_sha = subprocess.check_output(
                ["git", "rev-parse", "HEAD"], cwd=PROJECT_ROOT, universal_newlines=True
            ).strip()
        except (subprocess.CalledProcessError, FileNotFoundError):
            git_sha = "unknown"

        # Get build time (current time)
        build_time = datetime.utcnow().isoformat() + "Z"

        # Create a temporary server instance to get RULESET_SHA256
        server = ExchangeServer()

        # Print version information
        version_info = {
            "git_sha": git_sha,
            "build_time": build_time,
            "toolset_version": TOOLSET_VERSION,
            "RULESET_SHA256": server.RULESET_SHA256,
        }

        print(json.dumps(version_info, indent=2))
        return 0

    # Parse command line arguments
    port = 8080
    host = "0.0.0.0"
    auth_mode = None

    for arg in sys.argv[1:]:
        if arg.startswith("--port="):
            port = int(arg.split("=")[1])
        elif arg.startswith("--host="):
            host = arg.split("=")[1]
        elif arg.startswith("--auth-mode="):
            auth_mode = arg.split("=")[1]

    # Create server with optional auth_mode
    server = ExchangeServer(auth_mode=auth_mode)
    print("Exchange Server starting...")
    print("JSON-RPC: POST /mcp")
    print("SSE: GET /sse")
    print("ChatGPT SSE: GET /mcp/messages")
    print("Version: GET /version")
    print(
        "Available tools: ata.search, ata.fetch, a2a.task_create, a2a.task_status, a2a.task_result"
    )
    print("Press Ctrl+C to stop")

    server.run(host=host, port=port)


# Check for required secrets - fail-closed if missing
def check_required_secrets():
    """Check if all required secrets are present"""
    import os
    import sys

    # Check if auth is disabled via command line or environment
    auth_disabled = False

    # Check command line arguments
    for arg in sys.argv[1:]:
        if arg == "--auth-mode=none":
            auth_disabled = True
            break

    # Check environment variables
    if (
        os.getenv("OAUTH_DISABLED_FOR_CI", "0") == "1"
        or os.getenv("EXCHANGE_JSONRPC_AUTH_TYPE", "bearer") == "none"
    ):
        auth_disabled = True

    # Only check required OAuth secrets if auth is enabled
    if not auth_disabled:
        required_secrets = ["OAUTH_CLIENT_ID", "OAUTH_CLIENT_SECRET", "OAUTH_ISSUER_URL"]

        missing_secrets = []
        for secret in required_secrets:
            if secret not in os.environ:
                missing_secrets.append(secret)

        if missing_secrets:
            for secret in missing_secrets:
                print(f"ERROR: Missing required secret: {secret}")
                print(f"REASON_CODE: MISSING_REQUIRED_SECRET_{secret}")
            print("EXIT_CODE=1")
            sys.exit(1)


if __name__ == "__main__":
    # Check required secrets before starting the server
    check_required_secrets()
    main()
