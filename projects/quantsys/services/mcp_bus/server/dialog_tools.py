"""
Dialog Tools Library - Conversation management utilities for GPT, Cursor, and TRAE dialogs
Provides helper functions for dialog registration, conversation tracking, and message management
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


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


class DialogTools:
    """Dialog management tools library"""

    def __init__(self, repo_root: str):
        self.repo_root = Path(repo_root).resolve()
        self.ata_messages_dir = self.repo_root / "docs" / "REPORT" / "ata" / "messages"
        self.dialog_registry_dir = self.repo_root / "docs" / "REPORT" / "ata" / "dialogs"
        self.dialog_registry_file = self.dialog_registry_dir / "registry.json"
        self.ata_context_dir = self.repo_root / "docs" / "REPORT" / "ata" / "contexts"

        # Ensure directories exist
        self.ata_messages_dir.mkdir(parents=True, exist_ok=True)
        self.dialog_registry_dir.mkdir(parents=True, exist_ok=True)
        self.ata_context_dir.mkdir(parents=True, exist_ok=True)

    def load_registry(self) -> dict[str, Any]:
        """Load dialog registry"""
        if not self.dialog_registry_file.exists():
            return {"dialogs": {}, "next_id": {}}
        try:
            with open(self.dialog_registry_file, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {"dialogs": {}, "next_id": {}}

    def save_registry(self, registry: dict[str, Any]):
        """Save dialog registry"""
        with open(self.dialog_registry_file, "w", encoding="utf-8") as f:
            json.dump(registry, f, indent=2, ensure_ascii=False)

    def get_conversation_stats(self, params: ConversationStatsParams) -> dict[str, Any]:
        """Get conversation statistics"""
        messages = []

        # Load all messages
        if self.ata_messages_dir.exists():
            for task_dir in self.ata_messages_dir.iterdir():
                if not task_dir.is_dir():
                    continue

                # Filter by taskcode
                if params.taskcode and task_dir.name != params.taskcode:
                    continue

                for msg_file in task_dir.glob("*.json"):
                    try:
                        with open(msg_file, encoding="utf-8") as f:
                            message = json.load(f)

                        # Apply filters
                        if params.dialog_id:
                            if (
                                message.get("from_agent") != params.dialog_id
                                and message.get("to_agent") != params.dialog_id
                            ):
                                continue

                        if params.agent_type:
                            from_agent = message.get("from_agent", "")
                            to_agent = message.get("to_agent", "")
                            if (
                                params.agent_type not in from_agent
                                and params.agent_type not in to_agent
                            ):
                                continue

                        # Date filtering
                        if params.from_date or params.to_date:
                            created_at = message.get("created_at", "")
                            if created_at:
                                msg_date = (
                                    created_at.split("T")[0]
                                    if "T" in created_at
                                    else created_at[:10]
                                )
                                if params.from_date and msg_date < params.from_date:
                                    continue
                                if params.to_date and msg_date > params.to_date:
                                    continue

                        messages.append(message)
                    except Exception:
                        continue

        # Calculate statistics
        stats = {
            "total_messages": len(messages),
            "by_agent_type": {},
            "by_status": {},
            "by_priority": {},
            "by_kind": {},
            "dialog_participation": {},
            "date_range": {"earliest": None, "latest": None},
        }

        for msg in messages:
            # Count by agent type
            from_agent = msg.get("from_agent", "")
            to_agent = msg.get("to_agent", "")

            # Extract agent type from dialog ID (e.g., "Cursor-Dialog-1" -> "Cursor")
            for agent_id in [from_agent, to_agent]:
                if "-Dialog-" in agent_id:
                    agent_type = agent_id.split("-Dialog-")[0]
                    stats["by_agent_type"][agent_type] = (
                        stats["by_agent_type"].get(agent_type, 0) + 1
                    )
                elif agent_id in ["Cursor", "GPT", "TRAE"]:
                    stats["by_agent_type"][agent_id] = stats["by_agent_type"].get(agent_id, 0) + 1

            # Count by status
            status = msg.get("status", "pending")
            stats["by_status"][status] = stats["by_status"].get(status, 0) + 1

            # Count by priority
            priority = msg.get("priority", "normal")
            stats["by_priority"][priority] = stats["by_priority"].get(priority, 0) + 1

            # Count by kind
            kind = msg.get("kind", "unknown")
            stats["by_kind"][kind] = stats["by_kind"].get(kind, 0) + 1

            # Dialog participation
            if params.dialog_id or "-Dialog-" in from_agent or "-Dialog-" in to_agent:
                for agent_id in [from_agent, to_agent]:
                    if "-Dialog-" in agent_id:
                        stats["dialog_participation"][agent_id] = (
                            stats["dialog_participation"].get(agent_id, 0) + 1
                        )

            # Date range
            created_at = msg.get("created_at", "")
            if created_at:
                msg_date = created_at.split("T")[0] if "T" in created_at else created_at[:10]
                if (
                    not stats["date_range"]["earliest"]
                    or msg_date < stats["date_range"]["earliest"]
                ):
                    stats["date_range"]["earliest"] = msg_date
                if not stats["date_range"]["latest"] or msg_date > stats["date_range"]["latest"]:
                    stats["date_range"]["latest"] = msg_date

        return {"success": True, "stats": stats, "filters": params.dict(exclude_none=True)}

    def search_conversations(self, params: ConversationSearchParams) -> dict[str, Any]:
        """Search conversations by content"""
        results = []
        query_lower = params.query.lower()

        # Load all messages
        if self.ata_messages_dir.exists():
            for task_dir in self.ata_messages_dir.iterdir():
                if not task_dir.is_dir():
                    continue

                # Filter by taskcode
                if params.taskcode and task_dir.name != params.taskcode:
                    continue

                for msg_file in task_dir.glob("*.json"):
                    try:
                        with open(msg_file, encoding="utf-8") as f:
                            message = json.load(f)

                        # Apply filters
                        if params.dialog_id:
                            if (
                                message.get("from_agent") != params.dialog_id
                                and message.get("to_agent") != params.dialog_id
                            ):
                                continue

                        if params.agent_type:
                            from_agent = message.get("from_agent", "")
                            to_agent = message.get("to_agent", "")
                            if (
                                params.agent_type not in from_agent
                                and params.agent_type not in to_agent
                            ):
                                continue

                        # Search in payload
                        payload = message.get("payload", {})
                        payload_str = json.dumps(payload, ensure_ascii=False).lower()

                        # Search in other fields
                        message_str = json.dumps(message, ensure_ascii=False).lower()

                        if query_lower in payload_str or query_lower in message_str:
                            results.append(
                                {
                                    "msg_id": message.get("msg_id"),
                                    "taskcode": message.get("taskcode"),
                                    "from_agent": message.get("from_agent"),
                                    "to_agent": message.get("to_agent"),
                                    "kind": message.get("kind"),
                                    "created_at": message.get("created_at"),
                                    "preview": self._get_message_preview(payload),
                                    "file_path": str(msg_file.relative_to(self.repo_root)),
                                }
                            )
                    except Exception:
                        continue

        # Sort by created_at (newest first)
        results.sort(key=lambda x: x.get("created_at", ""), reverse=True)

        # Apply limit
        limited_results = results[: params.limit]

        return {
            "success": True,
            "query": params.query,
            "results": limited_results,
            "count": len(limited_results),
            "total_found": len(results),
        }

    def get_conversation_history(self, params: ConversationHistoryParams) -> dict[str, Any]:
        """Get conversation history for a dialog"""
        messages = []

        # Load all messages
        if self.ata_messages_dir.exists():
            for task_dir in self.ata_messages_dir.iterdir():
                if not task_dir.is_dir():
                    continue

                # Filter by taskcode
                if params.taskcode and task_dir.name != params.taskcode:
                    continue

                for msg_file in task_dir.glob("*.json"):
                    try:
                        with open(msg_file, encoding="utf-8") as f:
                            message = json.load(f)

                        # Filter by dialog_id
                        from_agent = message.get("from_agent", "")
                        to_agent = message.get("to_agent", "")

                        if from_agent != params.dialog_id and to_agent != params.dialog_id:
                            continue

                        # Add context if requested
                        if params.include_context:
                            taskcode = message.get("taskcode", "")
                            context_file = self.ata_context_dir / f"{taskcode}_context.json"
                            if context_file.exists():
                                try:
                                    with open(context_file, encoding="utf-8") as f:
                                        context = json.load(f)
                                    message["conversation_context"] = context
                                except Exception:
                                    pass

                        messages.append(message)
                    except Exception:
                        continue

        # Sort by created_at (oldest first for chronological order)
        messages.sort(key=lambda x: x.get("created_at", ""))

        # Apply limit (most recent)
        limited_messages = messages[-params.limit :] if len(messages) > params.limit else messages

        return {
            "success": True,
            "dialog_id": params.dialog_id,
            "messages": limited_messages,
            "count": len(limited_messages),
            "total": len(messages),
        }

    def mark_messages(self, params: ConversationMarkParams) -> dict[str, Any]:
        """Mark conversation messages with a status"""
        marked = []
        failed = []

        # Load all messages
        if self.ata_messages_dir.exists():
            for task_dir in self.ata_messages_dir.iterdir():
                if not task_dir.is_dir():
                    continue

                for msg_file in task_dir.glob("*.json"):
                    try:
                        with open(msg_file, encoding="utf-8") as f:
                            message = json.load(f)

                        msg_id = message.get("msg_id")
                        if msg_id not in params.msg_ids:
                            continue

                        # Check dialog_id matches
                        from_agent = message.get("from_agent", "")
                        to_agent = message.get("to_agent", "")
                        if from_agent != params.dialog_id and to_agent != params.dialog_id:
                            continue

                        # Update status
                        message["status"] = params.status
                        message["updated_at"] = datetime.now().isoformat()

                        # Save message
                        with open(msg_file, "w", encoding="utf-8") as f:
                            json.dump(message, f, indent=2, ensure_ascii=False)

                        marked.append(msg_id)
                    except Exception as e:
                        failed.append({"msg_id": message.get("msg_id"), "error": str(e)})

        return {
            "success": True,
            "marked": marked,
            "failed": failed,
            "total_requested": len(params.msg_ids),
            "total_marked": len(marked),
            "total_failed": len(failed),
        }

    def _get_message_preview(self, payload: dict[str, Any], max_length: int = 100) -> str:
        """Get a preview of message payload"""
        if isinstance(payload, dict):
            # Try to find text fields
            for key in ["message", "text", "content", "details", "action", "note"]:
                if key in payload and isinstance(payload[key], str):
                    text = payload[key]
                    if len(text) > max_length:
                        return text[:max_length] + "..."
                    return text
            # Fallback to JSON string
            json_str = json.dumps(payload, ensure_ascii=False)
            if len(json_str) > max_length:
                return json_str[:max_length] + "..."
            return json_str
        return str(payload)[:max_length]
