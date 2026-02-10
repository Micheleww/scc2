from tools.scc.lib.utils import load_json, norm_rel


def _type_name(x: Any) -> str:
    if x is None:
        return "null"
    if isinstance(x, bool):
        return "bool"
    if isinstance(x, int) and not isinstance(x, bool):
        return "int"
    if isinstance(x, float):
        return "float"
    if isinstance(x, str):
        return "str"
    if isinstance(x, list):
        return "list"
    if isinstance(x, dict):
        return "dict"
    return type(x).__name__


def _require_dict(obj: Any, ctx: str) -> tuple[dict, list[str]]:
    if isinstance(obj, dict):
        return obj, []
    return {}, [f"{ctx}: expected object, got {_type_name(obj)}"]


def _require_keys(obj: dict, keys: list[str], ctx: str) -> list[str]:
    errors: list[str] = []
    for k in keys:
        if k not in obj:
            errors.append(f"{ctx}: missing key {k}")
    return errors


def _deny_extra_keys(obj: dict, allowed: set[str], ctx: str) -> list[str]:
    extras = sorted(set(obj.keys()) - allowed)
    return [f"{ctx}: extra key {k}" for k in extras]


def _require_str(x: Any, ctx: str) -> list[str]:
    if isinstance(x, str) and x.strip():
        return []
    return [f"{ctx}: expected non-empty string, got {_type_name(x)}"]


def _require_bool(x: Any, ctx: str) -> list[str]:
    if isinstance(x, bool):
        return []
    return [f"{ctx}: expected boolean, got {_type_name(x)}"]


def _require_int(x: Any, ctx: str) -> list[str]:
    if isinstance(x, int) and not isinstance(x, bool):
        return []
    return [f"{ctx}: expected integer, got {_type_name(x)}"]


def _require_str_list(x: Any, ctx: str, allow_empty: bool = True) -> list[str]:
    if not isinstance(x, list):
        return [f"{ctx}: expected array, got {_type_name(x)}"]
    if not allow_empty and len(x) == 0:
        return [f"{ctx}: expected non-empty array"]
    errors: list[str] = []
    for i, v in enumerate(x):
        if not isinstance(v, str) or not v.strip():
            errors.append(f"{ctx}[{i}]: expected non-empty string, got {_type_name(v)}")
    return errors


def validate_submit_v1(obj: Any) -> list[str]:
    data, errors = _require_dict(obj, "submit")
    if errors:
        return errors

    allowed = {
        "schema_version",
        "task_id",
        "status",
        "reason_code",
        "changed_files",
        "new_files",
        "touched_files",
        "allow_paths",
        "ssot_pointers",
        "summary",
        "payload",
        "tests",
        "artifacts",
        "exit_code",
        "needs_input",
    }
    errors += _deny_extra_keys(data, allowed, "submit")
    errors += _require_keys(data, ["schema_version", "task_id", "status", "changed_files", "tests", "artifacts", "exit_code", "needs_input"], "submit")
    if data.get("schema_version") != "scc.submit.v1":
        errors.append("submit.schema_version != scc.submit.v1")
    errors += _require_str(data.get("task_id"), "submit.task_id")
    st = data.get("status")
    if st not in ("DONE", "NEED_INPUT", "FAILED"):
        errors.append(f"submit.status invalid: {st}")
    errors += _require_str_list(data.get("changed_files"), "submit.changed_files")
    if "new_files" in data:
        errors += _require_str_list(data.get("new_files"), "submit.new_files")
    if "touched_files" in data:
        errors += _require_str_list(data.get("touched_files"), "submit.touched_files")

    tests, e2 = _require_dict(data.get("tests"), "submit.tests")
    errors += e2
    errors += _deny_extra_keys(tests, {"commands", "passed", "summary"}, "submit.tests")
    errors += _require_keys(tests, ["commands", "passed", "summary"], "submit.tests")
    errors += _require_str_list(tests.get("commands"), "submit.tests.commands")
    errors += _require_bool(tests.get("passed"), "submit.tests.passed")
    errors += _require_str(tests.get("summary"), "submit.tests.summary")

    artifacts, e3 = _require_dict(data.get("artifacts"), "submit.artifacts")
    errors += e3
    req_art_keys = {"report_md", "selftest_log", "evidence_dir", "patch_diff", "submit_json"}
    errors += _require_keys(artifacts, sorted(req_art_keys), "submit.artifacts")
    errors += _deny_extra_keys(artifacts, req_art_keys, "submit.artifacts")
    for k in sorted(req_art_keys):
        errors += _require_str(artifacts.get(k), f"submit.artifacts.{k}")

    errors += _require_int(data.get("exit_code"), "submit.exit_code")
    if not isinstance(data.get("needs_input"), list):
        errors.append("submit.needs_input expected array")
    if "ssot_pointers" in data:
        errors += _require_str_list(data.get("ssot_pointers"), "submit.ssot_pointers")
    if "summary" in data and data.get("summary") is not None and not isinstance(data.get("summary"), str):
        errors.append(f"submit.summary expected string, got {_type_name(data.get('summary'))}")
    if "payload" in data and data.get("payload") is not None and not isinstance(data.get("payload"), dict):
        errors.append(f"submit.payload expected object, got {_type_name(data.get('payload'))}")
    return errors


def validate_preflight_v1(obj: Any) -> list[str]:
    data, errors = _require_dict(obj, "preflight")
    if errors:
        return errors
    allowed = {"schema_version", "task_id", "pass", "missing", "notes"}
    errors += _deny_extra_keys(data, allowed, "preflight")
    errors += _require_keys(data, ["schema_version", "task_id", "pass", "missing"], "preflight")
    if data.get("schema_version") != "scc.preflight.v1":
        errors.append("preflight.schema_version != scc.preflight.v1")
    errors += _require_str(data.get("task_id"), "preflight.task_id")
    errors += _require_bool(data.get("pass"), "preflight.pass")

    missing, e2 = _require_dict(data.get("missing"), "preflight.missing")
    errors += e2
    errors += _deny_extra_keys(missing, {"files", "symbols", "tests", "write_scope"}, "preflight.missing")
    errors += _require_keys(missing, ["files", "symbols", "tests", "write_scope"], "preflight.missing")
    errors += _require_str_list(missing.get("files"), "preflight.missing.files")
    errors += _require_str_list(missing.get("symbols"), "preflight.missing.symbols")
    errors += _require_str_list(missing.get("tests"), "preflight.missing.tests")
    errors += _require_str_list(missing.get("write_scope"), "preflight.missing.write_scope")
    if "notes" in data and data.get("notes") is not None and not isinstance(data.get("notes"), str):
        errors.append("preflight.notes expected string")
    return errors


def _validate_pins_result_v1(data: dict) -> list[str]:
    errors: list[str] = []
    allowed = {"schema_version", "task_id", "pins", "recommended_queries", "preflight_expectation"}
    errors += _deny_extra_keys(data, allowed, "pins_result")
    errors += _require_keys(data, ["schema_version", "task_id", "pins"], "pins_result")
    if data.get("schema_version") != "scc.pins_result.v1":
        errors.append("pins_result.schema_version != scc.pins_result.v1")
    errors += _require_str(data.get("task_id"), "pins_result.task_id")

    pins, e2 = _require_dict(data.get("pins"), "pins_result.pins")
    errors += e2
    # Minimal pinsSpec validation (strict enough for fail-closed)
    errors += _require_str_list(pins.get("allowed_paths"), "pins_result.pins.allowed_paths", allow_empty=False)
    if "forbidden_paths" in pins:
        errors += _require_str_list(pins.get("forbidden_paths"), "pins_result.pins.forbidden_paths")
    if "symbols" in pins:
        errors += _require_str_list(pins.get("symbols"), "pins_result.pins.symbols")
    if "max_files" in pins and pins.get("max_files") is not None and not isinstance(pins.get("max_files"), int):
        errors.append("pins_result.pins.max_files expected int")
    if "max_loc" in pins and pins.get("max_loc") is not None and not isinstance(pins.get("max_loc"), int):
        errors.append("pins_result.pins.max_loc expected int")
    if "line_windows" in pins and pins.get("line_windows") is not None and not isinstance(pins.get("line_windows"), dict):
        errors.append("pins_result.pins.line_windows expected object")
    return errors


def _validate_pins_result_v2(data: dict) -> list[str]:
    errors: list[str] = []
    allowed = {"schema_version", "task_id", "pins", "recommended_queries", "preflight_expectation"}
    errors += _deny_extra_keys(data, allowed, "pins_result")
    errors += _require_keys(data, ["schema_version", "task_id", "pins"], "pins_result")
    if data.get("schema_version") != "scc.pins_result.v2":
        errors.append("pins_result.schema_version != scc.pins_result.v2")
    errors += _require_str(data.get("task_id"), "pins_result.task_id")

    pins, e2 = _require_dict(data.get("pins"), "pins_result.pins")
    errors += e2

    items = pins.get("items")
    if not isinstance(items, list) or len(items) == 0:
        errors.append("pins_result.pins.items expected non-empty array")
        return errors

    for i, it in enumerate(items[:200]):
        if not isinstance(it, dict):
            errors.append(f"pins_result.pins.items[{i}]: expected object")
            continue
        errors += _deny_extra_keys(it, {"path", "reason", "read_only", "write_intent", "symbols", "line_windows"}, f"pins_result.pins.items[{i}]")
        errors += _require_str(it.get("path"), f"pins_result.pins.items[{i}].path")
        errors += _require_str(it.get("reason"), f"pins_result.pins.items[{i}].reason")
        errors += _require_bool(it.get("read_only"), f"pins_result.pins.items[{i}].read_only")
        errors += _require_bool(it.get("write_intent"), f"pins_result.pins.items[{i}].write_intent")
        if "symbols" in it:
            errors += _require_str_list(it.get("symbols"), f"pins_result.pins.items[{i}].symbols")
        if "line_windows" in it and it.get("line_windows") is not None and not isinstance(it.get("line_windows"), list):
            errors.append(f"pins_result.pins.items[{i}].line_windows expected array")

    # Legacy compatibility fields (optional but validated if present)
    if "allowed_paths" in pins:
        errors += _require_str_list(pins.get("allowed_paths"), "pins_result.pins.allowed_paths", allow_empty=False)
    if "forbidden_paths" in pins:
        errors += _require_str_list(pins.get("forbidden_paths"), "pins_result.pins.forbidden_paths")
    if "symbols" in pins:
        errors += _require_str_list(pins.get("symbols"), "pins_result.pins.symbols")
    if "max_files" in pins and pins.get("max_files") is not None and not isinstance(pins.get("max_files"), int):
        errors.append("pins_result.pins.max_files expected int")
    if "max_loc" in pins and pins.get("max_loc") is not None and not isinstance(pins.get("max_loc"), int):
        errors.append("pins_result.pins.max_loc expected int")
    if "line_windows" in pins and pins.get("line_windows") is not None and not isinstance(pins.get("line_windows"), dict):
        errors.append("pins_result.pins.line_windows expected object")
    return errors


def validate_pins_result(obj: Any) -> list[str]:
    data, errors = _require_dict(obj, "pins_result")
    if errors:
        return errors
    sv = data.get("schema_version")
    if sv == "scc.pins_result.v1":
        return _validate_pins_result_v1(data)
    if sv == "scc.pins_result.v2":
        return _validate_pins_result_v2(data)
    return [f"pins_result.schema_version unsupported: {sv}"]


# Back-compat: keep old function name, but accept v1 or v2.
def validate_pins_result_v1(obj: Any) -> list[str]:
    return validate_pins_result(obj)


def validate_replay_bundle_v1(obj: Any) -> list[str]:
    data, errors = _require_dict(obj, "replay_bundle")
    if errors:
        return errors
    allowed = {"schema_version", "task_id", "created_at", "source", "board_task_payload", "artifacts", "replay"}
    errors += _deny_extra_keys(data, allowed, "replay_bundle")
    errors += _require_keys(data, ["schema_version", "task_id", "created_at", "board_task_payload", "artifacts"], "replay_bundle")
    if data.get("schema_version") != "scc.replay_bundle.v1":
        errors.append("replay_bundle.schema_version != scc.replay_bundle.v1")
    errors += _require_str(data.get("task_id"), "replay_bundle.task_id")
    errors += _require_str(data.get("created_at"), "replay_bundle.created_at")
    bt, e2 = _require_dict(data.get("board_task_payload"), "replay_bundle.board_task_payload")
    errors += e2
    if not isinstance(bt, dict) or not bt:
        errors.append("replay_bundle.board_task_payload must be object")
    art, e3 = _require_dict(data.get("artifacts"), "replay_bundle.artifacts")
    errors += e3
    for k in ("submit_json", "preflight_json", "pins_json", "report_md", "selftest_log", "evidence_dir", "patch_diff"):
        errors += _require_str(art.get(k), f"replay_bundle.artifacts.{k}")
    return errors


def validate_retry_plan_v1(obj: Any) -> list[str]:
    data, errors = _require_dict(obj, "retry_plan")
    if errors:
        return errors
    allowed = {
        "schema_version",
        "task_id",
        "attempt",
        "max_attempts",
        "route",
        "strategy",
        "budgets",
        "pins_adjustments",
        "stop_conditions",
        "dlq_on_fail",
    }
    errors += _deny_extra_keys(data, allowed, "retry_plan")
    errors += _require_keys(data, ["schema_version", "task_id", "attempt", "max_attempts", "route", "strategy", "budgets", "stop_conditions"], "retry_plan")
    if data.get("schema_version") != "scc.retry_plan.v1":
        errors.append("retry_plan.schema_version != scc.retry_plan.v1")
    errors += _require_str(data.get("task_id"), "retry_plan.task_id")
    errors += _require_int(data.get("attempt"), "retry_plan.attempt")
    errors += _require_int(data.get("max_attempts"), "retry_plan.max_attempts")

    strat = data.get("strategy")
    if strat not in ("PINS_FIX", "SHRINK_RADIUS", "SPLIT_V2", "SWITCH_EXECUTOR", "SWITCH_MODEL", "DLQ"):
        errors.append(f"retry_plan.strategy invalid: {strat}")

    route, e2 = _require_dict(data.get("route"), "retry_plan.route")
    errors += e2
    errors += _deny_extra_keys(route, {"lane", "next_role", "notes"}, "retry_plan.route")
    errors += _require_keys(route, ["lane", "next_role"], "retry_plan.route")
    lane = route.get("lane")
    if lane not in ("fastlane", "mainlane", "batchlane", "quarantine", "dlq"):
        errors.append(f"retry_plan.route.lane invalid: {lane}")
    errors += _require_str(route.get("next_role"), "retry_plan.route.next_role")

    budgets, e3 = _require_dict(data.get("budgets"), "retry_plan.budgets")
    errors += e3
    errors += _deny_extra_keys(budgets, {"max_total_attempts", "max_verify_minutes", "max_children", "max_depth"}, "retry_plan.budgets")
    errors += _require_keys(budgets, ["max_total_attempts", "max_verify_minutes", "max_children", "max_depth"], "retry_plan.budgets")
    for k in ("max_total_attempts", "max_verify_minutes", "max_children", "max_depth"):
        errors += _require_int(budgets.get(k), f"retry_plan.budgets.{k}")

    if "stop_conditions" in data:
        errors += _require_str_list(data.get("stop_conditions"), "retry_plan.stop_conditions")
    if "dlq_on_fail" in data and data.get("dlq_on_fail") is not None and not isinstance(data.get("dlq_on_fail"), bool):
        errors.append("retry_plan.dlq_on_fail expected boolean")
    if "pins_adjustments" in data and data.get("pins_adjustments") is not None:
        pa, e4 = _require_dict(data.get("pins_adjustments"), "retry_plan.pins_adjustments")
        errors += e4
        errors += _deny_extra_keys(pa, {"add", "drop"}, "retry_plan.pins_adjustments")
        if "add" in pa:
            errors += _require_str_list(pa.get("add"), "retry_plan.pins_adjustments.add")
        if "drop" in pa:
            errors += _require_str_list(pa.get("drop"), "retry_plan.pins_adjustments.drop")
    return errors


def validate_trace_v1(obj: Any) -> list[str]:
    data, errors = _require_dict(obj, "trace")
    if errors:
        return errors
    allowed = {"schema_version", "task_id", "created_at", "updated_at", "config_hashes", "routing", "artifacts"}
    errors += _deny_extra_keys(data, allowed, "trace")
    errors += _require_keys(data, ["schema_version", "task_id", "created_at", "updated_at", "config_hashes", "routing", "artifacts"], "trace")
    if data.get("schema_version") != "scc.trace.v1":
        errors.append("trace.schema_version != scc.trace.v1")
    errors += _require_str(data.get("task_id"), "trace.task_id")
    errors += _require_str(data.get("created_at"), "trace.created_at")
    errors += _require_str(data.get("updated_at"), "trace.updated_at")

    ch, e2 = _require_dict(data.get("config_hashes"), "trace.config_hashes")
    errors += e2
    if isinstance(ch, dict):
        errors += _deny_extra_keys(ch, {"factory_policy_sha256", "roles_registry_sha256", "skills_registry_sha256"}, "trace.config_hashes")

    rt, e3 = _require_dict(data.get("routing"), "trace.routing")
    errors += e3
    if isinstance(rt, dict):
        errors += _deny_extra_keys(rt, {"executor", "model", "model_effective"}, "trace.routing")

    art, e4 = _require_dict(data.get("artifacts"), "trace.artifacts")
    errors += e4
    if isinstance(art, dict):
        errors += _deny_extra_keys(art, {"submit_json", "report_md", "selftest_log", "evidence_dir", "patch_diff", "verdict_json"}, "trace.artifacts")

    return errors


def validate_release_record_v1(obj: Any) -> list[str]:
    data, errors = _require_dict(obj, "release_record")
    if errors:
        return errors

    allowed = {"schema_version", "release_id", "created_at", "sources", "artifacts", "verification", "notes"}
    errors += _deny_extra_keys(data, allowed, "release_record")
    errors += _require_keys(data, ["schema_version", "release_id", "created_at", "sources", "artifacts", "verification"], "release_record")

    if data.get("schema_version") != "scc.release_record.v1":
        errors.append("release_record.schema_version != scc.release_record.v1")

    errors += _require_str(data.get("release_id"), "release_record.release_id")
    errors += _require_str(data.get("created_at"), "release_record.created_at")

    sources = data.get("sources")
    if not isinstance(sources, list) or len(sources) == 0:
        errors.append("release_record.sources: expected non-empty array")
    else:
        for i, s in enumerate(sources[:20]):
            if not isinstance(s, dict):
                errors.append(f"release_record.sources[{i}]: expected object, got {_type_name(s)}")
                continue
            errors += _require_keys(s, ["task_id", "submit_json", "patch_diff"], f"release_record.sources[{i}]")
            errors += _require_str(s.get("task_id"), f"release_record.sources[{i}].task_id")
            errors += _require_str(s.get("submit_json"), f"release_record.sources[{i}].submit_json")
            errors += _require_str(s.get("patch_diff"), f"release_record.sources[{i}].patch_diff")
            if "pr_bundle" in s and s.get("pr_bundle") is not None:
                errors += _require_str(s.get("pr_bundle"), f"release_record.sources[{i}].pr_bundle")

    artifacts = data.get("artifacts")
    if not isinstance(artifacts, dict):
        errors.append(f"release_record.artifacts: expected object, got {_type_name(artifacts)}")
    else:
        errors += _require_keys(artifacts, ["release_dir", "release_record_json"], "release_record.artifacts")
        errors += _require_str(artifacts.get("release_dir"), "release_record.artifacts.release_dir")
        errors += _require_str(artifacts.get("release_record_json"), "release_record.artifacts.release_record_json")

    ver = data.get("verification")
    if not isinstance(ver, dict):
        errors.append(f"release_record.verification: expected object, got {_type_name(ver)}")
    else:
        errors += _require_keys(ver, ["strict_gates_passed"], "release_record.verification")
        errors += _require_bool(ver.get("strict_gates_passed"), "release_record.verification.strict_gates_passed")

    if "notes" in data and data.get("notes") is not None and not isinstance(data.get("notes"), str):
        errors.append(f"release_record.notes: expected string|null, got {_type_name(data.get('notes'))}")

    return errors
