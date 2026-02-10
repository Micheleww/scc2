#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import pathlib
import re
import subprocess
import sys
from datetime import datetime, timezone
from typing import Any, Dict, List


def _default_repo_root() -> str:
    # tools/scc/ops/*.py -> repo root is 3 levels up
    return str(pathlib.Path(__file__).resolve().parents[3])


def _read_text(path: pathlib.Path) -> str:
    return path.read_text(encoding="utf-8-sig")


def _write_json(path: pathlib.Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


from tools.scc.lib.utils import norm_rel


def _extract_files_from_patch(patch_text: str) -> List[str]:
    files: List[str] = []
    seen = set()
    # unified diff usually has lines: --- a/path, +++ b/path
    for ln in patch_text.splitlines():
        if ln.startswith("+++ "):
            m = re.match(r"^\+\+\+\s+(?:b/)?(.+)$", ln.strip())
            if not m:
                continue
            p = m.group(1).strip()
            if p == "/dev/null":
                continue
            rel = norm_rel(p)
            if rel and rel not in seen:
                seen.add(rel)
                files.append(rel)
    return files


def _is_git_repo(repo: pathlib.Path) -> bool:
    return (repo / ".git").exists()


def _run_git(repo: pathlib.Path, args: List[str]) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=str(repo), text=True, capture_output=True)

def _git_current_branch(repo: pathlib.Path) -> str | None:
    r = _run_git(repo, ["rev-parse", "--abbrev-ref", "HEAD"])
    if r.returncode != 0:
        return None
    b = (r.stdout or "").strip()
    return b or None


def _git_is_clean(repo: pathlib.Path) -> bool:
    r = _run_git(repo, ["status", "--porcelain"])
    if r.returncode != 0:
        return False
    return (r.stdout or "").strip() == ""


def main() -> int:
    ap = argparse.ArgumentParser(description="Create an offline PR bundle (patch+metadata) for a task.")
    ap.add_argument("--repo-root", default=_default_repo_root())
    ap.add_argument("--task-id", required=True)
    ap.add_argument("--patch", default="", help="Patch path (default: artifacts/<task_id>/ssot_update.patch)")
    ap.add_argument("--title", default="")
    ap.add_argument("--body", default="")
    ap.add_argument("--labels", default="", help="Comma-separated labels")
    ap.add_argument("--out", default="", help="Output pr_bundle.json (default: artifacts/<task_id>/pr_bundle.json)")
    ap.add_argument("--apply-git", action="store_true", help="If repo is a git repo, apply patch + commit on a new branch")
    ap.add_argument("--merge-to", default="", help="If set, merge branch into target (git repo only; uses --ff-only)")
    args = ap.parse_args()

    repo = pathlib.Path(args.repo_root).resolve()
    task_id = str(args.task_id).strip()
    if not task_id:
        print("FAIL: missing task_id", file=sys.stderr)
        return 2

    patch_rel = args.patch.strip() or f"artifacts/{task_id}/ssot_update.patch"
    patch_path = pathlib.Path(patch_rel)
    if not patch_path.is_absolute():
        patch_path = (repo / patch_path).resolve()
    if not patch_path.exists():
        print(f"FAIL: missing patch: {patch_path.as_posix()}", file=sys.stderr)
        return 2

    patch_text = _read_text(patch_path)
    files = _extract_files_from_patch(patch_text)
    title = args.title.strip() or f"Auto patch bundle: {task_id}"
    body = args.body or ""
    labels = [x.strip() for x in (args.labels or "").split(",") if x.strip()]

    out_rel = args.out.strip() or f"artifacts/{task_id}/pr_bundle.json"
    out_path = pathlib.Path(out_rel)
    if not out_path.is_absolute():
        out_path = (repo / out_path).resolve()

    bundle: Dict[str, Any] = {
        "schema_version": "scc.pr_bundle.v1",
        "task_id": task_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "title": title,
        "body": body,
        "patch_path": norm_rel(str(patch_path.relative_to(repo))) if patch_path.is_relative_to(repo) else patch_path.as_posix(),
        "files": files,
        "labels": labels,
        "source": {"kind": "patch", "patch_bytes": len(patch_text.encode("utf-8"))},
        "git": {"applied": False, "branch": None, "commit": None, "notes": "Not applied."},
        "notes": "Offline PR bundle. Apply patch via git/apply or editor, then open PR in your VCS.",
    }

    merge_to = str(args.merge_to or "").strip()
    if merge_to and not args.apply_git:
        # merge implies apply+commit first
        args.apply_git = True

    git_errors: List[str] = []

    if args.apply_git:
        if not _is_git_repo(repo):
            bundle["git"] = {"applied": False, "error": "not_a_git_repo"}
            git_errors.append("not_a_git_repo")
        else:
            if not _git_is_clean(repo):
                bundle["git"] = {"applied": False, "error": "git_worktree_dirty"}
                git_errors.append("git_worktree_dirty")
                _write_json(out_path, bundle)
                print(
                    json.dumps(
                        {"ok": False, "task_id": task_id, "error": "git_worktree_dirty", "bundle": norm_rel(str(out_path.relative_to(repo)))},
                        ensure_ascii=False,
                    )
                )
                return 3

            starting_branch = _git_current_branch(repo)
            branch = f"scc/{task_id}"
            r1 = _run_git(repo, ["checkout", "-b", branch])
            if r1.returncode != 0:
                bundle["git"] = {"applied": False, "error": "git_checkout_failed", "stderr": r1.stderr}
                git_errors.append("git_checkout_failed")
            else:
                r2 = _run_git(repo, ["apply", "--whitespace=nowarn", norm_rel(str(patch_path.relative_to(repo)))])
                if r2.returncode != 0:
                    bundle["git"] = {"applied": False, "error": "git_apply_failed", "stderr": r2.stderr}
                    git_errors.append("git_apply_failed")
                else:
                    _run_git(repo, ["add", "-A"])
                    r3 = _run_git(repo, ["commit", "-m", title])
                    if r3.returncode != 0:
                        bundle["git"] = {"applied": False, "error": "git_commit_failed", "stderr": r3.stderr}
                        git_errors.append("git_commit_failed")
                    else:
                        # best-effort commit hash
                        r4 = _run_git(repo, ["rev-parse", "HEAD"])
                        commit = r4.stdout.strip() if r4.returncode == 0 else None
                        git_info: Dict[str, Any] = {"applied": True, "branch": branch, "commit": commit, "notes": "Patch applied and committed locally."}

                        if merge_to:
                            r5 = _run_git(repo, ["checkout", merge_to])
                            if r5.returncode != 0:
                                git_info["merged"] = False
                                git_info["merge_to"] = merge_to
                                git_info["error"] = "git_checkout_merge_target_failed"
                                git_info["stderr"] = r5.stderr
                                git_errors.append("git_checkout_merge_target_failed")
                            else:
                                r6 = _run_git(repo, ["merge", "--ff-only", branch])
                                if r6.returncode != 0:
                                    git_info["merged"] = False
                                    git_info["merge_to"] = merge_to
                                    git_info["error"] = "git_merge_failed"
                                    git_info["stderr"] = r6.stderr
                                    git_errors.append("git_merge_failed")
                                else:
                                    # After ff-only, HEAD is the same commit.
                                    r7 = _run_git(repo, ["rev-parse", "HEAD"])
                                    merged_commit = r7.stdout.strip() if r7.returncode == 0 else commit
                                    git_info["merged"] = True
                                    git_info["merge_to"] = merge_to
                                    git_info["merged_commit"] = merged_commit

                        bundle["git"] = git_info

            # best-effort: restore starting branch if merge was requested (or even if not)
            if starting_branch and starting_branch not in {"(unknown)", "HEAD"}:
                _run_git(repo, ["checkout", starting_branch])

    _write_json(out_path, bundle)
    print(json.dumps({"ok": True, "task_id": task_id, "bundle": norm_rel(str(out_path.relative_to(repo))) if out_path.is_relative_to(repo) else out_path.as_posix()}, ensure_ascii=False))
    return 0 if not git_errors else 4


if __name__ == "__main__":
    raise SystemExit(main())
