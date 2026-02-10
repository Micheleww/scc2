import hashlib
import json
import os
import pathlib
from typing import Any

from tools.scc.lib.utils import load_json, norm_rel


def _sha256_bytes(b: bytes) -> str:
    return "sha256:" + hashlib.sha256(b).hexdigest()


def _sha256_nonce_bytes(nonce: str, b: bytes) -> str:
    h = hashlib.sha256()
    h.update((nonce or "").encode("utf-8"))
    h.update(b)
    return "sha256:" + h.hexdigest()


def _read_bytes(path: pathlib.Path) -> bytes | None:
    try:
        return path.read_bytes()
    except Exception:
        return None


def run(repo: pathlib.Path, submit: dict, *, strict: bool = True) -> dict:
    """
    Gate: verify nonce-bound Context Pack v1 attestation proof.

    Preconditions:
    - If artifacts/<task_id>/context_pack_v1.json is present, the gateway must have produced
      evidence/context_pack_v1_proof.json and (for new tasks) proof must match bytes on disk.
    """
    task_id = str((submit or {}).get("task_id") or "unknown")
    art_dir = (repo / "artifacts" / task_id).resolve()
    ref_path = (art_dir / "context_pack_v1.json").resolve()
    if not ref_path.exists():
        # No v1 pack reference => nothing to prove.
        return {"errors": [], "warnings": []}

    errors: list[str] = []
    warnings: list[str] = []

    try:
        ref = load_json(ref_path)
    except Exception as e:
        return {"errors": [f"context_pack_v1.json parse failed: {e}"], "warnings": []}

    cp_id = str(ref.get("context_pack_id") or "").strip()
    if not cp_id:
        return {"errors": ["context_pack_v1.json: missing context_pack_id"], "warnings": []}

    # Only enforce proof strictly when ref declares it required (backwards compatible for legacy tasks).
    proof_required = bool(ref.get("proof_required") is True)

    evidence_proof = (art_dir / "evidence" / "context_pack_v1_proof.json").resolve()
    if not evidence_proof.exists():
        if strict and proof_required:
            return {"errors": ["missing artifacts/<task_id>/evidence/context_pack_v1_proof.json"], "warnings": []}
        return {"errors": [], "warnings": ["missing artifacts/<task_id>/evidence/context_pack_v1_proof.json (not required for legacy tasks)"]}

    try:
        proof = load_json(evidence_proof)
    except Exception as e:
        return {"errors": [f"context_pack_v1_proof.json parse failed: {e}"], "warnings": []}

    if not isinstance(proof, dict) or proof.get("schema_version") != "scc.context_pack_v1_proof.v1":
        return {"errors": ["context_pack_v1_proof.json: schema_version != scc.context_pack_v1_proof.v1"], "warnings": []}

    want_nonce = str(proof.get("attestation_nonce_job") or "").strip()
    if proof_required and not want_nonce:
        errors.append("context_pack_v1_proof.json: missing attestation_nonce_job")

    want_run = str(proof.get("context_pack_v1_id_job") or "").strip()
    if want_run and want_run != cp_id:
        errors.append(f"context_pack_v1_proof.json: context_pack_v1_id_job mismatch want={cp_id} got={want_run}")

    run_dir = (repo / "artifacts" / "scc_runs" / cp_id).resolve()
    pack_path = (run_dir / "rendered_context_pack.json").resolve()
    if not pack_path.exists():
        errors.append(f"missing artifacts/scc_runs/{cp_id}/rendered_context_pack.json")
        return {"errors": errors, "warnings": warnings}

    pack_bytes = _read_bytes(pack_path)
    if pack_bytes is None:
        errors.append(f"cannot read rendered_context_pack.json: {norm_rel(str(pack_path.relative_to(repo)))}")
        return {"errors": errors, "warnings": warnings}

    got_pack_sha = _sha256_bytes(pack_bytes)
    want_pack_sha = str(proof.get("pack_json_sha256_payload") or "").strip()
    if want_pack_sha and want_pack_sha != got_pack_sha:
        errors.append(f"pack_json_sha256_payload mismatch want={got_pack_sha} got={want_pack_sha}")

    want_pack_att = str(proof.get("pack_json_attest_sha256_payload") or "").strip()
    if want_nonce:
        got_pack_att = _sha256_nonce_bytes(want_nonce, pack_bytes)
        if want_pack_att and want_pack_att != got_pack_att:
            errors.append(f"pack_json_attest_sha256_payload mismatch want={got_pack_att} got={want_pack_att}")

    tb_dir = (run_dir / "task_bundle").resolve()
    if not tb_dir.exists():
        errors.append(f"missing artifacts/scc_runs/{cp_id}/task_bundle/")
        return {"errors": errors, "warnings": warnings}

    want_files = proof.get("task_bundle_files_sha256_payload")
    want_files_att = proof.get("task_bundle_files_attest_sha256_payload")
    if not isinstance(want_files, dict):
        errors.append("context_pack_v1_proof.json: task_bundle_files_sha256_payload missing/invalid")
        want_files = {}
    if not isinstance(want_files_att, dict):
        errors.append("context_pack_v1_proof.json: task_bundle_files_attest_sha256_payload missing/invalid")
        want_files_att = {}

    required = ["manifest.json", "pins.json", "preflight.json", "task.json"]
    optional = ["replay_bundle.json"]

    for f in required + optional:
        fp = (tb_dir / f).resolve()
        if f in required and not fp.exists():
            errors.append(f"missing task_bundle file: {f}")
            continue
        if not fp.exists():
            continue
        b = _read_bytes(fp)
        if b is None:
            errors.append(f"cannot read task_bundle file: {f}")
            continue
        got = _sha256_bytes(b)
        want = str(want_files.get(f) or "").strip()
        if want and want != got:
            errors.append(f"task_bundle_files_sha256_payload mismatch file={f} want={got} got={want}")
        if want_nonce:
            got_att = _sha256_nonce_bytes(want_nonce, b)
            want_att = str(want_files_att.get(f) or "").strip()
            if want_att and want_att != got_att:
                errors.append(f"task_bundle_files_attest_sha256_payload mismatch file={f} want={got_att} got={want_att}")

    if proof_required and str(os.environ.get("CONTEXT_PACK_V1_REQUIRED") or "true").lower() != "false":
        # In strict mode, for new tasks we expect both sha maps to include required files.
        for f in required:
            if strict and not str(want_files.get(f) or "").strip():
                errors.append(f"context_pack_v1_proof.json: missing sha entry for {f}")
            if strict and not str(want_files_att.get(f) or "").strip():
                errors.append(f"context_pack_v1_proof.json: missing attest sha entry for {f}")

    return {"errors": errors, "warnings": warnings}
