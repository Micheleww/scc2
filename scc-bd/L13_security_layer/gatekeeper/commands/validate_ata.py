#!/usr/bin/env python3
"""
ATA 校验子命令

功能：
1. 校验 ATA context.json 文件的存在性和完整性
2. 执行 schema 校验（v0.2 严格模式，v0.1 兼容模式）
3. 验证 evidence_paths 中的路径是否存在且为相对路径
4. 检查绝对路径
5. 处理 schema 版本兼容性

使用方法：
python -m tools.gatekeeper validate-ata --path <context.json_path>
"""

import json
import os

from jsonschema import ValidationError as SchemaValidationError
from jsonschema import validate

# 获取项目根目录
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))

# 加载 ATA schema
SCHEMA_PATH = os.path.join(
    PROJECT_ROOT, "tools", "gatekeeper", "schemas", "ata_context.schema.json"
)
with open(SCHEMA_PATH, encoding="utf-8") as f:
    ATA_SCHEMA = json.load(f)


def validate_agent_registry_invariants():
    """
    CI-hard-gate: validate agent registry invariants so CI and MCP hard gates stay aligned.
    - numeric_code must be int in [1,100] when present
    - numeric_code must be unique across agents
    - send_enabled must be boolean when present
    """
    registry_path = os.path.join(PROJECT_ROOT, ".cursor", "agent_registry.json")
    if not os.path.exists(registry_path):
        print("WARNING: agent_registry.json not found; skip agent registry invariants check")
        return True, "AGENT_REGISTRY_NOT_FOUND"
    try:
        with open(registry_path, encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        print(f"ERROR: Failed to load agent_registry.json: {e}")
        return False, "AGENT_REGISTRY_INVALID_JSON"

    agents = data.get("agents", {})
    if not isinstance(agents, dict):
        print("ERROR: agent_registry.json: agents must be an object")
        return False, "AGENT_REGISTRY_INVALID_FORMAT"

    used = {}
    for agent_id, agent_data in agents.items():
        if not isinstance(agent_id, str) or not agent_id.strip():
            print("ERROR: agent_registry.json: agent_id must be non-empty string")
            return False, "AGENT_REGISTRY_INVALID_AGENT_ID"
        if not isinstance(agent_data, dict):
            print(f"ERROR: agent_registry.json: agent entry must be object: {agent_id}")
            return False, "AGENT_REGISTRY_INVALID_AGENT_ENTRY"

        # send_enabled must be boolean when present
        if "send_enabled" in agent_data and not isinstance(agent_data["send_enabled"], bool):
            print(f"ERROR: agent_registry.json: send_enabled must be boolean: {agent_id}")
            return False, "AGENT_REGISTRY_SEND_ENABLED_INVALID"

        # numeric_code invariants
        code = agent_data.get("numeric_code", None)
        if code is None:
            continue
        if not isinstance(code, int):
            print(f"ERROR: agent_registry.json: numeric_code must be integer: {agent_id} -> {code}")
            return False, "AGENT_REGISTRY_NUMERIC_CODE_TYPE"
        if not (1 <= code <= 100):
            print(f"ERROR: agent_registry.json: numeric_code out of range: {agent_id} -> {code}")
            return False, "AGENT_REGISTRY_NUMERIC_CODE_RANGE"
        if code in used and used[code] != agent_id:
            print(
                f"ERROR: agent_registry.json: numeric_code duplicate: {code} used by {used[code]} and {agent_id}"
            )
            return False, "AGENT_REGISTRY_NUMERIC_CODE_DUPLICATE"
        used[code] = agent_id

    print("SUCCESS: agent_registry.json invariants check passed")
    return True, "SUCCESS"


def is_absolute_path(path):
    """检查路径是否为绝对路径（支持 Windows 和 POSIX）"""
    # Windows 绝对路径：以驱动器号开头，如 C:\ 或 C:/
    if os.name == "nt":
        return os.path.isabs(path) or (len(path) > 1 and path[1] == ":")
    # POSIX 绝对路径：以 / 开头
    else:
        return os.path.isabs(path) or path.startswith("/")


def validate_ata_context(context_path):
    """校验单个 ATA context.json 文件"""
    print(f"Validating ATA context: {context_path}")

    # 1. 检查文件是否存在且非空
    if not os.path.exists(context_path):
        print(f"ERROR: ATA context file not found: {context_path}")
        return False, "ATA_CONTEXT_NOT_FOUND"

    if os.path.getsize(context_path) == 0:
        print(f"ERROR: ATA context file is empty: {context_path}")
        return False, "ATA_CONTEXT_EMPTY"

    # 2. 加载并解析 JSON
    try:
        with open(context_path, encoding="utf-8") as f:
            context = json.load(f)
    except json.JSONDecodeError as e:
        print(f"ERROR: Invalid JSON in ATA context: {e}")
        return False, "ATA_CONTEXT_INVALID_JSON"

    # 3. 获取 schema 版本
    schema_version = context.get("schema_version", "v0.1")

    # 4. 版本处理逻辑
    if schema_version == "v0.1":
        # 兼容模式：v0.1 可以被读取，但必须提示 deprecated_schema
        print(f"WARNING: Deprecated schema version 'v0.1' detected in {context_path}")
        print("WARNING: Please upgrade to schema version 'v0.2' - reason_code=deprecated_schema")

        # v0.1 兼容验证：检查所有 v0.2 强制字段是否存在
        required_fields = [
            "task_code",
            "date",
            "owner_role",
            "goal",
            "scope_files",
            "how_to_repro",
            "expected",
            "actual",
            "next_actions",
            "evidence_paths",
            "rollback",
        ]

        for field in required_fields:
            if field not in context:
                print(f"ERROR: Missing required field '{field}' in v0.1 schema")
                return False, "ATA_SCHEMA_VALIDATION_FAILED"

    # 5. 执行 schema 校验（严格模式，适用于 v0.2 和 v0.1 兼容模式）
    try:
        validate(instance=context, schema=ATA_SCHEMA)
    except SchemaValidationError as e:
        print(f"ERROR: Schema validation failed: {e}")
        return False, "ATA_SCHEMA_VALIDATION_FAILED"

    # 6. 校验 evidence_paths 必须存在且非空
    evidence_paths = context.get("evidence_paths", [])
    if not isinstance(evidence_paths, list):
        print("ERROR: evidence_paths must be an array")
        return False, "ATA_EVIDENCE_PATHS_INVALID"

    if len(evidence_paths) == 0:
        print("ERROR: evidence_paths must not be empty")
        return False, "ATA_EVIDENCE_PATHS_EMPTY"

    # 7. 校验 evidence_paths 中的路径
    for path in evidence_paths:
        # 检查是否为绝对路径
        if is_absolute_path(path):
            print(f"ERROR: Absolute path in evidence_paths: {path}")
            print("ERROR: evidence_paths must contain only repo_root relative paths")
            return False, "ATA_ABSOLUTE_PATH"

        # 检查路径是否存在
        full_path = os.path.join(PROJECT_ROOT, path)
        if not os.path.exists(full_path):
            print(f"ERROR: Evidence path not found: {path}")
            return False, "ATA_EVIDENCE_PATH_NOT_FOUND"

    # 8. 检查 scope_files 中的绝对路径
    scope_files = context.get("scope_files", [])
    if not isinstance(scope_files, list):
        print("ERROR: scope_files must be an array")
        return False, "ATA_SCOPE_FILES_INVALID"

    for path in scope_files:
        if is_absolute_path(path):
            print(f"ERROR: Absolute path in scope_files: {path}")
            return False, "ATA_ABSOLUTE_PATH"

    print(f"SUCCESS: ATA context validation passed: {context_path}")
    return True, "SUCCESS"


def find_ata_context_files():
    """
    查找 ATA context.json 文件。

    CI 集成（推荐）：当环境变量 TASK_CODE 与 AREA 存在时，仅校验当前任务的：
      docs/REPORT/<AREA>/artifacts/<TASK_CODE>/ata/context.json

    兼容模式：若未提供 TASK_CODE/AREA，则回退为扫描 docs/REPORT/**/artifacts/**/ata/context.json。
    """
    context_files = []
    report_dir = os.path.join(PROJECT_ROOT, "docs", "REPORT")

    if not os.path.exists(report_dir):
        return context_files

    # Prefer deterministic, task-scoped validation in CI.
    task_code = os.environ.get("TASK_CODE", "").strip()
    area_env = os.environ.get("AREA", "").strip()
    if task_code and area_env:
        scoped = os.path.join(report_dir, area_env, "artifacts", task_code, "ata", "context.json")
        if os.path.exists(scoped):
            return [scoped]
        # If the current task did not produce an ATA context, treat as "no contexts found" (PASS in validator).
        return []

    # 遍历 docs/REPORT 目录下的所有 area
    for area in os.listdir(report_dir):
        area_path = os.path.join(report_dir, area)
        if not os.path.isdir(area_path):
            continue

        # 遍历 artifacts 目录
        artifacts_path = os.path.join(area_path, "artifacts")
        if not os.path.exists(artifacts_path):
            continue

        # 遍历所有 TaskCode 目录
        for task_code in os.listdir(artifacts_path):
            task_code_path = os.path.join(artifacts_path, task_code)
            if not os.path.isdir(task_code_path):
                continue

            # 检查 ata/context.json 是否存在
            context_path = os.path.join(task_code_path, "ata", "context.json")
            if os.path.exists(context_path):
                context_files.append(context_path)

    return context_files


def validate_all_ata_contexts():
    """校验所有 ATA context.json 文件"""
    # 0) Agent registry invariants (keep CI aligned with MCP hard gates)
    reg_ok, reg_reason = validate_agent_registry_invariants()
    if not reg_ok:
        return False, reg_reason

    context_files = find_ata_context_files()

    if not context_files:
        print("WARNING: No ATA context files found")
        return True, "ATA_NO_CONTEXT_FILES"

    all_passed = True
    for context_file in context_files:
        passed, reason_code = validate_ata_context(context_file)
        if not passed:
            all_passed = False

    return all_passed, "SUCCESS" if all_passed else "ATA_VALIDATION_FAILED"


def main(args):
    """主函数"""
    if args.path:
        # 校验单个文件
        passed, reason_code = validate_ata_context(args.path)
        exit(0 if passed else 1)
    else:
        # 校验所有文件
        passed, reason_code = validate_all_ata_contexts()
        exit(0 if passed else 1)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="ATA 校验工具")
    parser.add_argument("--path", type=str, help="ATA context.json 文件路径")

    args = parser.parse_args()
    main(args)
