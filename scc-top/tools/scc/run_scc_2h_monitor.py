from __future__ import annotations

import json
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.error import URLError
from urllib.request import Request, urlopen


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _http_get_json(url: str, *, timeout_s: float = 2.5) -> Dict[str, Any]:
    req = Request(url, headers={"accept": "application/json"})
    with urlopen(req, timeout=timeout_s) as resp:  # noqa: S310
        data = resp.read().decode("utf-8", errors="replace")
        try:
            return json.loads(data or "{}")
        except Exception:
            return {"ok": False, "error": "invalid_json", "raw": data}


@dataclass
class MonitorConfig:
    base_url: str = "http://127.0.0.1:18788"
    duration_s: int = 2 * 60 * 60
    interval_s: int = 30
    out_dir: str = "artifacts/scc_runs/scc_2h_monitor"


def main() -> int:
    cfg = MonitorConfig()
    out_dir = Path(cfg.out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    meta_path = out_dir / "meta.json"
    log_path = out_dir / "monitor.jsonl"

    meta_path.write_text(
        json.dumps(
            {
                "started_at": _utc_now_iso(),
                "base_url": cfg.base_url,
                "duration_s": cfg.duration_s,
                "interval_s": cfg.interval_s,
                "paths": {
                    "health": "/health",
                    "quota": "/scc/codex/quota",
                    "models": "/scc/codex/models",
                },
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    start = time.time()
    n = 0
    while True:
        elapsed = time.time() - start
        if elapsed >= cfg.duration_s:
            break
        n += 1
        rec: Dict[str, Any] = {"ts_utc": _utc_now_iso(), "seq": n}
        try:
            rec["health"] = _http_get_json(cfg.base_url + "/health")
        except URLError as e:
            rec["health"] = {"ok": False, "error": str(e)}

        try:
            rec["quota"] = _http_get_json(cfg.base_url + "/scc/codex/quota")
        except URLError as e:
            rec["quota"] = {"ok": False, "error": str(e)}

        try:
            models = _http_get_json(cfg.base_url + "/scc/codex/models")
            # keep log light
            items = (models.get("data") or {}).get("models") or (models.get("data") or {}).get("items") or []
            rec["models"] = {
                "ok": bool(models.get("ok")),
                "count": len(items) if isinstance(items, list) else None,
            }
        except URLError as e:
            rec["models"] = {"ok": False, "error": str(e)}

        with log_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

        time.sleep(max(1, int(cfg.interval_s)))

    done = {
        "finished_at": _utc_now_iso(),
        "samples": n,
        "exit_code": 0,
    }
    (out_dir / "verdict.json").write_text(json.dumps(done, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

