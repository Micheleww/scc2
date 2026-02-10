"""
Enhanced ATA (Agent-to-Agent) Communication Module
Optimized for smooth three-way communication between GPT, Cursor, and TRAE
"""

import hashlib
import json
import uuid
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any


class MessagePriority(Enum):
    """Message priority levels"""

    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    URGENT = "urgent"


class MessageStatus(Enum):
    """Message delivery status"""

    PENDING = "pending"
    DELIVERED = "delivered"
    READ = "read"
    ACKED = "acked"
    FAILED = "failed"


class ConversationContext:
    """Manages conversation context for better continuity"""

    def __init__(self, taskcode: str, context_dir: Path):
        self.taskcode = taskcode
        self.context_dir = context_dir
        self.context_file = context_dir / f"{taskcode}_context.json"
        self.context_dir.mkdir(parents=True, exist_ok=True)

    def load(self) -> dict[str, Any]:
        """Load conversation context"""
        if self.context_file.exists():
            try:
                with open(self.context_file, encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                return self._default_context()
        return self._default_context()

    def save(self, context: dict[str, Any]):
        """Save conversation context"""
        with open(self.context_file, "w", encoding="utf-8") as f:
            json.dump(context, f, indent=2, ensure_ascii=False)

    def _default_context(self) -> dict[str, Any]:
        """Default context structure"""
        return {
            "taskcode": self.taskcode,
            "participants": [],
            "message_count": 0,
            "last_message_at": None,
            "status": "active",
            "summary": "",
            "key_points": [],
            "next_actions": [],
        }

    def update(self, from_agent: str, to_agent: str, payload: dict[str, Any]):
        """Update context with new message"""
        context = self.load()

        # Add participants if not present
        if from_agent not in context["participants"]:
            context["participants"].append(from_agent)
        if to_agent not in context["participants"]:
            context["participants"].append(to_agent)

        # Update message count
        context["message_count"] += 1
        context["last_message_at"] = datetime.now().isoformat()

        # Extract key information from payload
        if "summary" in payload:
            context["summary"] = payload["summary"]
        if "key_points" in payload:
            context["key_points"].extend(payload.get("key_points", []))
        if "next_actions" in payload:
            context["next_actions"].extend(payload.get("next_actions", []))

        # Keep only last 10 key points and next actions
        context["key_points"] = context["key_points"][-10:]
        context["next_actions"] = context["next_actions"][-10:]

        self.save(context)
        return context


class MessageQueue:
    """Manages message queue for reliable delivery"""

    def __init__(self, queue_dir: Path):
        self.queue_dir = queue_dir
        self.queue_dir.mkdir(parents=True, exist_ok=True)

    def enqueue(self, msg_id: str, message: dict[str, Any]) -> bool:
        """Add message to queue"""
        queue_file = self.queue_dir / f"{msg_id}.json"
        try:
            with open(queue_file, "w", encoding="utf-8") as f:
                json.dump(
                    {
                        "msg_id": msg_id,
                        "message": message,
                        "enqueued_at": datetime.now().isoformat(),
                        "retries": 0,
                    },
                    f,
                    indent=2,
                    ensure_ascii=False,
                )
            return True
        except Exception:
            return False

    def dequeue(self, msg_id: str) -> dict[str, Any] | None:
        """Remove message from queue"""
        queue_file = self.queue_dir / f"{msg_id}.json"
        if queue_file.exists():
            try:
                queue_file.unlink()
                return True
            except Exception:
                return False
        return None

    def get_pending(self, to_agent: str) -> list[dict[str, Any]]:
        """Get pending messages for an agent"""
        pending = []
        for queue_file in self.queue_dir.glob("*.json"):
            try:
                with open(queue_file, encoding="utf-8") as f:
                    queue_item = json.load(f)
                    msg = queue_item.get("message", {})
                    if msg.get("to_agent") == to_agent:
                        pending.append(queue_item)
            except Exception:
                continue
        # Sort by enqueued_at
        pending.sort(key=lambda x: x.get("enqueued_at", ""))
        return pending


class ATAEnhanced:
    """Enhanced ATA communication manager"""

    def __init__(self, messages_dir: Path, context_dir: Path, queue_dir: Path):
        self.messages_dir = messages_dir
        self.context_dir = context_dir
        self.queue_dir = queue_dir

        # Ensure directories exist
        self.messages_dir.mkdir(parents=True, exist_ok=True)
        self.context_dir.mkdir(parents=True, exist_ok=True)
        self.queue_dir.mkdir(parents=True, exist_ok=True)

        self.context_manager = {}  # Cache for conversation contexts
        self.message_queue = MessageQueue(queue_dir)

    def get_conversation_context(self, taskcode: str) -> ConversationContext:
        """Get or create conversation context"""
        if taskcode not in self.context_manager:
            self.context_manager[taskcode] = ConversationContext(taskcode, self.context_dir)
        return self.context_manager[taskcode]

    def enhance_message(self, message: dict[str, Any]) -> dict[str, Any]:
        """Enhance message with additional metadata"""
        taskcode = message.get("taskcode", "")

        # Load conversation context
        context_manager = self.get_conversation_context(taskcode)
        context = context_manager.load()

        # Add context to message
        enhanced = message.copy()
        enhanced["context"] = {
            "conversation_status": context.get("status", "active"),
            "participants": context.get("participants", []),
            "message_index": context.get("message_count", 0) + 1,
            "summary": context.get("summary", ""),
            "suggested_actions": context.get("next_actions", [])[-3:],  # Last 3 actions
        }

        # Add priority if not present
        if "priority" not in enhanced:
            # Auto-detect priority from payload
            payload_text = str(enhanced.get("payload", {})).lower()
            if any(word in payload_text for word in ["urgent", "asap", "immediately", "紧急"]):
                enhanced["priority"] = MessagePriority.URGENT.value
            elif any(
                word in payload_text for word in ["important", "priority", "important", "重要"]
            ):
                enhanced["priority"] = MessagePriority.HIGH.value
            else:
                enhanced["priority"] = MessagePriority.NORMAL.value

        # Add status if not present
        if "status" not in enhanced:
            enhanced["status"] = MessageStatus.PENDING.value

        return enhanced

    def create_message_response(
        self,
        original_msg: dict[str, Any],
        response_payload: dict[str, Any],
        from_agent: str,
        kind: str = "response",
    ) -> dict[str, Any]:
        """Create a response message linked to original"""
        response = {
            "taskcode": original_msg.get("taskcode", ""),
            "from_agent": from_agent,
            "to_agent": original_msg.get("from_agent", ""),
            "kind": kind,
            "payload": response_payload,
            "prev_sha256": original_msg.get("sha256", ""),
            "in_reply_to": original_msg.get("msg_id", ""),
            "created_at": datetime.now().isoformat(),
            "priority": original_msg.get("priority", MessagePriority.NORMAL.value),
            "status": MessageStatus.PENDING.value,
        }

        # Generate message ID
        response["msg_id"] = self._generate_msg_id(response)
        response["sha256"] = self._calculate_sha256(response)

        return response

    def _generate_msg_id(self, message: dict[str, Any]) -> str:
        """Generate unique message ID"""
        taskcode = message.get("taskcode", "UNKNOWN")
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        random_suffix = str(uuid.uuid4())[:8]
        return f"{taskcode}-{timestamp}-{random_suffix}"

    def _calculate_sha256(self, message: dict[str, Any]) -> str:
        """Calculate SHA256 hash for message"""
        # Exclude sha256 and msg_id from hash calculation
        hash_dict = {k: v for k, v in message.items() if k not in ["sha256", "msg_id"]}
        hash_str = json.dumps(hash_dict, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(hash_str.encode("utf-8")).hexdigest()

    def get_conversation_thread(self, taskcode: str) -> list[dict[str, Any]]:
        """Get all messages in a conversation thread"""
        messages = []
        task_dir = self.messages_dir / taskcode
        if task_dir.exists():
            for msg_file in sorted(task_dir.glob("msg_*.json")):
                try:
                    with open(msg_file, encoding="utf-8") as f:
                        msg = json.load(f)
                        messages.append(msg)
                except Exception:
                    continue

        # Sort by created_at
        messages.sort(key=lambda x: x.get("created_at", ""))
        return messages

    def get_unread_messages(self, to_agent: str) -> list[dict[str, Any]]:
        """Get unread messages for an agent"""
        unread = []

        # Check queue first
        pending = self.message_queue.get_pending(to_agent)
        for item in pending:
            unread.append(item.get("message", {}))

        # Also check message directory
        for task_dir in self.messages_dir.iterdir():
            if task_dir.is_dir():
                for msg_file in task_dir.glob("msg_*.json"):
                    try:
                        with open(msg_file, encoding="utf-8") as f:
                            msg = json.load(f)
                            if (
                                msg.get("to_agent") == to_agent
                                and msg.get("status") != MessageStatus.READ.value
                            ):
                                unread.append(msg)
                    except Exception:
                        continue

        # Sort by created_at
        unread.sort(key=lambda x: x.get("created_at", ""))
        return unread

    def mark_as_read(self, msg_id: str) -> bool:
        """Mark message as read"""
        # Files are named like: msg_{timestamp}_{msg_id}.json (see ata_send)
        for task_dir in self.messages_dir.iterdir():
            if not task_dir.is_dir():
                continue
            try:
                candidates = list(task_dir.glob(f"msg_*_{msg_id}.json"))
                if not candidates:
                    # Fallback: scan any msg_*.json and match by payload field
                    for msg_file in task_dir.glob("msg_*.json"):
                        try:
                            with open(msg_file, encoding="utf-8") as f:
                                msg = json.load(f)
                            if msg.get("msg_id") == msg_id:
                                candidates = [msg_file]
                                break
                        except Exception:
                            continue

                for msg_file in candidates:
                    try:
                        with open(msg_file, encoding="utf-8") as f:
                            msg = json.load(f)
                        msg["status"] = MessageStatus.READ.value
                        msg["read_at"] = datetime.now().isoformat()
                        with open(msg_file, "w", encoding="utf-8") as f:
                            json.dump(msg, f, indent=2, ensure_ascii=False)
                        self.message_queue.dequeue(msg_id)
                        return True
                    except Exception:
                        continue
            except Exception:
                continue
        return False
