import argparse
import json
from pathlib import Path
from typing import List, Dict, Optional


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _relative_posix(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except Exception:
        # Best-effort fallback (should be rare if inputs are resolved under repo_root).
        return str(path).replace("\\", "/")


def _extract_conversation_meta(lines: List[str]) -> Dict[str, Optional[str]]:
    title = None
    conversation_id = None
    for line in lines:
        if title is None and line.startswith("# WebGPT Conversation:"):
            title = line.split(":", 1)[1].strip()
        if conversation_id is None and "- conversation_id:" in line:
            start = line.find("`")
            end = line.rfind("`")
            if start != -1 and end > start:
                conversation_id = line[start + 1 : end].strip()
        if title and conversation_id:
            break
    return {"title": title, "conversation_id": conversation_id}


def _extract_messages(lines: List[str]) -> List[Dict[str, str]]:
    messages: List[Dict[str, str]] = []
    current = None
    for line in lines:
        if line.startswith("## "):
            header = line[3:].strip()
            if " (" in header:
                role = header.split(" (", 1)[0].strip()
            else:
                role = header.strip()
            current = {"role": role, "lines": []}
            messages.append(current)
            continue
        if current is not None:
            current["lines"].append(line.rstrip("\n"))
    normalized = []
    for msg in messages:
        content_lines = msg["lines"]
        normalized.append({
            "role": msg["role"],
            "content": "\n".join(content_lines).strip(),
        })
    return normalized


def _first_non_empty_line(text: str) -> str:
    for line in text.splitlines():
        stripped = line.strip()
        if stripped:
            return stripped
    return ""


def _build_conversation_epic(
    convo_path: Path,
    repo_root: Path,
) -> Dict[str, object]:
    lines = _read_text(convo_path).splitlines()
    meta = _extract_conversation_meta(lines)
    conversation_id = meta.get("conversation_id") or convo_path.stem
    title = meta.get("title") or convo_path.stem
    messages = _extract_messages(lines)
    tasks = []
    message_index = 0
    for msg in messages:
        message_index += 1
        if msg["role"].lower() != "user":
            continue
        # task_id MUST be filesystem-safe across Windows/macOS/Linux.
        # Use "_" as the canonical separator (":" is invalid in Windows paths).
        task_id = f"{conversation_id}_{message_index:04d}"
        tasks.append({
            "task_id": task_id,
            "task_label": f"WebGPT user message {message_index:04d}",
            "contract_ref": "docs/ssot/04_contracts/task_tree.md#contract_ref_tbd",
            "evidence_refs": [
                _relative_posix(convo_path, repo_root),
            ],
            "source_anchor": f"message-{message_index:04d}",
        })
    if not tasks:
        task_id = f"{conversation_id}_0001"
        tasks.append({
            "task_id": task_id,
            "task_label": "(no user messages captured)",
            "contract_ref": "docs/ssot/04_contracts/task_tree.md#contract_ref_tbd",
            "evidence_refs": [
                _relative_posix(convo_path, repo_root),
            ],
            "source_anchor": "message-0001",
        })
    capability_id = f"{conversation_id}:capability:raw"
    epic_id = f"webgpt:{conversation_id}"
    return {
        "epic_id": epic_id,
        "title": title,
        "capabilities": [
            {
                "capability_id": capability_id,
                "title": "raw_webgpt_import",
                "tasks": tasks,
            }
        ],
    }


def _build_memory_epic(memory_path: Path, repo_root: Path) -> Dict[str, object]:
    memory_rel = _relative_posix(memory_path, repo_root)
    return {
        "epic_id": "webgpt:memory",
        "title": "WebGPT memory",
        "capabilities": [
            {
                "capability_id": "webgpt:memory:capability:raw",
                "title": "raw_webgpt_memory",
                "tasks": [
                    {
                        "task_id": "memory_0001",
                        "task_label": "Capture WebGPT memory",
                        "contract_ref": "docs/ssot/04_contracts/task_tree.md#contract_ref_tbd",
                        "evidence_refs": [memory_rel],
                        "source_anchor": "memory-0001",
                    }
                ],
            }
        ],
    }


def generate_task_tree(input_root: Path, output_path: Path) -> Dict[str, object]:
    repo_root = Path(__file__).resolve().parents[2]
    if not input_root.is_absolute():
        input_root = (repo_root / input_root).resolve()
    if not output_path.is_absolute():
        output_path = (repo_root / output_path).resolve()
    conversations_dir = input_root / "conversations"
    convo_paths = sorted(conversations_dir.glob("*.md"), key=lambda p: p.name)
    epics = []
    for convo_path in convo_paths:
        epics.append(_build_conversation_epic(convo_path, repo_root))
    memory_path = input_root / "memory.md"
    if memory_path.exists():
        epics.append(_build_memory_epic(memory_path, repo_root))
    output = {
        "schema_version": "v0.1",
        "source_root": _relative_posix(input_root, repo_root),
        "input_index": _relative_posix(input_root / "index.md", repo_root),
        "epics": epics,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(output, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    return output


def main() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(description="Generate task tree skeleton from WebGPT exports")
    parser.add_argument(
        "--input-root",
        default=str(repo_root / "docs" / "INPUTS" / "WEBGPT"),
        help="Root directory for WebGPT exports",
    )
    parser.add_argument(
        "--output",
        default=str(repo_root / "docs" / "DERIVED" / "task_tree.json"),
        help="Output path for task tree JSON",
    )
    args = parser.parse_args()
    input_root = Path(args.input_root)
    output_path = Path(args.output)
    generate_task_tree(input_root, output_path)


if __name__ == "__main__":
    main()
