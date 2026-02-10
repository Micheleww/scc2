import pathlib

from tools.scc.lib.utils import load_json, norm_rel as _norm_rel
from tools.scc.validators.contract_validator import validate_release_record_v1


def _require_keys(obj: dict, keys: list[str], ctx: str) -> list[str]:
    errors: list[str] = []
    for k in keys:
        if k not in obj:
            errors.append(f"{ctx}: missing key {k}")
    return errors


def run(repo: pathlib.Path) -> list[str]:
    errors: list[str] = []

    # Roles registry + role policies
    roles_registry_path = repo / "roles/registry.json"
    if not roles_registry_path.exists():
        return ["missing roles/registry.json"]
    roles_registry = load_json(roles_registry_path)
    errors += _require_keys(roles_registry, ["schema_version", "roles"], "roles/registry.json")
    role_entries = roles_registry.get("roles") or []
    role_to_policy: dict[str, str] = {}
    for e in role_entries:
        if not isinstance(e, dict):
            errors.append("roles/registry.json: invalid role entry")
            continue
        role = e.get("role")
        policy = e.get("policy")
        if not role or not policy:
            errors.append("roles/registry.json: role entry missing role/policy")
            continue
        role_to_policy[str(role)] = norm_rel(str(policy))
        if not (repo / policy).exists():
            errors.append(f"roles/registry.json: missing policy file: {policy}")

    for role, policy_rel in sorted(role_to_policy.items()):
        policy = load_json(repo / policy_rel)
        if policy.get("schema_version") != "scc.role_policy.v1":
            errors.append(f"{policy_rel}: schema_version != scc.role_policy.v1")
        if policy.get("role") != role:
            errors.append(f"{policy_rel}: role field mismatch (expected {role})")

    # Skills registry + skill definitions
    skills_registry_path = repo / "skills/registry.json"
    if not skills_registry_path.exists():
        errors.append("missing skills/registry.json")
        return errors
    skills_registry = load_json(skills_registry_path)
    errors += _require_keys(skills_registry, ["schema_version", "skills"], "skills/registry.json")
    skill_entries = skills_registry.get("skills") or []
    skill_ids: set[str] = set()
    for e in skill_entries:
        if not isinstance(e, dict):
            errors.append("skills/registry.json: invalid skill entry")
            continue
        sid = e.get("skill_id")
        path = e.get("path")
        if not sid or not path:
            errors.append("skills/registry.json: missing skill_id/path")
            continue
        sid = str(sid)
        skill_ids.add(sid)
        p = repo / str(path)
        if not p.exists():
            errors.append(f"skills/registry.json: missing skill file: {path}")
            continue
        data = load_json(p)
        if data.get("schema_version") != "scc.skill.v1":
            errors.append(f"{path}: schema_version != scc.skill.v1")
        if data.get("skill_id") != sid:
            errors.append(f"{path}: skill_id mismatch (expected {sid})")
        contracts = data.get("contracts") or {}
        for k in ("input_schema", "output_schema"):
            sp = contracts.get(k)
            if not sp or not isinstance(sp, str):
                errors.append(f"{path}: missing contracts.{k}")
                continue
            if not (repo / sp).exists():
                errors.append(f"{path}: contracts.{k} missing file {sp}")

    # Role-skill matrix
    matrix_path = repo / "roles/role_skill_matrix.json"
    if not matrix_path.exists():
        errors.append("missing roles/role_skill_matrix.json")
        return errors
    matrix = load_json(matrix_path)
    roles_map = matrix.get("roles") or {}
    for role, skills in roles_map.items():
        if role not in role_to_policy:
            errors.append(f"roles/role_skill_matrix.json: role not in registry: {role}")
        if not isinstance(skills, list):
            errors.append(f"roles/role_skill_matrix.json: role {role} skills not array")
            continue
        for sid in skills:
            if sid not in skill_ids:
                errors.append(f"roles/role_skill_matrix.json: unknown skill_id {sid} for role {role}")

    # Factory policy + eval manifest existence
    fp = repo / "config" / "factory_policy.json"
    if not fp.exists():
        errors.append("missing config/factory_policy.json")
    else:
        data = load_json(fp)
        if data.get("schema_version") != "scc.factory_policy.v1":
            errors.append("config/factory_policy.json: schema_version != scc.factory_policy.v1")
        errors += _require_keys(
            data,
            ["updated_at", "wip_limits", "lanes", "budgets", "event_routing", "circuit_breakers", "degradation_matrix", "verification_tiers"],
            "config/factory_policy.json",
        )

    ev = repo / "eval/eval_manifest.json"
    if not ev.exists():
        errors.append("missing eval/eval_manifest.json")
    else:
        data = load_json(ev)
        if data.get("schema_version") != "scc.eval_manifest.v1":
            errors.append("eval/eval_manifest.json: schema_version != scc.eval_manifest.v1")

    # Context Pack contracts (enterprise execution entrypoint)
    for p in (
        "contracts/context_pack/context_pack.schema.json",
        "contracts/context_pack/context_pack_ref.schema.json",
        "contracts/context_pack/context_pack_proof.schema.json",
    ):
        if not (repo / p).exists():
            errors.append(f"missing {p}")

    # Connectors registry (control-plane)
    cr = repo / "connectors" / "registry.json"
    if not cr.exists():
        errors.append("missing connectors/registry.json")
    else:
        try:
            data = load_json(cr)
        except Exception as e:
            errors.append(f"connectors/registry.json: json_parse_failed: {e}")
        else:
            if data.get("schema_version") != "scc.connector_registry.v1":
                errors.append("connectors/registry.json: schema_version != scc.connector_registry.v1")

    # Semantic context (read-only shared context layer)
    scx = repo / "semantic_context" / "index.jsonl"
    if not scx.exists():
        errors.append("missing semantic_context/index.jsonl")

    # SSOT facts registry (Map-driven drift gate input)
    ssot_reg = repo / "docs" / "SSOT" / "registry.json"
    if not ssot_reg.exists():
        errors.append("missing docs/SSOT/registry.json")
    else:
        data = load_json(ssot_reg)
        if data.get("schema_version") != "scc.ssot_registry.v1":
            errors.append("docs/SSOT/registry.json: schema_version != scc.ssot_registry.v1")
        facts = data.get("facts") or {}
        for k in ("modules", "entry_points", "contracts"):
            if k not in facts:
                errors.append(f"docs/SSOT/registry.json: facts missing {k}")
        contracts = facts.get("contracts") or []
        if isinstance(contracts, list):
            for p in contracts:
                if not isinstance(p, str) or not p:
                    continue
                if not (repo / p).exists():
                    errors.append(f"docs/SSOT/registry.json: missing listed contract schema {p}")

    # Release records (best-effort validation; fail-closed if present but invalid)
    for rel_root in ("releases", "releases_selfcheck"):
        root = repo / rel_root
        if not root.exists():
            continue
        release_files = sorted(root.glob("rel-*/release.json"))[-80:]
        for rf in release_files:
            try:
                obj = load_json(rf)
            except Exception as e:
                errors.append(f"{norm_rel(str(rf.relative_to(repo)))}: json_parse_failed: {e}")
                continue
            verr = validate_release_record_v1(obj)
            for e in verr[:50]:
                errors.append(f"{norm_rel(str(rf.relative_to(repo)))}: {e}")

    # Patterns + playbooks (best-effort structural validation, no full JSONSchema engine required)
    patterns_dir = repo / "patterns"
    if patterns_dir.exists():
        registry_path = patterns_dir / "registry.json"
        if not registry_path.exists():
            errors.append("missing patterns/registry.json")
        else:
            try:
                reg = load_json(registry_path)
            except Exception as e:
                errors.append(f"{norm_rel(str(registry_path.relative_to(repo)))}: json_parse_failed: {e}")
            else:
                if reg.get("schema_version") != "scc.patterns_registry.v1":
                    errors.append("patterns/registry.json: schema_version != scc.patterns_registry.v1")
                if "patterns" not in reg or not isinstance(reg.get("patterns"), list):
                    errors.append("patterns/registry.json: missing key patterns")
                else:
                    for it in reg.get("patterns")[:800]:
                        if not isinstance(it, dict):
                            errors.append("patterns/registry.json: invalid pattern entry")
                            continue
                        pid = it.get("pattern_id")
                        pth = it.get("path")
                        if not pid or not pth:
                            errors.append("patterns/registry.json: entry missing pattern_id/path")
                            continue
                        if not (repo / norm_rel(str(pth))).exists():
                            errors.append(f"patterns/registry.json: missing file {pth}")

        for p in sorted(patterns_dir.glob("*.json"))[:200]:
            if p.name in {"auto_summary.json"}:
                continue
            if p.name == "registry.json":
                continue
            try:
                data = load_json(p)
            except Exception as e:
                errors.append(f"{norm_rel(str(p.relative_to(repo)))}: json_parse_failed: {e}")
                continue
            if data.get("schema_version") != "scc.pattern.v1":
                errors.append(f"{norm_rel(str(p.relative_to(repo)))}: schema_version != scc.pattern.v1")
            for k in ("pattern_id", "created_at", "match", "stats"):
                if k not in data:
                    errors.append(f"{norm_rel(str(p.relative_to(repo)))}: missing key {k}")

    # Skills drafts registry + basic validation (L8 assets, deterministic)
    drafts_dir = repo / "skills_drafts"
    if drafts_dir.exists():
        reg_path = drafts_dir / "registry.json"
        if not reg_path.exists():
            errors.append("missing skills_drafts/registry.json")
        else:
            try:
                reg = load_json(reg_path)
            except Exception as e:
                errors.append(f"{norm_rel(str(reg_path.relative_to(repo)))}: json_parse_failed: {e}")
            else:
                if reg.get("schema_version") != "scc.skills_drafts_registry.v1":
                    errors.append("skills_drafts/registry.json: schema_version != scc.skills_drafts_registry.v1")
                if "skills" not in reg or not isinstance(reg.get("skills"), list):
                    errors.append("skills_drafts/registry.json: missing key skills")
                else:
                    for it in reg.get("skills")[:800]:
                        if not isinstance(it, dict):
                            errors.append("skills_drafts/registry.json: invalid skill entry")
                            continue
                        sid = it.get("skill_id")
                        pth = it.get("path")
                        if not sid or not pth:
                            errors.append("skills_drafts/registry.json: entry missing skill_id/path")
                            continue
                        if not (repo / norm_rel(str(pth))).exists():
                            errors.append(f"skills_drafts/registry.json: missing file {pth}")

        for p in sorted(drafts_dir.glob("*.json"))[:200]:
            if p.name == "registry.json":
                continue
            try:
                data = load_json(p)
            except Exception as e:
                errors.append(f"{norm_rel(str(p.relative_to(repo)))}: json_parse_failed: {e}")
                continue
            if data.get("schema_version") != "scc.skill.v1":
                errors.append(f"{norm_rel(str(p.relative_to(repo)))}: schema_version != scc.skill.v1")
            for k in ("skill_id", "version", "owner_role", "summary", "contracts", "enablement"):
                if k not in data:
                    errors.append(f"{norm_rel(str(p.relative_to(repo)))}: missing key {k}")

    playbooks_dir = repo / "playbooks"
    if playbooks_dir.exists():
        registry_path = playbooks_dir / "registry.json"
        if registry_path.exists():
            try:
                reg = load_json(registry_path)
            except Exception as e:
                errors.append(f"{norm_rel(str(registry_path.relative_to(repo)))}: json_parse_failed: {e}")
            else:
                if reg.get("schema_version") != "scc.playbooks_registry.v1":
                    errors.append("playbooks/registry.json: schema_version != scc.playbooks_registry.v1")
                if "playbooks" not in reg or not isinstance(reg.get("playbooks"), list):
                    errors.append("playbooks/registry.json: missing key playbooks")
                else:
                    for it in reg.get("playbooks")[:400]:
                        if not isinstance(it, dict):
                            errors.append("playbooks/registry.json: invalid playbook entry")
                            continue
                        pid = it.get("playbook_id")
                        pth = it.get("path")
                        if not pid or not pth:
                            errors.append("playbooks/registry.json: entry missing playbook_id/path")
                            continue
                        if not (repo / norm_rel(str(pth))).exists():
                            errors.append(f"playbooks/registry.json: missing file {pth}")

        for p in sorted(playbooks_dir.glob("*.json"))[:200]:
            if p.name == "overrides.json":
                try:
                    data = load_json(p)
                except Exception as e:
                    errors.append(f"{norm_rel(str(p.relative_to(repo)))}: json_parse_failed: {e}")
                    continue
                if data.get("schema_version") != "scc.playbook_overrides.v1":
                    errors.append(f"{norm_rel(str(p.relative_to(repo)))}: schema_version != scc.playbook_overrides.v1")
                if "overrides" not in data:
                    errors.append(f"{_norm_rel(str(p.relative_to(repo)))}: missing key overrides")
                continue
            if p.name == "registry.json":
                continue
            try:
                data = load_json(p)
            except Exception as e:
                errors.append(f"{norm_rel(str(p.relative_to(repo)))}: json_parse_failed: {e}")
                continue
            if data.get("schema_version") != "scc.playbook.v1":
                errors.append(f"{norm_rel(str(p.relative_to(repo)))}: schema_version != scc.playbook.v1")
            for k in ("playbook_id", "version", "pattern_id", "enablement", "actions"):
                if k not in data:
                    errors.append(f"{norm_rel(str(p.relative_to(repo)))}: missing key {k}")
            enablement = data.get("enablement") if isinstance(data, dict) else None
            if isinstance(enablement, dict) and enablement.get("schema_version") != "scc.enablement.v1":
                errors.append(f"{norm_rel(str(p.relative_to(repo)))}: enablement.schema_version != scc.enablement.v1")

    return errors
