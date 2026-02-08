---
oid: 01KGCV31G462QJYM5HBWGSSDN3
layer: DOCOPS
primary_unit: N.EVENTS
tags: [V.OID_VALIDATOR, S.NAV_UPDATE]
status: active
---

# Unit Registry (v0.1.0)

This registry defines the allowed values for `primary_unit` and `tags[]`.

## 0. Rules (normative)
- Every object MUST have exactly one `primary_unit` from this registry.
- Objects MAY have `tags[]` (multi-select) from this registry.
- Validator MUST fail if a referenced unit is not registered.
- Changes to this registry require a changelog entry and should be rare.

## 1. Naming convention
- Unit token format: <Stream>.<Unit>
- Stream: single uppercase letter
- Unit: uppercase with optional underscores

Examples:
- N.EVENTS
- D.TASKTREE
- V.VERDICT

## 2. Streams (canonical)
- G = Goal & Intake (human goal inputs and intake routing)
- R = Raw Capture (capture raw sources + manifests)
- N = Normalize (events normalization, binding, dedup)
- D = Derive Tasks (task tree derivation from raw)
- K = Contractize (contracts + acceptance definitions)
- X = Execute (dispatch + executors integration)
- V = Verify (tests + verdict + quality gates)
- P = Progress Review (periodic progress audits)
- S = Synthesize & Publish (canonical updates + distribution)
- F = Feedback (feedback package -> raw-b reintake)
- A = Agent Roles (routing/execution roles)
- C = Capability Catalog (capability inventory + mappings)
- W = Workspace (workspace invariants/specs)

## 3. Registered units (v0.1.0)

### G — Goal & Intake
- G.GOAL_INPUT          -- interpret new human goals from web chat raw
- G.INTAKE_ROUTING      -- route incoming items to derive/contract/dispatch

### R — Raw Capture
- R.CHAT_WEB            -- web chat capture (raw-a)
- R.CODEXCLI_RUN        -- codexcli run capture (transcript/diff/log)
- R.VSCODE_SESSION      -- vscode codex session capture
- R.MANIFEST            -- manifest spec + hashing + metadata

### N — Normalize
- N.EVENTS              -- generate canonical events stream (jsonl or DB)
- N.DEDUP               -- message_id / event_id dedup
- N.BIND_TASK_ID        -- bind/assign task_id across sources

### D — Derive Tasks
- D.EXTRACT_GOALS       -- extract goals/constraints/acceptance from raw
- D.TASKTREE            -- produce epic/feature/task/subtask tree
- D.PRIORITIZE          -- produce priority queue suggestions

### K — Contractize
- K.CONTRACT_DOC        -- generate contract docs/json for tasks
- K.ACCEPTANCE          -- acceptance criteria + command hints
- K.SCHEMA              -- contract schema versioning

### X — Execute
- X.DISPATCH            -- dispatch contracts to executors/queues
- X.EXEC_CODEXCLI       -- executor integration: codexcli
- X.EXEC_VSCODE         -- executor integration: vscode codex
- X.WORKSPACE_ADAPTER   -- workspace bootstrap, paths, environment

### V — Verify
- V.TESTS               -- run tests/smoke/typecheck
- V.VERDICT             -- verdict evaluation + pass/fail classification
- V.OID_VALIDATOR       -- oid_validator gate
- V.GUARD               -- generic guard checks (fail-closed)
- V.SKILL_GUARD         -- skill call guard (taskcode/guard chain)

### A — Agent Roles
- A.ROUTER              -- routes tasks to roles deterministically
- A.PLANNER             -- produces plan/contract drafts only
- A.EXECUTOR            -- applies changes within allowlist + produces evidence
- A.VERIFIER            -- runs acceptance + emits verdict artifacts
- A.AUDITOR             -- audits invariants/evidence without editing
- A.SECRETARY           -- summarizes raw inputs into derived notes
- A.FACTORY_MANAGER     -- prioritizes/dispatches; does not directly execute changes

### C — Capability Catalog
- C.CAPABILITY          -- capability inventory and mapping

### W — Workspace
- W.WORKSPACE           -- workspace invariants/specs

### P — Progress Review
- P.TRIGGER             -- OR-trigger logic (30 tasks / 48h / milestone / anomaly)
- P.REPORT              -- progress report generation
- P.DELTA               -- compute delta-to-goal metrics

### S — Synthesize & Publish
- S.CANONICAL_UPDATE    -- apply patches to canonical docs
- S.NAV_UPDATE          -- update navigation/index pages
- S.ADR                 -- decisions/ADR updates

### F — Feedback
- F.FEEDBACK            -- feedback stream (raw-b) and re-intake routing
- F.FEEDBACK_PACKAGE    -- generate system feedback package
- F.REINTAKE            -- write raw-b feedback and re-derive tasks

## 4. Changelog
### v0.1.0
- Initial registry.

