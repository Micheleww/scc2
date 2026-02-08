#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Full-chain trace demo: CodexCLI as decomposer + executor (no side effects).

Requires:
- unified server running on 127.0.0.1:18788
- codex CLI installed and logged in (`codex login`)
"""

import os
import sys
from pathlib import Path


def main() -> int:
    os.environ["PYTHONIOENCODING"] = "utf-8"
    repo_root = Path(__file__).resolve().parent.parent.parent
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))

    from tools.scc.orchestrators.codexcli_trace_demo import run_codexcli_demo

    res = run_codexcli_demo(repo_root=repo_root, goal="Demo: inspect SCC patch pipeline and summarize what it does (read-only tools allowed, no edits).")
    try:
        from tools.scc.orchestrators.codexcli_behavior_report import generate_codexcli_behavior_report

        generate_codexcli_behavior_report(demo_dir=Path(res.evidence_dir))
    except Exception as e:
        print("WARN: behavior report failed:", e)

    print("CODEXCLI_FULLCHAIN_DEMO_OK" if res.ok else "CODEXCLI_FULLCHAIN_DEMO_FAIL", res.task_id, res.evidence_dir)
    return 0 if res.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
