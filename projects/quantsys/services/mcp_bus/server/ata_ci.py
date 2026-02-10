from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class ATAEvidenceTriplet:
    report_path: Path
    selftest_log_path: Path
    evidence_dir: Path


class ATACIVerifier:
    def __init__(self, repo_root: Path):
        self.repo_root = repo_root
        self.guard_script = self.repo_root / "tools" / "ci" / "skill_call_guard.py"
        self.verdict_script = self.repo_root / "tools" / "ci" / "mvm-verdict.py"

    def verify_triplet(self, triplet: ATAEvidenceTriplet) -> dict[str, Any]:
        missing = []
        if not triplet.report_path.exists():
            missing.append(str(triplet.report_path))
        if not triplet.selftest_log_path.exists():
            missing.append(str(triplet.selftest_log_path))
        if not triplet.evidence_dir.exists():
            missing.append(str(triplet.evidence_dir))
        return {"success": not missing, "missing": missing}

    def run_guard(
        self,
        report_path: Path,
        selftest_log_path: Path,
        evidence_dir: Path,
        task_code: str,
        area: str,
    ) -> dict[str, Any]:
        if not self.guard_script.exists():
            return {"success": False, "error": "skill_call_guard.py not found"}
        cmd = [
            sys.executable,
            str(self.guard_script),
            "--taskcode",
            task_code,
            "--area",
            area,
        ]
        result = subprocess.run(cmd, cwd=str(self.repo_root), capture_output=True, text=True)
        return {
            "success": result.returncode == 0,
            "exit_code": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
        }

    def run_verdict(self) -> dict[str, Any]:
        if not self.verdict_script.exists():
            return {"success": False, "error": "mvm-verdict.py not found"}
        cmd = [sys.executable, str(self.verdict_script), "--case", "basic"]
        result = subprocess.run(cmd, cwd=str(self.repo_root), capture_output=True, text=True)
        verdict_path = self.repo_root / "mvm" / "verdict" / "verdict.json"
        verdict_data = None
        if verdict_path.exists():
            try:
                verdict_data = json.loads(verdict_path.read_text(encoding="utf-8"))
            except Exception:
                verdict_data = None
        return {
            "success": result.returncode == 0,
            "exit_code": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "verdict_path": str(verdict_path.relative_to(self.repo_root)) if verdict_path.exists() else None,
            "verdict": verdict_data,
        }
