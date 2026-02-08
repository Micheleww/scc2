---
oid: 01KGCV31H4K0W8TS2HEKQ09FH3
layer: CANON
primary_unit: G.GOAL_INPUT
tags: [S.CANONICAL_UPDATE, P.REPORT]
status: active
---

# Canonical Truth Set & Priority (v0.1.0)

## 0. Purpose
Define what is “current truth” and how conflicts are resolved.

## 1. Canonical Set (authoritative docs)
These are authoritative:
- GOALS: docs/CANONICAL/GOALS.md
- ROADMAP: docs/CANONICAL/ROADMAP.md
- CURRENT_STATE: docs/CANONICAL/CURRENT_STATE.md
- ADR (Decisions): docs/CANONICAL/ADR/index.md
- PROGRESS: docs/CANONICAL/PROGRESS.md

Non-authoritative by default:
- raw chat transcripts (inputs)
- execution logs/artifacts
- ad-hoc notes outside SSOT

## 2. Conflict priority
On conflict, apply priority:
1) Human Goal Input (web chat directives)
2) Contract backlog (approved contracts)
3) Self-driven improvements (only within contracts)

## 3. Evidence rule
Canonical claims MUST reference evidence paths (raw/artifacts) by oid or stable path.
Canonical MUST NOT embed large raw logs.

## 4. Changelog
- v0.1.0: initial
