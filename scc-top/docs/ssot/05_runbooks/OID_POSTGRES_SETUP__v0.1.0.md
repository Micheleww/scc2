---
oid: 01KGCW3SJ5N50FZM48E37A3KPX
layer: CANON
primary_unit: V.OID_VALIDATOR
tags: [X.WORKSPACE_ADAPTER, V.GUARD]
status: active
---

# OID Postgres Setup (v0.1.0)

Goal: make SCC OID registry (PostgreSQL `object_index`) available on the local host **without changing** the Unified Server port.

## 0. Rules (normative)
- Unified Server stays on its configured port (default `18788`).
- OID registry Postgres MAY run on a different local port (default for this repo: `18777`).
- Secrets MUST NOT be committed into the repo (no password in DSN / no `.env` checked in).
- Runtime secrets MUST be injected via process environment or OS secret store.

## 1. Start / Stop OID Postgres (local 18777)
- Start: `powershell -File tools/scc/ops/pg_oid_18777_start.ps1`
- Stop: `powershell -File tools/scc/ops/pg_oid_18777_stop.ps1`

Data dir: `artifacts/pg_oid/data_18777`  
Log file: `artifacts/pg_oid/pg_18777.log`

## 2. Environment injection (recommended)
Use DSN **without password**, and provide the password via `PGPASSWORD` (process env).

PowerShell (current session only):
- `\$env:SCC_OID_PG_DSN='postgresql://postgres@127.0.0.1:18777/scc_oid'`
- `\$env:PGPASSWORD='<YOUR_PASSWORD>'`

Persist DSN (user env) — safe because it contains no secret:
- `setx SCC_OID_PG_DSN "postgresql://postgres@127.0.0.1:18777/scc_oid"`

Do NOT persist `PGPASSWORD` in the repo. Prefer:
- per-session env injection (recommended), or
- Windows Credential Manager / service manager secret injection.

## 2.1 CI injection (GitHub Actions)
Secrets MUST be injected via CI secret store (never committed):
- `SCC_OID_PG_DSN` → exported as env `SCC_OID_PG_DSN`
- `SCC_OID_PG_PASSWORD` → exported as env `PGPASSWORD`

CI hard gate runs:
```bash
python tools/ci/run_phase4_checks.py --only oid-validator --area ci --taskcode OID_CI_WIRING_V010
```

## 3. Smoke checks (acceptance)
- Ensure schema exists: `python tools/scc/ops/oid_generator.py ensure-schema`
- Mint placeholders (writes registry + updates inline `oid`): `python tools/scc/ops/oid_mint_placeholders.py --apply`
- Validate (fail-closed): `powershell -File tools/scc/ops/oid_validator.ps1 -ReportDir docs/REPORT/<area>/artifacts/<TaskCode>`

