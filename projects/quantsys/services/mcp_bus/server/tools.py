import base64
import hashlib
import json
import os
import subprocess
import threading
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx
from pydantic import BaseModel, Field

from .ata_ci import ATAEvidenceTriplet, ATACIVerifier
from .ata_mailbox import ATAMailbox
from .ata_protocol import ATAEvent, ATAStatus, ATATaskCreate, map_a2a_status
from .ata_router import ATARouter
from .ata_trace import build_trace_info, trace_payload


class InboxAppendParams(BaseModel):
    date: str = Field(..., description="Date in YYYY-MM-DD format")
    task_code: str = Field(..., description="Task identifier")
    source: str = Field(..., description="Source identifier (e.g., ChatGPT, TRAE)")
    text: str = Field(..., description="Content to append")


class InboxTailParams(BaseModel):
    date: str = Field(..., description="Date in YYYY-MM-DD format")
    n: int = Field(default=50, description="Number of lines to return")


class BoardSetStatusParams(BaseModel):
    task_code: str = Field(..., description="Task identifier")
    status: str = Field(..., description="New status value")
    artifacts: str | None = Field(None, description="Artifacts/deliverables path")


class EchoParams(BaseModel):
    text: str = Field(..., description="Text to echo back")


class CloudCallParams(BaseModel):
    tool_name: str = Field(..., description="Name of the cloud tool to call")
    args: dict[str, Any] = Field(default_factory=dict, description="Arguments for the cloud tool")


class GitHubSearchParams(BaseModel):
    """Search GitHub repositories, code, or issues"""

    query: str = Field(..., description="Search query")
    search_type: str = Field(
        default="repositories", description="Search type: repositories, code, issues"
    )
    limit: int = Field(default=10, description="Maximum number of results to return")
    sort: str | None = Field(default=None, description="Sort option (stars, updated, etc.)")
    order: str | None = Field(default="desc", description="Sort order: asc or desc")


class CloudDocGetParams(BaseModel):
    doc_id: str = Field(..., description="ID of the document to get")
    fields: set[str] | None = Field(None, description="Fields to retrieve")


class CloudDocPatchParams(BaseModel):
    doc_id: str = Field(..., description="ID of the document to patch")
    data: dict[str, Any] = Field(..., description="Data to patch")


class DocGetParams(BaseModel):
    doc_id: str = Field(..., description="ID of the document to get")


class DocPatchParams(BaseModel):
    doc_id: str = Field(..., description="ID of the document to patch")
    base_rev: str | None = Field(None, description="Expected current revision of the document")
    ops: list[dict[str, Any]] = Field(..., description="List of patch operations")


class ExecParams(BaseModel):
    cmd: str = Field(..., description="Command to execute")
    cwd: str | None = Field(None, description="Working directory")
    env: dict[str, str] | None = Field(None, description="Environment variables")


# ATA Message Parameters - Enhanced
class ATASendParams(BaseModel):
    taskcode: str = Field(..., description="Task code associated with the message")
    from_agent: str = Field(..., description="Source agent (e.g., GPT, Cursor, TRAE)")
    to_agent: str = Field(..., description="Target agent (e.g., GPT, Cursor, TRAE)")
    kind: str = Field(
        default="request", description="Message kind (e.g., request, ack, response, bootstrap)"
    )
    payload: dict[str, Any] = Field(..., description="Message payload content")
    prev_sha256: str | None = Field(
        None, description="Previous message SHA256 for chain validation"
    )
    priority: str | None = Field(
        default="normal", description="Message priority (low, normal, high, urgent)"
    )
    requires_response: bool = Field(
        default=True, description="Whether this message requires a response"
    )
    context_hint: str | None = Field(None, description="Context hint for conversation continuity")


class ATASendRequestParams(BaseModel):
    """Non-admin: request an ATA send (queued for admin review)."""

    taskcode: str = Field(..., description="Task code associated with the message")
    from_agent: str = Field(..., description="Source agent (agent_id)")
    to_agent: str = Field(..., description="Target agent (agent_id)")
    kind: str = Field(
        default="request", description="Message kind (e.g., request, ack, response, bootstrap)"
    )
    payload: dict[str, Any] = Field(
        ..., description="Message payload content (must include message/text)"
    )
    priority: str | None = Field(
        default="normal", description="Message priority (low, normal, high, urgent)"
    )
    requires_response: bool = Field(
        default=True, description="Whether this message requires a response"
    )
    context_hint: str | None = Field(None, description="Context hint for conversation continuity")
    # Audit pointers required for approval (fail-closed at review time)
    report_path: str | None = Field(None, description="REPORT path pointer (repo-relative)")
    selftest_log_path: str | None = Field(
        None, description="selftest.log path pointer (repo-relative)"
    )
    evidence_dir: str | None = Field(
        None, description="Evidence artifacts dir pointer (repo-relative)"
    )


class ATASendReviewParams(BaseModel):
    """Admin: approve/reject a pending ATA send request."""

    request_id: str = Field(..., description="Outbox request id")
    action: str = Field(..., description="approve or reject")
    reason: str | None = Field(None, description="Reason for reject or optional note for approve")


class ATAReceiveParams(BaseModel):
    taskcode: str | None = Field(None, description="Filter by task code")
    from_agent: str | None = Field(None, description="Filter by source agent")
    to_agent: str | None = Field(None, description="Filter by target agent")
    kind: str | None = Field(None, description="Filter by message kind")
    priority: str | None = Field(None, description="Filter by priority (low, normal, high, urgent)")
    status: str | None = Field(
        None, description="Filter by status (pending, delivered, read, acked)"
    )
    unread_only: bool = Field(default=False, description="Return only unread messages")
    limit: int = Field(default=50, description="Maximum number of messages to return")
    include_context: bool = Field(
        default=False, description="Include conversation context in response"
    )


class ATAMessageMarkParams(BaseModel):
    """Mark ATA messages as read/acked/archived (receiver-side)."""

    msg_ids: list[str] = Field(..., description="List of ATA msg_id to mark")
    status: str = Field(..., description="Status to set (read, acked, archived)")


class ATATaskCreateParams(BaseModel):
    task_code: str | None = Field(None, description="ATA task code (optional)")
    from_agent: str | None = Field(None, description="Requesting agent id")
    owner_role: str | None = Field(None, description="Owner role for routing")
    area: str | None = Field(None, description="Task area/domain")
    priority: int = Field(default=1, description="Priority 0-3")
    goal: str = Field(..., description="Task goal")
    capsule: str = Field(..., description="Task capsule/instructions")
    how_to_repro: str = Field(..., description="Reproduction steps")
    expected: str = Field(..., description="Expected outcome")
    actual: str | None = Field(default=None, description="Actual outcome")
    evidence_requirements: str = Field(..., description="Evidence requirements")
    scope_files: list[str] = Field(default_factory=list, description="Repo-relative scope files")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Additional metadata")
    deadline: str | None = Field(default=None, description="Optional deadline")
    owner: str | None = Field(default=None, description="Owner name/id")
    task_type: str | None = Field(default=None, description="Task type")


class ATATaskStatusParams(BaseModel):
    task_code: str | None = Field(None, description="Task code")
    task_id: str | None = Field(None, description="Task id")


class ATATaskResultParams(BaseModel):
    task_code: str = Field(..., description="Task code")
    status: str | None = Field(None, description="Result status (DONE/FAIL/CANCELLED)")
    result: dict[str, Any] | None = Field(None, description="Result payload")
    report_path: str | None = Field(None, description="REPORT path (repo-relative)")
    selftest_log_path: str | None = Field(None, description="selftest.log path (repo-relative)")
    evidence_dir: str | None = Field(None, description="Evidence dir (repo-relative)")


class ATACIVerifyParams(BaseModel):
    task_code: str = Field(..., description="Task code")
    report_path: str | None = Field(None, description="REPORT path (repo-relative)")
    selftest_log_path: str | None = Field(None, description="selftest.log path (repo-relative)")
    evidence_dir: str | None = Field(None, description="Evidence dir (repo-relative)")


class DialogRegisterParams(BaseModel):
    """Register a Cursor dialog with a unique identity"""

    agent_type: str = Field(default="Cursor", description="Agent type (e.g., Cursor, GPT, TRAE)")
    dialog_name: str | None = Field(None, description="Optional dialog name/description")
    dialog_id: str | None = Field(
        None, description="Optional custom dialog ID (auto-generated if not provided)"
    )


class DialogListParams(BaseModel):
    """List all registered dialogs"""

    agent_type: str | None = Field(None, description="Filter by agent type")


class ConversationStatsParams(BaseModel):
    """Get statistics for conversations"""

    dialog_id: str | None = Field(None, description="Filter by dialog ID (optional)")
    agent_type: str | None = Field(None, description="Filter by agent type (optional)")
    taskcode: str | None = Field(None, description="Filter by task code (optional)")
    from_date: str | None = Field(None, description="Filter from date (YYYY-MM-DD)")
    to_date: str | None = Field(None, description="Filter to date (YYYY-MM-DD)")


class ConversationSearchParams(BaseModel):
    """Search conversations by content"""

    query: str = Field(..., description="Search query")
    dialog_id: str | None = Field(None, description="Filter by dialog ID (optional)")
    agent_type: str | None = Field(None, description="Filter by agent type (optional)")
    taskcode: str | None = Field(None, description="Filter by task code (optional)")
    limit: int = Field(default=50, description="Maximum number of results")


class ConversationHistoryParams(BaseModel):
    """Get conversation history for a dialog"""

    dialog_id: str = Field(..., description="Dialog ID")
    taskcode: str | None = Field(None, description="Filter by task code (optional)")
    limit: int = Field(default=100, description="Maximum number of messages")
    include_context: bool = Field(default=False, description="Include conversation context")


class ConversationMarkParams(BaseModel):
    """Mark conversation messages"""

    dialog_id: str = Field(..., description="Dialog ID")
    msg_ids: list[str] = Field(..., description="List of message IDs to mark")
    status: str = Field(..., description="Status to set (read, acked, archived)")


class FileReadParams(BaseModel):
    """Read file content for sending in ATA messages"""

    file_path: str = Field(..., description="Relative file path from repo root")
    encoding: str | None = Field(default="utf-8", description="File encoding (utf-8, binary)")
    max_size: int | None = Field(
        default=10485760, description="Maximum file size in bytes (default 10MB)"
    )


class ATASendWithFileParams(BaseModel):
    """Send ATA message with file content embedded"""

    taskcode: str = Field(..., description="Task code associated with the message")
    from_agent: str = Field(..., description="Source agent (e.g., GPT, Cursor, TRAE)")
    to_agent: str = Field(..., description="Target agent (e.g., GPT, Cursor, TRAE)")
    kind: str = Field(
        default="request", description="Message kind (e.g., request, ack, response, bootstrap)"
    )
    message: str | None = Field(None, description="Optional message text")
    file_path: str = Field(..., description="Relative file path from repo root to send")
    encoding: str | None = Field(
        default="utf-8", description="File encoding (utf-8 for text, binary for binary files)"
    )
    prev_sha256: str | None = Field(
        None, description="Previous message SHA256 for chain validation"
    )
    priority: str | None = Field(
        default="normal", description="Message priority (low, normal, high, urgent)"
    )
    requires_response: bool = Field(
        default=True, description="Whether this message requires a response"
    )
    context_hint: str | None = Field(None, description="Context hint for conversation continuity")


# Agent Collaboration Parameters
class TaskCreateParams(BaseModel):
    """Create a collaborative task"""

    task_description: str = Field(..., description="Task description")
    workflow_template: str | None = Field(None, description="Workflow template name")
    priority: str = Field(default="normal", description="Task priority (low, normal, high, urgent)")
    timeout: float | None = Field(None, description="Task timeout in seconds")
    required_roles: list[str] | None = Field(None, description="Required roles")


class TaskStatusParams(BaseModel):
    """Query task status"""

    task_id: str = Field(..., description="Task ID")
    include_subtasks: bool = Field(default=True, description="Include subtask status")


class AgentRegisterParams(BaseModel):
    """Register an agent"""

    agent_id: str = Field(..., description="Agent ID")
    agent_type: str = Field(..., description="Agent type (Cursor, GPT, TRAE)")
    role: str = Field(..., description="Agent role")
    capabilities: list[str] = Field(..., description="Agent capabilities")
    max_concurrent_tasks: int = Field(default=5, description="Max concurrent tasks")
    numeric_code: int | None = Field(
        None, description="Numeric code (1-100, unique, auto-assigned if not provided)"
    )
    send_enabled: bool | None = Field(
        None, description="Whether this agent is allowed to send ATA messages (read-only if false)"
    )
    category: str | None = Field(
        None,
        description="Agent category: 'user_ai' (用户AI) or 'system_ai' (系统AI), auto-inferred from numeric_code if not provided",
    )


class AgentApplyParams(BaseModel):
    """Apply for agent registration (pending approval by ATA admin)."""

    agent_id: str = Field(..., description="Desired Agent ID (unique key)")
    agent_type: str = Field(..., description="Agent type (Cursor, GPT, TRAE, etc.)")
    role: str = Field(..., description="Requested agent role")
    capabilities: list[str] = Field(..., description="Requested capabilities")
    max_concurrent_tasks: int = Field(default=5, description="Requested max concurrent tasks")
    numeric_code: int | None = Field(
        None, description="Requested numeric code (optional, admin may override)"
    )
    send_enabled: bool | None = Field(
        None, description="Requested send_enabled (optional, admin may override)"
    )
    category: str | None = Field(
        None,
        description="Requested category: 'user_ai' or 'system_ai' (optional, admin may override)",
    )
    note: str | None = Field(None, description="Optional note for admin")


class WorkflowExecuteParams(BaseModel):
    """Execute a workflow"""

    workflow_name: str = Field(..., description="Workflow template name")
    inputs: dict[str, Any] = Field(..., description="Workflow inputs")
    task_id: str | None = Field(None, description="Optional task ID")


class ResultGetParams(BaseModel):
    """Get task results"""

    task_id: str = Field(..., description="Task ID")
    include_intermediate: bool = Field(default=False, description="Include intermediate results")


class ToolExecutor:
    def __init__(self, repo_root: str, inbox_dir: str, board_file: str, security, audit_logger):
        self.repo_root = Path(repo_root).resolve()
        self.inbox_dir = self.repo_root / inbox_dir
        self.board_file = self.repo_root / board_file
        self.security = security
        self.audit = audit_logger
        self.ata_messages_dir = self.repo_root / "docs" / "REPORT" / "ata" / "messages"
        self.ata_messages_dir.mkdir(parents=True, exist_ok=True)

        # Enhanced ATA directories
        self.ata_context_dir = self.repo_root / "docs" / "REPORT" / "ata" / "contexts"
        self.ata_context_dir.mkdir(parents=True, exist_ok=True)
        self.ata_queue_dir = self.repo_root / "docs" / "REPORT" / "ata" / "queue"
        self.ata_queue_dir.mkdir(parents=True, exist_ok=True)

        # Dialog registry directory
        self.dialog_registry_dir = self.repo_root / "docs" / "REPORT" / "ata" / "dialogs"
        self.dialog_registry_dir.mkdir(parents=True, exist_ok=True)
        self.dialog_registry_file = self.dialog_registry_dir / "registry.json"

        # Import enhanced ATA module (optional, won't break if missing)
        try:
            from .ata_enhanced import ATAEnhanced

            self.ata_enhanced = ATAEnhanced(
                self.ata_messages_dir, self.ata_context_dir, self.ata_queue_dir
            )
        except ImportError:
            self.ata_enhanced = None

        # Initialize DialogTools for conversation management
        try:
            from .dialog_tools import DialogTools

            self.dialog_tools = DialogTools(str(repo_root))
        except ImportError:
            self.dialog_tools = None

        # Initialize Agent Collaboration modules
        try:
            from .aggregator import ResultAggregator
            from .coordinator import AgentCoordinator
            from .orchestrator import TaskOrchestrator
            from .workflow_engine import WorkflowEngine

            self.orchestrator = TaskOrchestrator(self.repo_root)
            self.coordinator = AgentCoordinator(self.repo_root)
            self.aggregator = ResultAggregator(self.repo_root)
            self.workflow_engine = WorkflowEngine(self.repo_root, self.coordinator, self)
        except ImportError:
            # If modules are not available, set to None
            self.orchestrator = None
            self.coordinator = None
            self.aggregator = None
            self.workflow_engine = None

        self.ata_mailbox = ATAMailbox(self.repo_root, self.security)
        self.ata_router = ATARouter(self.repo_root, self.coordinator)
        self.ata_ci = ATACIVerifier(self.repo_root)
        self.a2a_hub_url = os.getenv("A2A_HUB_URL") or (
            f"http://{os.getenv('A2A_HUB_HOST', '127.0.0.1')}:{os.getenv('A2A_HUB_PORT', '5001')}"
        )

        self.inbox_dir.mkdir(parents=True, exist_ok=True)

        # Version control - stores current rev for each file
        self._file_revs: dict[str, str] = {}

        # Request idempotency - stores completed request_ids and their results
        self._completed_requests: dict[str, dict] = {}

        # Concurrency control
        self._running_run_id: str | None = None
        self._lock = threading.Lock()

        # Initialize revs for existing files
        self._initialize_revs()

    # ----------------------------
    # ATA Admin hard-logic helpers
    # ----------------------------
    def _is_admin(self, auth_ctx: dict[str, Any] | None) -> bool:
        return bool(auth_ctx and auth_ctx.get("is_admin") is True)

    def _require_admin(self, auth_ctx: dict[str, Any] | None, action: str) -> dict[str, Any] | None:
        if self._is_admin(auth_ctx):
            return None
        return {
            "success": False,
            "error": f"ADMIN_REQUIRED: {action} requires ATA admin privileges (fail-closed)",
        }

    def _admin_vault_dir(self) -> Path:
        p = self.repo_root / "docs" / "REPORT" / "ata" / "admin_vault"
        p.mkdir(parents=True, exist_ok=True)
        return p

    def _agent_applications_dir(self) -> Path:
        p = self.repo_root / "docs" / "REPORT" / "ata" / "agent_applications"
        p.mkdir(parents=True, exist_ok=True)
        return p

    def _ata_outbox_dir(self) -> Path:
        p = self.repo_root / "docs" / "REPORT" / "ata" / "outbox"
        p.mkdir(parents=True, exist_ok=True)
        return p

    def _ata_outbox_file(self) -> Path:
        return self._ata_outbox_dir() / "pending.json"

    def _load_ata_outbox(self) -> dict[str, Any]:
        f = self._ata_outbox_file()
        if not f.exists():
            return {"requests": {}}
        try:
            with open(f, encoding="utf-8") as fp:
                data = json.load(fp)
            if not isinstance(data, dict):
                return {"requests": {}}
            if "requests" not in data or not isinstance(data["requests"], dict):
                data["requests"] = {}
            return data
        except Exception:
            return {"requests": {}}

    def _save_ata_outbox(self, data: dict[str, Any]) -> None:
        f = self._ata_outbox_file()
        with open(f, "w", encoding="utf-8") as fp:
            json.dump(data, fp, ensure_ascii=False, indent=2)

    def _is_repo_relative_path(self, p: str | None) -> bool:
        if not p or not isinstance(p, str):
            return False
        s = p.strip()
        if not s:
            return False
        # deny absolute or traversal
        if s.startswith("/") or s.startswith("\\"):
            return False
        if len(s) > 1 and s[1] == ":":
            return False
        if ".." in s:
            return False
        return True

    def _validate_outbox_template_for_approval(
        self,
        to_agent_id: str,
        payload: dict[str, Any],
        report_path: str | None,
        selftest_log_path: str | None,
        evidence_dir: str | None,
    ) -> str | None:
        """
        Admin review-time hard validation (fail-closed):
        - message/text must start with @对方#NN
        - audit pointers must be repo-relative and present
        """
        # audit pointers required
        if not self._is_repo_relative_path(report_path):
            return "TEMPLATE_INVALID: report_path is required and must be repo-relative"
        if not self._is_repo_relative_path(selftest_log_path):
            return "TEMPLATE_INVALID: selftest_log_path is required and must be repo-relative"
        if not self._is_repo_relative_path(evidence_dir):
            return "TEMPLATE_INVALID: evidence_dir is required and must be repo-relative"

        # message prefix
        msg_text = None
        if isinstance(payload, dict):
            if isinstance(payload.get("message"), str):
                msg_text = payload.get("message")
            elif isinstance(payload.get("text"), str):
                msg_text = payload.get("text")
        if not isinstance(msg_text, str) or not msg_text.strip():
            return "TEMPLATE_INVALID: payload.message (or payload.text) is required"

        if not self.coordinator:
            return "TEMPLATE_INVALID: AgentCoordinator not available"
        to_obj = self.coordinator.registry.get_agent(to_agent_id)
        if not to_obj or getattr(to_obj, "numeric_code", None) is None:
            return "TEMPLATE_INVALID: cannot resolve recipient display name"
        to_display = f"{to_obj.agent_id}#{int(to_obj.numeric_code):02d}"
        required_prefix = f"@{to_display}"
        if not msg_text.lstrip().startswith(required_prefix):
            return f"TEMPLATE_INVALID: message must start with '{required_prefix}'"
        return None

    def _agent_application_file(self) -> Path:
        return self._agent_applications_dir() / "pending.json"

    def _load_agent_applications(self) -> dict[str, Any]:
        f = self._agent_application_file()
        if not f.exists():
            return {"applications": {}}
        try:
            with open(f, encoding="utf-8") as fp:
                data = json.load(fp)
            if not isinstance(data, dict):
                return {"applications": {}}
            if "applications" not in data or not isinstance(data["applications"], dict):
                data["applications"] = {}
            return data
        except Exception:
            return {"applications": {}}

    def _save_agent_applications(self, data: dict[str, Any]) -> None:
        f = self._agent_application_file()
        with open(f, "w", encoding="utf-8") as fp:
            json.dump(data, fp, ensure_ascii=False, indent=2)

    def agent_apply(
        self,
        params: AgentApplyParams,
        caller: str = "unknown",
        user_agent: str | None = None,
        trace_id: str | None = None,
    ) -> dict:
        """Public: create/update a pending registration application."""
        start_time = datetime.now()
        try:
            if not self.coordinator:
                return {"success": False, "error": "AgentCoordinator not available"}

            agent_id = params.agent_id.strip()
            if not agent_id:
                return {"success": False, "error": "agent_id is required"}

            # If already registered, fail-closed (申请制度：注册只能管理员做)
            if self.coordinator.registry.get_agent(agent_id) is not None:
                return {"success": False, "error": f"Agent already registered: {agent_id}"}

            data = self._load_agent_applications()
            apps = data["applications"]
            apps[agent_id] = {
                "agent_id": agent_id,
                "agent_type": params.agent_type,
                "role": params.role,
                "capabilities": params.capabilities,
                "max_concurrent_tasks": params.max_concurrent_tasks,
                "requested_numeric_code": params.numeric_code,
                "requested_send_enabled": params.send_enabled,
                "requested_category": params.category,
                "note": params.note,
                "status": "pending",
                "submitted_at": datetime.now().isoformat() + "Z",
                "submitted_by": caller,
            }
            self._save_agent_applications(data)

            result = {
                "success": True,
                "agent_id": agent_id,
                "status": "pending",
                "pending_path": str(self._agent_application_file().relative_to(self.repo_root)),
            }
            self.audit.log_tool_call(
                "agent_apply",
                caller,
                params.dict(),
                True,
                result,
                start_time=start_time,
                user_agent=user_agent,
                trace_id=trace_id,
            )
            return result
        except Exception as e:
            error_msg = f"Failed to apply for agent registration: {str(e)}"
            self.audit.log_tool_call(
                "agent_apply",
                caller,
                params.dict(),
                False,
                error=error_msg,
                start_time=start_time,
                user_agent=user_agent,
                trace_id=trace_id,
            )
            return {"success": False, "error": error_msg}

    def agent_approve(
        self,
        agent_id: str,
        caller: str = "unknown",
        user_agent: str | None = None,
        trace_id: str | None = None,
        auth_ctx: dict[str, Any] | None = None,
        numeric_code: int | None = None,
        send_enabled: bool | None = None,
    ) -> dict:
        """Admin-only: approve a pending application and register the agent (ensures numeric_code uniqueness)."""
        start_time = datetime.now()
        try:
            admin_err = self._require_admin(auth_ctx, "agent_approve")
            if admin_err:
                self.audit.log_tool_call(
                    "agent_approve",
                    caller,
                    {"agent_id": agent_id},
                    False,
                    error=admin_err["error"],
                    start_time=start_time,
                    user_agent=user_agent,
                    trace_id=trace_id,
                )
                return admin_err
            if not self.coordinator:
                return {"success": False, "error": "AgentCoordinator not available"}

            data = self._load_agent_applications()
            apps = data.get("applications", {})
            app = apps.get(agent_id)
            if not app:
                return {
                    "success": False,
                    "error": f"No pending application for agent_id={agent_id}",
                }
            if app.get("status") != "pending":
                return {
                    "success": False,
                    "error": f"Application not pending: status={app.get('status')}",
                }

            # Admin can override requested numeric_code / send_enabled / category
            final_numeric = (
                numeric_code if numeric_code is not None else app.get("requested_numeric_code")
            )
            final_send = (
                send_enabled if send_enabled is not None else app.get("requested_send_enabled")
            )
            # Category: infer from numeric_code if not provided
            final_category = app.get("requested_category")
            if final_category is None and final_numeric is not None:
                if 1 <= final_numeric <= 10:
                    final_category = "system_ai"
                else:
                    final_category = "user_ai"

            result = self.coordinator.register_agent(
                agent_id=app["agent_id"],
                agent_type=app["agent_type"],
                role=app["role"],
                capabilities=app.get("capabilities", []),
                max_concurrent_tasks=app.get("max_concurrent_tasks", 5),
                numeric_code=final_numeric,
                send_enabled=final_send,
                category=final_category,
            )

            # Mark application
            app["status"] = "approved" if result.get("success") else "failed"
            app["approved_at"] = datetime.now().isoformat() + "Z"
            app["approved_by"] = caller
            app["register_result"] = result
            apps[agent_id] = app
            data["applications"] = apps
            self._save_agent_applications(data)

            self.audit.log_tool_call(
                "agent_approve",
                caller,
                {"agent_id": agent_id, "numeric_code": final_numeric, "send_enabled": final_send},
                bool(result.get("success")),
                result,
                start_time=start_time,
                user_agent=user_agent,
                trace_id=trace_id,
            )
            return result
        except Exception as e:
            error_msg = f"Failed to approve agent: {str(e)}"
            self.audit.log_tool_call(
                "agent_approve",
                caller,
                {"agent_id": agent_id},
                False,
                error=error_msg,
                start_time=start_time,
                user_agent=user_agent,
                trace_id=trace_id,
            )
            return {"success": False, "error": error_msg}

    # ----------------------------
    # ATA Outbox (proxy-send workflow)
    # ----------------------------
    def ata_send_request(
        self,
        params: ATASendRequestParams,
        caller: str = "unknown",
        user_agent: str | None = None,
        trace_id: str | None = None,
    ) -> dict:
        """Public: enqueue an ATA send request for admin review."""
        start_time = datetime.now()
        try:
            if not self.coordinator:
                return {"success": False, "error": "AgentCoordinator not available"}

            # from/to must be registered (fail-closed)
            if self.coordinator.registry.get_agent(params.from_agent) is None:
                return {"success": False, "error": f"Sender not registered: {params.from_agent}"}
            if self.coordinator.registry.get_agent(params.to_agent) is None:
                return {"success": False, "error": f"Recipient not registered: {params.to_agent}"}

            # sender must be allowed to send (policy: read-only agents cannot even request)
            from_obj = self.coordinator.registry.get_agent(params.from_agent)
            if from_obj is None or not bool(getattr(from_obj, "send_enabled", True)):
                return {"success": False, "error": f"Send disabled for agent: {params.from_agent}"}

            # create request id
            req_id = f"ATA-OUTBOX-{datetime.now().strftime('%Y%m%d%H%M%S')}-{hashlib.md5((params.taskcode + params.from_agent + params.to_agent).encode()).hexdigest()[:10]}"

            data = self._load_ata_outbox()
            reqs = data["requests"]
            reqs[req_id] = {
                "request_id": req_id,
                "status": "pending",
                "submitted_at": datetime.now().isoformat() + "Z",
                "submitted_by": caller,
                "taskcode": params.taskcode,
                "from_agent": params.from_agent,
                "to_agent": params.to_agent,
                "kind": params.kind,
                "payload": params.payload,
                "priority": params.priority,
                "requires_response": params.requires_response,
                "context_hint": params.context_hint,
                "report_path": params.report_path,
                "selftest_log_path": params.selftest_log_path,
                "evidence_dir": params.evidence_dir,
            }
            data["requests"] = reqs
            self._save_ata_outbox(data)

            result = {
                "success": True,
                "request_id": req_id,
                "status": "pending",
                "queue_path": str(self._ata_outbox_file().relative_to(self.repo_root)),
            }
            self.audit.log_tool_call(
                "ata_send_request",
                caller,
                params.dict(),
                True,
                result,
                start_time=start_time,
                user_agent=user_agent,
                trace_id=trace_id,
            )
            return result
        except Exception as e:
            error_msg = f"Failed to enqueue ata send request: {str(e)}"
            self.audit.log_tool_call(
                "ata_send_request",
                caller,
                params.dict(),
                False,
                error=error_msg,
                start_time=start_time,
                user_agent=user_agent,
                trace_id=trace_id,
            )
            return {"success": False, "error": error_msg}

    def ata_send_review(
        self,
        params: ATASendReviewParams,
        caller: str = "unknown",
        user_agent: str | None = None,
        trace_id: str | None = None,
        auth_ctx: dict[str, Any] | None = None,
    ) -> dict:
        """Admin: approve/reject a pending outbox request. Approve triggers actual ata_send."""
        start_time = datetime.now()
        try:
            admin_err = self._require_admin(auth_ctx, "ata_send_review")
            if admin_err:
                self.audit.log_tool_call(
                    "ata_send_review",
                    caller,
                    params.dict(),
                    False,
                    error=admin_err["error"],
                    start_time=start_time,
                    user_agent=user_agent,
                    trace_id=trace_id,
                )
                return admin_err

            action = (params.action or "").strip().lower()
            if action not in ("approve", "reject"):
                return {"success": False, "error": "action must be 'approve' or 'reject'"}

            data = self._load_ata_outbox()
            reqs = data.get("requests", {})
            req = reqs.get(params.request_id)
            if not req:
                return {"success": False, "error": f"Outbox request not found: {params.request_id}"}
            if req.get("status") != "pending":
                return {
                    "success": False,
                    "error": f"Outbox request not pending: status={req.get('status')}",
                }

            if action == "reject":
                req["status"] = "rejected"
                req["reviewed_at"] = datetime.now().isoformat() + "Z"
                req["reviewed_by"] = caller
                req["reject_reason"] = params.reason or "Rejected by admin"
                reqs[params.request_id] = req
                data["requests"] = reqs
                self._save_ata_outbox(data)
                result = {
                    "success": True,
                    "request_id": params.request_id,
                    "status": "rejected",
                    "reason": req["reject_reason"],
                }
                self.audit.log_tool_call(
                    "ata_send_review",
                    caller,
                    params.dict(),
                    True,
                    result,
                    start_time=start_time,
                    user_agent=user_agent,
                    trace_id=trace_id,
                )
                return result

            # approve: hard template validation + send
            if not self.coordinator:
                return {"success": False, "error": "AgentCoordinator not available"}
            tmpl_err = self._validate_outbox_template_for_approval(
                to_agent_id=req.get("to_agent"),
                payload=req.get("payload") if isinstance(req.get("payload"), dict) else {},
                report_path=req.get("report_path"),
                selftest_log_path=req.get("selftest_log_path"),
                evidence_dir=req.get("evidence_dir"),
            )
            if tmpl_err:
                # hard reject
                req["status"] = "rejected"
                req["reviewed_at"] = datetime.now().isoformat() + "Z"
                req["reviewed_by"] = caller
                req["reject_reason"] = (
                    tmpl_err if not params.reason else f"{tmpl_err}; note={params.reason}"
                )
                reqs[params.request_id] = req
                data["requests"] = reqs
                self._save_ata_outbox(data)
                result = {
                    "success": False,
                    "request_id": params.request_id,
                    "status": "rejected",
                    "error": req["reject_reason"],
                }
                self.audit.log_tool_call(
                    "ata_send_review",
                    caller,
                    params.dict(),
                    False,
                    error=req["reject_reason"],
                    start_time=start_time,
                    user_agent=user_agent,
                    trace_id=trace_id,
                )
                return result

            send_params = ATASendParams(
                taskcode=req["taskcode"],
                from_agent=req["from_agent"],
                to_agent=req["to_agent"],
                kind=req.get("kind", "request"),
                payload=req.get("payload") if isinstance(req.get("payload"), dict) else {},
                prev_sha256=req.get("prev_sha256"),
                priority=req.get("priority", "normal"),
                requires_response=bool(req.get("requires_response", True)),
                context_hint=req.get("context_hint"),
            )
            send_result = self.ata_send(
                send_params,
                caller=caller,
                user_agent=user_agent,
                trace_id=trace_id,
                auth_ctx=auth_ctx,
            )

            if not bool(send_result.get("success")):
                # fail-closed: keep pending but attach last_error
                req["last_error"] = send_result.get("error")
                reqs[params.request_id] = req
                data["requests"] = reqs
                self._save_ata_outbox(data)
                self.audit.log_tool_call(
                    "ata_send_review",
                    caller,
                    params.dict(),
                    False,
                    error=str(send_result.get("error")),
                    start_time=start_time,
                    user_agent=user_agent,
                    trace_id=trace_id,
                )
                return {
                    "success": False,
                    "request_id": params.request_id,
                    "status": "pending",
                    "error": send_result.get("error"),
                }

            # mark approved
            req["status"] = "approved"
            req["reviewed_at"] = datetime.now().isoformat() + "Z"
            req["reviewed_by"] = caller
            req["approve_note"] = params.reason
            req["send_result"] = {
                "msg_id": send_result.get("msg_id"),
                "sha256": send_result.get("sha256"),
                "file_path": send_result.get("file_path"),
            }
            reqs[params.request_id] = req
            data["requests"] = reqs
            self._save_ata_outbox(data)

            result = {
                "success": True,
                "request_id": params.request_id,
                "status": "approved",
                "send_result": req["send_result"],
            }
            self.audit.log_tool_call(
                "ata_send_review",
                caller,
                params.dict(),
                True,
                result,
                start_time=start_time,
                user_agent=user_agent,
                trace_id=trace_id,
            )
            return result
        except Exception as e:
            error_msg = f"Failed to review outbox request: {str(e)}"
            self.audit.log_tool_call(
                "ata_send_review",
                caller,
                params.dict(),
                False,
                error=error_msg,
                start_time=start_time,
                user_agent=user_agent,
                trace_id=trace_id,
            )
            return {"success": False, "error": error_msg}

    def inbox_append(
        self,
        params: InboxAppendParams,
        caller: str = "unknown",
        user_agent: str | None = None,
        trace_id: str | None = None,
        base_rev: str | None = None,
        request_id: str | None = None,
        running_run_id: str | None = None,
        auth_ctx: dict[str, Any] | None = None,
    ) -> dict:
        start_time = datetime.now()
        try:
            # Hard admin-only write policy (fail-closed)
            admin_err = self._require_admin(auth_ctx, "inbox_append")
            if admin_err:
                self.audit.log_tool_call(
                    "inbox_append",
                    caller,
                    params.dict(),
                    False,
                    error=admin_err["error"],
                    start_time=start_time,
                    user_agent=user_agent,
                    trace_id=trace_id,
                )
                return admin_err
            # Check idempotency
            existing_result = self._check_request_idempotency(request_id)
            if existing_result:
                return existing_result

            # Check concurrency lock
            if not self._check_lock(running_run_id):
                return {
                    "success": False,
                    "error": "Another operation is in progress",
                    "status": 409,
                }

            date_str = params.date
            if not self._validate_date_format(date_str):
                raise ValueError("Invalid date format. Use YYYY-MM-DD")

            inbox_file = self.inbox_dir / f"{date_str}.md"

            # Check base rev
            if not self._check_base_rev(inbox_file, base_rev):
                current_rev = self._get_file_rev(inbox_file)
                return {
                    "success": False,
                    "error": f"Revision mismatch: expected {base_rev}, got {current_rev}",
                    "status": 409,
                    "current_rev": current_rev,
                }

            allowed, message = self.security.check_access(str(inbox_file), "write")
            if not allowed:
                self.audit.log_tool_call(
                    "inbox_append",
                    caller,
                    params.dict(),
                    False,
                    error=message,
                    start_time=start_time,
                    user_agent=user_agent,
                    trace_id=trace_id,
                )
                return {"success": False, "error": message}

            # Acquire lock
            self._acquire_lock(running_run_id)

            timestamp = datetime.now().isoformat()
            block = f"""
## [{timestamp}] Task: {params.task_code} | Source: {params.source}

{params.text}

---
"""

            with open(inbox_file, "a", encoding="utf-8") as f:
                f.write(block)

            # Update rev
            new_rev = self._update_file_rev(inbox_file)

            result = {
                "success": True,
                "file_path": str(inbox_file.relative_to(self.repo_root)),
                "timestamp": timestamp,
                "rev": new_rev,
            }

            # Record completed request
            self._record_completed_request(request_id, result)

            self.audit.log_tool_call(
                "inbox_append",
                caller,
                params.dict(),
                True,
                result,
                start_time=start_time,
                user_agent=user_agent,
                trace_id=trace_id,
            )

            # Release lock
            self._release_lock()

            return result

        except Exception as e:
            # Release lock if acquired
            self._release_lock()

            error_msg = f"Failed to append to inbox: {str(e)}"
            self.audit.log_tool_call(
                "inbox_append",
                caller,
                params.dict(),
                False,
                error=error_msg,
                start_time=start_time,
                user_agent=user_agent,
                trace_id=trace_id,
            )
            return {"success": False, "error": error_msg}

    def inbox_tail(
        self,
        params: InboxTailParams,
        caller: str = "unknown",
        user_agent: str | None = None,
        trace_id: str | None = None,
    ) -> dict:
        start_time = datetime.now()
        try:
            date_str = params.date
            if not self._validate_date_format(date_str):
                raise ValueError("Invalid date format. Use YYYY-MM-DD")

            inbox_file = self.inbox_dir / f"{date_str}.md"

            allowed, message = self.security.check_access(str(inbox_file), "read")
            if not allowed:
                self.audit.log_tool_call(
                    "inbox_tail",
                    caller,
                    params.dict(),
                    False,
                    error=message,
                    start_time=start_time,
                    user_agent=user_agent,
                    trace_id=trace_id,
                )
                return {"success": False, "error": message}

            if not inbox_file.exists():
                result = {
                    "success": True,
                    "content": "",
                    "message": "Inbox file does not exist yet",
                }
                self.audit.log_tool_call(
                    "inbox_tail",
                    caller,
                    params.dict(),
                    True,
                    result,
                    start_time=start_time,
                    user_agent=user_agent,
                    trace_id=trace_id,
                )
                return result

            with open(inbox_file, encoding="utf-8") as f:
                lines = f.readlines()

            n = min(params.n, len(lines))
            content = "".join(lines[-n:]) if n > 0 else ""

            rev = self._get_file_rev(inbox_file)
            result = {"success": True, "content": content, "lines_returned": n, "rev": rev}
            self.audit.log_tool_call(
                "inbox_tail",
                caller,
                params.dict(),
                True,
                result,
                start_time=start_time,
                user_agent=user_agent,
                trace_id=trace_id,
            )
            return result

        except Exception as e:
            error_msg = f"Failed to read inbox: {str(e)}"
            self.audit.log_tool_call(
                "inbox_tail",
                caller,
                params.dict(),
                False,
                error=error_msg,
                start_time=start_time,
                user_agent=user_agent,
                trace_id=trace_id,
            )
            return {"success": False, "error": error_msg}

    def board_get(
        self, caller: str = "unknown", user_agent: str | None = None, trace_id: str | None = None
    ) -> dict:
        start_time = datetime.now()
        try:
            allowed, message = self.security.check_access(str(self.board_file), "read")
            if not allowed:
                self.audit.log_tool_call(
                    "board_get",
                    caller,
                    {},
                    False,
                    error=message,
                    start_time=start_time,
                    user_agent=user_agent,
                    trace_id=trace_id,
                )
                return {"success": False, "error": message}

            if not self.board_file.exists():
                result = {
                    "success": True,
                    "content": "",
                    "message": "Program Board file does not exist yet",
                }
                self.audit.log_tool_call(
                    "board_get",
                    caller,
                    {},
                    True,
                    result,
                    start_time=start_time,
                    user_agent=user_agent,
                    trace_id=trace_id,
                )
                return result

            with open(self.board_file, encoding="utf-8") as f:
                content = f.read()

            rev = self._get_file_rev(self.board_file)
            result = {"success": True, "content": content, "rev": rev}
            self.audit.log_tool_call(
                "board_get",
                caller,
                {},
                True,
                result,
                start_time=start_time,
                user_agent=user_agent,
                trace_id=trace_id,
            )
            return result

        except Exception as e:
            error_msg = f"Failed to read board: {str(e)}"
            self.audit.log_tool_call(
                "board_get",
                caller,
                {},
                False,
                error=error_msg,
                start_time=start_time,
                user_agent=user_agent,
                trace_id=trace_id,
            )
            return {"success": False, "error": error_msg}

    def board_set_status(
        self,
        params: BoardSetStatusParams,
        caller: str = "unknown",
        user_agent: str | None = None,
        trace_id: str | None = None,
        base_rev: str | None = None,
        request_id: str | None = None,
        running_run_id: str | None = None,
        auth_ctx: dict[str, Any] | None = None,
    ) -> dict:
        start_time = datetime.now()
        try:
            # Hard admin-only write policy (fail-closed)
            admin_err = self._require_admin(auth_ctx, "board_set_status")
            if admin_err:
                self.audit.log_tool_call(
                    "board_set_status",
                    caller,
                    params.dict(),
                    False,
                    error=admin_err["error"],
                    start_time=start_time,
                    user_agent=user_agent,
                    trace_id=trace_id,
                )
                return admin_err
            # Check idempotency
            existing_result = self._check_request_idempotency(request_id)
            if existing_result:
                return existing_result

            # Check concurrency lock
            if not self._check_lock(running_run_id):
                return {
                    "success": False,
                    "error": "Another operation is in progress",
                    "status": 409,
                }

            allowed, message = self.security.check_access(str(self.board_file), "write")
            if not allowed:
                self.audit.log_tool_call(
                    "board_set_status",
                    caller,
                    params.dict(),
                    False,
                    error=message,
                    start_time=start_time,
                    user_agent=user_agent,
                    trace_id=trace_id,
                )
                return {"success": False, "error": message}

            # Check base rev
            if not self._check_base_rev(self.board_file, base_rev):
                current_rev = self._get_file_rev(self.board_file)
                return {
                    "success": False,
                    "error": f"Revision mismatch: expected {base_rev}, got {current_rev}",
                    "status": 409,
                    "current_rev": current_rev,
                }

            # Acquire lock
            self._acquire_lock(running_run_id)

            if not self.board_file.exists():
                self.board_file.parent.mkdir(parents=True, exist_ok=True)
                with open(self.board_file, "w", encoding="utf-8") as f:
                    f.write("# QCC Program Board v0.1\n\n")

            with open(self.board_file, encoding="utf-8") as f:
                content = f.read()

            task_marker = f"**Task Code:** {params.task_code}"

            if task_marker not in content:
                error_msg = f"Task {params.task_code} not found in board"
                self.audit.log_tool_call(
                    "board_set_status",
                    caller,
                    params.dict(),
                    False,
                    error=error_msg,
                    start_time=start_time,
                    user_agent=user_agent,
                    trace_id=trace_id,
                )
                return {"success": False, "error": error_msg}

            lines = content.split("\n")
            updated_lines = []
            task_found = False
            status_updated = False
            artifacts_updated = False

            for i, line in enumerate(lines):
                updated_lines.append(line)

                if task_marker in line and not task_found:
                    task_found = True
                    for j in range(i + 1, min(i + 10, len(lines))):
                        if lines[j].strip().startswith("**Status:**"):
                            updated_lines[-1] = lines[j]
                            updated_lines.append(f"**Status:** {params.status}")
                            status_updated = True
                        elif lines[j].strip().startswith("**Artifacts:**"):
                            if params.artifacts:
                                updated_lines[-1] = lines[j]
                                updated_lines.append(f"**Artifacts:** {params.artifacts}")
                                artifacts_updated = True
                        elif lines[j].strip().startswith("##") or lines[j].strip().startswith(
                            "---"
                        ):
                            break

            if not status_updated:
                error_msg = f"Could not find Status field for task {params.task_code}"
                self.audit.log_tool_call(
                    "board_set_status",
                    caller,
                    params.dict(),
                    False,
                    error=error_msg,
                    start_time=start_time,
                    user_agent=user_agent,
                    trace_id=trace_id,
                )
                return {"success": False, "error": error_msg}

            with open(self.board_file, "w", encoding="utf-8") as f:
                f.write("\n".join(updated_lines))

            # Update rev
            new_rev = self._update_file_rev(self.board_file)

            result = {
                "success": True,
                "task_code": params.task_code,
                "status_updated": status_updated,
                "artifacts_updated": artifacts_updated,
                "rev": new_rev,
            }

            # Record completed request
            self._record_completed_request(request_id, result)

            self.audit.log_tool_call(
                "board_set_status",
                caller,
                params.dict(),
                True,
                result,
                start_time=start_time,
                user_agent=user_agent,
                trace_id=trace_id,
            )

            # Release lock
            self._release_lock()

            return result

        except Exception as e:
            # Release lock if acquired
            self._release_lock()

            error_msg = f"Failed to update board: {str(e)}"
            self.audit.log_tool_call(
                "board_set_status",
                caller,
                params.dict(),
                False,
                error=error_msg,
                start_time=start_time,
                user_agent=user_agent,
                trace_id=trace_id,
            )
            return {"success": False, "error": error_msg}

    def ping(
        self, caller: str = "unknown", user_agent: str | None = None, trace_id: str | None = None
    ) -> dict:
        start_time = datetime.now()
        try:
            # Simple ping tool that returns current timestamp
            result = {"success": True, "ok": True}
            self.audit.log_tool_call(
                "ping",
                caller,
                {},
                True,
                result,
                start_time=start_time,
                user_agent=user_agent,
                trace_id=trace_id,
            )
            return result
        except Exception as e:
            error_msg = f"Failed to execute ping: {str(e)}"
            self.audit.log_tool_call(
                "ping",
                caller,
                {},
                False,
                error=error_msg,
                start_time=start_time,
                user_agent=user_agent,
                trace_id=trace_id,
            )
            return {"success": False, "error": error_msg}

    def echo(
        self,
        params: EchoParams,
        caller: str = "unknown",
        user_agent: str | None = None,
        trace_id: str | None = None,
    ) -> dict:
        start_time = datetime.now()
        try:
            # Simple echo tool that returns the input text
            result = {"success": True, "text": params.text}
            self.audit.log_tool_call(
                "echo",
                caller,
                params.dict(),
                True,
                result,
                start_time=start_time,
                user_agent=user_agent,
                trace_id=trace_id,
            )
            return result
        except Exception as e:
            error_msg = f"Failed to execute echo: {str(e)}"
            self.audit.log_tool_call(
                "echo",
                caller,
                params.dict(),
                False,
                error=error_msg,
                start_time=start_time,
                user_agent=user_agent,
                trace_id=trace_id,
            )
            return {"success": False, "error": error_msg}

    def doc_get(
        self,
        params: DocGetParams,
        caller: str = "unknown",
        user_agent: str | None = None,
        trace_id: str | None = None,
    ) -> dict:
        start_time = datetime.now()
        try:
            # Parse doc_id to get file path
            doc_id = params.doc_id
            file_path = self._get_file_path_from_doc_id(doc_id)

            # Debug log
            print(f"DEBUG: repo_root={self.repo_root}, doc_id={doc_id}, file_path={file_path}")

            # Check access permission
            allowed, message = self.security.check_access(str(file_path), "read")
            if not allowed:
                self.audit.log_tool_call(
                    "doc_get",
                    caller,
                    params.dict(),
                    False,
                    error=message,
                    start_time=start_time,
                    user_agent=user_agent,
                    trace_id=trace_id,
                )
                return {"success": False, "error": message}

            # Check if file exists
            if not file_path.exists():
                self.audit.log_tool_call(
                    "doc_get",
                    caller,
                    params.dict(),
                    False,
                    error=f"Document not found: {doc_id}. Actual path checked: {file_path}",
                    start_time=start_time,
                    user_agent=user_agent,
                    trace_id=trace_id,
                )
                return {
                    "success": False,
                    "error": f"Document not found: {doc_id}. Actual path checked: {file_path}",
                    "status": 404,
                }

            # Read file content
            with open(file_path, encoding="utf-8") as f:
                content = f.read()

            # Get file revision
            rev = self._get_file_rev(file_path)

            result = {"success": True, "content": content, "rev": rev}

            self.audit.log_tool_call(
                "doc_get",
                caller,
                params.dict(),
                True,
                result,
                start_time=start_time,
                user_agent=user_agent,
                trace_id=trace_id,
            )
            return result

        except Exception as e:
            error_msg = f"Failed to get document: {str(e)}"
            self.audit.log_tool_call(
                "doc_get",
                caller,
                params.dict(),
                False,
                error=error_msg,
                start_time=start_time,
                user_agent=user_agent,
                trace_id=trace_id,
            )
            return {"success": False, "error": error_msg}

    def doc_patch(
        self,
        params: DocPatchParams,
        caller: str = "unknown",
        user_agent: str | None = None,
        trace_id: str | None = None,
        base_rev: str | None = None,
        request_id: str | None = None,
        running_run_id: str | None = None,
        auth_ctx: dict[str, Any] | None = None,
    ) -> dict:
        start_time = datetime.now()
        try:
            admin_err = self._require_admin(auth_ctx, "doc_patch")
            if admin_err:
                self.audit.log_tool_call(
                    "doc_patch",
                    caller,
                    params.dict(),
                    False,
                    error=admin_err["error"],
                    start_time=start_time,
                    user_agent=user_agent,
                    trace_id=trace_id,
                )
                return admin_err
            # Check idempotency
            existing_result = self._check_request_idempotency(request_id)
            if existing_result:
                return existing_result

            # Check concurrency lock
            if not self._check_lock(running_run_id):
                return {
                    "success": False,
                    "error": "Another operation is in progress",
                    "status": 409,
                }

            # Parse doc_id to get file path
            doc_id = params.doc_id
            file_path = self._get_file_path_from_doc_id(doc_id)

            # Check access permission
            allowed, message = self.security.check_access(str(file_path), "write")
            if not allowed:
                self.audit.log_tool_call(
                    "doc_patch",
                    caller,
                    params.dict(),
                    False,
                    error=message,
                    start_time=start_time,
                    user_agent=user_agent,
                    trace_id=trace_id,
                )
                return {"success": False, "error": message}

            # Check if file exists
            if not file_path.exists():
                self.audit.log_tool_call(
                    "doc_patch",
                    caller,
                    params.dict(),
                    False,
                    error=f"Document not found: {doc_id}",
                    start_time=start_time,
                    user_agent=user_agent,
                    trace_id=trace_id,
                )
                return {"success": False, "error": f"Document not found: {doc_id}", "status": 404}

            # Check base rev (if provided)
            if params.base_rev:
                current_rev = self._get_file_rev(file_path)
                if params.base_rev != current_rev:
                    self.audit.log_tool_call(
                        "doc_patch",
                        caller,
                        params.dict(),
                        False,
                        error=f"Revision mismatch: expected {params.base_rev}, got {current_rev}",
                        start_time=start_time,
                        user_agent=user_agent,
                        trace_id=trace_id,
                    )
                    return {
                        "success": False,
                        "error": f"Revision mismatch: expected {params.base_rev}, got {current_rev}",
                        "status": 409,
                        "current_rev": current_rev,
                    }

            # Acquire lock
            self._acquire_lock(running_run_id)

            # Read current content
            with open(file_path, encoding="utf-8") as f:
                current_content = f.read()

            # Apply patch operations (simplified implementation)
            new_content = self._apply_patch_ops(current_content, params.ops)

            # Write new content to file
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(new_content)

            # Update revision
            new_rev = self._update_file_rev(file_path)

            # Generate change_id (unique identifier for this change)
            change_id = hashlib.sha256(
                f"{doc_id}:{new_rev}:{datetime.now().isoformat()}".encode()
            ).hexdigest()[:16]

            result = {"success": True, "new_rev": new_rev, "change_id": change_id}

            # Record completed request
            self._record_completed_request(request_id, result)

            self.audit.log_tool_call(
                "doc_patch",
                caller,
                params.dict(),
                True,
                result,
                start_time=start_time,
                user_agent=user_agent,
                trace_id=trace_id,
            )

            # Release lock
            self._release_lock()

            return result

        except Exception as e:
            # Release lock if acquired
            self._release_lock()

            error_msg = f"Failed to patch document: {str(e)}"
            self.audit.log_tool_call(
                "doc_patch",
                caller,
                params.dict(),
                False,
                error=error_msg,
                start_time=start_time,
                user_agent=user_agent,
                trace_id=trace_id,
            )
            return {"success": False, "error": error_msg}

    def _get_file_path_from_doc_id(self, doc_id: str) -> Path:
        """Convert doc_id to file path"""
        # Simple implementation: doc_id is a relative path from repo root
        return self.repo_root / doc_id

    def _apply_patch_ops(self, content: str, ops: list[dict[str, Any]]) -> str:
        """Apply patch operations to content"""
        # Simplified implementation: only support "replace" operation for now
        new_content = content
        for op in ops:
            op_type = op.get("type")
            if op_type == "replace":
                new_content = op.get("value", "")
        return new_content

    def cloud_call(
        self,
        params: CloudCallParams,
        caller: str = "unknown",
        user_agent: str | None = None,
        trace_id: str | None = None,
    ) -> dict:
        start_time = datetime.now()
        max_retries = 3
        retry_delay = 1.0  # seconds

        # Get upstream MCP URL from environment
        upstream_url = os.getenv("UPSTREAM_MCP_URL")
        if not upstream_url:
            error_msg = "UPSTREAM_MCP_URL not configured"
            self.audit.log_tool_call(
                "cloud_call",
                caller,
                params.dict(),
                False,
                error=error_msg,
                start_time=start_time,
                user_agent=user_agent,
                trace_id=trace_id,
            )
            return {"success": False, "error": error_msg}

        # Get authentication config
        upstream_auth_mode = os.getenv("UPSTREAM_AUTH_MODE", "none").lower()
        upstream_auth_value = os.getenv("UPSTREAM_AUTH_TOKEN") or os.getenv("UPSTREAM_AUTH_VALUE")

        # Prepare headers
        headers = {
            "Content-Type": "application/json",
            "User-Agent": user_agent or "QCC-Bus-MCP/0.1.0",
        }

        # Add authentication header if configured
        if upstream_auth_mode == "bearer" and upstream_auth_value:
            headers["Authorization"] = f"Bearer {upstream_auth_value}"
        elif upstream_auth_mode == "api_key" and upstream_auth_value:
            headers["X-API-Key"] = upstream_auth_value

        # Prepare the request to upstream MCP
        request_body = {
            "jsonrpc": "2.0",
            "id": "cloud_call",
            "method": "tools/call",
            "params": {"name": params.tool_name, "arguments": params.args},
        }

        # Retry logic with exponential backoff
        last_error = None
        for attempt in range(max_retries):
            try:
                # Send request to upstream MCP
                timeout = 30.0 + (attempt * 10.0)  # Increase timeout for retries
                response = httpx.post(
                    upstream_url,
                    json=request_body,
                    headers=headers,
                    timeout=timeout,
                    follow_redirects=True,
                )

                # Handle HTTP errors
                if response.status_code >= 500 and attempt < max_retries - 1:
                    # Server error - retry
                    wait_time = retry_delay * (2**attempt)
                    import time

                    time.sleep(wait_time)
                    continue

                response.raise_for_status()

                # Parse response
                response_data = response.json()

                # Check for JSON-RPC error
                if "error" in response_data:
                    error_code = response_data["error"].get("code", -1)
                    error_message = response_data["error"].get("message", "Unknown error")

                    # Don't retry on client errors (4xx)
                    if 400 <= error_code < 500:
                        error_msg = f"Cloud MCP error: {error_message} (code: {error_code})"
                        self.audit.log_tool_call(
                            "cloud_call",
                            caller,
                            params.dict(),
                            False,
                            error=error_msg,
                            start_time=start_time,
                            user_agent=user_agent,
                            trace_id=trace_id,
                        )
                        return {"success": False, "error": error_msg}
                    # Retry on server errors (5xx)
                    elif error_code >= 500 and attempt < max_retries - 1:
                        wait_time = retry_delay * (2**attempt)
                        import time

                        time.sleep(wait_time)
                        continue

                # Success
                result = {
                    "success": True,
                    "data": response_data.get("result", {}),
                    "response_id": response_data.get("id"),
                }

                self.audit.log_tool_call(
                    "cloud_call",
                    caller,
                    params.dict(),
                    True,
                    result,
                    start_time=start_time,
                    user_agent=user_agent,
                    trace_id=trace_id,
                )
                return result

            except httpx.TimeoutException as e:
                last_error = f"Timeout connecting to cloud MCP: {str(e)}"
                if attempt < max_retries - 1:
                    wait_time = retry_delay * (2**attempt)
                    import time

                    time.sleep(wait_time)
                    continue
            except httpx.RequestError as e:
                last_error = f"Request error: {str(e)}"
                if attempt < max_retries - 1:
                    wait_time = retry_delay * (2**attempt)
                    import time

                    time.sleep(wait_time)
                    continue
            except httpx.HTTPStatusError as e:
                last_error = f"HTTP {e.response.status_code}: {str(e)}"
                # Don't retry on 4xx errors
                if 400 <= e.response.status_code < 500:
                    break
                if attempt < max_retries - 1:
                    wait_time = retry_delay * (2**attempt)
                    import time

                    time.sleep(wait_time)
                    continue
            except Exception as e:
                last_error = f"Unexpected error: {str(e)}"
                if attempt < max_retries - 1:
                    wait_time = retry_delay * (2**attempt)
                    import time

                    time.sleep(wait_time)
                    continue

        # All retries failed
        error_msg = f"Failed to call cloud tool after {max_retries} attempts: {last_error}"
        self.audit.log_tool_call(
            "cloud_call",
            caller,
            params.dict(),
            False,
            error=error_msg,
            start_time=start_time,
            user_agent=user_agent,
            trace_id=trace_id,
        )
        return {"success": False, "error": error_msg}

    def cloud_doc_get(
        self,
        params: CloudDocGetParams,
        caller: str = "unknown",
        user_agent: str | None = None,
        trace_id: str | None = None,
    ) -> dict:
        start_time = datetime.now()
        try:
            # Use cloud_call to get document
            cloud_params = CloudCallParams(
                tool_name="doc_get", args={"doc_id": params.doc_id, "fields": params.fields}
            )
            result = self.cloud_call(cloud_params, caller, user_agent, trace_id)

            self.audit.log_tool_call(
                "cloud_doc_get",
                caller,
                params.dict(),
                True,
                result,
                start_time=start_time,
                user_agent=user_agent,
                trace_id=trace_id,
            )
            return result
        except Exception as e:
            error_msg = f"Failed to execute cloud_doc_get: {str(e)}"
            self.audit.log_tool_call(
                "cloud_doc_get",
                caller,
                params.dict(),
                False,
                error=error_msg,
                start_time=start_time,
                user_agent=user_agent,
                trace_id=trace_id,
            )
            return {"success": False, "error": error_msg}

    def cloud_doc_patch(
        self,
        params: CloudDocPatchParams,
        caller: str = "unknown",
        user_agent: str | None = None,
        trace_id: str | None = None,
    ) -> dict:
        start_time = datetime.now()
        try:
            # Use cloud_call to patch document
            cloud_params = CloudCallParams(
                tool_name="doc_patch", args={"doc_id": params.doc_id, "data": params.data}
            )
            result = self.cloud_call(cloud_params, caller, user_agent, trace_id)

            self.audit.log_tool_call(
                "cloud_doc_patch",
                caller,
                params.dict(),
                True,
                result,
                start_time=start_time,
                user_agent=user_agent,
                trace_id=trace_id,
            )
            return result
        except Exception as e:
            error_msg = f"Failed to execute cloud_doc_patch: {str(e)}"
            self.audit.log_tool_call(
                "cloud_doc_patch",
                caller,
                params.dict(),
                False,
                error=error_msg,
                start_time=start_time,
                user_agent=user_agent,
                trace_id=trace_id,
            )
            return {"success": False, "error": error_msg}

    def exec(
        self,
        params: ExecParams,
        caller: str = "unknown",
        user_agent: str | None = None,
        trace_id: str | None = None,
    ) -> dict:
        start_time = datetime.now()
        try:
            # Prepare environment
            env = os.environ.copy()
            if params.env:
                env.update(params.env)

            # Determine working directory
            cwd = params.cwd or self.repo_root

            # Execute command
            process = subprocess.Popen(
                params.cmd,
                shell=True,
                cwd=cwd,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )

            stdout, stderr = process.communicate()
            exit_code = process.returncode

            result = {
                "success": exit_code == 0,
                "exit_code": exit_code,
                "stdout": stdout,
                "stderr": stderr,
            }

            self.audit.log_tool_call(
                "exec",
                caller,
                params.dict(),
                exit_code == 0,
                result,
                start_time=start_time,
                user_agent=user_agent,
                trace_id=trace_id,
            )
            return result
        except Exception as e:
            error_msg = f"Failed to execute command: {str(e)}"
            self.audit.log_tool_call(
                "exec",
                caller,
                params.dict(),
                False,
                error=error_msg,
                start_time=start_time,
                user_agent=user_agent,
                trace_id=trace_id,
            )
            return {"success": False, "error": error_msg}

    def _validate_date_format(self, date_str: str) -> bool:
        try:
            datetime.strptime(date_str, "%Y-%m-%d")
            return True
        except ValueError:
            return False

    def _initialize_revs(self):
        """Initialize revs for existing files"""
        # Initialize board file rev
        if self.board_file.exists():
            rev = self._calculate_file_rev(self.board_file)
            self._file_revs[str(self.board_file)] = rev

        # Initialize inbox files rev
        for file in self.inbox_dir.glob("*.md"):
            rev = self._calculate_file_rev(file)
            self._file_revs[str(file)] = rev

    def _calculate_file_rev(self, file_path: Path) -> str:
        """Calculate rev for a file based on its content"""
        if not file_path.exists():
            return "0"

        with open(file_path, "rb") as f:
            content = f.read()

        return hashlib.sha256(content).hexdigest()[:16]

    def _get_file_rev(self, file_path: Path) -> str:
        """Get current rev for a file"""
        file_str = str(file_path)
        if file_str not in self._file_revs:
            self._file_revs[file_str] = self._calculate_file_rev(file_path)
        return self._file_revs[file_str]

    def _update_file_rev(self, file_path: Path) -> str:
        """Update rev for a file and return the new rev"""
        file_str = str(file_path)
        new_rev = self._calculate_file_rev(file_path)
        self._file_revs[file_str] = new_rev
        return new_rev

    def _check_request_idempotency(self, request_id: str | None) -> dict | None:
        """Check if request_id has been processed before"""
        if not request_id:
            return None
        return self._completed_requests.get(request_id)

    def _record_completed_request(self, request_id: str | None, result: dict):
        """Record a completed request"""
        if request_id:
            self._completed_requests[request_id] = result

    def _check_lock(self, run_id: str | None) -> bool:
        """Check if there's a running run_id"""
        with self._lock:
            if self._running_run_id and self._running_run_id != run_id:
                return False
            return True

    def _acquire_lock(self, run_id: str | None):
        """Acquire the lock"""
        with self._lock:
            self._running_run_id = run_id

    def _release_lock(self):
        """Release the lock"""
        with self._lock:
            self._running_run_id = None

    def _check_base_rev(self, file_path: Path, base_rev: str | None) -> bool:
        """Check if base_rev matches current file rev"""
        if not base_rev:
            return True  # No base_rev provided, skip check

        current_rev = self._get_file_rev(file_path)
        return base_rev == current_rev

    def ata_task_create(
        self,
        params: ATATaskCreateParams,
        caller: str = "unknown",
        user_agent: str | None = None,
        trace_id: str | None = None,
    ) -> dict:
        """Create an ATA task with routing, mailbox, and A2A Hub integration."""
        start_time = datetime.now()
        try:
            routing_decision = self.ata_router.route(params.dict())
            owner_role = params.owner_role or routing_decision.owner_role or "implementer"
            area = params.area or "ata"
            from_agent = params.from_agent or "UI-TARS-desktop"
            if self.coordinator and self.coordinator.registry.get_agent(from_agent) is None:
                from_agent = "UI-TARS-desktop"

            create_payload = ATATaskCreate(
                task_code=params.task_code,
                owner_role=owner_role,
                area=area,
                priority=params.priority,
                goal=params.goal,
                capsule=params.capsule,
                how_to_repro=params.how_to_repro,
                expected=params.expected,
                actual=params.actual or "pending",
                evidence_requirements=params.evidence_requirements,
                scope_files=params.scope_files,
                metadata=params.metadata,
                deadline=params.deadline,
                owner=params.owner,
                task_type=params.task_type,
            )

            routing_payload = {
                "task_code": create_payload.task_code,
                "area": area,
                "owner_role": owner_role,
                "priority": create_payload.priority,
            }
            routing_info = {}
            try:
                routing_resp = httpx.post(
                    f"{self.a2a_hub_url}/api/task/routing",
                    json=routing_payload,
                    timeout=10,
                    trust_env=False,
                )
                if routing_resp.status_code == 200:
                    routing_info = routing_resp.json().get("result", {})
            except Exception:
                routing_info = {}

            a2a_payload = create_payload.to_a2a_payload()
            a2a_payload["owner_role"] = owner_role
            a2a_payload["area"] = area
            a2a_resp = httpx.post(
                f"{self.a2a_hub_url}/api/task/create",
                json=a2a_payload,
                timeout=20,
                headers={"X-A2A-Role": "submitter"},
                trust_env=False,
            )
            if a2a_resp.status_code != 200:
                return {"success": False, "error": f"A2A Hub error: {a2a_resp.text}"}
            a2a_data = a2a_resp.json()
            if not a2a_data.get("success"):
                return {"success": False, "error": a2a_data.get("error", "A2A Hub failed")}

            agent_id = a2a_data.get("agent_id") or routing_decision.agent_id
            date_str = datetime.utcnow().strftime("%Y%m%d")
            report_path = f"docs/REPORT/ata/REPORT__{create_payload.task_code}__{date_str}.md"
            evidence_dir = f"docs/REPORT/ata/artifacts/{create_payload.task_code}/"
            selftest_log_path = f"{evidence_dir}selftest.log"
            evidence_paths = [report_path, selftest_log_path, evidence_dir]

            trace_info = build_trace_info(dict(os.environ))

            context = create_payload.to_context(evidence_paths)
            mailbox_meta = {
                "a2a_task_id": a2a_data.get("task_id"),
                "a2a_status": a2a_data.get("status"),
                "agent_id": agent_id,
                "routing": routing_info,
                "router_rule": routing_decision.rule_id,
                "router_reasoning": routing_decision.reasoning,
                "trace": trace_payload(trace_info),
                "from_agent": from_agent,
            }
            mailbox_paths = self.ata_mailbox.init_task(context, mailbox_meta)

            self.ata_mailbox.append_event(
                ATAEvent(
                    task_code=create_payload.task_code,
                    status=ATAStatus.CREATED,
                    timestamp=datetime.utcnow().isoformat() + "Z",
                    actor=from_agent,
                    message="ATA task created",
                    details={"a2a_task_id": a2a_data.get("task_id")},
                )
            )
            self.ata_mailbox.append_event(
                ATAEvent(
                    task_code=create_payload.task_code,
                    status=ATAStatus.ROUTED,
                    timestamp=datetime.utcnow().isoformat() + "Z",
                    actor="ata_router",
                    message="ATA task routed",
                    details={
                        "owner_role": owner_role,
                        "rule_id": routing_decision.rule_id,
                        "routing_info": routing_info,
                    },
                )
            )
            if agent_id:
                self.ata_mailbox.append_event(
                    ATAEvent(
                        task_code=create_payload.task_code,
                        status=ATAStatus.ASSIGNED,
                        timestamp=datetime.utcnow().isoformat() + "Z",
                        actor="a2a_hub",
                        message="ATA task assigned",
                        details={"agent_id": agent_id},
                    )
                )

            send_request_result = None
            if agent_id:
                to_display = agent_id
                if self.coordinator:
                    to_obj = self.coordinator.registry.get_agent(agent_id)
                    if to_obj and getattr(to_obj, "numeric_code", None) is not None:
                        to_display = f"{to_obj.agent_id}#{int(to_obj.numeric_code):02d}"
                message_text = (
                    f"@{to_display} 【ATA任务】{create_payload.task_code}\n"
                    f"目标: {create_payload.goal}\n"
                    f"说明: {create_payload.capsule}\n"
                    f"Mailbox: {mailbox_paths.mailbox_dir.relative_to(self.repo_root)}\n"
                    f"EvidenceDir: {evidence_dir}\n"
                )
                payload = {
                    "message": message_text,
                    "text": message_text,
                    "task_code": create_payload.task_code,
                    "mailbox_dir": str(mailbox_paths.mailbox_dir.relative_to(self.repo_root)),
                    "report_path": report_path,
                    "selftest_log_path": selftest_log_path,
                    "evidence_dir": evidence_dir,
                    "trace": trace_payload(trace_info),
                }
                send_request_result = self.ata_send_request(
                    ATASendRequestParams(
                        taskcode=create_payload.task_code,
                        from_agent=from_agent,
                        to_agent=agent_id,
                        kind="request",
                        payload=payload,
                        priority="normal",
                        requires_response=True,
                        report_path=report_path,
                        selftest_log_path=selftest_log_path,
                        evidence_dir=evidence_dir,
                    ),
                    caller=caller,
                    user_agent=user_agent,
                    trace_id=trace_id,
                )
                if send_request_result.get("success"):
                    self.ata_mailbox.write_message(
                        create_payload.task_code,
                        send_request_result.get("request_id", "outbox_request"),
                        payload,
                    )

            result = {
                "success": True,
                "task_code": create_payload.task_code,
                "a2a_task_id": a2a_data.get("task_id"),
                "a2a_status": a2a_data.get("status"),
                "ata_status": (ATAStatus.ASSIGNED if agent_id else ATAStatus.ROUTED).value,
                "agent_id": agent_id,
                "mailbox_dir": str(mailbox_paths.mailbox_dir.relative_to(self.repo_root)),
                "report_path": report_path,
                "selftest_log_path": selftest_log_path,
                "evidence_dir": evidence_dir,
                "routing": routing_info,
                "trace": trace_payload(trace_info),
                "send_request": send_request_result,
            }

            self.audit.log_tool_call(
                "ata_task_create",
                caller,
                params.dict(),
                True,
                result,
                start_time=start_time,
                user_agent=user_agent,
                trace_id=trace_id,
            )
            return result
        except Exception as e:
            error_msg = f"Failed to create ATA task: {str(e)}"
            self.audit.log_tool_call(
                "ata_task_create",
                caller,
                params.dict(),
                False,
                error=error_msg,
                start_time=start_time,
                user_agent=user_agent,
                trace_id=trace_id,
            )
            return {"success": False, "error": error_msg}

    def ata_task_status(
        self,
        params: ATATaskStatusParams,
        caller: str = "unknown",
        user_agent: str | None = None,
        trace_id: str | None = None,
    ) -> dict:
        """Query ATA task status from A2A Hub."""
        start_time = datetime.now()
        try:
            if not params.task_code and not params.task_id:
                return {"success": False, "error": "task_code or task_id required"}
            resp = httpx.get(
                f"{self.a2a_hub_url}/api/task/status",
                params={"task_code": params.task_code, "task_id": params.task_id},
                timeout=10,
                headers={"X-A2A-Role": "auditor"},
                trust_env=False,
            )
            if resp.status_code != 200:
                return {"success": False, "error": f"A2A Hub error: {resp.text}"}
            data = resp.json()
            if not data.get("success"):
                return {"success": False, "error": data.get("error", "A2A Hub failed")}

            task = data.get("task", {})
            ata_status = map_a2a_status(task.get("status"))
            result = {
                "success": True,
                "task": task,
                "ata_status": ata_status.value,
                "mailbox_dir": (
                    str(self.ata_mailbox.get_paths(task.get("task_code", "")).mailbox_dir.relative_to(self.repo_root))
                    if task.get("task_code")
                    else None
                ),
            }
            self.audit.log_tool_call(
                "ata_task_status",
                caller,
                params.dict(),
                True,
                result,
                start_time=start_time,
                user_agent=user_agent,
                trace_id=trace_id,
            )
            return result
        except Exception as e:
            error_msg = f"Failed to get ATA task status: {str(e)}"
            self.audit.log_tool_call(
                "ata_task_status",
                caller,
                params.dict(),
                False,
                error=error_msg,
                start_time=start_time,
                user_agent=user_agent,
                trace_id=trace_id,
            )
            return {"success": False, "error": error_msg}

    def ata_task_result(
        self,
        params: ATATaskResultParams,
        caller: str = "unknown",
        user_agent: str | None = None,
        trace_id: str | None = None,
    ) -> dict:
        """Submit ATA task result to A2A Hub and record mailbox event."""
        start_time = datetime.now()
        try:
            payload = {"task_code": params.task_code}
            if params.status:
                payload["status"] = params.status
            if params.result:
                payload["result"] = params.result

            resp = httpx.post(
                f"{self.a2a_hub_url}/api/task/result",
                json=payload,
                timeout=20,
                headers={"X-A2A-Role": "worker"},
                trust_env=False,
            )
            if resp.status_code != 200:
                return {"success": False, "error": f"A2A Hub error: {resp.text}"}
            data = resp.json()
            if not data.get("success"):
                return {"success": False, "error": data.get("error", "A2A Hub failed")}

            self.ata_mailbox.append_event(
                ATAEvent(
                    task_code=params.task_code,
                    status=map_a2a_status(data.get("status")),
                    timestamp=datetime.utcnow().isoformat() + "Z",
                    actor=caller,
                    message="ATA task result submitted",
                    details={
                        "report_path": params.report_path,
                        "selftest_log_path": params.selftest_log_path,
                        "evidence_dir": params.evidence_dir,
                    },
                )
            )

            result = {"success": True, "status": data.get("status"), "message": data.get("message")}
            self.audit.log_tool_call(
                "ata_task_result",
                caller,
                params.dict(),
                True,
                result,
                start_time=start_time,
                user_agent=user_agent,
                trace_id=trace_id,
            )
            return result
        except Exception as e:
            error_msg = f"Failed to submit ATA task result: {str(e)}"
            self.audit.log_tool_call(
                "ata_task_result",
                caller,
                params.dict(),
                False,
                error=error_msg,
                start_time=start_time,
                user_agent=user_agent,
                trace_id=trace_id,
            )
            return {"success": False, "error": error_msg}

    def ata_ci_verify(
        self,
        params: ATACIVerifyParams,
        caller: str = "unknown",
        user_agent: str | None = None,
        trace_id: str | None = None,
    ) -> dict:
        """Run CI verification for ATA evidence triplet."""
        start_time = datetime.now()
        try:
            date_str = datetime.utcnow().strftime("%Y%m%d")
            report_path = params.report_path or f"docs/REPORT/ata/REPORT__{params.task_code}__{date_str}.md"
            evidence_dir = params.evidence_dir or f"docs/REPORT/ata/artifacts/{params.task_code}/"
            selftest_log_path = params.selftest_log_path or f"{evidence_dir}selftest.log"

            triplet = ATAEvidenceTriplet(
                report_path=self.repo_root / report_path,
                selftest_log_path=self.repo_root / selftest_log_path,
                evidence_dir=self.repo_root / evidence_dir,
            )
            triplet_check = self.ata_ci.verify_triplet(triplet)
            if not triplet_check.get("success"):
                return {"success": False, "error": "Missing evidence", "missing": triplet_check["missing"]}

            guard_result = self.ata_ci.run_guard(
                triplet.report_path,
                triplet.selftest_log_path,
                triplet.evidence_dir,
                params.task_code,
                "ata",
            )
            verdict_result = self.ata_ci.run_verdict()
            strict_verdict = os.getenv("ATA_CI_STRICT_VERDICT", "false").lower() == "true"
            guard_success = bool(guard_result.get("success"))
            verdict_success = bool(verdict_result.get("success"))

            verdict_payload = {
                "task_code": params.task_code,
                "guard": guard_result,
                "verdict": verdict_result.get("verdict"),
                "verdict_path": verdict_result.get("verdict_path"),
            }
            self.ata_mailbox.write_verdict(params.task_code, verdict_payload)
            self.ata_mailbox.append_event(
                ATAEvent(
                    task_code=params.task_code,
                    status=ATAStatus.CI,
                    timestamp=datetime.utcnow().isoformat() + "Z",
                    actor=caller,
                    message="ATA CI verification completed",
                    details={
                        "guard_success": guard_success,
                        "verdict_success": verdict_success,
                        "verdict_path": verdict_result.get("verdict_path"),
                        "strict_verdict": strict_verdict,
                    },
                )
            )

            result = {
                "success": guard_success and (verdict_success or not strict_verdict),
                "guard": guard_result,
                "verdict": verdict_result,
                "verdict_path": verdict_result.get("verdict_path"),
                "mailbox_dir": str(
                    self.ata_mailbox.get_paths(params.task_code).mailbox_dir.relative_to(self.repo_root)
                ),
                "strict_verdict": strict_verdict,
            }
            if guard_success and not verdict_success and not strict_verdict:
                result["verdict_warning"] = (
                    "verdict_failed_but_guard_passed"
                )
            self.audit.log_tool_call(
                "ata_ci_verify",
                caller,
                params.dict(),
                True,
                result,
                start_time=start_time,
                user_agent=user_agent,
                trace_id=trace_id,
            )
            return result
        except Exception as e:
            error_msg = f"Failed to run ATA CI verification: {str(e)}"
            self.audit.log_tool_call(
                "ata_ci_verify",
                caller,
                params.dict(),
                False,
                error=error_msg,
                start_time=start_time,
                user_agent=user_agent,
                trace_id=trace_id,
            )
            return {"success": False, "error": error_msg}

    def ata_send(
        self,
        params: ATASendParams,
        caller: str = "unknown",
        user_agent: str | None = None,
        trace_id: str | None = None,
        auth_ctx: dict[str, Any] | None = None,
    ) -> dict:
        """Send an ATA message with automatic routing"""
        start_time = datetime.now()
        try:
            # ---- Hard gate: only ATA admin can send (proxy-send mode) ----
            admin_err = self._require_admin(auth_ctx, "ata_send")
            if admin_err:
                self.audit.log_tool_call(
                    "ata_send",
                    caller,
                    params.dict(),
                    False,
                    error=admin_err["error"],
                    start_time=start_time,
                    user_agent=user_agent,
                    trace_id=trace_id,
                )
                return admin_err

            # ---- Hard gate #0: from_agent/to_agent must be registered (fail-closed) ----
            if not self.coordinator:
                error_msg = "ATA send validation requires AgentCoordinator (fail-closed)"
                self.audit.log_tool_call(
                    "ata_send",
                    caller,
                    params.dict(),
                    False,
                    error=error_msg,
                    start_time=start_time,
                    user_agent=user_agent,
                    trace_id=trace_id,
                )
                return {"success": False, "error": error_msg}

            if not params.from_agent or not isinstance(params.from_agent, str):
                return {"success": False, "error": "from_agent is required"}
            if not params.to_agent or not isinstance(params.to_agent, str):
                return {"success": False, "error": "to_agent is required"}

            from_obj0 = self.coordinator.registry.get_agent(params.from_agent)
            if from_obj0 is None:
                return {"success": False, "error": f"Sender not registered: {params.from_agent}"}
            to_obj0 = self.coordinator.registry.get_agent(params.to_agent)
            if to_obj0 is None:
                return {"success": False, "error": f"Recipient not registered: {params.to_agent}"}

            # ---- Hard logic: read-only agents can receive but cannot send ----
            try:
                if self.coordinator and params.from_agent:
                    from_obj = from_obj0
                    if from_obj is not None and hasattr(from_obj, "send_enabled"):
                        if not bool(from_obj.send_enabled):
                            error_msg = f"Send disabled for agent: {params.from_agent}"
                            self.audit.log_tool_call(
                                "ata_send",
                                caller,
                                params.dict(),
                                False,
                                error=error_msg,
                                start_time=start_time,
                                user_agent=user_agent,
                                trace_id=trace_id,
                            )
                            return {"success": False, "error": error_msg}
            except Exception:
                # Fail-closed: if cannot validate send permission, reject
                error_msg = "ATA send permission validation failed (fail-closed)"
                self.audit.log_tool_call(
                    "ata_send",
                    caller,
                    params.dict(),
                    False,
                    error=error_msg,
                    start_time=start_time,
                    user_agent=user_agent,
                    trace_id=trace_id,
                )
                return {"success": False, "error": error_msg}

            # Generate message ID if not provided
            msg_id = f"ATA-MSG-{datetime.now().strftime('%Y%m%d%H%M%S')}-{hashlib.md5(str(params.taskcode).encode()).hexdigest()[:8]}"

            # Auto-routing: if to_agent is not specified, use routing engine
            to_agent = params.to_agent
            routing_decision = None
            routing_rule = None

            if not to_agent:
                # Try to load routing engine
                try:
                    routing_engine_path = (
                        Path(self.repo_root) / "tools" / "ata" / "routing_engine.py"
                    )
                    if routing_engine_path.exists():
                        import sys

                        sys.path.insert(0, str(routing_engine_path.parent))
                        from routing_engine import ATARoutingEngine

                        routing_engine = ATARoutingEngine()
                        message_for_routing = {
                            "from_agent": params.from_agent,
                            "to_agent": params.to_agent,
                            "taskcode": params.taskcode,
                            "kind": params.kind,
                            "priority": params.priority,
                            "domain": params.payload.get("domain")
                            if isinstance(params.payload, dict)
                            else None,
                        }
                        routing_result = routing_engine.route_message(message_for_routing)
                        to_agent = routing_result.get("to_agent", params.to_agent)
                        routing_decision = routing_result.get("routing_decision")
                        routing_rule = routing_result.get("routing_rule")
                except Exception:
                    # If routing fails, use original to_agent
                    pass

            # ---- Fail-closed comm rule enforcement: message must start with "@对方#NN" ----
            # Resolve display name using coordinator registry when available.
            try:
                to_display = None
                if self.coordinator and to_agent:
                    to_obj = self.coordinator.registry.get_agent(to_agent)
                    if to_obj and getattr(to_obj, "numeric_code", None) is not None:
                        to_display = f"{to_obj.agent_id}#{int(to_obj.numeric_code):02d}"
                    elif to_obj:
                        to_display = to_obj.agent_id

                payload = params.payload if isinstance(params.payload, dict) else {}
                msg_text = None
                if isinstance(payload, dict):
                    if isinstance(payload.get("message"), str):
                        msg_text = payload.get("message")
                    elif isinstance(payload.get("text"), str):
                        msg_text = payload.get("text")

                # Enforce only when we can determine recipient + message text exists
                if to_display and isinstance(msg_text, str):
                    required_prefix = f"@{to_display}"
                    if not msg_text.lstrip().startswith(required_prefix):
                        error_msg = (
                            f"ATA comm rule violation: message must start with '{required_prefix}'"
                        )
                        self.audit.log_tool_call(
                            "ata_send",
                            caller,
                            params.dict(),
                            False,
                            error=error_msg,
                            start_time=start_time,
                            user_agent=user_agent,
                            trace_id=trace_id,
                        )
                        return {"success": False, "error": error_msg}
            except Exception:
                # Fail-closed: if we cannot validate, reject to avoid silent non-compliance
                error_msg = "ATA comm rule validation failed (fail-closed)"
                self.audit.log_tool_call(
                    "ata_send",
                    caller,
                    params.dict(),
                    False,
                    error=error_msg,
                    start_time=start_time,
                    user_agent=user_agent,
                    trace_id=trace_id,
                )
                return {"success": False, "error": error_msg}

            # Create message object with enhanced fields
            message = {
                "msg_id": msg_id,
                "taskcode": params.taskcode,
                "from_agent": params.from_agent,
                "to_agent": to_agent,
                "created_at": datetime.now().isoformat() + "Z",
                "kind": params.kind,
                "payload": params.payload,
                "prev_sha256": params.prev_sha256,
                "priority": params.priority,
                "requires_response": params.requires_response,
                "status": "pending",  # pending, delivered, read, acked
                "context_hint": params.context_hint,
            }

            # Add routing information if available
            if routing_decision:
                message["routing_decision"] = routing_decision
            if routing_rule:
                message["routing_rule"] = routing_rule

            # Calculate SHA256 (excluding sha256 field itself)
            message_without_sha256 = message.copy()
            message_without_sha256.pop("sha256", None)
            sha256_content = json.dumps(message_without_sha256, sort_keys=True, ensure_ascii=False)
            sha256_hash = hashlib.sha256(sha256_content.encode("utf-8")).hexdigest()
            message["sha256"] = sha256_hash

            # Create task directory if it doesn't exist
            task_dir = self.ata_messages_dir / params.taskcode
            task_dir.mkdir(parents=True, exist_ok=True)

            # Generate filename based on timestamp and message ID
            timestamp = datetime.now().strftime("%Y%m%dT%H%M%S")
            filename = f"msg_{timestamp}_{msg_id}.json"
            message_file = task_dir / filename

            # Check access permission
            allowed, message_error = self.security.check_access(str(message_file), "write")
            if not allowed:
                self.audit.log_tool_call(
                    "ata_send",
                    caller,
                    params.dict(),
                    False,
                    error=message_error,
                    start_time=start_time,
                    user_agent=user_agent,
                    trace_id=trace_id,
                )
                return {"success": False, "error": message_error}

            # Update conversation context if enhanced ATA is available
            if self.ata_enhanced:
                context_manager = self.ata_enhanced.get_conversation_context(params.taskcode)
                context_manager.update(params.from_agent, params.to_agent, params.payload)

                # Enhance message with context
                enhanced_message = self.ata_enhanced.enhance_message(message)
                message.update(enhanced_message)

            # Write message to file
            with open(message_file, "w", encoding="utf-8") as f:
                json.dump(message, f, ensure_ascii=False, indent=2)

            # Add to message queue for delivery tracking
            if self.ata_enhanced:
                self.ata_enhanced.message_queue.enqueue(msg_id, message)

            result = {
                "success": True,
                "msg_id": msg_id,
                "file_path": str(message_file.relative_to(self.repo_root)),
                "sha256": sha256_hash,
                "priority": message.get("priority", "normal"),
                "status": message.get("status", "pending"),
            }

            self.audit.log_tool_call(
                "ata_send",
                caller,
                params.dict(),
                True,
                result,
                start_time=start_time,
                user_agent=user_agent,
                trace_id=trace_id,
            )
            return result

        except Exception as e:
            error_msg = f"Failed to send ATA message: {str(e)}"
            self.audit.log_tool_call(
                "ata_send",
                caller,
                params.dict(),
                False,
                error=error_msg,
                start_time=start_time,
                user_agent=user_agent,
                trace_id=trace_id,
            )
            return {"success": False, "error": error_msg}

    def ata_receive(
        self,
        params: ATAReceiveParams,
        caller: str = "unknown",
        user_agent: str | None = None,
        trace_id: str | None = None,
        auth_ctx: dict[str, Any] | None = None,
    ) -> dict:
        """Receive ATA messages with optional filtering"""
        start_time = datetime.now()
        try:
            messages = []

            # Scan all message files in the ATA messages directory
            if not self.ata_messages_dir.exists():
                result = {"success": True, "messages": [], "count": 0}
                self.audit.log_tool_call(
                    "ata_receive",
                    caller,
                    params.dict(),
                    True,
                    result,
                    start_time=start_time,
                    user_agent=user_agent,
                    trace_id=trace_id,
                )
                return result

            # Find all JSON message files
            for task_dir in self.ata_messages_dir.iterdir():
                if not task_dir.is_dir():
                    continue

                # Filter by taskcode if specified
                if params.taskcode and task_dir.name != params.taskcode:
                    continue

                for msg_file in task_dir.glob("*.json"):
                    try:
                        # Read message file
                        with open(msg_file, encoding="utf-8") as f:
                            message = json.load(f)

                        # Apply filters
                        if params.from_agent and message.get("from_agent") != params.from_agent:
                            continue
                        if params.to_agent and message.get("to_agent") != params.to_agent:
                            continue
                        if params.kind and message.get("kind") != params.kind:
                            continue
                        if params.priority and message.get("priority") != params.priority:
                            continue
                        if params.status and message.get("status") != params.status:
                            continue

                        # Filter unread messages if requested
                        if params.unread_only:
                            msg_status = message.get("status", "pending")
                            if msg_status in ["read", "acked"]:
                                continue

                        # Add relative file path
                        message["file_path"] = str(msg_file.relative_to(self.repo_root))

                        # Add context if requested
                        if params.include_context and self.ata_enhanced:
                            taskcode = message.get("taskcode", "")
                            context_manager = self.ata_enhanced.get_conversation_context(taskcode)
                            context = context_manager.load()
                            message["conversation_context"] = context

                        messages.append(message)

                    except (json.JSONDecodeError, KeyError):
                        # Skip invalid message files
                        continue

            # Sort by priority first (urgent > high > normal > low), then by created_at (newest first)
            priority_order = {"urgent": 4, "high": 3, "normal": 2, "low": 1}
            messages.sort(
                key=lambda x: (
                    priority_order.get(x.get("priority", "normal"), 2),
                    x.get("created_at", ""),
                ),
                reverse=True,
            )

            # Apply limit
            limited_messages = messages[: params.limit]

            # Add summary statistics
            stats = {"total": len(messages), "by_priority": {}, "by_status": {}, "unread_count": 0}
            for msg in messages:
                priority = msg.get("priority", "normal")
                stats["by_priority"][priority] = stats["by_priority"].get(priority, 0) + 1
                status = msg.get("status", "pending")
                stats["by_status"][status] = stats["by_status"].get(status, 0) + 1
                if status in ["pending", "delivered"]:
                    stats["unread_count"] += 1

            result = {
                "success": True,
                "messages": limited_messages,
                "count": len(limited_messages),
                "total_found": len(messages),
                "statistics": stats,
            }

            self.audit.log_tool_call(
                "ata_receive",
                caller,
                params.dict(),
                True,
                result,
                start_time=start_time,
                user_agent=user_agent,
                trace_id=trace_id,
            )
            return result

        except Exception as e:
            error_msg = f"Failed to receive ATA messages: {str(e)}"
            self.audit.log_tool_call(
                "ata_receive",
                caller,
                params.dict(),
                False,
                error=error_msg,
                start_time=start_time,
                user_agent=user_agent,
                trace_id=trace_id,
            )
            return {"success": False, "error": error_msg}

    def ata_message_mark(
        self,
        params: ATAMessageMarkParams,
        caller: str = "unknown",
        user_agent: str | None = None,
        trace_id: str | None = None,
        auth_ctx: dict[str, Any] | None = None,
    ) -> dict:
        """Mark ATA message(s) as read/acked/archived to avoid repeated polling reprocessing."""
        start_time = datetime.now()
        try:
            status = (params.status or "").strip().lower()
            if status not in ["read", "acked", "archived"]:
                return {"success": False, "error": "status must be one of: read, acked, archived"}

            msg_ids = [str(x).strip() for x in (params.msg_ids or []) if str(x).strip()]
            if not msg_ids:
                return {"success": False, "error": "msg_ids is required"}

            updated = 0
            missing = 0

            # Prefer enhanced ATA helper if available (also de-queues)
            if self.ata_enhanced and status == "read":
                for mid in msg_ids:
                    ok = self.ata_enhanced.mark_as_read(mid)
                    if ok:
                        updated += 1
                    else:
                        missing += 1
            else:
                # Generic fallback: update message file status in-place (best-effort).
                for mid in msg_ids:
                    found = False
                    for task_dir in self.ata_messages_dir.iterdir():
                        if not task_dir.is_dir():
                            continue
                        candidates = list(task_dir.glob(f"msg_*_{mid}.json"))
                        if not candidates:
                            continue
                        for msg_file in candidates:
                            try:
                                with open(msg_file, encoding="utf-8") as f:
                                    msg = json.load(f)
                                msg["status"] = status
                                msg[f"{status}_at"] = datetime.now().isoformat() + "Z"
                                with open(msg_file, "w", encoding="utf-8") as f:
                                    json.dump(msg, f, ensure_ascii=False, indent=2)
                                updated += 1
                                found = True
                                break
                            except Exception:
                                continue
                        if found:
                            break
                    if not found:
                        missing += 1

            result = {"success": True, "updated": updated, "missing": missing, "status": status}
            self.audit.log_tool_call(
                "ata_message_mark",
                caller,
                params.dict(),
                True,
                result,
                start_time=start_time,
                user_agent=user_agent,
                trace_id=trace_id,
            )
            return result
        except Exception as e:
            error_msg = f"Failed to mark ATA messages: {str(e)}"
            self.audit.log_tool_call(
                "ata_message_mark",
                caller,
                params.dict(),
                False,
                error=error_msg,
                start_time=start_time,
                user_agent=user_agent,
                trace_id=trace_id,
            )
            return {"success": False, "error": error_msg}

    def file_read(
        self,
        params: FileReadParams,
        caller: str = "unknown",
        user_agent: str | None = None,
        trace_id: str | None = None,
    ) -> dict:
        """Read file content for sending in ATA messages"""
        start_time = datetime.now()
        try:
            # Resolve file path
            file_path = self.repo_root / params.file_path

            # Check access permission
            allowed, message_error = self.security.check_access(str(file_path), "read")
            if not allowed:
                self.audit.log_tool_call(
                    "file_read",
                    caller,
                    params.dict(),
                    False,
                    error=message_error,
                    start_time=start_time,
                    user_agent=user_agent,
                    trace_id=trace_id,
                )
                return {"success": False, "error": message_error}

            # Check if file exists
            if not file_path.exists():
                error_msg = f"File not found: {params.file_path}"
                self.audit.log_tool_call(
                    "file_read",
                    caller,
                    params.dict(),
                    False,
                    error=error_msg,
                    start_time=start_time,
                    user_agent=user_agent,
                    trace_id=trace_id,
                )
                return {"success": False, "error": error_msg}

            # Check file size
            file_size = file_path.stat().st_size
            if file_size > params.max_size:
                error_msg = f"File too large: {file_size} bytes (max: {params.max_size})"
                self.audit.log_tool_call(
                    "file_read",
                    caller,
                    params.dict(),
                    False,
                    error=error_msg,
                    start_time=start_time,
                    user_agent=user_agent,
                    trace_id=trace_id,
                )
                return {"success": False, "error": error_msg}

            # Read file content
            if params.encoding in ["binary", "base64"]:
                with open(file_path, "rb") as f:
                    content_bytes = f.read()
                content = base64.b64encode(content_bytes).decode("utf-8")
                encoding_used = "base64"
            else:
                with open(file_path, encoding=params.encoding or "utf-8") as f:
                    content = f.read()
                encoding_used = params.encoding or "utf-8"

            result = {
                "success": True,
                "file_path": str(file_path.relative_to(self.repo_root)),
                "content": content,
                "encoding": encoding_used,
                "size": file_size,
            }

            self.audit.log_tool_call(
                "file_read",
                caller,
                params.dict(),
                True,
                result,
                start_time=start_time,
                user_agent=user_agent,
                trace_id=trace_id,
            )
            return result

        except Exception as e:
            error_msg = f"Failed to read file: {str(e)}"
            self.audit.log_tool_call(
                "file_read",
                caller,
                params.dict(),
                False,
                error=error_msg,
                start_time=start_time,
                user_agent=user_agent,
                trace_id=trace_id,
            )
            return {"success": False, "error": error_msg}

    def ata_send_with_file(
        self,
        params: ATASendWithFileParams,
        caller: str = "unknown",
        user_agent: str | None = None,
        trace_id: str | None = None,
    ) -> dict:
        """Send ATA message with file content embedded"""
        start_time = datetime.now()
        try:
            # Read file content first
            file_read_params = FileReadParams(
                file_path=params.file_path,
                encoding=params.encoding,
                max_size=10485760,  # 10MB default
            )
            file_result = self.file_read(file_read_params, caller, user_agent, trace_id)

            if not file_result.get("success"):
                return file_result

            # Build payload with file content
            payload = {
                "message": params.message,
                "file": {
                    "path": params.file_path,
                    "content": file_result["content"],
                    "encoding": file_result["encoding"],
                    "size": file_result["size"],
                },
            }

            # Send ATA message with file content in payload
            ata_send_params = ATASendParams(
                taskcode=params.taskcode,
                from_agent=params.from_agent,
                to_agent=params.to_agent,
                kind=params.kind,
                payload=payload,
                prev_sha256=params.prev_sha256,
                priority=params.priority,
                requires_response=params.requires_response,
                context_hint=params.context_hint,
            )

            result = self.ata_send(ata_send_params, caller, user_agent, trace_id)

            # Add file info to result
            if result.get("success"):
                result["file_path"] = params.file_path
                result["file_size"] = file_result["size"]
                result["file_encoding"] = file_result["encoding"]

            self.audit.log_tool_call(
                "ata_send_with_file",
                caller,
                params.dict(),
                result.get("success", False),
                result,
                start_time=start_time,
                user_agent=user_agent,
                trace_id=trace_id,
            )
            return result

        except Exception as e:
            error_msg = f"Failed to send ATA message with file: {str(e)}"
            self.audit.log_tool_call(
                "ata_send_with_file",
                caller,
                params.dict(),
                False,
                error=error_msg,
                start_time=start_time,
                user_agent=user_agent,
                trace_id=trace_id,
            )
            return {"success": False, "error": error_msg}

    def dialog_register(
        self,
        params: DialogRegisterParams,
        caller: str = "unknown",
        user_agent: str | None = None,
        trace_id: str | None = None,
    ) -> dict:
        """Register a dialog with unique identity"""
        start_time = datetime.now()
        try:
            if not self.dialog_tools:
                return {"success": False, "error": "DialogTools not available"}

            registry = self.dialog_tools.load_registry()
            dialogs = registry.get("dialogs", {})
            next_id = registry.get("next_id", {})

            # Generate dialog ID if not provided
            if not params.dialog_id:
                agent_type = params.agent_type or "Cursor"
                dialog_num = next_id.get(agent_type, 1)
                dialog_id = f"{agent_type}-Dialog-{dialog_num}"
                next_id[agent_type] = dialog_num + 1
            else:
                dialog_id = params.dialog_id

            # Register dialog
            dialogs[dialog_id] = {
                "dialog_id": dialog_id,
                "agent_type": params.agent_type or "Cursor",
                "dialog_name": params.dialog_name,
                "registered_at": datetime.now().isoformat(),
                "caller": caller,
            }

            registry["dialogs"] = dialogs
            registry["next_id"] = next_id

            # Save registry
            self.dialog_tools.save_registry(registry)

            # Auto-register to Agent Coordinator if available
            agent_registered = False
            if self.coordinator:
                try:
                    # Try to determine role from subagents.json
                    role = "implementer"  # default role
                    capabilities = []

                    # Heuristic: allow dialog_name to hint role (Architect/Implementer/Reviewer/Tester)
                    try:
                        dn = (params.dialog_name or "").lower()
                        if any(k in dn for k in ["architect", "架构", "系统设计"]):
                            role = "architect"
                        elif any(k in dn for k in ["reviewer", "审查", "评审"]):
                            role = "reviewer"
                        elif any(k in dn for k in ["tester", "测试"]):
                            role = "tester"
                        elif any(k in dn for k in ["implementer", "实现", "开发"]):
                            role = "implementer"
                    except Exception:
                        pass

                    # Load subagents.json to get role information
                    subagents_file = self.repo_root / ".cursor" / "subagents.json"
                    if subagents_file.exists():
                        try:
                            with open(subagents_file, encoding="utf-8") as f:
                                subagents_config = json.load(f)

                            # Try to find matching role (simplified: use first available role as default)
                            roles = subagents_config.get("roles", {})
                            default_role = subagents_config.get("default_role", "implementer")
                            # If heuristic role not present in config, fall back to default_role
                            if role not in roles:
                                role = default_role

                            # Get capabilities from role config
                            if role in roles:
                                role_config = roles[role]
                                capabilities = role_config.get("capabilities", [])
                        except Exception:
                            pass

                    # Register agent to coordinator
                    coordinator_result = self.coordinator.register_agent(
                        agent_id=dialog_id,
                        agent_type=params.agent_type or "Cursor",
                        role=role,
                        capabilities=capabilities,
                        max_concurrent_tasks=5,
                    )
                    agent_registered = coordinator_result.get("success", False)
                except Exception:
                    # If coordinator registration fails, continue without it
                    agent_registered = False

            result = {
                "success": True,
                "dialog_id": dialog_id,
                "registered_at": dialogs[dialog_id]["registered_at"],
                "agent_registered": agent_registered,
            }

            self.audit.log_tool_call(
                "dialog_register",
                caller,
                params.dict(),
                True,
                result,
                start_time=start_time,
                user_agent=user_agent,
                trace_id=trace_id,
            )
            return result

        except Exception as e:
            error_msg = f"Failed to register dialog: {str(e)}"
            self.audit.log_tool_call(
                "dialog_register",
                caller,
                params.dict(),
                False,
                error=error_msg,
                start_time=start_time,
                user_agent=user_agent,
                trace_id=trace_id,
            )
            return {"success": False, "error": error_msg}

    def dialog_list(
        self,
        params: DialogListParams,
        caller: str = "unknown",
        user_agent: str | None = None,
        trace_id: str | None = None,
    ) -> dict:
        """List all registered dialogs"""
        start_time = datetime.now()
        try:
            if not self.dialog_tools:
                return {"success": False, "error": "DialogTools not available"}

            registry = self.dialog_tools.load_registry()
            dialogs = registry.get("dialogs", {})

            # Filter by agent_type if specified
            filtered_dialogs = []
            for dialog_id, dialog_info in dialogs.items():
                if params.agent_type and dialog_info.get("agent_type") != params.agent_type:
                    continue
                filtered_dialogs.append(dialog_info)

            result = {"success": True, "dialogs": filtered_dialogs, "count": len(filtered_dialogs)}

            self.audit.log_tool_call(
                "dialog_list",
                caller,
                params.dict(),
                True,
                result,
                start_time=start_time,
                user_agent=user_agent,
                trace_id=trace_id,
            )
            return result

        except Exception as e:
            error_msg = f"Failed to list dialogs: {str(e)}"
            self.audit.log_tool_call(
                "dialog_list",
                caller,
                params.dict(),
                False,
                error=error_msg,
                start_time=start_time,
                user_agent=user_agent,
                trace_id=trace_id,
            )
            return {"success": False, "error": error_msg}

    def conversation_stats(
        self,
        params: ConversationStatsParams,
        caller: str = "unknown",
        user_agent: str | None = None,
        trace_id: str | None = None,
    ) -> dict:
        """Get conversation statistics"""
        start_time = datetime.now()
        try:
            if not self.dialog_tools:
                return {"success": False, "error": "DialogTools not available"}

            result = self.dialog_tools.get_conversation_stats(params)

            self.audit.log_tool_call(
                "conversation_stats",
                caller,
                params.dict(),
                True,
                result,
                start_time=start_time,
                user_agent=user_agent,
                trace_id=trace_id,
            )
            return result

        except Exception as e:
            error_msg = f"Failed to get conversation stats: {str(e)}"
            self.audit.log_tool_call(
                "conversation_stats",
                caller,
                params.dict(),
                False,
                error=error_msg,
                start_time=start_time,
                user_agent=user_agent,
                trace_id=trace_id,
            )
            return {"success": False, "error": error_msg}

    def conversation_search(
        self,
        params: ConversationSearchParams,
        caller: str = "unknown",
        user_agent: str | None = None,
        trace_id: str | None = None,
    ) -> dict:
        """Search conversations by content"""
        start_time = datetime.now()
        try:
            if not self.dialog_tools:
                return {"success": False, "error": "DialogTools not available"}

            result = self.dialog_tools.search_conversations(params)

            self.audit.log_tool_call(
                "conversation_search",
                caller,
                params.dict(),
                True,
                result,
                start_time=start_time,
                user_agent=user_agent,
                trace_id=trace_id,
            )
            return result

        except Exception as e:
            error_msg = f"Failed to search conversations: {str(e)}"
            self.audit.log_tool_call(
                "conversation_search",
                caller,
                params.dict(),
                False,
                error=error_msg,
                start_time=start_time,
                user_agent=user_agent,
                trace_id=trace_id,
            )
            return {"success": False, "error": error_msg}

    def conversation_history(
        self,
        params: ConversationHistoryParams,
        caller: str = "unknown",
        user_agent: str | None = None,
        trace_id: str | None = None,
    ) -> dict:
        """Get conversation history for a dialog"""
        start_time = datetime.now()
        try:
            if not self.dialog_tools:
                return {"success": False, "error": "DialogTools not available"}

            result = self.dialog_tools.get_conversation_history(params)

            self.audit.log_tool_call(
                "conversation_history",
                caller,
                params.dict(),
                True,
                result,
                start_time=start_time,
                user_agent=user_agent,
                trace_id=trace_id,
            )
            return result

        except Exception as e:
            error_msg = f"Failed to get conversation history: {str(e)}"
            self.audit.log_tool_call(
                "conversation_history",
                caller,
                params.dict(),
                False,
                error=error_msg,
                start_time=start_time,
                user_agent=user_agent,
                trace_id=trace_id,
            )
            return {"success": False, "error": error_msg}

    def conversation_mark(
        self,
        params: ConversationMarkParams,
        caller: str = "unknown",
        user_agent: str | None = None,
        trace_id: str | None = None,
    ) -> dict:
        """Mark conversation messages with a status"""
        start_time = datetime.now()
        try:
            if not self.dialog_tools:
                return {"success": False, "error": "DialogTools not available"}

            result = self.dialog_tools.mark_messages(params)

            self.audit.log_tool_call(
                "conversation_mark",
                caller,
                params.dict(),
                True,
                result,
                start_time=start_time,
                user_agent=user_agent,
                trace_id=trace_id,
            )
            return result

        except Exception as e:
            error_msg = f"Failed to mark conversation messages: {str(e)}"
            self.audit.log_tool_call(
                "conversation_mark",
                caller,
                params.dict(),
                False,
                error=error_msg,
                start_time=start_time,
                user_agent=user_agent,
                trace_id=trace_id,
            )
            return {"success": False, "error": error_msg}

    # Agent Collaboration Methods
    def task_create(
        self,
        params: TaskCreateParams,
        caller: str = "unknown",
        user_agent: str | None = None,
        trace_id: str | None = None,
        auth_ctx: dict[str, Any] | None = None,
    ) -> dict:
        """Create a collaborative task"""
        start_time = datetime.now()
        try:
            admin_err = self._require_admin(auth_ctx, "task_create")
            if admin_err:
                self.audit.log_tool_call(
                    "task_create",
                    caller,
                    params.dict(),
                    False,
                    error=admin_err["error"],
                    start_time=start_time,
                    user_agent=user_agent,
                    trace_id=trace_id,
                )
                return admin_err
            if not self.orchestrator:
                return {"success": False, "error": "TaskOrchestrator not available"}

            result = self.orchestrator.create_task(
                task_description=params.task_description,
                workflow_template=params.workflow_template,
                priority=params.priority,
                timeout=params.timeout,
                required_roles=params.required_roles,
            )

            self.audit.log_tool_call(
                "task_create",
                caller,
                params.dict(),
                True,
                result,
                start_time=start_time,
                user_agent=user_agent,
                trace_id=trace_id,
            )
            return result

        except Exception as e:
            error_msg = f"Failed to create task: {str(e)}"
            self.audit.log_tool_call(
                "task_create",
                caller,
                params.dict(),
                False,
                error=error_msg,
                start_time=start_time,
                user_agent=user_agent,
                trace_id=trace_id,
            )
            return {"success": False, "error": error_msg}

    def task_status(
        self,
        params: TaskStatusParams,
        caller: str = "unknown",
        user_agent: str | None = None,
        trace_id: str | None = None,
    ) -> dict:
        """Query task status"""
        start_time = datetime.now()
        try:
            if not self.orchestrator:
                return {"success": False, "error": "TaskOrchestrator not available"}

            result = self.orchestrator.get_task_status(
                task_id=params.task_id, include_subtasks=params.include_subtasks
            )

            self.audit.log_tool_call(
                "task_status",
                caller,
                params.dict(),
                True,
                result,
                start_time=start_time,
                user_agent=user_agent,
                trace_id=trace_id,
            )
            return result

        except Exception as e:
            error_msg = f"Failed to get task status: {str(e)}"
            self.audit.log_tool_call(
                "task_status",
                caller,
                params.dict(),
                False,
                error=error_msg,
                start_time=start_time,
                user_agent=user_agent,
                trace_id=trace_id,
            )
            return {"success": False, "error": error_msg}

    def agent_register(
        self,
        params: AgentRegisterParams,
        caller: str = "unknown",
        user_agent: str | None = None,
        trace_id: str | None = None,
        auth_ctx: dict[str, Any] | None = None,
    ) -> dict:
        """Register an agent"""
        start_time = datetime.now()
        try:
            admin_err = self._require_admin(auth_ctx, "agent_register")
            if admin_err:
                self.audit.log_tool_call(
                    "agent_register",
                    caller,
                    params.dict(),
                    False,
                    error=admin_err["error"],
                    start_time=start_time,
                    user_agent=user_agent,
                    trace_id=trace_id,
                )
                return admin_err
            if not self.coordinator:
                return {"success": False, "error": "AgentCoordinator not available"}

            result = self.coordinator.register_agent(
                agent_id=params.agent_id,
                agent_type=params.agent_type,
                role=params.role,
                capabilities=params.capabilities,
                max_concurrent_tasks=params.max_concurrent_tasks,
                numeric_code=params.numeric_code,
                send_enabled=params.send_enabled,
                category=params.category,
            )

            self.audit.log_tool_call(
                "agent_register",
                caller,
                params.dict(),
                True,
                result,
                start_time=start_time,
                user_agent=user_agent,
                trace_id=trace_id,
            )
            return result

        except Exception as e:
            error_msg = f"Failed to register agent: {str(e)}"
            self.audit.log_tool_call(
                "agent_register",
                caller,
                params.dict(),
                False,
                error=error_msg,
                start_time=start_time,
                user_agent=user_agent,
                trace_id=trace_id,
            )
            return {"success": False, "error": error_msg}

    # ----------------------------
    # Admin Vault (admin-only read/write)
    # ----------------------------
    def admin_vault_put(
        self,
        args: dict[str, Any],
        caller: str = "unknown",
        user_agent: str | None = None,
        trace_id: str | None = None,
        auth_ctx: dict[str, Any] | None = None,
    ) -> dict:
        start_time = datetime.now()
        try:
            admin_err = self._require_admin(auth_ctx, "admin_vault_put")
            if admin_err:
                self.audit.log_tool_call(
                    "admin_vault_put",
                    caller,
                    args,
                    False,
                    error=admin_err["error"],
                    start_time=start_time,
                    user_agent=user_agent,
                    trace_id=trace_id,
                )
                return admin_err
            doc_name = str(args.get("doc_name") or "").strip()
            content = args.get("content")
            if not doc_name or not isinstance(content, str):
                return {
                    "success": False,
                    "error": "doc_name (string) and content (string) are required",
                }
            if ".." in doc_name or "/" in doc_name or "\\" in doc_name:
                return {"success": False, "error": "Invalid doc_name (no path traversal)"}
            target = self._admin_vault_dir() / doc_name
            with open(target, "w", encoding="utf-8") as f:
                f.write(content)
            result = {"success": True, "doc_path": str(target.relative_to(self.repo_root))}
            self.audit.log_tool_call(
                "admin_vault_put",
                caller,
                {"doc_name": doc_name, "size": len(content)},
                True,
                result,
                start_time=start_time,
                user_agent=user_agent,
                trace_id=trace_id,
            )
            return result
        except Exception as e:
            error_msg = f"Failed to write admin vault doc: {str(e)}"
            self.audit.log_tool_call(
                "admin_vault_put",
                caller,
                args,
                False,
                error=error_msg,
                start_time=start_time,
                user_agent=user_agent,
                trace_id=trace_id,
            )
            return {"success": False, "error": error_msg}

    def admin_vault_get(
        self,
        args: dict[str, Any],
        caller: str = "unknown",
        user_agent: str | None = None,
        trace_id: str | None = None,
        auth_ctx: dict[str, Any] | None = None,
    ) -> dict:
        start_time = datetime.now()
        try:
            admin_err = self._require_admin(auth_ctx, "admin_vault_get")
            if admin_err:
                self.audit.log_tool_call(
                    "admin_vault_get",
                    caller,
                    args,
                    False,
                    error=admin_err["error"],
                    start_time=start_time,
                    user_agent=user_agent,
                    trace_id=trace_id,
                )
                return admin_err
            doc_name = str(args.get("doc_name") or "").strip()
            if not doc_name:
                return {"success": False, "error": "doc_name is required"}
            if ".." in doc_name or "/" in doc_name or "\\" in doc_name:
                return {"success": False, "error": "Invalid doc_name (no path traversal)"}
            target = self._admin_vault_dir() / doc_name
            if not target.exists():
                return {"success": False, "error": f"Not found: {doc_name}"}
            with open(target, encoding="utf-8") as f:
                content = f.read()
            result = {
                "success": True,
                "doc_path": str(target.relative_to(self.repo_root)),
                "content": content,
            }
            self.audit.log_tool_call(
                "admin_vault_get",
                caller,
                {"doc_name": doc_name},
                True,
                {"success": True, "doc_path": result["doc_path"]},
                start_time=start_time,
                user_agent=user_agent,
                trace_id=trace_id,
            )
            return result
        except Exception as e:
            error_msg = f"Failed to read admin vault doc: {str(e)}"
            self.audit.log_tool_call(
                "admin_vault_get",
                caller,
                args,
                False,
                error=error_msg,
                start_time=start_time,
                user_agent=user_agent,
                trace_id=trace_id,
            )
            return {"success": False, "error": error_msg}

    def workflow_execute(
        self,
        params: WorkflowExecuteParams,
        caller: str = "unknown",
        user_agent: str | None = None,
        trace_id: str | None = None,
        auth_ctx: dict[str, Any] | None = None,
    ) -> dict:
        """Execute a workflow"""
        start_time = datetime.now()
        try:
            admin_err = self._require_admin(auth_ctx, "workflow_execute")
            if admin_err:
                self.audit.log_tool_call(
                    "workflow_execute",
                    caller,
                    params.dict(),
                    False,
                    error=admin_err["error"],
                    start_time=start_time,
                    user_agent=user_agent,
                    trace_id=trace_id,
                )
                return admin_err
            if not self.workflow_engine:
                return {"success": False, "error": "WorkflowEngine not available"}

            result = self.workflow_engine.executor.execute_workflow(
                workflow_name=params.workflow_name, inputs=params.inputs, task_id=params.task_id
            )

            self.audit.log_tool_call(
                "workflow_execute",
                caller,
                params.dict(),
                True,
                result,
                start_time=start_time,
                user_agent=user_agent,
                trace_id=trace_id,
            )
            return result

        except Exception as e:
            error_msg = f"Failed to execute workflow: {str(e)}"
            self.audit.log_tool_call(
                "workflow_execute",
                caller,
                params.dict(),
                False,
                error=error_msg,
                start_time=start_time,
                user_agent=user_agent,
                trace_id=trace_id,
            )
            return {"success": False, "error": error_msg}

    def result_get(
        self,
        params: ResultGetParams,
        caller: str = "unknown",
        user_agent: str | None = None,
        trace_id: str | None = None,
        auth_ctx: dict[str, Any] | None = None,
    ) -> dict:
        """Get task results"""
        start_time = datetime.now()
        try:
            admin_err = self._require_admin(auth_ctx, "result_get")
            if admin_err:
                self.audit.log_tool_call(
                    "result_get",
                    caller,
                    params.dict(),
                    False,
                    error=admin_err["error"],
                    start_time=start_time,
                    user_agent=user_agent,
                    trace_id=trace_id,
                )
                return admin_err
            if not self.aggregator:
                return {"success": False, "error": "ResultAggregator not available"}

            result = self.aggregator.get_result(
                task_id=params.task_id, include_intermediate=params.include_intermediate
            )

            self.audit.log_tool_call(
                "result_get",
                caller,
                params.dict(),
                True,
                result,
                start_time=start_time,
                user_agent=user_agent,
                trace_id=trace_id,
            )
            return result

        except Exception as e:
            error_msg = f"Failed to get results: {str(e)}"
            self.audit.log_tool_call(
                "result_get",
                caller,
                params.dict(),
                False,
                error=error_msg,
                start_time=start_time,
                user_agent=user_agent,
                trace_id=trace_id,
            )
            return {"success": False, "error": error_msg}

    def github_search(
        self,
        params: GitHubSearchParams,
        caller: str = "unknown",
        user_agent: str | None = None,
        trace_id: str | None = None,
    ) -> dict:
        """Search GitHub repositories, code, or issues"""
        start_time = datetime.now()
        try:
            github_token = os.getenv("GITHUB_TOKEN")
            headers = {"Accept": "application/vnd.github.v3+json"}
            if github_token:
                headers["Authorization"] = f"token {github_token}"

            base_url = "https://api.github.com/search"
            if params.search_type == "repositories":
                url = f"{base_url}/repositories"
            elif params.search_type == "code":
                url = f"{base_url}/code"
            elif params.search_type == "issues":
                url = f"{base_url}/issues"
            else:
                return {"success": False, "error": f"Invalid search_type: {params.search_type}"}

            search_params = {"q": params.query, "per_page": min(params.limit, 100)}
            if params.sort:
                search_params["sort"] = params.sort
            if params.order:
                search_params["order"] = params.order

            response = httpx.get(url, headers=headers, params=search_params, timeout=30.0)
            response.raise_for_status()
            data = response.json()

            items = data.get("items", [])[: params.limit]
            results = []
            for item in items:
                if params.search_type == "repositories":
                    results.append(
                        {
                            "name": item.get("full_name"),
                            "description": item.get("description"),
                            "url": item.get("html_url"),
                            "stars": item.get("stargazers_count"),
                            "language": item.get("language"),
                            "updated_at": item.get("updated_at"),
                        }
                    )
                elif params.search_type == "code":
                    results.append(
                        {
                            "name": item.get("name"),
                            "path": item.get("path"),
                            "repository": item.get("repository", {}).get("full_name"),
                            "url": item.get("html_url"),
                            "language": item.get("language"),
                        }
                    )
                elif params.search_type == "issues":
                    results.append(
                        {
                            "title": item.get("title"),
                            "number": item.get("number"),
                            "repository": item.get("repository_url").split("/repos/")[-1]
                            if item.get("repository_url")
                            else None,
                            "url": item.get("html_url"),
                            "state": item.get("state"),
                            "created_at": item.get("created_at"),
                        }
                    )

            result = {
                "success": True,
                "query": params.query,
                "search_type": params.search_type,
                "total_count": data.get("total_count", 0),
                "results": results,
            }
            self.audit.log_tool_call(
                "github_search",
                caller,
                params.dict(),
                True,
                result,
                start_time=start_time,
                user_agent=user_agent,
                trace_id=trace_id,
            )
            return result
        except Exception as e:
            error_msg = f"Failed to search GitHub: {str(e)}"
            self.audit.log_tool_call(
                "github_search",
                caller,
                params.dict(),
                False,
                error=error_msg,
                start_time=start_time,
                user_agent=user_agent,
                trace_id=trace_id,
            )
            return {"success": False, "error": error_msg}
