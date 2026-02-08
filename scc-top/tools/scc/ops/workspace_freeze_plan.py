from __future__ import annotations

import argparse
import os
import subprocess
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _run_git(root: Path, args: list[str]) -> str:
    p = subprocess.run(  # noqa: S603
        ["git", *args],
        cwd=str(root),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    return p.stdout


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _top(path: str) -> str:
    p = path.replace("\\", "/").lstrip("/")
    return p.split("/", 1)[0] if p else ""


def _group_for(path: str) -> str:
    p = path.replace("\\", "/")
    if p.startswith("docs/"):
        return "docs"
    if p.startswith("configs/") or p.startswith("config/"):
        return "configs"
    if p.startswith("tools/scc/") or p.startswith("tools/unified_server/") or p.startswith("tools/validator/"):
        return "scc_core"
    if p.startswith(".github/") or p.startswith(".githooks/") or p in {".gitignore", ".dockerignore"}:
        return "repo_hygiene"
    if p.startswith("contracts/"):
        return "contracts"
    return "other"


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="Generate a workspace freeze (commit-splitting) plan for staged changes.")
    ap.add_argument("--apply", action="store_true", help="Not implemented; this tool is plan-only.")
    args = ap.parse_args(argv)
    if args.apply:
        raise SystemExit("--apply is not supported (plan-only)")

    root = _repo_root()
    reports = root / "artifacts" / "scc_state" / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    ts = _utc_now().strftime("%Y%m%d_%H%M%S")
    out = reports / f"workspace_freeze_plan_{ts}.md"

    porcelain = _run_git(root, ["status", "--porcelain=v1", "-uno"])
    staged = [line[3:] for line in porcelain.splitlines() if line[:2] in {"A ", "M ", "D ", "R ", "C ", "AM", "MM", "MD", "RM", "RA"}]

    group_counts = Counter(_group_for(p) for p in staged)
    top_counts = Counter(_top(p) for p in staged)

    lines: list[str] = []
    lines.append(f"# Workspace Freeze Plan ({ts})")
    lines.append("")
    lines.append("目标：把大量 staged changes 收敛为少量可回滚 commit，降低 AI 执行时的“状态不确定性”。")
    lines.append("")
    lines.append(f"- staged_files: `{len(staged)}`")
    lines.append("")
    lines.append("## 分组统计（按功能域）")
    for k, v in group_counts.most_common():
        lines.append(f"- {k}: `{v}`")
    lines.append("")
    lines.append("## 分组统计（按顶层目录）")
    for k, v in top_counts.most_common(20):
        lines.append(f"- {k or '(root)'}: `{v}`")
    lines.append("")
    lines.append("## 推荐封板方式（按组拆 commit）")
    lines.append("")
    lines.append("说明：本计划不自动执行，以避免误操作；你可以逐条复制执行。")
    lines.append("")
    lines.append("1) 先清空 staged（不丢工作区修改）：")
    lines.append("```bash")
    lines.append("git restore --staged .")
    lines.append("```")
    lines.append("")

    groups_order = ["scc_core", "docs", "repo_hygiene", "configs", "contracts", "other"]
    for g in groups_order:
        files = [p for p in staged if _group_for(p) == g]
        if not files:
            continue
        lines.append(f"2) Commit: `{g}`（{len(files)} files）")
        lines.append("```bash")
        if g == "scc_core":
            lines.append("git add tools/scc tools/unified_server tools/validator")
            lines.append("git commit -m \"SCC: core ops + endpoints\"")
        elif g == "docs":
            lines.append("git add docs")
            lines.append("git commit -m \"Docs: navigation + ops\"")
        elif g == "repo_hygiene":
            lines.append("git add .github .githooks .gitignore .dockerignore")
            lines.append("git commit -m \"Repo: hygiene + governance\"")
        elif g == "configs":
            lines.append("git add configs config")
            lines.append("git commit -m \"Configs: normalize defaults\"")
        elif g == "contracts":
            lines.append("git add contracts")
            lines.append("git commit -m \"Contracts: update schemas\"")
        else:
            lines.append("# WARNING: other is large; consider splitting further by top-level dirs.")
            lines.append("git add <paths...>")
            lines.append("git commit -m \"WIP: other\"")
        lines.append("```")
        lines.append("")

    lines.append("## 注意事项")
    lines.append("")
    lines.append("- Windows 特殊设备文件 `NUL` 会导致 `git add .` 失败；避免使用 blanket add，按目录 add。")
    lines.append("- 如果要把隔离区/产物也提交，请先明确目的（建议默认不提交）。")

    _write(out, "\n".join(lines))
    print(f"[workspace_freeze_plan] report_md={out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

