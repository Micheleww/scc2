from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _http_json(*, method: str, url: str, token: str | None, body: dict | None = None) -> dict:
    data = None
    headers = {"accept": "application/json"}
    if token:
        headers["x-admin-token"] = token
    if body is not None:
        raw = json.dumps(body, ensure_ascii=False).encode("utf-8")
        headers["content-type"] = "application/json"
        data = raw
    req = Request(url=url, method=method.upper(), headers=headers, data=data)
    with urlopen(req, timeout=20) as resp:  # noqa: S310
        txt = resp.read().decode("utf-8", errors="replace")
        return json.loads(txt)


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="Export all WebGPT archived conversations to docs/INPUTS/WEBGPT/*.md")
    ap.add_argument("--base-url", default=os.environ.get("SCC_BASE_URL") or "http://127.0.0.1:18788")
    ap.add_argument("--admin-token", default=os.environ.get("UNIFIED_SERVER_ADMIN_TOKEN") or "")
    ap.add_argument("--limit", type=int, default=200)
    args = ap.parse_args(argv)

    base = str(args.base_url).rstrip("/")
    token = str(args.admin_token).strip() or None

    root = _repo_root()
    reports = root / "artifacts" / "scc_state" / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    ts = _utc_now().strftime("%Y%m%d_%H%M%S")
    report_md = reports / f"webgpt_export_all_{ts}.md"

    lines: list[str] = []
    lines.append(f"# WebGPT Export All ({ts})")
    lines.append("")
    lines.append(f"- base_url: `{base}`")
    lines.append(f"- limit: `{int(args.limit)}`")
    lines.append("")

    try:
        listing = _http_json(method="GET", url=f"{base}/scc/webgpt/list?limit={int(args.limit)}", token=token)
    except (HTTPError, URLError, TimeoutError) as e:
        lines.append(f"- ERROR: list failed: `{type(e).__name__}: {e}`")
        report_md.write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(f"[webgpt_export_all] report_md={report_md}")
        return 2

    convs = listing.get("conversations") or []
    if not isinstance(convs, list):
        convs = []

    lines.append(f"- conversations: `{len(convs)}`")
    lines.append("")

    ok = 0
    fail = 0
    for c in convs:
        if not isinstance(c, dict):
            continue
        cid = str(c.get("conversation_id") or "").strip()
        title = str(c.get("title") or "").strip()
        if not cid:
            continue
        try:
            out = _http_json(method="POST", url=f"{base}/scc/webgpt/export", token=token, body={"conversation_id": cid})
            if out.get("ok") is True:
                ok += 1
                lines.append(f"- OK `{cid}` → `{out.get('doc_path')}` ({title})")
            else:
                fail += 1
                lines.append(f"- FAIL `{cid}` ({title}) err=`{out.get('error')}`")
        except Exception as e:
            fail += 1
            lines.append(f"- FAIL `{cid}` ({title}) err=`{type(e).__name__}: {e}`")

    lines.append("")
    lines.append(f"- exported_ok: `{ok}`")
    lines.append(f"- exported_fail: `{fail}`")
    report_md.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"[webgpt_export_all] ok={ok} fail={fail} conversations={len(convs)}")
    print(f"[webgpt_export_all] report_md={report_md}")
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

