from __future__ import annotations

import argparse
import json
import os
import random
import socket
import threading
import time
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from http.client import HTTPConnection, HTTPSConnection, HTTPResponse
from pathlib import Path
from typing import Any, Callable, Iterable, Literal
from urllib.parse import urlparse


HttpMethod = Literal["GET", "POST"]


@dataclass(frozen=True)
class EndpointSpec:
    name: str
    method: HttpMethod
    path: str
    weight: float
    json_body_factory: Callable[[], dict[str, Any]] | None = None


def _find_repo_root(start: Path) -> Path:
    cur = start.resolve()
    for p in [cur, *cur.parents]:
        if (p / ".git").exists():
            return p
    return start.resolve()


def _now_iso_utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _safe_percentile_ms(values_ms: list[float], p: float) -> float | None:
    if not values_ms:
        return None
    if p <= 0:
        return min(values_ms)
    if p >= 100:
        return max(values_ms)
    xs = sorted(values_ms)
    # Nearest-rank (inclusive) percentile
    k = int((p / 100.0) * len(xs) + 0.999999999)
    k = max(1, min(len(xs), k))
    return xs[k - 1]


def _join_base_path(base_path: str, endpoint_path: str) -> str:
    bp = (base_path or "").rstrip("/")
    ep = endpoint_path if endpoint_path.startswith("/") else f"/{endpoint_path}"
    return f"{bp}{ep}" if bp else ep


class _LeakyBucketRateLimiter:
    def __init__(self, *, qps: float | None):
        self._interval_s = (1.0 / qps) if (qps is not None and qps > 0) else None
        self._lock = threading.Lock()
        self._next_allowed = time.perf_counter()

    def acquire(self) -> None:
        if self._interval_s is None:
            return
        sleep_s = 0.0
        with self._lock:
            now = time.perf_counter()
            t = self._next_allowed if self._next_allowed > now else now
            self._next_allowed = t + self._interval_s
            sleep_s = t - now
        if sleep_s > 0:
            time.sleep(sleep_s)


class _EndpointChooser:
    def __init__(self, endpoints: list[EndpointSpec], *, seed: int):
        self._endpoints = endpoints
        self._weights = [max(0.0, float(e.weight)) for e in endpoints]
        self._rng = random.Random(seed)

    def pick(self) -> EndpointSpec:
        # random.choices is available in 3.6+
        return self._rng.choices(self._endpoints, weights=self._weights, k=1)[0]


class _HttpClient:
    def __init__(
        self,
        *,
        scheme: str,
        host: str,
        port: int | None,
        timeout_s: float,
        default_headers: dict[str, str],
    ):
        self._scheme = scheme
        self._host = host
        self._port = port
        self._timeout_s = float(timeout_s)
        self._default_headers = dict(default_headers)
        self._conn: HTTPConnection | HTTPSConnection | None = None

    def _new_conn(self) -> HTTPConnection | HTTPSConnection:
        if self._scheme == "https":
            return HTTPSConnection(self._host, self._port, timeout=self._timeout_s)
        return HTTPConnection(self._host, self._port, timeout=self._timeout_s)

    def _ensure_conn(self) -> HTTPConnection | HTTPSConnection:
        if self._conn is None:
            self._conn = self._new_conn()
        return self._conn

    def _reset_conn(self) -> None:
        try:
            if self._conn is not None:
                self._conn.close()
        finally:
            self._conn = None

    def request_json(
        self,
        *,
        method: HttpMethod,
        path: str,
        json_body: dict[str, Any] | None,
        extra_headers: dict[str, str] | None = None,
    ) -> tuple[int | None, float, int, str | None]:
        t0 = time.perf_counter()
        status: int | None = None
        nbytes = 0
        err: str | None = None
        body_bytes: bytes | None = None

        headers = dict(self._default_headers)
        if extra_headers:
            headers.update({k: v for k, v in extra_headers.items() if v is not None})

        if json_body is not None:
            body_bytes = json.dumps(json_body, ensure_ascii=False).encode("utf-8")
            headers.setdefault("content-type", "application/json")
        else:
            body_bytes = None

        try:
            conn = self._ensure_conn()
            conn.request(method, path, body=body_bytes, headers=headers)
            resp: HTTPResponse = conn.getresponse()
            status = int(resp.status)
            # Drain response to keep connection reusable (cap to 2MB).
            chunk = resp.read(2_000_000)
            nbytes = len(chunk) if chunk is not None else 0
        except (socket.timeout, TimeoutError):
            err = "timeout"
            self._reset_conn()
        except Exception as e:
            err = f"{type(e).__name__}"
            self._reset_conn()
        dt = time.perf_counter() - t0
        return status, dt, nbytes, err


def _build_payloads(*, repo_path: str, run_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
    goal = f"SCC HTTP stress harness ({run_id})"

    base_req = {
        "task": {
            "goal": goal,
            "commands_hint": [],
            "success_criteria": [],
            "stop_condition": [],
            "scope_allow": [],
            "artifacts_expectation": [],
        },
        "workspace": {
            "repo_path": repo_path,
            "bootstrap_cmds": [],
            "test_cmds": [],
            "artifact_paths": [],
        },
        "timeout_s": 30,
    }
    plan_payload = dict(base_req)
    orchestrate_payload = {
        "orchestrator": {"profile": "plan"},
        **base_req,
    }
    return plan_payload, orchestrate_payload


def _render_report_md(report: dict[str, Any]) -> str:
    meta = report.get("meta") or {}
    endpoints = report.get("endpoints") or {}
    status_codes = meta.get("status_codes") or {}

    lines: list[str] = []
    lines.append("# SCC HTTP Stress Report")
    lines.append("")
    lines.append(f"- run_id: `{meta.get('run_id')}`")
    lines.append(f"- started_at_utc: `{meta.get('started_at_utc')}`")
    lines.append(f"- ended_at_utc: `{meta.get('ended_at_utc')}`")
    lines.append(f"- base_url: `{meta.get('base_url')}`")
    lines.append(f"- duration_s: `{meta.get('duration_s')}`")
    lines.append(f"- concurrency: `{meta.get('concurrency')}`")
    lines.append(f"- target_qps: `{meta.get('target_qps')}`")
    lines.append(f"- total_requests: `{meta.get('total_requests')}`")
    lines.append(f"- error_rate: `{meta.get('error_rate')}`")
    lines.append(f"- p50_ms: `{meta.get('p50_ms')}`")
    lines.append(f"- p95_ms: `{meta.get('p95_ms')}`")
    if status_codes:
        sc_str = ", ".join([f"{k}:{v}" for k, v in sorted(status_codes.items(), key=lambda kv: str(kv[0]))])
        lines.append(f"- status_codes: `{sc_str}`")
    lines.append("")

    top3 = (report.get("slowest_endpoints_top3") or [])[:3]
    if top3:
        lines.append("## Slowest endpoints (by p95)")
        for row in top3:
            p95 = row.get("p95_ms")
            p95_s = "n/a" if p95 is None else f"{p95}"
            lines.append(
                f"- `{row.get('name')}` p95={p95_s}ms total={row.get('total')} errors={row.get('errors')}"
            )
        lines.append("")

    lines.append("## Per-endpoint summary")
    lines.append("")
    lines.append("| endpoint | method | path | total | errors | error_rate | p50_ms | p95_ms | status_codes |")
    lines.append("|---|---:|---:|---:|---:|---:|---:|---:|---|")
    for name, row in endpoints.items():
        sc = row.get("status_codes") or {}
        sc_str = ", ".join([f"{k}:{v}" for k, v in sorted(sc.items(), key=lambda kv: str(kv[0]))])
        lines.append(
            "| {name} | {method} | `{path}` | {total} | {errors} | {er} | {p50} | {p95} | {sc} |".format(
                name=str(name),
                method=str(row.get("method") or ""),
                path=str(row.get("path") or ""),
                total=int(row.get("total") or 0),
                errors=int(row.get("errors") or 0),
                er=str(row.get("error_rate") or "0"),
                p50=str(row.get("p50_ms") if row.get("p50_ms") is not None else ""),
                p95=str(row.get("p95_ms") if row.get("p95_ms") is not None else ""),
                sc=sc_str,
            )
        )
    lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="SCC unified server HTTP stress harness (real requests).")
    ap.add_argument("--base-url", default=os.environ.get("SCC_BASE_URL") or "http://127.0.0.1:18788")
    ap.add_argument("--duration-s", type=float, default=30.0)
    ap.add_argument("--concurrency", type=int, default=8)
    ap.add_argument("--profile", default="", help="Optional JSON profile file (endpoints/weights/duration/concurrency/qps).")
    ap.add_argument("--qps", type=float, default=None)
    ap.add_argument("--interval-ms", type=float, default=None)
    ap.add_argument("--admin-token", default=os.environ.get("SCC_ADMIN_TOKEN") or os.environ.get("UNIFIED_SERVER_ADMIN_TOKEN") or "")
    ap.add_argument("--repo-path", default="")
    ap.add_argument("--timeout-s", type=float, default=10.0)
    args = ap.parse_args(argv)

    profile = None
    if str(args.profile or "").strip():
        p = Path(str(args.profile)).expanduser()
        if not p.is_absolute():
            p = (_find_repo_root(Path.cwd()) / p).resolve()
        profile = json.loads(p.read_text(encoding="utf-8"))

    qps_arg = args.qps
    interval_ms_arg = args.interval_ms
    if profile:
        if profile.get("qps") is not None:
            qps_arg = float(profile.get("qps"))
            interval_ms_arg = None
        if profile.get("interval_ms") is not None:
            interval_ms_arg = float(profile.get("interval_ms"))
            qps_arg = None

    if qps_arg is not None and interval_ms_arg is not None:
        raise SystemExit("Provide only one: --qps OR --interval-ms (profile counts too)")
    target_qps: float | None = float(qps_arg) if qps_arg is not None else None
    if interval_ms_arg is not None:
        ms = float(interval_ms_arg)
        if ms <= 0:
            raise SystemExit("--interval-ms must be > 0")
        target_qps = 1000.0 / ms

    duration_s = float(profile.get("duration_s")) if profile and profile.get("duration_s") is not None else float(args.duration_s)
    if duration_s <= 0:
        raise SystemExit("--duration-s must be > 0")
    concurrency = int(profile.get("concurrency")) if profile and profile.get("concurrency") is not None else int(args.concurrency)
    if concurrency <= 0:
        raise SystemExit("--concurrency must be > 0")

    u = urlparse(str(args.base_url).strip())
    if u.scheme not in {"http", "https"}:
        raise SystemExit("--base-url must start with http:// or https://")
    if not u.hostname:
        raise SystemExit("--base-url must include a hostname")

    base_path = u.path or ""
    host = u.hostname
    port = u.port
    base_url_norm = f"{u.scheme}://{host}{(':' + str(port)) if port else ''}{base_path}".rstrip("/")

    repo_root = _find_repo_root(Path(args.repo_path).resolve() if args.repo_path else Path.cwd())
    repo_path = str(repo_root) if (args.repo_path or "").strip() == "" else str(Path(args.repo_path).resolve())

    run_id = f"{int(time.time() * 1000)}_{os.getpid()}"
    started_at_utc = _now_iso_utc()
    out_dir = (repo_root / "artifacts" / "scc_state" / "stress_runs" / run_id).resolve()
    out_dir.mkdir(parents=True, exist_ok=False)

    plan_payload, orch_payload = _build_payloads(repo_path=repo_path, run_id=run_id)

    def _body_factory(body_spec: dict[str, Any] | None) -> Callable[[], dict[str, Any]] | None:
        if not body_spec:
            return None
        kind = str(body_spec.get("type") or "").strip().lower()
        if kind in {"scc_task_plan", "plan"}:
            return lambda: plan_payload
        if kind in {"scc_task_orchestrate_plan", "orchestrate_plan", "orchestrate"}:
            return lambda: orch_payload
        raw = body_spec.get("json")
        if isinstance(raw, dict):
            return lambda: raw
        return None

    endpoints: list[EndpointSpec] = []
    profile_eps = (profile or {}).get("endpoints") if profile else None
    if isinstance(profile_eps, list) and profile_eps:
        for e in profile_eps:
            if not isinstance(e, dict):
                continue
            name = str(e.get("name") or "").strip() or "endpoint"
            method = str(e.get("method") or "GET").strip().upper()
            if method not in {"GET", "POST"}:
                continue
            path = str(e.get("path") or "").strip() or "/health/ready"
            weight = float(e.get("weight") or 0.0)
            body = e.get("body") if isinstance(e.get("body"), dict) else None
            endpoints.append(
                EndpointSpec(
                    name=name,
                    method=method,  # type: ignore[arg-type]
                    path=path,
                    weight=weight,
                    json_body_factory=_body_factory(body),
                )
            )

    if not endpoints:
        endpoints = [
            EndpointSpec(name="health_ready", method="GET", path="/health/ready", weight=0.25),
            EndpointSpec(name="executor_status", method="GET", path="/executor/status", weight=0.25),
            EndpointSpec(name="scc_system_metrics", method="GET", path="/scc/system/metrics", weight=0.25),
            EndpointSpec(
                name="scc_task_plan",
                method="POST",
                path="/scc/task/plan",
                weight=0.15,
                json_body_factory=lambda: plan_payload,
            ),
            EndpointSpec(
                name="scc_task_orchestrate_plan",
                method="POST",
                path="/scc/task/orchestrate",
                weight=0.10,
                json_body_factory=lambda: orch_payload,
            ),
        ]

    default_headers = {
        "accept": "application/json",
        "user-agent": "scc-stress-harness/0.1.0",
    }
    if str(args.admin_token).strip():
        default_headers["x-admin-token"] = str(args.admin_token).strip()

    limiter = _LeakyBucketRateLimiter(qps=target_qps)
    stop_at = time.perf_counter() + duration_s

    results_lock = threading.Lock()
    all_results: list[tuple[str, str, str, float, int | None, str | None]] = []
    # (endpoint_name, method, path, latency_ms, status, err)

    def worker(worker_id: int) -> None:
        chooser = _EndpointChooser(endpoints, seed=(int(time.time() * 1000) + worker_id * 9973))
        client = _HttpClient(
            scheme=u.scheme,
            host=host,
            port=port,
            timeout_s=float(args.timeout_s),
            default_headers=default_headers,
        )
        local: list[tuple[str, str, str, float, int | None, str | None]] = []
        while time.perf_counter() < stop_at:
            limiter.acquire()
            if time.perf_counter() >= stop_at:
                break
            spec = chooser.pick()
            full_path = _join_base_path(base_path, spec.path)
            body = spec.json_body_factory() if spec.json_body_factory else None
            status, dt_s, _nbytes, err = client.request_json(method=spec.method, path=full_path, json_body=body)
            local.append((spec.name, spec.method, spec.path, dt_s * 1000.0, status, err))
        with results_lock:
            all_results.extend(local)

    threads = [threading.Thread(target=worker, args=(i,), daemon=True) for i in range(concurrency)]
    t_start = time.perf_counter()
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    t_end = time.perf_counter()

    # Aggregate
    by_ep_latency: dict[str, list[float]] = defaultdict(list)
    by_ep_status: dict[str, Counter[str]] = defaultdict(Counter)
    overall_status: Counter[str] = Counter()
    all_latency_ms: list[float] = []
    by_ep_total: Counter[str] = Counter()
    by_ep_errors: Counter[str] = Counter()
    ep_meta: dict[str, tuple[str, str]] = {}

    total = 0
    errors = 0
    for name, method, path, latency_ms, status, err in all_results:
        total += 1
        by_ep_total[name] += 1
        ep_meta[name] = (method, path)
        latency_ms_f = float(latency_ms)
        all_latency_ms.append(latency_ms_f)
        by_ep_latency[name].append(latency_ms_f)
        if status is None:
            by_ep_status[name]["EXC"] += 1
            overall_status["EXC"] += 1
            by_ep_errors[name] += 1
            errors += 1
        else:
            by_ep_status[name][str(status)] += 1
            overall_status[str(status)] += 1
            if status >= 400:
                by_ep_errors[name] += 1
                errors += 1

    endpoints_report: dict[str, Any] = {}
    for ep in endpoints:
        name = ep.name
        method, path = ep.method, ep.path
        lat = by_ep_latency.get(name, [])
        total_n = int(by_ep_total.get(name, 0))
        err_n = int(by_ep_errors.get(name, 0))
        endpoints_report[name] = {
            "method": method,
            "path": path,
            "total": total_n,
            "errors": err_n,
            "error_rate": (err_n / total_n) if total_n else 0.0,
            "p50_ms": _safe_percentile_ms(lat, 50),
            "p95_ms": _safe_percentile_ms(lat, 95),
            "min_ms": min(lat) if lat else None,
            "max_ms": max(lat) if lat else None,
            "status_codes": dict(by_ep_status.get(name, {})),
        }

    slowest = []
    for name, row in endpoints_report.items():
        slowest.append(
            {
                "name": name,
                "p95_ms": row.get("p95_ms"),
                "total": row.get("total"),
                "errors": row.get("errors"),
            }
        )
    slowest.sort(key=lambda r: (r.get("p95_ms") is None, -(float(r.get("p95_ms") or 0.0))))

    report: dict[str, Any] = {
        "meta": {
            "run_id": run_id,
            "started_at_utc": started_at_utc,
            "ended_at_utc": _now_iso_utc(),
            "base_url": base_url_norm,
            "duration_s": duration_s,
            "wall_time_s": t_end - t_start,
            "concurrency": concurrency,
            "target_qps": target_qps,
            "timeout_s": float(args.timeout_s),
            "admin_token_present": bool(str(args.admin_token).strip()),
            "repo_path": repo_path,
            "total_requests": total,
            "errors": errors,
            "error_rate": (errors / total) if total else 0.0,
            "p50_ms": _safe_percentile_ms(all_latency_ms, 50),
            "p95_ms": _safe_percentile_ms(all_latency_ms, 95),
            "status_codes": dict(overall_status),
        },
        "endpoints": endpoints_report,
        "slowest_endpoints_top3": slowest[:3],
    }

    (out_dir / "report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    (out_dir / "report.md").write_text(_render_report_md(report), encoding="utf-8")

    print(f"[scc_stress] run_id={run_id}")
    print(f"[scc_stress] out_dir={out_dir}")
    print(f"[scc_stress] total={total} errors={errors} error_rate={(errors / total) if total else 0.0:.4f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
