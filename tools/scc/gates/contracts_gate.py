import os
import pathlib

from tools.scc.validators.contract_validator import (
    load_json,
    validate_pins_result_v1,
    validate_preflight_v1,
    validate_replay_bundle_v1,
    validate_retry_plan_v1,
    validate_submit_v1,
)


def _norm_rel(p: str) -> str:
    return p.replace("\\", "/").lstrip("./")


def _read_last_line(path: pathlib.Path) -> str:
    try:
        lines = path.read_text(encoding="utf-8-sig").splitlines()
        # Accept trailing blank lines; enforce on the last non-empty line.
        for ln in reversed(lines):
            s = ln.strip()
            if s:
                return s
        return ""
    except Exception:
        return ""


def run(repo: pathlib.Path, submit: dict, submit_path: pathlib.Path):
    errors: list[str] = []
    warnings: list[str] = []

    # 1) submit.json schema (strict, fail-closed)
    errors += validate_submit_v1(submit)

    task_id = submit.get("task_id") if isinstance(submit, dict) else None
    task_id = str(task_id) if task_id else "unknown"
    art_dir = repo / "artifacts" / task_id

    # 2) required artifact files must exist
    artifacts = submit.get("artifacts") if isinstance(submit, dict) else None
    if isinstance(artifacts, dict):
        for k in ("report_md", "selftest_log", "patch_diff", "submit_json"):
            p = artifacts.get(k)
            if isinstance(p, str) and p:
                abs_path = (repo / _norm_rel(p)).resolve()
                if not abs_path.exists():
                    errors.append(f"missing artifact file: {k} -> {_norm_rel(p)}")
        ev = artifacts.get("evidence_dir")
        if isinstance(ev, str) and ev:
            ev_abs = (repo / _norm_rel(ev)).resolve()
            if not ev_abs.exists():
                errors.append(f"missing evidence dir: {_norm_rel(ev)}")

    # 3) selftest.log must end with EXIT_CODE=0
    selftest_path = art_dir / "selftest.log"
    if selftest_path.exists():
        last = _read_last_line(selftest_path)
        if last != "EXIT_CODE=0":
            errors.append(f"selftest.log last line must be EXIT_CODE=0 (got {last!r})")
    else:
        errors.append("missing artifacts/<task_id>/selftest.log")

    # 4) preflight.json must exist + schema
    preflight_path = art_dir / "preflight.json"
    if preflight_path.exists():
        try:
            pre = load_json(preflight_path)
        except Exception as e:
            errors.append(f"preflight.json parse failed: {e}")
        else:
            errors += validate_preflight_v1(pre)
    else:
        errors.append("missing artifacts/<task_id>/preflight.json")

    # 5) pins artifacts must exist + schema
    pins_path = art_dir / "pins" / "pins.json"
    if pins_path.exists():
        try:
            pins = load_json(pins_path)
        except Exception as e:
            errors.append(f"pins/pins.json parse failed: {e}")
        else:
            errors += validate_pins_result_v1(pins)
            sv = pins.get("schema_version") if isinstance(pins, dict) else None
            if sv != "scc.pins_result.v2":
                warnings.append(f"pins schema_version is not audited v2 (got {sv!r}); prefer scc.pins_result.v2 with pins.items[].reason")
                if str(os.environ.get("PINS_V2_REQUIRED") or "false").lower() == "true":
                    errors.append("pins v2 required (set by PINS_V2_REQUIRED=true)")
    else:
        errors.append("missing artifacts/<task_id>/pins/pins.json")

    # 6) replay bundle is required for L3 replayability
    replay_path = art_dir / "replay_bundle.json"
    if replay_path.exists():
        try:
            rb = load_json(replay_path)
        except Exception as e:
            errors.append(f"replay_bundle.json parse failed: {e}")
        else:
            errors += validate_replay_bundle_v1(rb)
    else:
        errors.append("missing artifacts/<task_id>/replay_bundle.json")

    # 7) retry_plan.json is optional but must validate if present (L6+)
    retry_plan_path = art_dir / "retry_plan.json"
    if retry_plan_path.exists():
        try:
            rp = load_json(retry_plan_path)
        except Exception as e:
            errors.append(f"retry_plan.json parse failed: {e}")
        else:
            errors += validate_retry_plan_v1(rp)

    # 8) enterprise execution entrypoint: slot-based Context Pack v1 reference must exist when required
    if str(os.environ.get("CONTEXT_PACK_V1_REQUIRED") or "true").lower() != "false":
        ref_path = art_dir / "context_pack_v1.json"
        if not ref_path.exists():
            errors.append("missing artifacts/<task_id>/context_pack_v1.json")

    return {"errors": errors, "warnings": warnings}
