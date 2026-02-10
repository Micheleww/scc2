from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return ""


def _read_json(path: Path) -> Optional[Dict[str, Any]]:
    try:
        obj = json.loads(path.read_text(encoding="utf-8"))
        return obj if isinstance(obj, dict) else None
    except Exception:
        return None


def _count_toolish_markers(stderr: str) -> Dict[str, int]:
    """
    Heuristic counters for Codex CLI logs.
    """
    counts: Dict[str, int] = {}
    for key, pat in [
        ("tokens_used_lines", r"^tokens used\s*$"),
        ("mcp_startup", r"^mcp startup:"),
        ("thinking_blocks", r"^thinking\s*$"),
        ("tool_word", r"tool[-_ ]?call|readToolCall|grepToolCall|globToolCall|lsToolCall"),
        ("shell_word", r"\bshell\b|shellToolCall|powershell|bash -lc|\brg\b|\bcat\b|Get-ChildItem|Select-String"),
    ]:
        counts[key] = len(re.findall(pat, stderr, flags=re.IGNORECASE | re.MULTILINE))
    return counts


@dataclass(frozen=True)
class CodexRunArtifacts:
    run_id: str
    server_artifacts_dir: str
    prompt_file: str
    stdout_file: str
    stderr_file: str
    model: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class CodexChildBehavior:
    id: str
    prompt_file: str
    stdout_file: str
    stderr_file: str
    exit_code: Optional[int]
    parsed_json: Optional[Dict[str, Any]]
    heuristics: Dict[str, int]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def generate_codexcli_behavior_report(*, demo_dir: Path) -> Dict[str, Any]:
    """
    Build a machine-readable behavior report from artifacts/codexcli_remote_runs/<run_id>/...

    Input:
      demo_dir = artifacts/scc_tasks/<task_id>/evidence/codexcli_demo/
    """
    demo_dir = Path(demo_dir).resolve()
    decompose = _read_json(demo_dir / "decompose_raw.json") or {}
    children = _read_json(demo_dir / "children_run_raw.json") or {}

    meta = {
        "ok": True,
        "updated_utc": _utc_now_iso(),
        "demo_dir": str(demo_dir),
        "decompose_run_id": str((decompose.get("run_id") or "")),
        "children_run_id": str((children.get("run_id") or "")),
    }

    # Try to infer run folders
    repo_root = demo_dir
    for _ in range(6):
        if (repo_root / "artifacts").exists():
            break
        repo_root = repo_root.parent
    codex_runs = (repo_root / "artifacts" / "codexcli_remote_runs").resolve()

    out: Dict[str, Any] = {"meta": meta, "decompose": {}, "children": []}

    # Decompose behavior
    try:
        d_run_id = str(decompose.get("run_id") or "")
        if d_run_id:
            d_dir = (codex_runs / d_run_id).resolve()
            out["decompose"] = {
                "run_id": d_run_id,
                "prompt": _read_text(d_dir / "prompt.txt"),
                "stdout": _read_text(d_dir / "stdout.log")[:20000],
                "stderr": _read_text(d_dir / "stderr.log")[:20000],
                "heuristics": _count_toolish_markers(_read_text(d_dir / "stderr.log")),
            }
    except Exception:
        out["decompose"] = {}

    # Children behavior: each parent_<id>/prompt.txt exists under children server_artifacts_dir
    try:
        c_run_id = str(children.get("run_id") or "")
        if c_run_id:
            c_dir = (codex_runs / c_run_id).resolve()
            behaviors: List[CodexChildBehavior] = []
            for step in sorted(c_dir.glob("parent_*")):
                pid = step.name.replace("parent_", "")
                prompt_file = str((step / "prompt.txt").resolve())
                stdout_file = str((step / "stdout.log").resolve())
                stderr_file = str((step / "stderr.log").resolve())
                stderr = _read_text(Path(stderr_file))
                stdout = _read_text(Path(stdout_file))
                parsed = None
                try:
                    parsed = json.loads(stdout) if stdout.strip().startswith("{") else None
                except Exception:
                    parsed = None
                behaviors.append(
                    CodexChildBehavior(
                        id=str(pid),
                        prompt_file=prompt_file,
                        stdout_file=stdout_file,
                        stderr_file=stderr_file,
                        exit_code=None,
                        parsed_json=parsed,
                        heuristics=_count_toolish_markers(stderr),
                    )
                )
            out["children"] = [b.to_dict() for b in behaviors]
    except Exception:
        out["children"] = []

    report_path = demo_dir / "behavior_report.json"
    report_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    return out
