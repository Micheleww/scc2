from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from .ulid import ulid_new


def _normalize_pg_dsn(dsn: str) -> str:
    s = (dsn or "").strip()
    # SQLAlchemy-style URL -> psycopg2 URL
    if s.startswith("postgresql+psycopg2://"):
        s = "postgresql://" + s[len("postgresql+psycopg2://") :]
    return s


def get_oid_pg_dsn() -> str:
    dsn = (
        os.getenv("SCC_OID_PG_DSN")
        or os.getenv("SCC_OID_DATABASE_URL")
        or os.getenv("DATABASE_URL")
        or ""
    )
    return _normalize_pg_dsn(dsn)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class OidObject:
    oid: str
    path: str
    kind: str
    layer: str
    primary_unit: str
    tags: List[str]
    status: str
    sha256: Optional[str]
    derived_from: List[str]
    replaced_by: Optional[str]
    stable_key: Optional[str]
    hint: Optional[str]


class OidRegistryError(RuntimeError):
    pass


def _connect(dsn: str):
    try:
        import psycopg2  # type: ignore
    except Exception as e:  # pragma: no cover
        raise OidRegistryError(f"psycopg2_not_available: {e}") from e

    if not dsn:
        raise OidRegistryError("missing_pg_dsn: set SCC_OID_PG_DSN or DATABASE_URL")
    return psycopg2.connect(dsn)


def ensure_schema(*, dsn: str) -> None:
    conn = _connect(dsn)
    try:
        conn.autocommit = True
        cur = conn.cursor()
        cur.execute(
            """
CREATE TABLE IF NOT EXISTS objects (
  oid TEXT PRIMARY KEY,
  path TEXT NOT NULL,
  kind TEXT NOT NULL,
  layer TEXT NOT NULL,
  primary_unit TEXT NOT NULL,
  tags TEXT[] NOT NULL DEFAULT '{}'::text[],
  status TEXT NOT NULL DEFAULT 'active',
  sha256 TEXT NULL,
  derived_from TEXT[] NOT NULL DEFAULT '{}'::text[],
  replaced_by TEXT NULL,
  stable_key TEXT NULL,
  hint TEXT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
"""
        )
        cur.execute(
            """
CREATE TABLE IF NOT EXISTS oid_events (
  event_id TEXT PRIMARY KEY,
  oid TEXT NOT NULL REFERENCES objects(oid),
  kind TEXT NOT NULL,
  payload JSONB NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
"""
        )
        # Indexes / invariants
        try:
            cur.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS objects_active_path_uniq ON objects(path) WHERE status='active';"
            )
        except Exception:
            pass
        try:
            cur.execute("CREATE INDEX IF NOT EXISTS objects_primary_unit_idx ON objects(primary_unit);")
        except Exception:
            pass
        try:
            cur.execute("CREATE INDEX IF NOT EXISTS objects_tags_gin ON objects USING GIN(tags);")
        except Exception:
            pass
        try:
            cur.execute("CREATE UNIQUE INDEX IF NOT EXISTS objects_stable_key_uniq ON objects(stable_key) WHERE stable_key IS NOT NULL;")
        except Exception:
            pass
    finally:
        conn.close()


def _to_pg_path(path: str) -> str:
    return (path or "").replace("\\", "/").lstrip("./")


def get_by_oid(*, dsn: str, oid: str) -> Optional[OidObject]:
    conn = _connect(dsn)
    try:
        cur = conn.cursor()
        cur.execute(
            """
SELECT oid, path, kind, layer, primary_unit, tags, status, sha256, derived_from, replaced_by, stable_key, hint
FROM objects
WHERE oid = %s
""",
            (oid,),
        )
        row = cur.fetchone()
        if not row:
            return None
        return OidObject(
            oid=row[0],
            path=row[1],
            kind=row[2],
            layer=row[3],
            primary_unit=row[4],
            tags=list(row[5] or []),
            status=row[6],
            sha256=row[7],
            derived_from=list(row[8] or []),
            replaced_by=row[9],
            stable_key=row[10],
            hint=row[11],
        )
    finally:
        conn.close()


def issue_new(
    *,
    dsn: str,
    path: str,
    kind: str,
    layer: str,
    primary_unit: str,
    tags: List[str],
    stable_key: Optional[str] = None,
    hint: Optional[str] = None,
) -> Tuple[str, bool]:
    """
    Returns (oid, issued). If stable_key exists, returns existing oid with issued=False.
    """
    ensure_schema(dsn=dsn)
    conn = _connect(dsn)
    try:
        conn.autocommit = False
        cur = conn.cursor()
        if stable_key:
            cur.execute("SELECT oid FROM objects WHERE stable_key=%s", (stable_key,))
            row = cur.fetchone()
            if row and row[0]:
                conn.commit()
                return str(row[0]), False

        oid = ulid_new()
        pg_path = _to_pg_path(path)

        try:
            cur.execute(
                """
INSERT INTO objects (oid, path, kind, layer, primary_unit, tags, status, stable_key, hint)
VALUES (%s, %s, %s, %s, %s, %s::text[], 'active', %s, %s)
""",
                (oid, pg_path, kind, layer, primary_unit, tags, stable_key, hint),
            )
        except Exception as e:
            conn.rollback()
            raise OidRegistryError(f"insert_failed: {e}") from e

        event_id = ulid_new()
        payload = {"ts": _utc_now(), "action": "ISSUED", "path": pg_path, "stable_key": stable_key, "hint": hint}
        cur.execute(
            "INSERT INTO oid_events (event_id, oid, kind, payload) VALUES (%s, %s, %s, %s::jsonb)",
            (event_id, oid, "ISSUED", json.dumps(payload, ensure_ascii=False)),
        )
        conn.commit()
        return oid, True
    finally:
        conn.close()


def migrate(
    *,
    dsn: str,
    oid: str,
    patch: Dict[str, Any],
    reason: str,
    actor: str,
) -> bool:
    ensure_schema(dsn=dsn)
    conn = _connect(dsn)
    try:
        conn.autocommit = False
        cur = conn.cursor()
        cur.execute(
            "SELECT path, kind, layer, primary_unit, tags, status, sha256, derived_from, replaced_by FROM objects WHERE oid=%s",
            (oid,),
        )
        row = cur.fetchone()
        if not row:
            conn.rollback()
            raise OidRegistryError("oid_not_found")
        before = {
            "path": row[0],
            "kind": row[1],
            "layer": row[2],
            "primary_unit": row[3],
            "tags": list(row[4] or []),
            "status": row[5],
            "sha256": row[6],
            "derived_from": list(row[7] or []),
            "replaced_by": row[8],
        }

        allowed_fields = {"path", "layer", "primary_unit", "tags", "status", "sha256", "derived_from", "replaced_by"}
        update_fields = {k: v for k, v in (patch or {}).items() if k in allowed_fields and v is not None}
        if "path" in update_fields:
            update_fields["path"] = _to_pg_path(str(update_fields["path"]))
        if "tags" in update_fields and not isinstance(update_fields["tags"], list):
            raise OidRegistryError("invalid_tags")
        if "derived_from" in update_fields and not isinstance(update_fields["derived_from"], list):
            raise OidRegistryError("invalid_derived_from")

        if not update_fields:
            conn.rollback()
            return False

        set_sql = []
        params: List[Any] = []
        for k, v in update_fields.items():
            if k in ("tags", "derived_from"):
                set_sql.append(f"{k} = %s::text[]")
            else:
                set_sql.append(f"{k} = %s")
            params.append(v)
        set_sql.append("updated_at = now()")
        params.append(oid)

        cur.execute(f"UPDATE objects SET {', '.join(set_sql)} WHERE oid=%s", tuple(params))

        after = dict(before)
        after.update(update_fields)
        event_id = ulid_new()
        payload = {
            "ts": _utc_now(),
            "action": "MIGRATED",
            "reason": reason,
            "actor": actor,
            "from": before,
            "to": after,
        }
        cur.execute(
            "INSERT INTO oid_events (event_id, oid, kind, payload) VALUES (%s, %s, %s, %s::jsonb)",
            (event_id, oid, "MIGRATED", json.dumps(payload, ensure_ascii=False)),
        )
        conn.commit()
        return True
    finally:
        conn.close()


def register_existing(
    *,
    dsn: str,
    oid: str,
    path: str,
    kind: str,
    layer: str,
    primary_unit: str,
    tags: List[str],
    status: str = "active",
    sha256: Optional[str] = None,
    derived_from: Optional[List[str]] = None,
    replaced_by: Optional[str] = None,
    hint: Optional[str] = None,
) -> str:
    """
    Bootstrap/sync helper: upsert an object with an already-assigned oid.

    Used to import inline-embedded OIDs into Postgres (so oid_validator can be fail-closed).
    Returns an action string: inserted|updated|noop.
    """
    ensure_schema(dsn=dsn)
    conn = _connect(dsn)
    try:
        conn.autocommit = False
        cur = conn.cursor()
        pg_path = _to_pg_path(path)
        cur.execute(
            "SELECT path, kind, layer, primary_unit, tags, status, sha256, derived_from, replaced_by FROM objects WHERE oid=%s",
            (oid,),
        )
        row = cur.fetchone()
        want = {
            "path": pg_path,
            "kind": kind,
            "layer": layer,
            "primary_unit": primary_unit,
            "tags": list(tags or []),
            "status": status or "active",
            "sha256": sha256,
            "derived_from": list(derived_from or []),
            "replaced_by": replaced_by,
        }

        action = "noop"
        if not row:
            try:
                cur.execute(
                    """
INSERT INTO objects (oid, path, kind, layer, primary_unit, tags, status, sha256, derived_from, replaced_by, hint)
VALUES (%s, %s, %s, %s, %s, %s::text[], %s, %s, %s::text[], %s, %s)
""",
                    (
                        oid,
                        want["path"],
                        want["kind"],
                        want["layer"],
                        want["primary_unit"],
                        want["tags"],
                        want["status"],
                        want["sha256"],
                        want["derived_from"],
                        want["replaced_by"],
                        hint,
                    ),
                )
            except Exception as e:
                conn.rollback()
                raise OidRegistryError(f"register_existing_insert_failed: {e}") from e
            action = "inserted"
            event_id = ulid_new()
            payload = {"ts": _utc_now(), "action": "IMPORTED", **want}
            cur.execute(
                "INSERT INTO oid_events (event_id, oid, kind, payload) VALUES (%s, %s, %s, %s::jsonb)",
                (event_id, oid, "IMPORTED", json.dumps(payload, ensure_ascii=False)),
            )
            conn.commit()
            return action

        before = {
            "path": row[0],
            "kind": row[1],
            "layer": row[2],
            "primary_unit": row[3],
            "tags": list(row[4] or []),
            "status": row[5],
            "sha256": row[6],
            "derived_from": list(row[7] or []),
            "replaced_by": row[8],
        }

        # Compute delta (do not touch stable_key).
        patch: Dict[str, Any] = {}
        for k in ("path", "kind", "layer", "primary_unit", "status", "sha256", "replaced_by"):
            if before.get(k) != want.get(k):
                patch[k] = want.get(k)
        if sorted(before.get("tags") or []) != sorted(want.get("tags") or []):
            patch["tags"] = want.get("tags") or []
        if sorted(before.get("derived_from") or []) != sorted(want.get("derived_from") or []):
            patch["derived_from"] = want.get("derived_from") or []

        if patch:
            set_sql = []
            params: List[Any] = []
            for k, v in patch.items():
                if k in ("tags", "derived_from"):
                    set_sql.append(f"{k} = %s::text[]")
                else:
                    set_sql.append(f"{k} = %s")
                params.append(v)
            set_sql.append("updated_at = now()")
            params.append(oid)
            cur.execute(f"UPDATE objects SET {', '.join(set_sql)} WHERE oid=%s", tuple(params))
            action = "updated"
            event_id = ulid_new()
            payload = {"ts": _utc_now(), "action": "SYNCED", "from": before, "to": {**before, **patch}}
            cur.execute(
                "INSERT INTO oid_events (event_id, oid, kind, payload) VALUES (%s, %s, %s, %s::jsonb)",
                (event_id, oid, "SYNCED", json.dumps(payload, ensure_ascii=False)),
            )
        conn.commit()
        return action
    finally:
        conn.close()
