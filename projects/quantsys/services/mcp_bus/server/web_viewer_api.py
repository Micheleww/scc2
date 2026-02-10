"""
Web Viewer API functions for ATA messages
Integrated into the main MCP server
"""

import json
import os
from pathlib import Path
from typing import Any

# Get repository root from environment or use default
REPO_ROOT = Path(os.getenv("REPO_ROOT", "d:\\quantsys")).resolve()
ATA_MESSAGES_DIR = REPO_ROOT / "docs" / "REPORT" / "ata" / "messages"


def load_all_ata_messages() -> list[dict[str, Any]]:
    """Load all ATA messages from the messages directory"""
    messages = []

    if not ATA_MESSAGES_DIR.exists():
        return messages

    # Scan all subdirectories
    for taskcode_dir in ATA_MESSAGES_DIR.iterdir():
        if not taskcode_dir.is_dir():
            continue

        # Load all JSON files in this directory
        for msg_file in taskcode_dir.glob("*.json"):
            try:
                with open(msg_file, encoding="utf-8") as f:
                    msg_data = json.load(f)
                    msg_data["file_path"] = str(msg_file.relative_to(REPO_ROOT))
                    messages.append(msg_data)
            except (OSError, json.JSONDecodeError) as e:
                print(f"Error loading {msg_file}: {e}")
                continue

    # Sort by created_at
    messages.sort(key=lambda x: x.get("created_at", ""))
    return messages


def get_message_preview(payload: dict[str, Any], max_length: int = 100) -> str:
    """Get a preview of the message payload"""
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
