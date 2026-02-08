# SCC HTTP Stress Harness (v0)

Real HTTP pressure test script for the unified server (no mocks).

## Usage

```powershell
python tools/scc/stress/run_http_stress.py `
  --base-url http://127.0.0.1:18788 `
  --duration-s 120 `
  --concurrency 12 `
  --qps 20
```

If your server requires admin auth, provide a token:

```powershell
$env:SCC_ADMIN_TOKEN = "..."
python tools/scc/stress/run_http_stress.py --base-url http://127.0.0.1:18788 --duration-s 60 --concurrency 8 --qps 10
```

## Outputs

Writes:

- `artifacts/scc_state/stress_runs/<run_id>/report.json`
- `artifacts/scc_state/stress_runs/<run_id>/report.md`

Reports include overall + per-endpoint `p50/p95`, error rate, and HTTP status code distribution.

