---
oid: 01KGCV31F255AQQB7JQXKHWB05
layer: DOCOPS
primary_unit: V.OID_VALIDATOR
tags: [R.MANIFEST, N.EVENTS, S.CANONICAL_UPDATE]
status: active
---

# OID / ULID Spec (v0.1.0)

This document defines how SCC issues, embeds, validates, and migrates object identifiers (OIDs).

## 0. Normative summary
- OID is ULID.
- OIDs are minted ONLY by SCC OID Generator (single source of issuance).
- PostgreSQL is the authoritative registry (object_index).
- Key doc trees MUST embed OID inline.
- Moves/renames/classification changes MUST go through migrate.
- `oid_validator` runs in CI/verdict; failure blocks merge/push.
- PostgreSQL is source of truth; inline metadata must match.

## 1. Definitions
- OID: ULID identifying a durable object (file/doc/schema/report/artifact).
- Object: any durable asset tracked by SCC.
- Registry: authoritative mapping of OID ↔ object metadata in PostgreSQL.
- primary_unit: exactly one canonical unit token (mutually exclusive).
- tags: optional multi-select unit tokens.

## 2. Canonical ULID format
- 26-char Crockford Base32
- Uppercase only
- Allowed chars: 0-9 A-H J K M N P-T V-Z

Validation rules:
- length == 26
- charset valid
- uppercase only

## 3. Authoritative registry (PostgreSQL)
### 3.1 Tables (minimum)
#### objects
- oid TEXT PRIMARY KEY
- path TEXT NOT NULL                        -- repo_root relative for file objects
- kind TEXT NOT NULL                        -- md/json/ts/py/log/patch/...
- layer TEXT NOT NULL                       -- RAW|DERIVED|CANON|DIST|CODE|CONF|TOOL|REPORT
- primary_unit TEXT NOT NULL                -- must exist in Unit Registry
- tags TEXT[] NOT NULL DEFAULT '{}'::text[]
- status TEXT NOT NULL DEFAULT 'active'     -- active|moved|deprecated|tombstoned
- sha256 TEXT NULL
- derived_from TEXT[] NOT NULL DEFAULT '{}'::text[]
- replaced_by TEXT NULL
- created_at TIMESTAMPTZ NOT NULL DEFAULT now()
- updated_at TIMESTAMPTZ NOT NULL DEFAULT now()

Recommended indexes:
- UNIQUE(path) WHERE status='active'
- INDEX(primary_unit)
- GIN(tags)

#### oid_events
- event_id TEXT PRIMARY KEY                 -- ULID
- oid TEXT NOT NULL REFERENCES objects(oid)
- kind TEXT NOT NULL                        -- ISSUED|MIGRATED|COLLISION
- payload JSONB NOT NULL
- created_at TIMESTAMPTZ NOT NULL DEFAULT now()

### 3.2 Registry invariants
- oid is unique
- active path is unique for file objects
- move/rename updates path, oid unchanged
- migration always appends oid_events

## 4. SCC OID Generator (single source of issuance)
Agents MUST NOT generate ULIDs directly via ad-hoc libraries.

### 4.1 Canonical interface (HTTP is source of truth)
POST /scc/oid/new

Body (minimum):
- path: repo_root relative path
- kind: file type
- layer: one of RAW|DERIVED|CANON|DIST|CODE|CONF|TOOL|REPORT
- primary_unit: unit token from Unit Registry
- tags: optional array of unit tokens
- stable_key: optional idempotency key
- hint: optional

Example request:
{
  "path": "docs/CANONICAL/GOALS.md",
  "kind": "md",
  "layer": "CANON",
  "primary_unit": "G.GOAL_INPUT",
  "tags": ["S.CANONICAL_UPDATE"],
  "stable_key": "docs/CANONICAL/GOALS.md",
  "hint": "canonical goals doc"
}

Returns:
{ "oid": "<ULID>", "issued": true|false }

Rules:
- If stable_key is present and already issued, return existing oid (issued=false).
- Otherwise mint new ULID, insert objects record, append oid_events (ISSUED).

POST /scc/oid/migrate

Body:
- oid: the ULID to migrate
- patch: allowed changes (path, primary_unit, tags, layer, status)
- reason: human-readable reason
- actor: agent_id

Example request:
{
  "oid": "<ULID>",
  "patch": { "path": "docs/CANONICAL/GOALS.md" },
  "reason": "rename/move canonical goals file",
  "actor": "agent:docops"
}

Returns:
{ "oid": "<ULID>", "migrated": true }

Rules:
- oid never changes
- MUST append oid_events (MIGRATED) with from→to patch and reason/actor

### 4.2 CLI wrapper (recommended)
Provide `scc oid ...` commands that call the HTTP generator:
- scc oid new --path ... --kind ... --layer ... --primary-unit ... [--tags ...] [--stable-key ...] [--hint ...]
- scc oid migrate --oid ... --path ... [--primary-unit ...] [--tags ...] --reason ... --actor ...

## 5. Inline embedding (mandatory for key doc trees)
Mandatory embedding for:
- docs/ssot/**
- docs/DOCOPS/** (if present)
- docs/CANONICAL/**
- docs/ARCH/contracts/** (if present)

docs/REPORT/** is index-only in v0.1.0 (no inline requirement).

NOTE:
- docs/ARCH/** (outside docs/ARCH/contracts/**) is treated as legacy / demotion-in-progress in v0.1.0; do not enforce inline OID there until migrated into SSOT.

### 5.1 Markdown (YAML frontmatter) — required
At the top of the file:

---
oid: <ULID>
layer: <ARCH|DOCOPS|CANON|...>
primary_unit: <Stream.Unit>
tags: [<Stream.Unit>...]
status: active
---

### 5.2 JSON — required
Top-level fields:

{
  "oid": "<ULID>",
  "layer": "...",
  "primary_unit": "...",
  "tags": ["..."],
  "status": "active"
}

### 5.3 Code files — optional/incremental
Header comment block containing:
- oid: <ULID>
- primary_unit: <Stream.Unit>
- tags: ...

## 6. Unified Migration Protocol (mandatory)
### 6.1 When migrate is required
MUST use /scc/oid/migrate for:
- any file move/rename affecting path
- changing primary_unit
- changing tags
- changing layer/status

Direct edits to embedded metadata without migration are forbidden.

### 6.2 Split/Merge rules
Split:
- new objects get new oids via /new
- new objects MUST set derived_from=[old_oid]

Merge:
- one survivor oid remains active
- merged objects become deprecated/tombstoned and set replaced_by=survivor_oid

## 7. oid_validator (mandatory in CI/verdict)
Validator checks:
1) Mandatory trees have inline oid present.
2) Inline oid exists in PostgreSQL objects table.
3) PostgreSQL path matches file path for file objects.
4) Inline primary_unit/tags/layer/status match PostgreSQL record (PostgreSQL is authority).
5) primary_unit exists in Unit Registry.
6) No duplicate active paths.
7) Optional: sha256 match if enabled.

Outputs:
- report path
- exit code 0/1 (fail blocks)

## 8. CI gate integration
- Include oid_validator in selftest/verdict pipeline.
- Only green verdict may produce pass tag for server-side gate.
- Server-side pre-receive hook remains unchanged; oid enforcement happens inside verdict.

