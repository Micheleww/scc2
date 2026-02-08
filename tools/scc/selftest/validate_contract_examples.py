#!/usr/bin/env python
import json
import pathlib
import sys
from typing import Any


def _load_json(path: pathlib.Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _json_pointer_get(doc: Any, pointer: str) -> Any:
    if pointer in ("", "#", "/"):
        return doc
    if pointer.startswith("#"):
        pointer = pointer[1:]
    if pointer.startswith("/"):
        pointer = pointer[1:]
    cur = doc
    for part in pointer.split("/"):
        part = part.replace("~1", "/").replace("~0", "~")
        if isinstance(cur, dict):
            cur = cur.get(part)
        elif isinstance(cur, list):
            cur = cur[int(part)]
        else:
            return None
    return cur


def _resolve_ref(repo: pathlib.Path, ref: str, root_schema: dict) -> tuple[dict, dict]:
    if ref.startswith("#"):
        resolved = _json_pointer_get(root_schema, ref)
        if not isinstance(resolved, dict):
            return {}, root_schema
        return resolved, root_schema

    ref_path = pathlib.Path(ref)
    if not ref_path.is_absolute():
        ref_path = repo / ref_path
    loaded = _load_json(ref_path)
    return loaded, loaded


def _is_type(value: Any, schema_type: str) -> bool:
    if schema_type == "object":
        return isinstance(value, dict)
    if schema_type == "array":
        return isinstance(value, list)
    if schema_type == "string":
        return isinstance(value, str)
    if schema_type == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if schema_type == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if schema_type == "boolean":
        return isinstance(value, bool)
    if schema_type == "null":
        return value is None
    return True  # unknown -> skip


def _validate(repo: pathlib.Path, data: Any, schema: dict, ctx: str, root_schema: dict | None = None) -> list[str]:
    errors: list[str] = []

    if root_schema is None:
        root_schema = schema

    if "$ref" in schema:
        resolved, new_root = _resolve_ref(repo, schema["$ref"], root_schema)
        return _validate(repo, data, resolved, ctx, new_root)

    if "const" in schema and data != schema["const"]:
        errors.append(f"{ctx}: const mismatch (expected {schema['const']})")
        return errors

    if "enum" in schema and data not in schema["enum"]:
        errors.append(f"{ctx}: enum mismatch (got {data})")
        return errors

    st = schema.get("type")
    if isinstance(st, list):
        if not any(_is_type(data, t) for t in st):
            errors.append(f"{ctx}: type mismatch (expected one of {st})")
            return errors
    elif isinstance(st, str):
        if not _is_type(data, st):
            errors.append(f"{ctx}: type mismatch (expected {st})")
            return errors

    if schema.get("type") == "object" and isinstance(data, dict):
        required = schema.get("required") or []
        for k in required:
            if k not in data:
                errors.append(f"{ctx}: missing required key {k}")

        props = schema.get("properties") or {}
        additional = schema.get("additionalProperties", True)
        for k, v in data.items():
            if k in props:
                errors += _validate(repo, v, props[k], f"{ctx}.{k}", root_schema)
            else:
                if additional is False:
                    errors.append(f"{ctx}: additionalProperties not allowed: {k}")
                elif isinstance(additional, dict):
                    errors += _validate(repo, v, additional, f"{ctx}.{k}", root_schema)

    if schema.get("type") == "array" and isinstance(data, list):
        items = schema.get("items")
        if isinstance(items, dict):
            for i, v in enumerate(data):
                errors += _validate(repo, v, items, f"{ctx}[{i}]", root_schema)

    return errors


def main() -> int:
    repo = pathlib.Path.cwd()
    pairs = [
        ("contracts/dlq/dlq.schema.json", "contracts/examples/dlq.example.json"),
        ("contracts/retry_plan/retry_plan.schema.json", "contracts/examples/retry_plan.example.json"),
        ("contracts/enablement/enablement.schema.json", "contracts/examples/enablement.example.json"),
        ("contracts/pattern/pattern.schema.json", "contracts/examples/pattern.example.json"),
        ("contracts/playbook/playbook.schema.json", "contracts/examples/playbook.example.json"),
        ("contracts/playbook/playbooks_registry.schema.json", "playbooks/registry.json"),
        ("contracts/eval/eval_manifest.schema.json", "contracts/examples/eval_manifest.example.json"),
        ("contracts/factory_policy/factory_policy.schema.json", "factory_policy.json"),
        ("contracts/eval/eval_manifest.schema.json", "eval/eval_manifest.json"),
        ("contracts/release/release_record.schema.json", "contracts/examples/release_record.example.json"),
    ]

    all_errors: list[str] = []
    for schema_rel, instance_rel in pairs:
        schema = _load_json(repo / schema_rel)
        inst = _load_json(repo / instance_rel)
        errs = _validate(repo, inst, schema, instance_rel)
        all_errors += [f"{schema_rel} -> {e}" for e in errs]

    # Validate all curated eval sample sets (if any) against the schema.
    sample_schema_rel = "contracts/eval/eval_sample_set.schema.json"
    sample_schema = _load_json(repo / sample_schema_rel)
    sample_sets_dir = repo / "eval" / "sample_sets"
    if sample_sets_dir.exists():
        for p in sorted(sample_sets_dir.glob("*.json")):
            inst_rel = str(p.relative_to(repo)).replace("\\", "/")
            inst = _load_json(p)
            errs = _validate(repo, inst, sample_schema, inst_rel)
            all_errors += [f"{sample_schema_rel} -> {e}" for e in errs]

    if all_errors:
        for e in all_errors:
            print("FAIL:", e, file=sys.stderr)
        return 1

    print("PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
