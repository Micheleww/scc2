---
oid: 01KGCV31SY172FN22A81WSMR13
layer: CANON
primary_unit: D.TASKTREE
tags: [K.CONTRACT_DOC, N.BIND_TASK_ID]
status: active
---

# Task Model & Codes (v0.1.0)

## 0. Purpose
Make every task machine-locatable and auditable.

## 1. Hierarchy (mandatory)
- EPIC: long-lived theme
- CAPABILITY: deliverable capability package
- COMPONENT/JOB: system module or repeatable job
- TASK: atomic executable work item

## 2. task_id rules (mandatory)

### 2.1 Generation & stability
- `task_id` MUST be stable for the same intent across retries.
- `task_id` MUST be mintable idempotently from a stable key (source + stable_key).

### 2.2 Cross-intake binding (minimum)
Bind across sources by stable keys:
- Web chat: `(conversation_id, message_id)` or a stable hash of the quoted directive.
- codexcli: `(run_id, workspace_root, contract_ref)` when applicable.
- vscode: `(session_id, workspace_root, contract_ref)` when applicable.

If multiple sources refer to the same intent, they MUST resolve to one `task_id` (dedup/bind), not multiple parallel tasks.

## 3. Required identifiers (mandatory)
- task_id: unique
- contract_ref: link/path/oid to contract
- touched_oids: list of object oids modified/created
- evidence_oids: list of evidence oids produced/used

## 4. Atomic vs Chain
- Atomic TASK MUST map to exactly one executable unit (one contract).
- Chain groups multiple atomic tasks with dependencies.

## 5. Storage & reference (minimum)
- EPIC/CAPABILITY/TASK tree MUST be materialized as a canonical file (Task Tree).
- `contract_ref` MUST point to a materialized contract file (placeholder allowed) and be reachable from SSOT registry.

## 6. State machine & minimum events

### 6.1 Minimal status model
queued → started → produced → verified(pass|fail) → done | dlq

### 6.2 Minimum event kinds (non-exhaustive)
- TASK_QUEUED
- TASK_STARTED
- TASK_PRODUCED (diff/log produced)
- TASK_VERIFIED (verdict recorded)
- TASK_DONE
- TASK_DLQ (dead-lettered)

### 6.3 Required event fields (minimum)
- task_id
- source (web_chat|codexcli|vscode|system)
- contract_ref
- touched_oids[]
- evidence_oids[]
- verdict (pass|fail) and optional fail_class
- timestamp (ISO8601)

## 7. Completion backfill (mandatory)
Every completed TASK MUST backfill:
- contract_ref
- touched_oids[]
- evidence_oids[]
- verdict (pass/fail, optional fail_class)

## 8. Changelog
- v0.1.0: initial
