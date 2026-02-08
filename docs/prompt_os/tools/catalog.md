# Tool Catalog

## Table of Contents

- [Overview](#overview)
- [Catalog](#catalog)
- [Per-Tool Usage Constraints](#per-tool-usage-constraints)

## Overview

This document lists the tools an agent may use, how they are categorized, and what operational constraints apply.

## Catalog

| Tool | Category | Description | Risk Level | Requires Auth |
|------|----------|-------------|------------|---------------|
| git | VCS | Version control operations (status/diff/commit/checkout). | LOW | No |
| rg (ripgrep) | Search | Fast text search across the repo. | LOW | No |
| node | Runtime | Execute JavaScript/TypeScript via Node.js. | MEDIUM | No |
| python | Runtime | Execute Python scripts and one-liners. | MEDIUM | No |
| pytest | Test | Run Python tests. | LOW | No |
| network | IO | Outbound network access (HTTP(S), downloads, API calls). | HIGH | Yes (role) |
| bash | Shell | Execute arbitrary shell commands. | HIGH | No |
| fs.read | File | Read files (subject to pins/allowlist). | LOW | No (via pins) |
| fs.write | File | Write files (subject to pins/allowlist). | MEDIUM | No (via pins) |
| fs.delete | File | Delete files/directories. | HIGH | Yes (explicit) |

## Per-Tool Usage Constraints

### git

- Allowed: `status`, `diff`, `log`, `blame`, `show`, `checkout` (read-only operations preferred).
- Restricted: history rewrites (`rebase`, `filter-repo`) require explicit approval.
- Never: force-push to protected branches.

### rg (ripgrep)

- Allowed: search within allowed paths.
- Avoid scanning secrets directories (e.g., `secrets/**`) even if present.

### node

- Allowed: deterministic scripts and local tooling.
- Restricted: running untrusted packages or `npm install` without approval.

### python

- Allowed: deterministic scripts and local validation.
- Restricted: network calls from Python unless `network` is explicitly authorized.

### pytest

- Allowed: run unit/integration tests.
- Prefer: targeted tests over full suite to reduce runtime.

### network

- Requires role authorization; treat as high-risk.
- Must: domain allowlist, request logging (method, host, path), and rate limiting.
- Never: send secrets, PII, or confidential content.

### bash

- High-risk due to arbitrary execution.
- Must: preflight plan describing what will be executed and why.
- Never: destructive commands (`rm -rf`, disk operations) without explicit approval.

### fs.read

- Must: obey pins/allowlist; default deny outside the allowlist.
- Prefer: smallest reads necessary (single file, narrow scope).

### fs.write

- Must: obey pins/allowlist; avoid bulk rewrites.
- Must: keep diffs minimal and focused.

### fs.delete

- Requires explicit human approval.
- Must: produce an audit record of deleted paths.
