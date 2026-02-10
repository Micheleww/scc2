import argparse
import json
import pathlib
import sys
import urllib.error
import urllib.request


def _post_json(url: str, payload: dict) -> dict:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=20) as r:
        raw = r.read().decode("utf-8")
        return json.loads(raw) if raw else {}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--bundle", required=True, help="Path to artifacts/<task_id>/replay_bundle.json")
    ap.add_argument("--base", default="http://127.0.0.1:18788", help="Gateway base URL")
    ap.add_argument("--dispatch", action="store_true", help="Dispatch immediately after creating task")
    args = ap.parse_args()

    bundle_path = pathlib.Path(args.bundle)
    if not bundle_path.exists():
        print(f"missing bundle: {bundle_path}", file=sys.stderr)
        return 2

    try:
        bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"bad json: {e}", file=sys.stderr)
        return 2

    payload = bundle.get("board_task_payload")
    if not isinstance(payload, dict) or not payload:
        print("bundle missing board_task_payload", file=sys.stderr)
        return 2

    try:
        created = _post_json(f"{args.base}/board/tasks", payload)
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        print(f"create task failed: {e.code} {body}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"create task error: {e}", file=sys.stderr)
        return 1

    new_id = created.get("id")
    if not new_id:
        print(f"create task returned unexpected response: {created}", file=sys.stderr)
        return 1

    print(json.dumps({"created_task_id": new_id}, ensure_ascii=False))
    if not args.dispatch:
        return 0

    try:
        out = _post_json(f"{args.base}/board/tasks/{new_id}/dispatch", {})
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        print(f"dispatch failed: {e.code} {body}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"dispatch error: {e}", file=sys.stderr)
        return 1

    print(json.dumps({"dispatch": out}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

