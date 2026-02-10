#!/usr/bin/env python3
"""
A2A Hub - Minimal implementation

This is a minimal A2A Hub that supports:
- task.create: Create new tasks with TaskCode, instructions, owner_role, and optional deadline
- task.status: Query task status
- task.result: Submit task results with artifact pointers and sha256 hashes

Storage: SQLite database in tools/a2a_hub/state/
"""

import datetime
import hashlib
import json
import os
import sqlite3
import uuid

from flask import Flask, g, jsonify, request

app = Flask(__name__)

# RBAC Configuration
# Define roles and their permissions
ROLES = {
    "submitter": ["create", "read_all"],
    # Worker must be able to:
    # - register itself (/api/agent/register => assign)
    # - poll tasks & heartbeat (/api/task/next, /api/task/heartbeat => read_all)
    # - report results (/api/task/result => report_result)
    # NOTE: Worker is still NOT allowed to create tasks.
    "worker": ["report_result", "read_all", "assign"],
    "auditor": ["read_all"],
    "admin": ["create", "assign", "report_result", "replay_dlq", "read_all"],
}

# Map API endpoints to required permissions
# Format: (endpoint, method) -> permission
ENDPOINT_PERMISSIONS = {
    # Task endpoints
    ("/api/task/create", "POST"): "create",
    ("/api/task/status", "GET"): "read_all",
    ("/api/task/result", "POST"): "report_result",
    ("/api/task/next", "GET"): "read_all",
    ("/api/task/heartbeat", "POST"): "read_all",
    ("/api/task/routing", "POST"): "read_all",
    # DLQ endpoints
    ("/api/dlq/list", "GET"): "read_all",
    ("/api/dlq", "GET"): "read_all",
    ("/api/dlq/replay", "POST"): "replay_dlq",
    ("/api/dlq/<dlq_id>", "GET"): "read_all",
    ("/api/dlq/task/<task_code>", "GET"): "read_all",
    # Agent endpoints
    ("/api/agent/register", "POST"): "assign",
    ("/api/agent/list", "GET"): "read_all",
    ("/api/agent/<agent_id>", "GET"): "read_all",
    ("/api/agent/<agent_id>", "PUT"): "assign",
    ("/api/agent/<agent_id>", "DELETE"): "assign",
}

# Metrics counters
metrics = {"tasks_created": 0, "tasks_done": 0, "tasks_fail": 0, "queue_depth": 0}

# Configuration
STATE_DIR = os.path.join(os.path.dirname(__file__), "state")
DB_PATH = os.path.join(STATE_DIR, "a2a_hub.db")

# Secret key for artifact signing (from environment variable)
# No default - must be set via environment variable
SECRET_KEY = os.environ.get("A2A_HUB_SECRET_KEY")

# Priority Aging Configuration
PRIORITY_AGING_CONFIG = {
    "aging_threshold": 300,  # Time in seconds before a low priority task gets aged
    "aging_step": 1,  # How much to increase priority by when aging
    "max_priority": 3,  # Maximum priority level
    "min_priority": 0,  # Minimum priority level
    "check_interval": 60,  # How often to check for tasks that need aging (seconds)
}

# Task status transitions (state machine)
TASK_STATUS_TRANSITIONS = {
    "PENDING": {"RUNNING", "FAIL"},
    "RUNNING": {"DONE", "FAIL", "PENDING"},
    "DONE": set(),
    "FAIL": {"PENDING", "DLQ"},
    "DLQ": set(),
}


def is_valid_status_transition(current_status: str, target_status: str) -> bool:
    if not current_status or not target_status:
        return True
    if current_status == target_status:
        return True
    return target_status in TASK_STATUS_TRANSITIONS.get(current_status, set())


# RBAC Helper Functions
def get_hashed_identity(identity):
    """
    Return a hashed version of the identity for logging purposes
    """
    if not identity:
        return "unknown"
    return hashlib.sha256(identity.encode()).hexdigest()


def get_user_role():
    """
    Get the user role from the request headers
    """
    return request.headers.get("X-A2A-Role", "submitter")


def get_user_token():
    """
    Get the user token from the request headers
    """
    return request.headers.get("X-A2A-Token", "")


def check_permission(role, permission):
    """
    Check if a role has the required permission
    """
    if role not in ROLES:
        return False
    return permission in ROLES[role]


def get_required_permission(endpoint, method):
    """
    Get the required permission for a given endpoint and method
    """
    # Check exact match first
    if (endpoint, method) in ENDPOINT_PERMISSIONS:
        return ENDPOINT_PERMISSIONS[(endpoint, method)]

    # Check for wildcard endpoints (like /api/agent/<agent_id>)
    for (key_endpoint, key_method), permission in ENDPOINT_PERMISSIONS.items():
        if "<" in key_endpoint and method == key_method:
            # Extract base path without parameter
            base_key = key_endpoint.split("/<")[0] + "/"
            base_endpoint = endpoint.split("/")[0] + "/" + "/".join(endpoint.split("/")[1:-1]) + "/"
            if base_key == base_endpoint:
                return permission

    # Default to read_all for unknown endpoints
    return "read_all"


# Ensure state directory exists
os.makedirs(STATE_DIR, exist_ok=True)


# Authentication and Authorization Middleware
@app.before_request
def before_request():
    """
    Middleware to authenticate and authorize requests
    """
    # Skip authentication for health check and version endpoints
    if request.path in ["/api/health", "/version"]:
        return None

    # Get user role from headers
    role = get_user_role()
    token = get_user_token()

    # Get required permission for the endpoint
    endpoint = request.path
    method = request.method
    required_permission = get_required_permission(endpoint, method)

    # Check if the role has the required permission
    if not check_permission(role, required_permission):
        # Log the unauthorized access attempt with hashed token
        hashed_token = get_hashed_identity(token)
        now = datetime.datetime.utcnow().isoformat() + "Z"
        log_entry = {
            "timestamp": now,
            "level": "ERROR",
            "component": "rbac",
            "event": "UNAUTHORIZED_ACCESS",
            "role": role,
            "endpoint": endpoint,
            "token_hash": hashed_token,
            "reason_code": "acl_denied",
            "message": f"Role {role} does not have permission {required_permission} for endpoint {endpoint}",
        }
        print(json.dumps(log_entry))

        return jsonify(
            {
                "success": False,
                "error": f"Role {role} does not have permission {required_permission}",
                "reason_code": "acl_denied",
            }
        ), 403

    # Store user information in g for use in routes
    g.user_role = role
    g.token_hash = get_hashed_identity(token)

    return None


def verify_artifact_signature(artifact):
    """
    Verify the signature of an artifact pointer package.

    Args:
        artifact (dict): Artifact pointer package

    Returns:
        tuple: (success, reason_code, message)
    """
    import hashlib
    import hmac
    import json
    from datetime import datetime, timedelta

    # Check if signature fields exist
    required_fields = ["signature", "signed_at", "signing_algorithm"]
    for field in required_fields:
        if field not in artifact:
            return False, "ARTIFACT_SIGNATURE_MISSING", f"Missing required field: {field}"

    # Check if signing algorithm is supported
    if artifact["signing_algorithm"] != "HMAC-SHA256":
        return (
            False,
            "ARTIFACT_SIGNATURE_ALGORITHM_INVALID",
            f"Unsupported signing algorithm: {artifact['signing_algorithm']}",
        )

    # Check if signature is expired (5 minutes)
    try:
        signed_at = datetime.fromisoformat(artifact["signed_at"].replace("Z", "+00:00"))
        # Use offset-naive datetime for comparison
        signed_at_naive = signed_at.replace(tzinfo=None)
        now_naive = datetime.utcnow()
        if now_naive - signed_at_naive > timedelta(minutes=5):
            return False, "ARTIFACT_SIGNATURE_EXPIRED", "Signature expired (older than 5 minutes)"
    except ValueError:
        return False, "ARTIFACT_SIGNATURE_INVALID", "Invalid signed_at format"

    # Create a copy of the artifact without signature fields
    artifact_copy = artifact.copy()
    for field in required_fields:
        del artifact_copy[field]

    # Serialize to standard JSON string (no spaces, sorted keys)
    try:
        artifact_json = json.dumps(artifact_copy, separators=(",", ":"), sort_keys=True)
    except Exception as e:
        return False, "ARTIFACT_SIGNATURE_INVALID", f"Failed to serialize artifact: {e}"

    # Calculate expected signature
    try:
        expected_signature = hmac.new(
            SECRET_KEY.encode(), artifact_json.encode(), hashlib.sha256
        ).hexdigest()
    except Exception as e:
        return False, "ARTIFACT_SIGNATURE_INVALID", f"Failed to calculate signature: {e}"

    # Compare signatures
    if not hmac.compare_digest(expected_signature, artifact["signature"]):
        return False, "ARTIFACT_SIGNATURE_INVALID", "Invalid signature"

    # Signature is valid
    return True, None, "Signature verified successfully"


def init_db():
    """Initialize the database."""
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.execute("PRAGMA busy_timeout = 5000")
    cursor = conn.cursor()

    # Create tasks table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS tasks (
        id TEXT PRIMARY KEY,
        task_code TEXT NOT NULL,
        instructions TEXT NOT NULL,
        owner_role TEXT NOT NULL,
        deadline TEXT,
        status TEXT DEFAULT 'PENDING',
        result TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        timeout_seconds INTEGER DEFAULT 3600,
        retry_count INTEGER DEFAULT 0,
        max_retries INTEGER DEFAULT 3,
        agent_id TEXT,
        next_retry_ts TEXT,
        retry_backoff_sec INTEGER DEFAULT 60,
        reason_code TEXT,
        last_error TEXT,
        lease_expiry_ts TEXT,
        lease_seconds INTEGER DEFAULT 60,
        priority INTEGER DEFAULT 0,
        area TEXT,
        worker_type TEXT,
        routing_decision TEXT,
        trace_id TEXT,
        dependencies TEXT,
        message_id TEXT
    )
    """)

    # ---- schema migration (fail-safe) ----
    # Ensure tasks has message_id (older DBs won't)
    cursor.execute("PRAGMA table_info(tasks)")
    task_columns = [column[1] for column in cursor.fetchall()]
    if "message_id" not in task_columns:
        cursor.execute("ALTER TABLE tasks ADD COLUMN message_id TEXT")

    # Switch idempotency key: message_id (task_code is display label only)
    # Drop old task_code unique index if it exists
    try:
        cursor.execute("DROP INDEX IF EXISTS idx_task_code_unique")
    except Exception:
        pass

    # Non-unique index for task_code (query performance / legacy)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_task_code ON tasks (task_code)")

    # Unique index for message_id (idempotency). Keep NULL allowed for legacy.
    # Partial unique index prevents multiple non-NULL message_id rows.
    cursor.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_message_id_unique ON tasks (message_id) WHERE message_id IS NOT NULL"
    )

    # Create agents table for registry
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS agents (
        id TEXT PRIMARY KEY,
        agent_id TEXT NOT NULL,
        owner_role TEXT NOT NULL,
        capabilities TEXT NOT NULL,
        online INTEGER DEFAULT 1,
        last_seen TEXT NOT NULL,
        allowed_tools TEXT NOT NULL,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        capacity INTEGER DEFAULT 1,
        available_capacity INTEGER DEFAULT 1,
        completion_limit_per_minute INTEGER DEFAULT 60,
        current_completion_count INTEGER DEFAULT 0,
        completion_window_start TEXT NOT NULL,
        worker_type TEXT
    )
    """)

    # ---- schema migration (fail-safe) ----
    # Ensure agents has worker_type (older DBs won't)
    cursor.execute("PRAGMA table_info(agents)")
    agent_columns = [column[1] for column in cursor.fetchall()]
    if "worker_type" not in agent_columns:
        cursor.execute("ALTER TABLE agents ADD COLUMN worker_type TEXT")

    # Create unique index for agent_id
    cursor.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_agent_id_unique ON agents (agent_id)")

    # Create DLQ table for failed tasks if it doesn't exist
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS dlq (
        id TEXT PRIMARY KEY,
        task_code TEXT NOT NULL,
        task_id TEXT,
        message_id TEXT,
        trace_id TEXT NOT NULL,
        reason_code TEXT NOT NULL,
        last_error TEXT,
        task_data TEXT NOT NULL,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        replay_who TEXT,
        replay_when TEXT,
        replay_why TEXT
    )
    """)

    # Check if the dlq table has the new columns, if not, add them
    cursor.execute("PRAGMA table_info(dlq)")
    dlq_columns = [column[1] for column in cursor.fetchall()]

    if "task_id" not in dlq_columns:
        cursor.execute("ALTER TABLE dlq ADD COLUMN task_id TEXT")
    if "message_id" not in dlq_columns:
        cursor.execute("ALTER TABLE dlq ADD COLUMN message_id TEXT")
    if "replay_who" not in dlq_columns:
        cursor.execute("ALTER TABLE dlq ADD COLUMN replay_who TEXT")
    if "replay_when" not in dlq_columns:
        cursor.execute("ALTER TABLE dlq ADD COLUMN replay_when TEXT")
    if "replay_why" not in dlq_columns:
        cursor.execute("ALTER TABLE dlq ADD COLUMN replay_why TEXT")

    # Create routing_rules table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS routing_rules (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        rule_id TEXT NOT NULL,
        condition TEXT NOT NULL,
        target_worker TEXT NOT NULL,
        priority INTEGER NOT NULL,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """)

    # Create routing_audit table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS routing_audit (
        id TEXT PRIMARY KEY,
        trace_id TEXT NOT NULL,
        routing_decision TEXT NOT NULL,
        timestamp TEXT NOT NULL,
        input TEXT NOT NULL,
        output TEXT NOT NULL
    )
    """)

    # Create workflows table for workflow management
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS workflows (
        id TEXT PRIMARY KEY,
        workflow_id TEXT NOT NULL,
        name TEXT NOT NULL,
        status TEXT DEFAULT 'ACTIVE',
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        last_recovery_time TEXT,
        recovery_status TEXT
    )
    """)

    # Create unique index for workflow_id
    cursor.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_workflow_id_unique ON workflows (workflow_id)"
    )

    # Insert default routing rules
    cursor.execute("SELECT COUNT(*) FROM routing_rules")
    if cursor.fetchone()[0] == 0:
        now = datetime.datetime.utcnow().isoformat() + "Z"
        default_rules = [
            ("R1", "area=ci/exchange", "Trae", 100, now, now),
            ("R2", "owner_role=SRE Engineer", "Cursor", 90, now, now),
            ("R3", "priority>=2", "Trae", 80, now, now),
            ("R4", "area=ci/controlplane", "Trae", 70, now, now),
            ("R5", 'task_code starts with "ATA-"', "Trae", 60, now, now),
            ("R6", "default", "Other", 10, now, now),
        ]
        cursor.executemany(
            """
        INSERT INTO routing_rules (rule_id, condition, target_worker, priority, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
            default_rules,
        )

    conn.commit()
    conn.close()


def get_routing_decision(task_data):
    """
    Get routing decision for a task based on routing rules

    Args:
        task_data: Dictionary containing task information

    Returns:
        tuple: (worker_type, routing_decision, trace_id)
    """
    # Generate trace_id
    trace_id = str(uuid.uuid4())

    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.execute("PRAGMA busy_timeout = 5000")
    cursor = conn.cursor()

    # Get all routing rules ordered by priority desc
    cursor.execute(
        "SELECT rule_id, condition, target_worker FROM routing_rules ORDER BY priority DESC"
    )
    rules = cursor.fetchall()

    # Default result
    worker_type = "Other"
    routing_decision = "Matched by default rule"

    # Extract task attributes
    task_code = task_data.get("TaskCode", "")
    area = task_data.get("area", "")
    owner_role = task_data.get("owner_role", "")
    priority = task_data.get("priority", 0)

    # Apply rules
    for rule_id, condition, target_worker in rules:
        if condition == "default":
            # Default rule, always match if no other rules matched
            worker_type = target_worker
            routing_decision = f"Matched by {rule_id}: {condition}"
            break

        # Parse and evaluate condition
        matched = False
        if ">=" in condition:
            # Greater than or equal condition
            key, value = condition.split(">=", 1)
            key = key.strip()
            value = value.strip()

            if key == "priority" and priority >= int(value):
                matched = True
        elif "=" in condition and not condition.startswith("task_code starts with"):
            # Simple equality condition
            key, value = condition.split("=", 1)
            key = key.strip()
            value = value.strip()

            if key == "area" and area == value or key == "owner_role" and owner_role == value:
                matched = True
        elif condition.startswith("task_code starts with"):
            # Starts with condition
            prefix = condition.split('"')[1]
            if task_code.startswith(prefix):
                matched = True

        if matched:
            worker_type = target_worker
            routing_decision = f"Matched by {rule_id}: {condition}"
            break

    conn.close()

    # Log routing decision
    now = datetime.datetime.utcnow().isoformat() + "Z"

    # Store in audit table
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        """
    INSERT INTO routing_audit (id, trace_id, routing_decision, timestamp, input, output)
    VALUES (?, ?, ?, ?, ?, ?)
    """,
        (
            str(uuid.uuid4()),
            trace_id,
            routing_decision,
            now,
            json.dumps(task_data),
            json.dumps({"worker_type": worker_type, "routing_decision": routing_decision}),
        ),
    )
    conn.commit()
    conn.close()

    return worker_type, routing_decision, trace_id


@app.route("/api/task/routing", methods=["POST"])
def get_task_routing():
    """Get routing decision for a task"""
    task_data = request.json

    # Validate required fields
    required_fields = ["task_code", "area", "owner_role", "priority"]
    for field in required_fields:
        if field not in task_data:
            return jsonify({"error": f"Missing required field: {field}"}), 400

    # Convert to the same format as create_task
    formatted_task_data = {
        "TaskCode": task_data["task_code"],
        "area": task_data["area"],
        "owner_role": task_data["owner_role"],
        "priority": task_data["priority"],
    }

    worker_type, routing_decision, trace_id = get_routing_decision(formatted_task_data)

    return jsonify(
        {
            "success": True,
            "result": {
                "worker_type": worker_type,
                "routing_decision": routing_decision,
                "trace_id": trace_id,
            },
            "trace_id": trace_id,
        }
    )


@app.route("/api/task/create", methods=["POST"])
def create_task():
    """Create a new task (idempotent)."""
    data = request.json

    # Map old field name to new field name for backward compatibility
    task_data = data.copy()
    if "TaskCode" in task_data:
        task_data["task_code"] = task_data.pop("TaskCode")
    # Optional backward-compat alias
    if "MessageId" in task_data and "message_id" not in task_data:
        task_data["message_id"] = task_data.pop("MessageId")

    # Validate required fields for task template
    required_fields = [
        "task_code",
        "area",
        "owner_role",
        "instructions",
        "how_to_repro",
        "expected",
        "evidence_requirements",
    ]
    missing_fields = [
        field for field in required_fields if field not in task_data or not task_data[field]
    ]

    if missing_fields:
        return jsonify(
            {
                "success": False,
                "error": f"Missing required fields: {missing_fields}",
                "reason_code": "invalid_task_template",
            }
        ), 400

    # Idempotency key: message_id (task_code is display label only).
    # Backward-compat: if message_id is not provided, derive a deterministic legacy id from task_code.
    message_id = task_data.get("message_id")
    if not message_id:
        message_id = f"legacy:{task_data['task_code']}"
    task_data["message_id"] = message_id

    # Routing decision (used for both task metadata and agent selection)
    worker_type, routing_decision, trace_id = get_routing_decision(task_data)

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Check if task already exists by message_id
    cursor.execute(
        "SELECT id, status, agent_id, task_code FROM tasks WHERE message_id = ?",
        (task_data["message_id"],),
    )
    existing_task = cursor.fetchone()
    if existing_task:
        conn.close()
        return jsonify(
            {
                "success": True,
                "task_id": existing_task[0],
                "task_code": existing_task[3],
                "status": existing_task[1],
                "agent_id": existing_task[2],
                "message_id": task_data["message_id"],
            }
        )

    # Extract required capabilities from instructions
    instructions = task_data["instructions"].lower()

    # Find a matching agent based on area/owner_role (queue partitioning)
    # Get all online agents with available capacity that match the task's area and owner_role
    agent_sql = """
    SELECT agent_id, owner_role, capabilities, allowed_tools, available_capacity,
           completion_limit_per_minute, current_completion_count, completion_window_start, worker_type
    FROM agents
    WHERE online = 1 AND available_capacity > 0 AND owner_role = ?
    """
    agent_params: list = [task_data["owner_role"]]
    # Only enforce strict worker_type matching for Cursor tasks.
    # For other worker types (e.g. Trae/Other), allow legacy agents with NULL worker_type.
    if worker_type == "Cursor":
        agent_sql += " AND worker_type = ?"
        agent_params.append(worker_type)

    cursor.execute(agent_sql, tuple(agent_params))
    agents = cursor.fetchall()

    matched_agent = None
    for agent in agents:
        agent_id = agent[0]
        agent_owner_role = agent[1]
        capabilities_str = agent[2]
        allowed_tools_str = agent[3]
        available_capacity = agent[4]
        completion_limit_per_minute = agent[5]
        current_completion_count = agent[6]
        completion_window_start = agent[7]

        capabilities = json.loads(capabilities_str)
        allowed_tools = json.loads(allowed_tools_str)

        # Check if agent has required capabilities
        # Simple capability matching - check if any capability is mentioned in instructions
        capability_match = False
        for capability in capabilities:
            if capability.lower() in instructions:
                capability_match = True
                break

        # If no specific capabilities mentioned, match any agent with the right owner_role
        if not capability_match:
            capability_match = True

        if capability_match:
            # Check if agent is within completion limit per minute
            # First reset window if needed
            window_start_dt = datetime.datetime.fromisoformat(
                completion_window_start.replace("Z", "+00:00")
            ).replace(tzinfo=None)
            now = datetime.datetime.utcnow()

            # Reset window if needed
            if (now - window_start_dt).total_seconds() >= 60:
                # Reset completion count
                cursor.execute(
                    """
                UPDATE agents 
                SET current_completion_count = 0, completion_window_start = ? 
                WHERE agent_id = ?
                """,
                    (now.isoformat() + "Z", agent_id),
                )
                conn.commit()
                current_completion_count = 0

            # Check if within limit
            if current_completion_count < completion_limit_per_minute:
                matched_agent = agent_id
                break

    if not matched_agent:
        conn.close()
        return jsonify(
            {
                "success": False,
                "error": "No matching agent found with available capacity and completion limit",
                "reason_code": "AGENT_QUOTA_EXCEEDED",
                "task_code": task_data["task_code"],
            }
        ), 400

    # Create new task if it doesn't exist and assign to matched agent
    task_id = str(uuid.uuid4())
    now = datetime.datetime.utcnow().isoformat() + "Z"

    # Get priority from request, default to 0, validate range 0-3
    priority = task_data.get("priority", 0)
    # Ensure priority is within 0-3 range
    if priority < 0:
        priority = 0
    elif priority > 3:
        priority = 3

    # Handle dependencies
    dependencies = task_data.get("dependencies", [])
    if isinstance(dependencies, list):
        dependencies_json = json.dumps(dependencies)
    else:
        dependencies_json = json.dumps([])

    try:
        cursor.execute(
            """
        INSERT INTO tasks (
            id, task_code, instructions, owner_role, deadline, status, 
            result, created_at, updated_at, timeout_seconds, max_retries, agent_id,
            next_retry_ts, retry_backoff_sec, priority, area, worker_type,
            routing_decision, trace_id, dependencies, message_id
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
            (
                task_id,
                task_data["task_code"],
                task_data["instructions"],
                task_data["owner_role"],
                task_data.get("deadline"),
                "PENDING",
                None,
                now,
                now,
                task_data.get("timeout_seconds", 3600),
                task_data.get("max_retries", 3),
                matched_agent,
                None,
                task_data.get("retry_backoff_sec", 60),
                priority,
                task_data["area"],
                worker_type,
                routing_decision,
                trace_id,
                dependencies_json,
                task_data["message_id"],
            ),
        )

        # Increment tasks_created counter for new tasks
        metrics["tasks_created"] += 1
        # Increment queue_depth for new pending tasks
        metrics["queue_depth"] += 1

        # Log task creation with hashed token
        log_entry = {
            "timestamp": now,
            "level": "INFO",
            "component": "task",
            "event": "TASK_CREATED",
            "task_id": task_id,
            "task_code": task_data["task_code"],
            "message_id": task_data["message_id"],
            "role": g.user_role,
            "token_hash": g.token_hash,
            "message": f"Task {task_data['task_code']} created by role {g.user_role}",
        }
        print(json.dumps(log_entry))

        # 扣减agent的available_capacity
        cursor.execute(
            """
        UPDATE agents
        SET available_capacity = available_capacity - 1, updated_at = ?
        WHERE agent_id = ?
        """,
            (now, matched_agent),
        )

        conn.commit()
        conn.close()

        return jsonify(
            {
                "success": True,
                "task_id": task_id,
                "task_code": task_data["task_code"],
                "message_id": task_data["message_id"],
                "status": "PENDING",
                "agent_id": matched_agent,
                "timeout_seconds": task_data.get("timeout_seconds", 3600),
                "max_retries": task_data.get("max_retries", 3),
            }
        )
    except sqlite3.IntegrityError:
        # Handle race condition where task was created between check and insert
        conn.rollback()
        cursor.execute(
            "SELECT id, status, agent_id, task_code FROM tasks WHERE message_id = ?",
            (task_data["message_id"],),
        )
        existing_task = cursor.fetchone()
        conn.close()

        if existing_task:
            return jsonify(
                {
                    "success": True,
                    "task_id": existing_task[0],
                    "task_code": existing_task[3],
                    "status": existing_task[1],
                    "agent_id": existing_task[2],
                    "message_id": task_data["message_id"],
                }
            )
        else:
            return jsonify({"error": "Failed to create task due to race condition"}), 500


@app.route("/api/task/status", methods=["GET"])
def get_task_status():
    """Query task status."""
    task_code = request.args.get("task_code")
    task_id = request.args.get("task_id")
    message_id = request.args.get("message_id")

    if not task_code and not task_id and not message_id:
        return jsonify({"error": "Missing task_code, task_id, or message_id parameter"}), 400

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    if message_id:
        cursor.execute(
            "SELECT * FROM tasks WHERE message_id = ? ORDER BY created_at DESC LIMIT 1",
            (message_id,),
        )
    elif task_id:
        cursor.execute("SELECT * FROM tasks WHERE id = ?", (task_id,))
    else:
        cursor.execute("SELECT * FROM tasks WHERE task_code = ? ORDER BY created_at DESC LIMIT 1", (task_code,))

    task = cursor.fetchone()
    conn.close()

    if not task:
        return jsonify({"error": "Task not found"}), 404

    # Format the response with all fields including timeout, retry information, and priority
    task_dict = {
        "id": task[0],
        "task_code": task[1],
        "instructions": task[2],
        "owner_role": task[3],
        "deadline": task[4],
        "status": task[5],
        "result": json.loads(task[6]) if task[6] else None,
        "created_at": task[7],
        "updated_at": task[8],
        "timeout_seconds": task[9],
        "retry_count": task[10],
        "max_retries": task[11],
        "agent_id": task[12],
        "next_retry_ts": task[13],
        "retry_backoff_sec": task[14],
        "reason_code": task[15],
        "last_error": task[16],
        "priority": task[19] if len(task) > 19 else 0,  # Priority is at index 19
        "message_id": task[25] if len(task) > 25 else None,
    }

    return jsonify({"success": True, "task": task_dict})


@app.route("/api/task/heartbeat", methods=["POST"])
def task_heartbeat():
    """Update task heartbeat and extend lease."""
    data = request.json

    # Validate required fields
    required_fields = ["task_id"]
    for field in required_fields:
        if field not in data:
            return jsonify({"error": f"Missing required field: {field}"}), 400

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Check if task exists and is in RUNNING status
    task_id = data["task_id"]
    cursor.execute("SELECT id, status, agent_id, lease_seconds FROM tasks WHERE id = ?", (task_id,))
    task = cursor.fetchone()

    if not task:
        conn.close()
        return jsonify({"error": "Task not found"}), 404

    if task[1] != "RUNNING":
        conn.close()
        return jsonify({"error": f"Task is not in RUNNING status (current: {task[1]})"}), 400

    # Calculate new lease expiry time
    now = datetime.datetime.utcnow()
    lease_seconds = task[3] if task[3] else 60  # Default to 60 seconds if not set
    new_lease_expiry = now + datetime.timedelta(seconds=lease_seconds)
    new_lease_expiry_ts = new_lease_expiry.isoformat() + "Z"
    updated_at = now.isoformat() + "Z"

    # Update task lease
    cursor.execute(
        """
    UPDATE tasks
    SET lease_expiry_ts = ?, updated_at = ?
    WHERE id = ?
    """,
        (new_lease_expiry_ts, updated_at, task_id),
    )

    conn.commit()
    conn.close()

    return jsonify(
        {
            "success": True,
            "message": "Heartbeat received, lease extended",
            "task_id": task_id,
            "new_lease_expiry": new_lease_expiry_ts,
            "lease_seconds": lease_seconds,
        }
    )


@app.route("/api/task/next", methods=["GET"])
def get_next_task():
    """Get next pending task for a specific agent, considering retry schedule."""
    agent_id = request.args.get("agent_id")

    if not agent_id:
        return jsonify({"error": "Missing agent_id parameter"}), 400

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Get current time for retry scheduling
    now = datetime.datetime.utcnow().isoformat() + "Z"

    # Get agent info to determine which queue it belongs to
    cursor.execute(
        """
    SELECT owner_role 
    FROM agents 
    WHERE agent_id = ?
    """,
        (agent_id,),
    )
    agent_info = cursor.fetchone()
    if not agent_info:
        conn.close()
        return jsonify({"success": True, "task": None, "message": "Agent not found"})

    agent_owner_role = agent_info[0]

    # ACK 丢失/重复恢复：若该 agent 已有未过期 lease 的 RUNNING 任务，优先返回同一任务
    try:
        cursor.execute(
            """
        SELECT * FROM tasks
        WHERE status = 'RUNNING' AND agent_id = ? AND lease_expiry_ts IS NOT NULL AND lease_expiry_ts > ?
        ORDER BY updated_at DESC
        LIMIT 1
        """,
            (agent_id, now),
        )
        running_task = cursor.fetchone()
        if running_task:
            # Extend lease on re-delivery to avoid accidental expiry during ACK 恢复
            now_dt = datetime.datetime.utcnow()
            lease_seconds = running_task[18] if len(running_task) > 18 and running_task[18] else 60
            lease_expiry = now_dt + datetime.timedelta(seconds=lease_seconds)
            lease_expiry_ts = lease_expiry.isoformat() + "Z"
            updated_at = now_dt.isoformat() + "Z"
            cursor.execute(
                """
            UPDATE tasks
            SET lease_expiry_ts = ?, updated_at = ?
            WHERE id = ? AND status = 'RUNNING'
            """,
                (lease_expiry_ts, updated_at, running_task[0]),
            )
            conn.commit()
            conn.close()

            task_dict = {
                "id": running_task[0],
                "task_code": running_task[1],
                "instructions": running_task[2],
                "owner_role": running_task[3],
                "deadline": running_task[4],
                "status": "RUNNING",
                "result": json.loads(running_task[6]) if running_task[6] else None,
                "created_at": running_task[7],
                "updated_at": updated_at,
                "timeout_seconds": running_task[9],
                "retry_count": running_task[10],
                "max_retries": running_task[11],
                "agent_id": running_task[12],
                "next_retry_ts": None,
                "retry_backoff_sec": running_task[14],
                "reason_code": running_task[15],
                "last_error": running_task[16],
                "lease_expiry_ts": lease_expiry_ts,
                "lease_seconds": lease_seconds,
                "lease_expiry": lease_expiry_ts,
                "priority": running_task[19] if len(running_task) > 19 else 0,
                "area": running_task[20] if len(running_task) > 20 else None,
                "worker_type": running_task[21] if len(running_task) > 21 else None,
                "routing_decision": running_task[22] if len(running_task) > 22 else None,
                "trace_id": running_task[23] if len(running_task) > 23 else None,
                "dependencies": running_task[24] if len(running_task) > 24 else None,
                "message_id": running_task[25] if len(running_task) > 25 else None,
            }
            return jsonify(
                {
                    "success": True,
                    "task": task_dict,
                    "message": "Re-delivering leased RUNNING task (ACK recovery)",
                }
            )
    except Exception:
        # Fall through to normal pending selection
        pass

    # Get all pending tasks for this agent that match its owner_role (queue partitioning)
    # Tasks with the same owner_role belong to the same queue
    cursor.execute(
        """
    SELECT * FROM tasks 
    WHERE status = 'PENDING' AND agent_id = ? AND owner_role = ? 
        AND (next_retry_ts IS NULL OR next_retry_ts <= ?)
    ORDER BY 
        CASE WHEN next_retry_ts IS NULL THEN 0 ELSE 1 END, 
        priority DESC, 
        created_at ASC
    """,
        (agent_id, agent_owner_role, now),
    )

    tasks = cursor.fetchall()

    selected_task = None
    now_dt = datetime.datetime.utcnow().isoformat() + "Z"

    for task in tasks:
        task_id = task[0]
        dependencies_json = task[24] if len(task) > 24 else None

        # Check if task has dependencies
        if dependencies_json:
            try:
                dependencies = json.loads(dependencies_json)
            except json.JSONDecodeError:
                dependencies = []

            if dependencies:
                # Check status of all dependencies
                all_dependencies_done = True
                any_dependency_failed = False

                for dep_task_id in dependencies:
                    cursor.execute("SELECT status FROM tasks WHERE id = ?", (dep_task_id,))
                    dep_status = cursor.fetchone()

                    if dep_status:
                        dep_status = dep_status[0]
                        if dep_status != "DONE":
                            all_dependencies_done = False
                            if dep_status == "FAIL" or dep_status == "DLQ":
                                any_dependency_failed = True
                                break
                    else:
                        # Dependency task not found, consider it as failed
                        all_dependencies_done = False
                        any_dependency_failed = True
                        break

                if any_dependency_failed:
                    # Block the task if any dependency failed
                    cursor.execute(
                        """
                    UPDATE tasks 
                    SET status = ?, updated_at = ?, reason_code = ? 
                    WHERE id = ?
                    """,
                        ("BLOCKED", now_dt, "dep_failed", task_id),
                    )
                    conn.commit()
                    continue

                if not all_dependencies_done:
                    # Skip this task, dependencies not ready yet
                    continue

        # Task has no dependencies or all dependencies are DONE
        selected_task = task
        break

    if not selected_task:
        conn.close()
        return jsonify(
            {"success": True, "task": None, "message": "No pending tasks found for this agent"}
        )

    # Calculate lease expiry time
    now_dt = datetime.datetime.utcnow()
    lease_seconds = 60  # Default lease time
    lease_expiry = now_dt + datetime.timedelta(seconds=lease_seconds)
    lease_expiry_ts = lease_expiry.isoformat() + "Z"
    updated_at = now_dt.isoformat() + "Z"

    # Update task status to RUNNING, clear next_retry_ts, and set lease
    # Use atomic update with status check to prevent race conditions
    cursor.execute(
        """
    UPDATE tasks 
    SET status = ?, updated_at = ?, next_retry_ts = ?, lease_expiry_ts = ?, lease_seconds = ? 
    WHERE id = ? AND status = 'PENDING'
    """,
        ("RUNNING", updated_at, None, lease_expiry_ts, lease_seconds, selected_task[0]),
    )

    # Check if the update was successful (affected rows > 0)
    if cursor.rowcount == 0:
        conn.close()
        # Task was already assigned to another worker, try again
        return jsonify(
            {
                "success": True,
                "task": None,
                "message": "Task was already assigned to another worker",
            }
        )

    conn.commit()
    conn.close()

    # Format the response with all new retry fields, lease information, and priority
    task_dict = {
        "id": selected_task[0],
        "task_code": selected_task[1],
        "instructions": selected_task[2],
        "owner_role": selected_task[3],
        "deadline": selected_task[4],
        "status": "RUNNING",  # Return updated status
        "result": json.loads(selected_task[6]) if selected_task[6] else None,
        "created_at": selected_task[7],
        "updated_at": updated_at,  # Return updated time
        "timeout_seconds": selected_task[9],
        "retry_count": selected_task[10],
        "max_retries": selected_task[11],
        "agent_id": selected_task[12],
        "next_retry_ts": None,  # Cleared for running task
        "retry_backoff_sec": selected_task[14],
        "reason_code": selected_task[15],
        "last_error": selected_task[16],
        "lease_expiry_ts": selected_task[17],
        "lease_seconds": lease_seconds,
        "lease_expiry": lease_expiry_ts,
        "priority": selected_task[19] if len(selected_task) > 19 else 0,  # Priority is at index 19
        "area": selected_task[20] if len(selected_task) > 20 else None,  # Area is at index 20
        "worker_type": selected_task[21] if len(selected_task) > 21 else None,
        "routing_decision": selected_task[22] if len(selected_task) > 22 else None,
        "trace_id": selected_task[23] if len(selected_task) > 23 else None,
        "dependencies": selected_task[24]
        if len(selected_task) > 24
        else None,  # Dependencies at index 24
        "message_id": selected_task[25] if len(selected_task) > 25 else None,
    }

    return jsonify(
        {
            "success": True,
            "task": task_dict,
            "message": "Task assigned and status updated to RUNNING",
        }
    )


@app.route("/api/dlq/list", methods=["GET"])
def get_dlq_list():
    """Get DLQ entries with pagination support."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Get pagination parameters
    page = int(request.args.get("page", 1))
    page_size = int(request.args.get("page_size", 10))

    # Validate pagination parameters
    if page < 1:
        page = 1
    if page_size < 1:
        page_size = 10
    if page_size > 100:
        page_size = 100

    # Calculate offset
    offset = (page - 1) * page_size

    # Get total count
    cursor.execute("SELECT COUNT(*) FROM dlq")
    total_count = cursor.fetchone()[0]

    # Get paginated entries
    cursor.execute(
        """
    SELECT id, task_code, task_id, message_id, trace_id, reason_code, last_error, task_data, created_at, updated_at,
           replay_who, replay_when, replay_why
    FROM dlq 
    ORDER BY created_at DESC 
    LIMIT ? OFFSET ?
    """,
        (page_size, offset),
    )
    dlq_entries = cursor.fetchall()
    conn.close()

    # Format response
    result = []
    for entry in dlq_entries:
        result.append(
            {
                "id": entry[0],
                "task_code": entry[1],
                "task_id": entry[2],
                "message_id": entry[3],
                "trace_id": entry[4],
                "reason_code": entry[5],
                "last_error": entry[6],
                "task_data": json.loads(entry[7]) if entry[7] else None,
                "created_at": entry[8],
                "updated_at": entry[9],
                "replay_who": entry[10],
                "replay_when": entry[11],
                "replay_why": entry[12],
            }
        )

    # Calculate total pages
    total_pages = (total_count + page_size - 1) // page_size

    return jsonify(
        {
            "success": True,
            "dlq_entries": result,
            "pagination": {
                "page": page,
                "page_size": page_size,
                "total_count": total_count,
                "total_pages": total_pages,
            },
        }
    )


@app.route("/api/dlq", methods=["GET"])
def get_dlq_entries():
    """Get all DLQ entries (deprecated, use /api/dlq/list instead)."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute(
        """
    SELECT id, task_code, task_id, message_id, trace_id, reason_code, last_error, task_data, created_at, updated_at,
           replay_who, replay_when, replay_why
    FROM dlq
    ORDER BY created_at DESC
    """
    )
    dlq_entries = cursor.fetchall()
    conn.close()

    # Format response
    result = []
    for entry in dlq_entries:
        result.append(
            {
                "id": entry[0],
                "task_code": entry[1],
                "task_id": entry[2],
                "message_id": entry[3],
                "trace_id": entry[4],
                "reason_code": entry[5],
                "last_error": entry[6],
                "task_data": json.loads(entry[7]) if entry[7] else None,
                "created_at": entry[8],
                "updated_at": entry[9],
                "replay_who": entry[10],
                "replay_when": entry[11],
                "replay_why": entry[12],
            }
        )

    return jsonify({"success": True, "dlq_entries": result})


@app.route("/api/dlq/replay", methods=["POST"])
def replay_dlq_entry():
    """Replay a DLQ entry by resetting the task to PENDING and re-dispatching it."""
    data = request.json

    # Validate required fields
    required_fields = ["dlq_id"]
    for field in required_fields:
        if field not in data:
            return jsonify({"error": f"Missing required field: {field}"}), 400

    dlq_id = data["dlq_id"]

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Get DLQ entry
    cursor.execute(
        """
    SELECT id, task_code, task_id, message_id, trace_id, reason_code, last_error, task_data, created_at, updated_at,
           replay_who, replay_when, replay_why
    FROM dlq
    WHERE id = ?
    """,
        (dlq_id,),
    )
    dlq_entry = cursor.fetchone()

    if not dlq_entry:
        conn.close()
        return jsonify({"error": "DLQ entry not found"}), 404

    # Parse task data
    try:
        task_data = json.loads(dlq_entry[7])
    except json.JSONDecodeError:
        conn.close()
        return jsonify({"error": "Invalid task_data in DLQ entry"}), 400

    # Get agent_id from task data
    agent_id = task_data.get("agent_id")
    if not agent_id:
        conn.close()
        return jsonify({"error": "Missing agent_id in task_data"}), 400

    # Safety: If the task is already DONE, do not allow replay (prevents duplicate execution)
    original_task_id = dlq_entry[2] or task_data.get("id") or task_data.get("task_id")
    if original_task_id:
        cursor.execute("SELECT status FROM tasks WHERE id = ?", (original_task_id,))
        row = cursor.fetchone()
        if row and row[0] == "DONE":
            conn.close()
            return jsonify({"error": "Task already DONE; replay forbidden"}), 400

    # Get who/when/why for audit
    replay_who = data.get("who", "system")
    replay_when = datetime.datetime.utcnow().isoformat() + "Z"
    replay_why = data.get("why", "Replayed from DLQ")

    # Update task status to PENDING and reset retry count
    now = datetime.datetime.utcnow().isoformat() + "Z"

    # Check if task still exists in tasks table
    if original_task_id:
        cursor.execute("SELECT id FROM tasks WHERE id = ?", (original_task_id,))
    else:
        cursor.execute("SELECT id FROM tasks WHERE message_id = ?", (dlq_entry[3],))
    task_exists = cursor.fetchone()

    if task_exists:
        # Update existing task
        cursor.execute(
            """
        UPDATE tasks
        SET status = ?, retry_count = 0, next_retry_ts = NULL, updated_at = ?, 
            reason_code = NULL, last_error = NULL
        WHERE id = ?
        """,
            ("PENDING", now, task_exists[0]),
        )
    else:
        # Recreate task if it doesn't exist
        task_id = original_task_id or str(uuid.uuid4())
        cursor.execute(
            """
        INSERT INTO tasks (
            id, task_code, instructions, owner_role, deadline, status, 
            result, created_at, updated_at, timeout_seconds, retry_count, max_retries, agent_id, 
            next_retry_ts, retry_backoff_sec, priority, area, worker_type, routing_decision, trace_id, dependencies, message_id
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
            (
                task_id,
                task_data["task_code"],
                task_data["instructions"],
                task_data["owner_role"],
                task_data.get("deadline"),
                "PENDING",
                None,
                now,
                now,
                task_data.get("timeout_seconds", 3600),
                0,
                task_data.get("max_retries", 3),
                agent_id,
                None,
                task_data.get("retry_backoff_sec", 60),
                task_data.get("priority", 0),
                task_data.get("area"),
                task_data.get("worker_type"),
                task_data.get("routing_decision"),
                task_data.get("trace_id"),
                task_data.get("dependencies"),
                dlq_entry[3] or task_data.get("message_id"),
            ),
        )

    # Update DLQ entry with audit info
    cursor.execute(
        """
    UPDATE dlq
    SET replay_who = ?, replay_when = ?, replay_why = ?, updated_at = ?
    WHERE id = ?
    """,
        (replay_who, replay_when, replay_why, now, dlq_id),
    )

    # Log DLQ replay with hashed token
    log_entry = {
        "timestamp": now,
        "level": "INFO",
        "component": "dlq",
        "event": "DLQ_REPLAYED",
        "dlq_id": dlq_id,
        "task_code": dlq_entry[1],
        "task_id": dlq_entry[2],
        "message_id": dlq_entry[3],
        "role": g.user_role,
        "token_hash": g.token_hash,
        "replay_who": replay_who,
        "replay_why": replay_why,
        "message": f"DLQ entry {dlq_id} replayed by role {g.user_role}",
    }
    print(json.dumps(log_entry))

    conn.commit()
    conn.close()

    return jsonify(
        {
            "success": True,
            "message": f"DLQ entry {dlq_id} replayed successfully",
            "task_code": dlq_entry[1],
            "agent_id": agent_id,
            "audit": {"who": replay_who, "when": replay_when, "why": replay_why},
        }
    )


@app.route("/api/dlq/<dlq_id>", methods=["GET"])
def get_dlq_entry(dlq_id):
    """Get a specific DLQ entry by ID."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute(
        """
    SELECT id, task_code, task_id, message_id, trace_id, reason_code, last_error, task_data, created_at, updated_at,
           replay_who, replay_when, replay_why
    FROM dlq
    WHERE id = ?
    """,
        (dlq_id,),
    )
    entry = cursor.fetchone()
    conn.close()

    if not entry:
        return jsonify({"error": "DLQ entry not found"}), 404

    return jsonify(
        {
            "success": True,
            "dlq_entry": {
                "id": entry[0],
                "task_code": entry[1],
                "task_id": entry[2],
                "message_id": entry[3],
                "trace_id": entry[4],
                "reason_code": entry[5],
                "last_error": entry[6],
                "task_data": json.loads(entry[7]) if entry[7] else None,
                "created_at": entry[8],
                "updated_at": entry[9],
                "replay_who": entry[10],
                "replay_when": entry[11],
                "replay_why": entry[12],
            },
        }
    )


@app.route("/api/dlq/task/<task_code>", methods=["GET"])
def get_dlq_entry_by_task_code(task_code):
    """Get DLQ entry by task_code."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute(
        """
    SELECT id, task_code, task_id, message_id, trace_id, reason_code, last_error, task_data, created_at, updated_at,
           replay_who, replay_when, replay_why
    FROM dlq
    WHERE task_code = ?
    ORDER BY created_at DESC
    LIMIT 1
    """,
        (task_code,),
    )
    entry = cursor.fetchone()
    conn.close()

    if not entry:
        return jsonify({"error": "DLQ entry not found for this task_code"}), 404

    return jsonify(
        {
            "success": True,
            "dlq_entry": {
                "id": entry[0],
                "task_code": entry[1],
                "task_id": entry[2],
                "message_id": entry[3],
                "trace_id": entry[4],
                "reason_code": entry[5],
                "last_error": entry[6],
                "task_data": json.loads(entry[7]) if entry[7] else None,
                "created_at": entry[8],
                "updated_at": entry[9],
                "replay_who": entry[10],
                "replay_when": entry[11],
                "replay_why": entry[12],
            },
        }
    )


@app.route("/api/dlq/message/<message_id>", methods=["GET"])
def get_dlq_entry_by_message_id(message_id):
    """Get DLQ entry by message_id (idempotency key)."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        """
    SELECT id, task_code, task_id, message_id, trace_id, reason_code, last_error, task_data, created_at, updated_at,
           replay_who, replay_when, replay_why
    FROM dlq
    WHERE message_id = ?
    ORDER BY created_at DESC
    LIMIT 1
    """,
        (message_id,),
    )
    entry = cursor.fetchone()
    conn.close()

    if not entry:
        return jsonify({"error": "DLQ entry not found for this message_id"}), 404

    return jsonify(
        {
            "success": True,
            "dlq_entry": {
                "id": entry[0],
                "task_code": entry[1],
                "task_id": entry[2],
                "message_id": entry[3],
                "trace_id": entry[4],
                "reason_code": entry[5],
                "last_error": entry[6],
                "task_data": json.loads(entry[7]) if entry[7] else None,
                "created_at": entry[8],
                "updated_at": entry[9],
                "replay_who": entry[10],
                "replay_when": entry[11],
                "replay_why": entry[12],
            },
        }
    )


# Workflow recovery API endpoints
@app.route("/api/workflow/recover", methods=["POST"])
def workflow_recover():
    """Trigger workflow recovery manually."""
    success, message, recovered_tasks, inconsistent_tasks = recover_workflow()

    return jsonify(
        {
            "success": success,
            "message": message,
            "recovered_tasks": recovered_tasks,
            "inconsistent_tasks": inconsistent_tasks,
        }
    )


@app.route("/api/workflow/status", methods=["GET"])
def workflow_status():
    """Get workflow status."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    try:
        # Get task counts by status
        cursor.execute("SELECT status, COUNT(*) FROM tasks GROUP BY status")
        task_counts = {row[0]: row[1] for row in cursor.fetchall()}

        # Ensure all statuses are present
        all_statuses = ["PENDING", "RUNNING", "DONE", "FAIL", "DLQ"]
        for status in all_statuses:
            if status not in task_counts:
                task_counts[status] = 0

        # Get workflow recovery status
        cursor.execute(
            'SELECT workflow_id, name, status, last_recovery_time, recovery_status FROM workflows WHERE workflow_id = "default"'
        )
        workflow = cursor.fetchone()

        workflow_info = {
            "workflow_id": "default",
            "name": "Default Workflow",
            "status": "ACTIVE",
            "last_recovery_time": None,
            "recovery_status": None,
        }

        if workflow:
            workflow_info = {
                "workflow_id": workflow[0],
                "name": workflow[1],
                "status": workflow[2],
                "last_recovery_time": workflow[3],
                "recovery_status": workflow[4],
            }

        conn.close()

        return jsonify(
            {
                "success": True,
                "status": "HEALTHY",
                "task_counts": task_counts,
                "workflow": workflow_info,
            }
        )
    except Exception as e:
        conn.close()
        return jsonify({"error": str(e), "success": False}), 500


def validate_canonical_pack(pack):
    """
    Validate the canonical pack format according to the specification.

    Args:
        pack (dict): The result pointer package to validate

    Returns:
        tuple: (is_valid, reason_code, message)
    """
    import re
    import uuid

    # Required fields in exact order
    required_fields = [
        "task_code",
        "trace_id",
        "status",
        "submit_path",
        "ata_path",
        "evidence_paths",
        "sha256_map",
        "ruleset_sha256",
    ]

    # 1. Check if all required fields are present
    pack_fields = list(pack.keys())
    missing_fields = [field for field in required_fields if field not in pack_fields]
    if missing_fields:
        return False, "MISSING_REQUIRED_FIELD", f"Missing required field(s): {missing_fields}"

    # 2. Check if fields are in the correct order
    if pack_fields != required_fields:
        return False, "INVALID_FIELD_ORDER", "Fields not in required order"

    # 3. Check field types
    if not isinstance(pack["task_code"], str):
        return False, "INVALID_FIELD_FORMAT", "task_code must be a string"

    if not isinstance(pack["trace_id"], str):
        return False, "INVALID_FIELD_FORMAT", "trace_id must be a string"

    if not isinstance(pack["status"], str):
        return False, "INVALID_FIELD_FORMAT", "status must be a string"

    if not isinstance(pack["submit_path"], str):
        return False, "INVALID_FIELD_FORMAT", "submit_path must be a string"

    if not isinstance(pack["ata_path"], str):
        return False, "INVALID_FIELD_FORMAT", "ata_path must be a string"

    if not isinstance(pack["evidence_paths"], list):
        return False, "INVALID_FIELD_FORMAT", "evidence_paths must be an array"

    for path in pack["evidence_paths"]:
        if not isinstance(path, str):
            return False, "INVALID_FIELD_FORMAT", "All evidence_paths must be strings"

    if not isinstance(pack["sha256_map"], dict):
        return False, "INVALID_FIELD_FORMAT", "sha256_map must be an object"

    if not isinstance(pack["ruleset_sha256"], str):
        return False, "INVALID_FIELD_FORMAT", "ruleset_sha256 must be a string"

    # 4. Check status value
    allowed_statuses = ["PASS", "FAIL", "ERROR"]
    if pack["status"] not in allowed_statuses:
        return (
            False,
            "INVALID_STATUS",
            f"Invalid status value: {pack['status']}. Allowed values: {allowed_statuses}",
        )

    # 5. Check trace_id is valid UUID v4
    try:
        trace_uuid = uuid.UUID(pack["trace_id"])
        if trace_uuid.version != 4:
            return False, "INVALID_UUID", "trace_id must be a valid UUID v4"
    except ValueError:
        return False, "INVALID_UUID", "trace_id must be a valid UUID v4 string"

    # 6. Check SHA-256 format (64 hex characters)
    sha256_pattern = r"^[0-9a-fA-F]{64}$"

    # Check ruleset_sha256
    if not re.match(sha256_pattern, pack["ruleset_sha256"]):
        return (
            False,
            "INVALID_SHA256",
            "ruleset_sha256 must be a valid 64-character hexadecimal string",
        )

    # Check all hashes in sha256_map
    for file_path, file_hash in pack["sha256_map"].items():
        if not re.match(sha256_pattern, file_hash):
            return False, "INVALID_SHA256", f"Invalid SHA-256 hash for {file_path}: {file_hash}"

    return True, None, "Canonical pack is valid"


@app.route("/api/task/result", methods=["POST"])
def submit_task_result():
    """Submit task results with signature verification."""
    data = request.json

    # Resolve task identity:
    # - task_id: task identity (end-to-end)
    # - message_id: delivery idempotency key
    # - task_code: display label (legacy fallback only)
    task_id = data.get("task_id")
    message_id = data.get("message_id")
    task_code = data.get("task_code") or data.get("TaskCode")

    if not task_id and not message_id and not task_code:
        return jsonify({"error": "Missing task_id, message_id, or task_code"}), 400

    # Check if result contains artifact pointer package that needs verification
    result = data.get("result")
    if result and isinstance(result, dict):
        # If result has pointers field, it's an artifact pointer package that needs verification
        if "pointers" in result:
            # Verify artifact signature
            is_valid, reason_code, message = verify_artifact_signature(result)
            if not is_valid:
                return jsonify(
                    {"error": message, "reason_code": reason_code, "success": False}
                ), 400
        # Validate canonical pack format for A2A result packs
        else:
            # Check if this is a canonical pack (has required fields)
            canonical_fields = [
                "task_code",
                "trace_id",
                "status",
                "submit_path",
                "ata_path",
                "evidence_paths",
                "sha256_map",
                "ruleset_sha256",
            ]
            if all(field in result for field in canonical_fields):
                # Validate the canonical pack format
                is_valid, reason_code, message = validate_canonical_pack(result)
                if not is_valid:
                    return jsonify(
                        {"error": message, "reason_code": reason_code, "success": False}
                    ), 400

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Resolve the task row
    resolved = None
    if task_id:
        cursor.execute("SELECT id, task_code, status, message_id FROM tasks WHERE id = ?", (task_id,))
        resolved = cursor.fetchone()
    elif message_id:
        cursor.execute(
            "SELECT id, task_code, status, message_id FROM tasks WHERE message_id = ?",
            (message_id,),
        )
        resolved = cursor.fetchone()
    else:
        cursor.execute(
            "SELECT id, task_code, status, message_id FROM tasks WHERE task_code = ? ORDER BY created_at DESC LIMIT 1",
            (task_code,),
        )
        resolved = cursor.fetchone()

    if not resolved:
        conn.close()
        return jsonify({"error": "Task not found"}), 404

    resolved_task_id, resolved_task_code, current_status, resolved_message_id = (
        resolved[0],
        resolved[1],
        resolved[2],
        resolved[3],
    )

    # Update task status and result
    now = datetime.datetime.utcnow().isoformat() + "Z"

    # Get status from request or default to DONE if result is provided
    status = data.get("status")

    # Log result submission with hashed token
    log_entry = {
        "timestamp": now,
        "level": "INFO",
        "component": "task",
        "event": "RESULT_SUBMITTED",
        "task_id": resolved_task_id,
        "task_code": resolved_task_code,
        "message_id": resolved_message_id,
        "status": status,
        "role": g.user_role,
        "token_hash": g.token_hash,
        "message": f"Result submitted for task {resolved_task_code} by role {g.user_role} with status {status}",
    }
    print(json.dumps(log_entry))

    # Validate status value
    valid_statuses = ["PENDING", "RUNNING", "DONE", "FAIL"]
    if status and status not in valid_statuses:
        conn.close()
        return jsonify({"error": f"Invalid status: {status}. Valid values: {valid_statuses}"}), 400

    # Default status based on result presence
    if not status:
        status = "DONE" if result else "RUNNING"

    # Validate result structure if provided
    result_json = None
    if result:
        if not isinstance(result, dict):
            conn.close()
            return jsonify({"error": "Result must be a JSON object"}), 400

        # Basic validation of result fields (pointer + hash pattern)
        if "pointers" in result:
            if not isinstance(result["pointers"], list):
                conn.close()
                return jsonify({"error": "pointers must be a list"}), 400

            for pointer in result["pointers"]:
                if not isinstance(pointer, dict):
                    conn.close()
                    return jsonify({"error": "Each pointer must be a JSON object"}), 400
                if "type" not in pointer or "path" not in pointer or "sha256" not in pointer:
                    conn.close()
                    return jsonify(
                        {"error": "Each pointer must have type, path, and sha256 fields"}
                    ), 400

        result_json = json.dumps(result)

    if current_status and status and not is_valid_status_transition(current_status, status):
        conn.close()
        return jsonify(
            {
                "error": f"Invalid status transition: {current_status} -> {status}",
                "reason_code": "INVALID_STATUS_TRANSITION",
                "success": False,
            }
        ), 400

    # Update retry count if status is FAIL
    if status == "FAIL":
        # Get current retry count and max retries
        cursor.execute(
            "SELECT retry_count, max_retries, retry_backoff_sec FROM tasks WHERE id = ?",
            (resolved_task_id,),
        )
        task_retry_info = cursor.fetchone()
        if task_retry_info:
            current_retry = task_retry_info[0]
            max_retries = task_retry_info[1]
            retry_backoff = task_retry_info[2]

            new_retry_count = current_retry + 1

            if new_retry_count <= max_retries:
                # Calculate next retry timestamp (exponential backoff)
                base = int(retry_backoff or 0)
                delay = base * (2 ** max(0, new_retry_count - 1))
                delay = min(delay, 3600)  # cap at 1 hour
                next_retry = datetime.datetime.utcnow() + datetime.timedelta(seconds=delay)
                next_retry_ts = next_retry.isoformat() + "Z"

                # Update task with retry info and set back to PENDING
                cursor.execute(
                    """
                UPDATE tasks
                SET status = ?, result = ?, retry_count = ?, updated_at = ?, 
                    next_retry_ts = ?, reason_code = ?, last_error = ?
                WHERE id = ?
                """,
                    (
                        "PENDING",
                        result_json,
                        new_retry_count,
                        now,
                        next_retry_ts,
                        data.get("reason_code", "TASK_FAILED"),
                        data.get("last_error", "Unknown error"),
                        resolved_task_id,
                    ),
                )

                # Update metrics - move back to queue
                if current_status in ["RUNNING"]:
                    metrics["queue_depth"] += 1
            else:
                # Max retries reached, move to DLQ
                # First get task details
                cursor.execute("SELECT * FROM tasks WHERE id = ?", (resolved_task_id,))
                task_details = cursor.fetchone()

                if task_details:
                    # Create DLQ entry
                    dlq_id = str(uuid.uuid4())
                    trace_id = task_details[0]  # Use task ID as trace ID

                    cursor.execute(
                        """
                    INSERT INTO dlq (id, task_code, task_id, message_id, trace_id, reason_code, last_error, task_data, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                        (
                            dlq_id,
                            task_details[1],
                            task_details[0],
                            task_details[25] if len(task_details) > 25 else None,
                            trace_id,
                            data.get("reason_code", "MAX_RETRIES_REACHED"),
                            data.get("last_error", "Max retries reached"),
                            json.dumps(
                                {
                                    "id": task_details[0],
                                    "task_code": task_details[1],
                                    "message_id": task_details[25] if len(task_details) > 25 else None,
                                    "instructions": task_details[2],
                                    "owner_role": task_details[3],
                                    "deadline": task_details[4],
                                    "status": task_details[5],
                                    "result": json.loads(task_details[6])
                                    if task_details[6]
                                    else None,
                                    "created_at": task_details[7],
                                    "updated_at": task_details[8],
                                    "timeout_seconds": task_details[9],
                                    "retry_count": new_retry_count,
                                    "max_retries": task_details[11],
                                    "agent_id": task_details[12],
                                    "retry_backoff_sec": task_details[14],
                                    "priority": task_details[19] if len(task_details) > 19 else 0,
                                    "area": task_details[20] if len(task_details) > 20 else None,
                                    "worker_type": task_details[21] if len(task_details) > 21 else None,
                                    "routing_decision": task_details[22] if len(task_details) > 22 else None,
                                    "trace_id": task_details[23] if len(task_details) > 23 else None,
                                    "dependencies": task_details[24] if len(task_details) > 24 else None,
                                }
                            ),
                            now,
                            now,
                        ),
                    )

                    # Update task status to DLQ
                    cursor.execute(
                        """
                    UPDATE tasks
                    SET status = ?, result = ?, retry_count = ?, updated_at = ?, 
                        reason_code = ?, last_error = ?
                    WHERE id = ?
                    """,
                        (
                            "DLQ",
                            result_json,
                            new_retry_count,
                            now,
                            data.get("reason_code", "MAX_RETRIES_REACHED"),
                            data.get("last_error", "Max retries reached"),
                            resolved_task_id,
                        ),
                    )
        else:
            # Fallback - simple status update if retry info not available
            cursor.execute(
                """
            UPDATE tasks
            SET status = ?, result = ?, retry_count = retry_count + 1, updated_at = ?
            WHERE id = ?
            """,
                (status, result_json, now, resolved_task_id),
            )
    else:
        # Normal status update without retry increment
        if status == "DONE":
            # When task is DONE, clear reason_code and last_error fields
            cursor.execute(
                """
            UPDATE tasks
            SET status = ?, result = ?, updated_at = ?, 
                reason_code = NULL, last_error = NULL
            WHERE id = ?
            """,
                (status, result_json, now, resolved_task_id),
            )
        else:
            # For other statuses, keep reason_code and last_error if they exist
            cursor.execute(
                """
            UPDATE tasks
            SET status = ?, result = ?, updated_at = ?
            WHERE id = ?
            """,
                (status, result_json, now, resolved_task_id),
            )

    if cursor.rowcount == 0:
        conn.close()
        return jsonify({"error": "Task not found"}), 404

    # Use resolved_task_id (task identity)
    task_id = resolved_task_id

    # FAILURE PROPAGATION: If task is failing, mark all dependent tasks as BLOCKED
    if status in ["FAIL", "DLQ"]:
        # Find all tasks that have this task in their dependencies
        cursor.execute("SELECT id, dependencies FROM tasks WHERE status = ?", ("PENDING",))
        pending_tasks = cursor.fetchall()

        for pending_task in pending_tasks:
            pending_task_id = pending_task[0]
            dependencies_json = pending_task[1]

            if dependencies_json:
                try:
                    dependencies = json.loads(dependencies_json)
                    if isinstance(dependencies, list) and task_id in dependencies:
                        # This task depends on the failed task, mark as BLOCKED
                        cursor.execute(
                            """
                        UPDATE tasks 
                        SET status = ?, updated_at = ?, reason_code = ? 
                        WHERE id = ?
                        """,
                            ("BLOCKED", now, "dep_failed", pending_task_id),
                        )
                except json.JSONDecodeError:
                    # Invalid dependencies JSON, skip
                    continue

    # Get agent_id for the task
    cursor.execute("SELECT agent_id FROM tasks WHERE id = ?", (resolved_task_id,))
    task_agent = cursor.fetchone()
    agent_id = task_agent[0] if task_agent else None

    # Update metrics based on status change
    if status == "DONE" and current_status != "DONE":
        metrics["tasks_done"] += 1
        if current_status in ["PENDING", "RUNNING"]:
            metrics["queue_depth"] = max(0, metrics["queue_depth"] - 1)
        # 恢复agent的available_capacity
        if agent_id:
            cursor.execute(
                """
            UPDATE agents
            SET available_capacity = available_capacity + 1, updated_at = ?
            WHERE agent_id = ?
            """,
                (now, agent_id),
            )

            # Update completion count
            # First reset window if needed
            reset_completion_window_if_needed(agent_id, cursor)

            # Then increment completion count
            cursor.execute(
                """
            UPDATE agents 
            SET current_completion_count = current_completion_count + 1, updated_at = ? 
            WHERE agent_id = ?
            """,
                (now, agent_id),
            )
    elif status == "FAIL" and current_status != "FAIL":
        metrics["tasks_fail"] += 1
        if current_status in ["PENDING", "RUNNING"]:
            metrics["queue_depth"] = max(0, metrics["queue_depth"] - 1)
        # 恢复agent的available_capacity
        if agent_id:
            cursor.execute(
                """
            UPDATE agents
            SET available_capacity = available_capacity + 1, updated_at = ?
            WHERE agent_id = ?
            """,
                (now, agent_id),
            )
    elif status == "RUNNING" and current_status == "PENDING":
        metrics["queue_depth"] = max(0, metrics["queue_depth"] - 1)
    elif status == "PENDING" and current_status != "PENDING":
        metrics["queue_depth"] += 1

    conn.commit()
    conn.close()

    return jsonify({"success": True, "message": "Result submitted successfully", "status": status})


def check_workflow_consistency():
    """
    Check workflow consistency and return inconsistent tasks.

    Returns:
        tuple: (consistent, inconsistent_tasks)
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    now = datetime.datetime.utcnow().isoformat() + "Z"
    inconsistent_tasks = []

    try:
        # Get all tasks
        cursor.execute("SELECT id, task_code, status, lease_expiry_ts, dependencies FROM tasks")
        tasks = cursor.fetchall()

        # Create a task status map for quick lookup
        # 注意：dependencies 使用 task_id（不是 task_code）
        task_status_map = {
            task[0]: {
                "task_code": task[1],
                "status": task[2],
                "lease_expiry_ts": task[3],
                "dependencies": json.loads(task[4]) if task[4] else [],
            }
            for task in tasks
        }

        # Check each task for consistency
        for task in tasks:
            task_id = task[0]
            task_code = task[1]
            status = task[2]
            lease_expiry_ts = task[3]
            dependencies_json = task[4]
            dependencies = json.loads(dependencies_json) if dependencies_json else []

            # Check 1: RUNNING tasks must have valid lease
            if status == "RUNNING":
                if not lease_expiry_ts or lease_expiry_ts < now:
                    inconsistent_tasks.append(
                        {
                            "task_code": task_code,
                            "reason_code": "RUNNING_TASK_MISSING_VALID_LEASE",
                            "description": f"Running task {task_code} has no valid lease",
                        }
                    )

            # Check 2: Dependencies must be completed before task
            for dep_code in dependencies:
                if dep_code not in task_status_map:
                    inconsistent_tasks.append(
                        {
                            "task_code": task_code,
                            "reason_code": "MISSING_DEPENDENCY_TASK",
                            "description": f"Task {task_code} has missing dependency {dep_code}",
                        }
                    )
                else:
                    dep_status = task_status_map[dep_code]["status"]
                    # If task is completed or running, dependency must be completed
                    if status in ["RUNNING", "DONE"] and dep_status not in ["DONE", "completed"]:
                        inconsistent_tasks.append(
                            {
                                "task_code": task_code,
                                "reason_code": "TASK_COMPLETED_BEFORE_DEPENDENCY",
                                "description": f"Task {task_code} is {status} but dependency {dep_code} is {dep_status}",
                            }
                        )
                    # If dependency failed, task should not be active
                    if dep_status == "FAIL" and status not in ["FAIL", "DLQ"]:
                        inconsistent_tasks.append(
                            {
                                "task_code": task_code,
                                "reason_code": "DEPENDENCY_FAILED_BUT_TASK_ACTIVE",
                                "description": f"Dependency {dep_code} failed but task {task_code} is {status}",
                            }
                        )

        conn.close()
        return len(inconsistent_tasks) == 0, inconsistent_tasks
    except Exception as e:
        conn.close()
        return False, [
            {"task_code": "system", "reason_code": "SYSTEM_ERROR", "description": str(e)}
        ]


def repair_workflow_inconsistencies():
    """
    Repair workflow inconsistencies.

    Returns:
        tuple: (success, repaired_tasks, errors)
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    now = datetime.datetime.utcnow().isoformat() + "Z"
    repaired_tasks = []
    errors = []

    try:
        # Get all RUNNING tasks with invalid leases
        cursor.execute(
            'SELECT id, task_code, lease_expiry_ts FROM tasks WHERE status = "RUNNING" AND (lease_expiry_ts IS NULL OR lease_expiry_ts < ?)',
            (now,),
        )
        invalid_running_tasks = cursor.fetchall()

        # Repair RUNNING tasks with invalid leases
        for task in invalid_running_tasks:
            task_id = task[0]
            task_code = task[1]

            # Update task to PENDING
            cursor.execute(
                """
            UPDATE tasks
            SET status = ?, lease_expiry_ts = NULL, updated_at = ?
            WHERE id = ?
            """,
                ("PENDING", now, task_id),
            )

            repaired_tasks.append(
                {
                    "task_code": task_code,
                    "old_status": "RUNNING",
                    "new_status": "PENDING",
                    "reason": "Invalid lease expired",
                }
            )

        # Get all tasks with failed dependencies but active status
        cursor.execute("SELECT id, task_code, status, dependencies FROM tasks")
        all_tasks = cursor.fetchall()

        # Create a task status map for quick lookup
        task_status_map = {}
        for task in all_tasks:
            task_status_map[task[0]] = {"task_code": task[1], "status": task[2]}

        for task in all_tasks:
            task_id = task[0]
            task_code = task[1]
            status = task[2]
            dependencies_json = task[3]
            dependencies = json.loads(dependencies_json) if dependencies_json else []

            # Check if any dependency is in FAIL state
            for dep_code in dependencies:
                if dep_code in task_status_map and task_status_map[dep_code]["status"] == "FAIL":
                    if status not in ["FAIL", "DLQ"]:
                        # Update task to FAIL
                        cursor.execute(
                            """
                        UPDATE tasks
                        SET status = ?, reason_code = ?, last_error = ?, updated_at = ?
                        WHERE id = ?
                        """,
                            (
                                "FAIL",
                                "DEPENDENCY_FAILED",
                                f"Dependency {dep_code} failed",
                                now,
                                task_id,
                            ),
                        )

                        repaired_tasks.append(
                            {
                                "task_code": task_code,
                                "old_status": status,
                                "new_status": "FAIL",
                                "reason": f"Dependency {dep_code} failed",
                            }
                        )
                    break

        conn.commit()
        conn.close()
        return True, repaired_tasks, errors
    except Exception as e:
        conn.rollback()
        conn.close()
        errors.append(str(e))
        return False, repaired_tasks, errors


def recover_workflow():
    """
    Recover workflow state after restart.

    Returns:
        tuple: (success, message, recovered_tasks, inconsistent_tasks)
    """
    now = datetime.datetime.utcnow().isoformat() + "Z"

    # Step 1: Check consistency
    consistent, inconsistent_tasks = check_workflow_consistency()

    if not consistent:
        # Step 2: Repair inconsistencies
        repair_success, repaired_tasks, repair_errors = repair_workflow_inconsistencies()

        if repair_success:
            # Step 3: Verify repair was successful
            consistent, final_inconsistent_tasks = check_workflow_consistency()
            if consistent:
                # Step 4: Update workflow recovery status
                conn = sqlite3.connect(DB_PATH)
                cursor = conn.cursor()

                # Check if default workflow exists, create if not
                cursor.execute('SELECT id FROM workflows WHERE workflow_id = "default"')
                default_workflow = cursor.fetchone()

                if not default_workflow:
                    # Create default workflow
                    workflow_id = str(uuid.uuid4())
                    cursor.execute(
                        """
                    INSERT INTO workflows (id, workflow_id, name, status, created_at, updated_at, last_recovery_time, recovery_status)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                        (
                            workflow_id,
                            "default",
                            "Default Workflow",
                            "ACTIVE",
                            now,
                            now,
                            now,
                            "SUCCESS",
                        ),
                    )
                else:
                    # Update existing workflow
                    cursor.execute(
                        """
                    UPDATE workflows
                    SET last_recovery_time = ?, recovery_status = ?, updated_at = ?
                    WHERE workflow_id = "default"
                    """,
                        (now, "SUCCESS", now),
                    )

                conn.commit()
                conn.close()

                return (
                    True,
                    f"Workflow recovered successfully, repaired {len(repaired_tasks)} tasks",
                    repaired_tasks,
                    [],
                )
            else:
                # Update workflow recovery status to FAILED
                conn = sqlite3.connect(DB_PATH)
                cursor = conn.cursor()

                # Check if default workflow exists, create if not
                cursor.execute('SELECT id FROM workflows WHERE workflow_id = "default"')
                default_workflow = cursor.fetchone()

                if not default_workflow:
                    workflow_id = str(uuid.uuid4())
                    cursor.execute(
                        """
                    INSERT INTO workflows (id, workflow_id, name, status, created_at, updated_at, last_recovery_time, recovery_status)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                        (
                            workflow_id,
                            "default",
                            "Default Workflow",
                            "ACTIVE",
                            now,
                            now,
                            now,
                            "FAILED",
                        ),
                    )
                else:
                    cursor.execute(
                        """
                    UPDATE workflows
                    SET last_recovery_time = ?, recovery_status = ?, updated_at = ?
                    WHERE workflow_id = "default"
                    """,
                        (now, "FAILED", now),
                    )

                conn.commit()
                conn.close()

                return (
                    False,
                    "Workflow recovery failed, could not repair all inconsistencies",
                    repaired_tasks,
                    final_inconsistent_tasks,
                )
        else:
            return (
                False,
                f"Failed to repair workflow inconsistencies: {repair_errors}",
                [],
                inconsistent_tasks,
            )
    else:
        # Workflow is already consistent
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        # Check if default workflow exists, create if not
        cursor.execute('SELECT id FROM workflows WHERE workflow_id = "default"')
        default_workflow = cursor.fetchone()

        if not default_workflow:
            workflow_id = str(uuid.uuid4())
            cursor.execute(
                """
            INSERT INTO workflows (id, workflow_id, name, status, created_at, updated_at, last_recovery_time, recovery_status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (workflow_id, "default", "Default Workflow", "ACTIVE", now, now, now, "SUCCESS"),
            )
        else:
            cursor.execute(
                """
            UPDATE workflows
            SET last_recovery_time = ?, recovery_status = ?, updated_at = ?
            WHERE workflow_id = "default"
            """,
                (now, "SUCCESS", now),
            )

        conn.commit()
        conn.close()

        return True, "Workflow is already consistent", [], []


# MCP Bridge integration point
def submit_artifact_pointer(task_code, pointers):
    """
    Submit artifact pointers for a task.
    This function is designed to be called by the exchange_server's tools/call in the future.

    Args:
        task_code (str): Task code
        pointers (list): List of artifact pointers with type, path, and sha256

    Returns:
        bool: Success status
    """
    try:
        # Create result structure
        result = {
            "pointers": pointers,
            "submitted_at": datetime.datetime.utcnow().isoformat() + "Z",
        }

        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        now = datetime.datetime.utcnow().isoformat() + "Z"
        cursor.execute(
            """
        UPDATE tasks
        SET status = ?, result = ?, updated_at = ?, 
            reason_code = NULL, last_error = NULL
        WHERE task_code = ?
        """,
            ("DONE", json.dumps(result), now, task_code),
        )

        if cursor.rowcount == 0:
            conn.close()
            return False

        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"Error submitting artifact pointer: {e}")
        return False


# Agent registry API endpoints
@app.route("/api/agent/register", methods=["POST"])
def register_agent():
    """Register a new agent."""
    data = request.json

    # Validate required fields
    required_fields = ["agent_id", "owner_role", "capabilities", "allowed_tools"]
    for field in required_fields:
        if field not in data:
            return jsonify({"error": f"Missing required field: {field}"}), 400

    # Get capacity from request or use default value
    capacity = data.get("capacity", 1)
    available_capacity = data.get("available_capacity", capacity)
    completion_limit_per_minute = data.get("completion_limit_per_minute", 60)

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Check if agent already exists
    cursor.execute("SELECT id FROM agents WHERE agent_id = ?", (data["agent_id"],))
    existing_agent = cursor.fetchone()

    now = datetime.datetime.utcnow().isoformat() + "Z"

    if existing_agent:
        # Update existing agent
        cursor.execute(
            """
        UPDATE agents
        SET owner_role = ?, capabilities = ?, online = ?, last_seen = ?, allowed_tools = ?, 
            capacity = ?, available_capacity = ?, completion_limit_per_minute = ?, worker_type = ?, updated_at = ?
        WHERE agent_id = ?
        """,
            (
                data["owner_role"],
                json.dumps(data["capabilities"]),
                data.get("online", 1),
                now,
                json.dumps(data["allowed_tools"]),
                capacity,
                available_capacity,
                completion_limit_per_minute,
                data.get("worker_type"),
                now,
                data["agent_id"],
            ),
        )
    else:
        # Register new agent
        agent_db_id = str(uuid.uuid4())
        cursor.execute(
            """
        INSERT INTO agents (id, agent_id, owner_role, capabilities, online, last_seen, allowed_tools,
                           capacity, available_capacity, completion_limit_per_minute, current_completion_count,
                           completion_window_start, worker_type, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
            (
                agent_db_id,
                data["agent_id"],
                data["owner_role"],
                json.dumps(data["capabilities"]),
                data.get("online", 1),
                now,
                json.dumps(data["allowed_tools"]),
                capacity,
                available_capacity,
                completion_limit_per_minute,
                0,
                now,
                data.get("worker_type"),
                now,
                now,
            ),
        )

    # Log agent registration with hashed token
    now = datetime.datetime.utcnow().isoformat() + "Z"
    log_entry = {
        "timestamp": now,
        "level": "INFO",
        "component": "agent",
        "event": "AGENT_REGISTERED",
        "agent_id": data["agent_id"],
        "owner_role": data["owner_role"],
        "role": g.user_role,
        "token_hash": g.token_hash,
        "message": f"Agent {data['agent_id']} registered by role {g.user_role}",
    }
    print(json.dumps(log_entry))

    conn.commit()
    conn.close()

    return jsonify({"success": True, "message": "Agent registered successfully"})


@app.route("/api/agent/list", methods=["GET"])
def list_agents():
    """List all agents."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM agents")
    agents = cursor.fetchall()
    conn.close()

    agent_list = []
    for agent in agents:
        agent_list.append(
            {
                "id": agent[0],
                "agent_id": agent[1],
                "owner_role": agent[2],
                "capabilities": json.loads(agent[3]),
                "online": bool(agent[4]),
                "last_seen": agent[5],
                "allowed_tools": json.loads(agent[6]),
                "created_at": agent[7],
                "updated_at": agent[8],
                "capacity": agent[9] if len(agent) > 9 else 1,
                "available_capacity": agent[10] if len(agent) > 10 else 1,
                "completion_limit_per_minute": agent[11] if len(agent) > 11 else 60,
                "current_completion_count": agent[12] if len(agent) > 12 else 0,
                "completion_window_start": agent[13] if len(agent) > 13 else agent[5],
                "worker_type": agent[14] if len(agent) > 14 else None,
            }
        )

    return jsonify({"success": True, "agents": agent_list})


@app.route("/api/agent/<agent_id>", methods=["GET"])
def get_agent(agent_id):
    """Get agent details."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM agents WHERE agent_id = ?", (agent_id,))
    agent = cursor.fetchone()
    conn.close()

    if not agent:
        return jsonify({"error": "Agent not found"}), 404

    return jsonify(
        {
            "success": True,
            "agent": {
                "id": agent[0],
                "agent_id": agent[1],
                "owner_role": agent[2],
                "capabilities": json.loads(agent[3]),
                "online": bool(agent[4]),
                "last_seen": agent[5],
                "allowed_tools": json.loads(agent[6]),
                "created_at": agent[7],
                "updated_at": agent[8],
                "capacity": agent[9] if len(agent) > 9 else 1,
                "available_capacity": agent[10] if len(agent) > 10 else 1,
                "completion_limit_per_minute": agent[11] if len(agent) > 11 else 60,
                "current_completion_count": agent[12] if len(agent) > 12 else 0,
                "completion_window_start": agent[13] if len(agent) > 13 else agent[5],
                "worker_type": agent[14] if len(agent) > 14 else None,
            },
        }
    )


@app.route("/api/agent/<agent_id>", methods=["PUT"])
def update_agent(agent_id):
    """Update agent details."""
    data = request.json
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Check if agent exists
    cursor.execute("SELECT id FROM agents WHERE agent_id = ?", (agent_id,))
    if not cursor.fetchone():
        conn.close()
        return jsonify({"error": "Agent not found"}), 404

    now = datetime.datetime.utcnow().isoformat() + "Z"

    # Update agent fields
    update_fields = []
    update_values = []

    if "owner_role" in data:
        update_fields.append("owner_role = ?")
        update_values.append(data["owner_role"])
    if "capabilities" in data:
        update_fields.append("capabilities = ?")
        update_values.append(json.dumps(data["capabilities"]))
    if "online" in data:
        update_fields.append("online = ?")
        update_values.append(1 if data["online"] else 0)
    if "last_seen" in data:
        update_fields.append("last_seen = ?")
        update_values.append(data["last_seen"])
    else:
        update_fields.append("last_seen = ?")
        update_values.append(now)
    if "allowed_tools" in data:
        update_fields.append("allowed_tools = ?")
        update_values.append(json.dumps(data["allowed_tools"]))
    if "capacity" in data:
        update_fields.append("capacity = ?")
        update_values.append(data["capacity"])
    if "available_capacity" in data:
        update_fields.append("available_capacity = ?")
        update_values.append(data["available_capacity"])
    if "completion_limit_per_minute" in data:
        update_fields.append("completion_limit_per_minute = ?")
        update_values.append(data["completion_limit_per_minute"])
    # If capacity is updated but available_capacity is not, ensure available_capacity doesn't exceed capacity
    if "capacity" in data and "available_capacity" not in data:
        cursor.execute("SELECT available_capacity FROM agents WHERE agent_id = ?", (agent_id,))
        current_available_capacity = cursor.fetchone()[0]
        new_capacity = data["capacity"]
        if current_available_capacity > new_capacity:
            update_fields.append("available_capacity = ?")
            update_values.append(new_capacity)

    update_fields.append("updated_at = ?")
    update_values.append(now)
    update_values.append(agent_id)

    query = f"UPDATE agents SET {', '.join(update_fields)} WHERE agent_id = ?"
    cursor.execute(query, update_values)

    conn.commit()
    conn.close()

    return jsonify({"success": True, "message": "Agent updated successfully"})


@app.route("/api/agent/<agent_id>", methods=["DELETE"])
def deregister_agent(agent_id):
    """Deregister an agent."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Check if agent exists
    cursor.execute("SELECT id FROM agents WHERE agent_id = ?", (agent_id,))
    if not cursor.fetchone():
        conn.close()
        return jsonify({"error": "Agent not found"}), 404

    # Delete agent
    cursor.execute("DELETE FROM agents WHERE agent_id = ?", (agent_id,))

    conn.commit()
    conn.close()

    return jsonify({"success": True, "message": "Agent deregistered successfully"})


# @app.route('/metrics', methods=['GET'])
def metrics_endpoint():
    """Metrics endpoint for Prometheus - Temporarily disabled"""
    # This endpoint is temporarily disabled until metrics collection is implemented
    return jsonify({"error": "Metrics endpoint not implemented"}), 501


@app.route("/api/health", methods=["GET"])
def health_check():
    """Health check endpoint for A2A Hub."""
    try:
        # Check database connection
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT 1")
        cursor.fetchone()
        conn.close()

        return jsonify(
            {
                "success": True,
                "status": "healthy",
                "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
                "version": "v0.1",
                "service": "a2a-hub",
            }
        ), 200
    except Exception as e:
        return jsonify(
            {
                "success": False,
                "status": "unhealthy",
                "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
                "version": "v0.1",
                "service": "a2a-hub",
                "error": str(e),
            }
        ), 500


# Version information endpoint
@app.route("/version", methods=["GET"])
def get_version():
    """Get version information"""
    import os
    import subprocess

    # Get project root directory
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))

    # Get git SHA
    try:
        git_sha = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=project_root, universal_newlines=True
        ).strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        git_sha = "unknown"

    # Get build time (current time)
    build_time = datetime.datetime.utcnow().isoformat() + "Z"

    # Return version information
    version_info = {
        "git_sha": git_sha,
        "build_time": build_time,
        "toolset_version": "v0.1",
        "RULESET_SHA256": "dummy_ruleset_sha256_value_1234567890abcdef",
    }

    return jsonify(version_info)


# Command-line interface for cleanup/rollback
def cleanup_state():
    """Cleanup/rollback the state by deleting the database."""
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
        print(f"State cleaned up: {DB_PATH} deleted")
        return True
    else:
        print(f"No state to cleanup: {DB_PATH} does not exist")
        return False


# Helper function to reset agent completion count if window has expired
def reset_completion_window_if_needed(agent_id, cursor=None):
    """Reset agent completion count if the current window has expired."""
    conn = None
    owns_conn = False
    if cursor is None:
        conn = sqlite3.connect(DB_PATH, timeout=10)
        conn.execute("PRAGMA busy_timeout = 5000")
        cursor = conn.cursor()
        owns_conn = True

    # Get agent info
    cursor.execute(
        """
    SELECT completion_window_start, completion_limit_per_minute 
    FROM agents 
    WHERE agent_id = ?
    """,
        (agent_id,),
    )
    agent_info = cursor.fetchone()

    if not agent_info:
        if owns_conn and conn:
            conn.close()
        return

    window_start = agent_info[0]
    limit_per_minute = agent_info[1]

    # Parse window start time
    window_start_dt = datetime.datetime.fromisoformat(window_start.replace("Z", "+00:00")).replace(
        tzinfo=None
    )
    now = datetime.datetime.utcnow()

    # Check if one minute has passed
    if (now - window_start_dt).total_seconds() >= 60:
        # Reset completion count and window start
        new_window_start = now.isoformat() + "Z"
        cursor.execute(
            """
        UPDATE agents 
        SET current_completion_count = 0, completion_window_start = ? 
        WHERE agent_id = ?
        """,
            (new_window_start, agent_id),
        )
        if owns_conn and conn:
            conn.commit()
    if owns_conn and conn:
        conn.close()


# Check for required secrets before starting the server
def check_required_secrets():
    """Check if all required secrets are present"""
    import os
    import sys

    required_secrets = ["A2A_HUB_SECRET_KEY"]

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


# Function to check and handle expired leases
def check_expired_leases():
    """Check for tasks with expired leases and update their status to PENDING."""
    import time

    while True:
        try:
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()

            # Get current time in proper ISO format with timezone
            now_dt = datetime.datetime.now(datetime.UTC)
            now = now_dt.isoformat().replace("+00:00", "Z")

            # Find tasks with expired leases
            cursor.execute(
                """
            SELECT id, task_code, status, agent_id, retry_count, max_retries, retry_backoff_sec 
            FROM tasks 
            WHERE status = 'RUNNING' AND lease_expiry_ts IS NOT NULL AND lease_expiry_ts < ?
            """,
                (now,),
            )

            expired_tasks = cursor.fetchall()

            if expired_tasks:
                print(f"Found {len(expired_tasks)} tasks with expired leases")

                for task in expired_tasks:
                    (
                        task_id,
                        task_code,
                        status,
                        agent_id,
                        retry_count,
                        max_retries,
                        retry_backoff_sec,
                    ) = task

                    print(
                        f"Task {task_id} ({task_code}) has expired lease, updating status to PENDING"
                    )

                    # Calculate next retry time if we're using retry mechanism
                    next_retry_ts = None

                    # 恢复agent的available_capacity
                    if agent_id:
                        cursor.execute(
                            """
                        UPDATE agents
                        SET available_capacity = available_capacity + 1, updated_at = ?
                        WHERE agent_id = ?
                        """,
                            (now, agent_id),
                        )

                    # Update task status to PENDING and clear lease
                    cursor.execute(
                        """
                    UPDATE tasks 
                    SET status = ?, updated_at = ?, lease_expiry_ts = NULL, next_retry_ts = ? 
                    WHERE id = ?
                    """,
                        ("PENDING", now, next_retry_ts, task_id),
                    )

                    # Update metrics - task moved from RUNNING to PENDING, so queue_depth increases by 1
                    metrics["queue_depth"] = max(0, metrics["queue_depth"] + 1)

            conn.commit()
            conn.close()

        except Exception as e:
            print(f"Error checking expired leases: {e}")

        # Sleep for 10 seconds before next check
        time.sleep(10)


# Function to check and apply priority aging
def check_priority_aging():
    """Check for pending tasks that have been waiting too long and increase their priority."""
    import time

    while True:
        try:
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()

            # Get current time
            now_dt = datetime.datetime.now(datetime.UTC)
            now = now_dt.isoformat().replace("+00:00", "Z")

            # Find pending tasks and their creation times
            cursor.execute("""
            SELECT id, task_code, priority, created_at 
            FROM tasks 
            WHERE status = 'PENDING' 
            ORDER BY created_at ASC
            """)

            pending_tasks = cursor.fetchall()

            for task in pending_tasks:
                task_id, task_code, current_priority, created_at_str = task

                # Parse created_at time
                created_at = datetime.datetime.fromisoformat(created_at_str.replace("Z", "+00:00"))

                # Calculate time since task creation in seconds
                wait_time_seconds = (now_dt - created_at).total_seconds()

                # Check if task needs priority aging
                if (
                    wait_time_seconds > PRIORITY_AGING_CONFIG["aging_threshold"]
                    and current_priority < PRIORITY_AGING_CONFIG["max_priority"]
                ):
                    # Calculate new priority
                    new_priority = min(
                        current_priority + PRIORITY_AGING_CONFIG["aging_step"],
                        PRIORITY_AGING_CONFIG["max_priority"],
                    )

                    # Update task priority
                    cursor.execute(
                        """
                    UPDATE tasks 
                    SET priority = ?, updated_at = ? 
                    WHERE id = ?
                    """,
                        (new_priority, now, task_id),
                    )

                    # Output structured log for scheduling decision
                    log_entry = {
                        "timestamp": now,
                        "level": "INFO",
                        "component": "priority_aging",
                        "event": "TASK_PRIORITY_INCREASED",
                        "task_id": task_id,
                        "task_code": task_code,
                        "current_priority": current_priority,
                        "new_priority": new_priority,
                        "wait_time_seconds": wait_time_seconds,
                        "aging_threshold": PRIORITY_AGING_CONFIG["aging_threshold"],
                        "reason": "TASK_STARVATION_PREVENTION",
                    }
                    print(json.dumps(log_entry))

            conn.commit()
            conn.close()

        except Exception as e:
            error_entry = {
                "timestamp": datetime.datetime.now(datetime.UTC).isoformat().replace("+00:00", "Z"),
                "level": "ERROR",
                "component": "priority_aging",
                "event": "ERROR",
                "message": f"Error checking priority aging: {e}",
            }
            print(json.dumps(error_entry))

        # Sleep for configured check interval
        time.sleep(PRIORITY_AGING_CONFIG["check_interval"])


if __name__ == "__main__":
    import sys

    # Check if --version flag is provided
    if "--version" in sys.argv:
        import os
        import subprocess

        # Get project root directory
        project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))

        # Get git SHA
        try:
            git_sha = subprocess.check_output(
                ["git", "rev-parse", "HEAD"], cwd=project_root, universal_newlines=True
            ).strip()
        except (subprocess.CalledProcessError, FileNotFoundError):
            git_sha = "unknown"

        # Get build time (current time)
        build_time = datetime.datetime.utcnow().isoformat() + "Z"

        # Print version information
        version_info = {
            "git_sha": git_sha,
            "build_time": build_time,
            "toolset_version": "v0.1",
            "RULESET_SHA256": "dummy_ruleset_sha256_value_1234567890abcdef",
        }

        print(json.dumps(version_info, indent=2))
        sys.exit(0)

    if len(sys.argv) > 1:
        if sys.argv[1] == "cleanup":
            cleanup_state()
            sys.exit(0)

    # Check required secrets before starting the server
    check_required_secrets()

    # Initialize database
    init_db()

    # Run workflow recovery on startup
    print("Running workflow recovery on startup...")
    success, message, recovered_tasks, inconsistent_tasks = recover_workflow()
    print(f"Workflow recovery result: {'SUCCESS' if success else 'FAILED'}")
    print(f"Recovery message: {message}")
    if recovered_tasks:
        print(f"Recovered {len(recovered_tasks)} tasks:")
        for task in recovered_tasks:
            print(f"  - {task['task_code']}: {task['old_status']} -> {task['new_status']}")
    if inconsistent_tasks:
        print(f"Found {len(inconsistent_tasks)} inconsistent tasks:")
        for task in inconsistent_tasks:
            print(f"  - {task['task_code']}: {task['reason_code']} - {task['description']}")
    print()

    # Start lease expiration checker in background thread
    import threading

    lease_checker_thread = threading.Thread(target=check_expired_leases, daemon=True)
    lease_checker_thread.start()
    print("Started lease expiration checker thread")

    # Start priority aging checker in background thread
    priority_aging_thread = threading.Thread(target=check_priority_aging, daemon=True)
    priority_aging_thread.start()
    print("Started priority aging checker thread")

    # Start Flask server
    print("Starting A2A Hub...")
    print(f"Database: {DB_PATH}")
    print("Endpoints:")
    print("  POST /api/task/create - Create new task")
    print("  GET /api/task/status?task_code=XXX - Query task status")
    print("  GET /api/task/next - Get next pending task")
    print("  POST /api/task/heartbeat - Update task heartbeat and extend lease")
    print("  POST /api/task/result - Submit task result")
    print("  GET /version - Get version information")
    print("  ")
    print("To cleanup state: python main.py cleanup")
    print("To get version: python main.py --version")
    print("  ")

    app.run(host="0.0.0.0", port=5001, debug=False)
