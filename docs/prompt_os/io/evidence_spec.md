# PromptOS IO Layer — Evidence Specification

This document defines the **evidence artifacts** required to support reproducible, auditable task execution.

Evidence serves two purposes:

1. **Reproducibility**: another system (or human) can understand what changed and how it was validated.
2. **Adjudication**: the gateway can decide PASS/FAIL with minimal ambiguity.

---

## 1) Evidence Types

The following evidence items are standard.

- `patch.diff`: A git-style unified diff representing the repo change.
- `selftest.log`: Full log of self-tests executed (or the test plan if tests are deferred to gateway policy).
- `report.md`: Human-readable execution report (rationale, decisions, changed files).
- `submit.json`: Machine-readable submission object as defined in `schemas.md`.
- `screenshots/` (optional): Any screenshot evidence; only if relevant and allowed.

---

## 2) Evidence Directory Structure

Recommended structure (task-scoped directory):

```
artifacts/
├── report.md
├── selftest.log
├── evidence/
│   ├── patch.diff
│   ├── pre_state.json
│   └── post_state.json
├── patch.diff
└── submit.json
```

Notes:

- Keeping a copy of `patch.diff` at both `artifacts/patch.diff` and `artifacts/evidence/patch.diff` makes it easy for tools that expect either location.
- `pre_state.json` and `post_state.json` SHOULD capture minimal state needed to compare before/after (e.g., file list, sizes, hashes).

---

## 3) Evidence Retention Policy

Retention SHOULD balance auditability with storage cost.

Recommended baseline:

- Keep task evidence for **30 days** for routine tasks.
- Keep evidence for **90–180 days** for high-impact releases, security changes, or incident response.
- Allow **manual pinning** of evidence for long-term retention when required by compliance.

Deletion policy:

- Expired evidence MAY be deleted automatically.
- Deletion MUST preserve privacy constraints (e.g., redact secrets before long-term retention).

---

## 4) Evidence Validation Rules

The gateway (or a local preflight) SHOULD validate evidence using the rules below.

### `patch.diff`

- MUST be parseable as a unified diff.
- SHOULD include all repo changes reflected in `changed_files` and `new_files`.
- MUST NOT include changes outside pinned scope.

### `selftest.log`

- MUST be present.
- MUST include the exact commands intended/executed.
- MUST end with a terminal line like: `EXIT_CODE=<int>`.
- SHOULD include timestamps and working directory context.

### `report.md`

- MUST be present.
- MUST list: goal summary, key decisions, and changed/new files.
- SHOULD call out any deviations (e.g., tests deferred to gateway).

### `submit.json`

- MUST validate against the Task Output Schema in `schemas.md`.
- `changed_files` and `new_files` MUST match actual repo diff scope.
- `tests.commands` MUST be an array of strings; each string SHOULD be runnable by the gateway.

### `screenshots/` (optional)

- MUST contain only task-relevant images.
- MUST avoid secrets/credentials.

