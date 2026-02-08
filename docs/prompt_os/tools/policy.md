# Tool Usage Policy

## Table of Contents

- [Overview](#overview)
- [1. Default Deny](#1-default-deny)
- [2. Explicit Deny Override](#2-explicit-deny-override)
- [3. Risk-based Approval](#3-risk-based-approval)
- [4. Audit Trail](#4-audit-trail)
- [Operational Notes](#operational-notes)

## Overview

This policy defines how an agent decides whether a tool may be used, based on role policy, explicit denies, and risk level.

## 1. Default Deny

- If a tool is **not** listed in `role.policy.tools.allow`, it is **forbidden**.
- “Not listed” includes unknown tools, aliases, or tools whose names do not match exactly.
- When uncertain, the agent must stop and request clarification or updated policy.

## 2. Explicit Deny Override

- Tools listed in `role.policy.tools.deny` are **absolutely forbidden**.
- Deny overrides allow: if a tool is in both `allow` and `deny`, the effective decision is **deny**.

## 3. Risk-based Approval

Risk level controls the required gating before a tool call.

### LOW (Auto-allow)

- Allowed when present in `allow` and not present in `deny`.
- Minimal preflight: confirm scope and target paths.

### MEDIUM (Preflight required)

- Requires a preflight checklist to pass before execution.
- Preflight must include:
  - Intent: what the command will do.
  - Scope: which files/paths are impacted.
  - Safety: why it is not destructive and how to roll back.
  - Determinism: no hidden downloads or remote code execution.

### HIGH (Human approval or special role)

- Requires explicit human approval **or** a privileged role with documented authorization.
- Must include an execution plan and an audit record.
- Must be narrowly scoped; broad or destructive operations are not allowed by default.

## 4. Audit Trail

- Every tool invocation must be recorded as evidence.
- The audit record should include:
  - Timestamp
  - Tool name and risk level
  - Parameters (redacted as needed)
  - Result (success/failure)
  - Files changed (if any)

## Operational Notes

- Prefer the least-privileged tool that can accomplish the goal.
- Never exfiltrate secrets/PII via `network` or logs.
- For filesystem tools, pins/allowlists are enforcement boundaries; they are not “recommendations”.
