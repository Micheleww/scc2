#!/usr/bin/env python3
import glob
import hashlib
import json
import os
from datetime import datetime


def calculate_sha256(file_path):
    """计算文件的 SHA256 哈希值"""
    sha256_hash = hashlib.sha256()
    try:
        with open(file_path, "rb") as f:
            # 读取文件内容，分块处理以支持大文件
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256_hash.update(byte_block)
        return sha256_hash.hexdigest()
    except (OSError, PermissionError) as e:
        print(f"[ERROR] 无法读取文件 {file_path}: {e}")
        raise


def get_protected_files(protected_globs):
    """获取所有受保护的文件路径"""
    protected_files = set()
    for glob_pattern in protected_globs:
        files = glob.glob(glob_pattern, recursive=True)
        if not files:
            print(f"[ERROR] Glob 模式 '{glob_pattern}' 没有匹配到任何文件")
            raise ValueError(f"Glob 模式 '{glob_pattern}' 没有匹配到任何文件")
        for file in files:
            if os.path.isfile(file):
                # Normalize to repo-relative POSIX-style paths for cross-platform stability.
                protected_files.add(file.replace("\\", "/"))
    return sorted(protected_files)


def write_manifest(manifest_path):
    """生成并写入 Manifest 文件"""
    try:
        # 读取现有的 manifest 文件
        with open(manifest_path, encoding="utf-8", errors="replace") as f:
            manifest_data = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        print(f"[ERROR] 无法读取或解析 Manifest 文件 {manifest_path}: {e}")
        return 1

    # 确保 manifest 结构包含必要字段
    if "protected_globs" not in manifest_data:
        manifest_data["protected_globs"] = [
            "law/**",
            "tools/gatekeeper/*.py",
            "configs/current/qcc_manifest.json",
            "configs/current/import_rules.yaml",
            "configs/current/law_pointer_rules.yaml",
            ".pre-commit-config.yaml",
            ".github/workflows/qcc-gate.yml",
            "docs/REPORT/artifacts/qcc_gatekeeper/**",
        ]

    if "entries" not in manifest_data:
        manifest_data["entries"] = {}

    # 更新版本信息
    manifest_data["version"] = "0.4.0"
    manifest_data["qcc_version"] = "R04"
    manifest_data["updated_at"] = datetime.utcnow().isoformat() + "Z"
    if manifest_data["created_at"] is None:
        manifest_data["created_at"] = manifest_data["updated_at"]

    try:
        # 获取所有受保护文件
        manifest_path_norm = manifest_path.replace("\\", "/")
        protected_files = get_protected_files(manifest_data["protected_globs"])

        # 计算每个文件的哈希值并更新 entries
        entries = {}
        for file_path in protected_files:
            # 跳过 manifest 文件本身，最后单独处理
            if file_path == manifest_path_norm:
                continue
            sha256 = calculate_sha256(file_path)
            entries[file_path] = sha256

        # 保存临时 entries（不含 manifest 本身）
        manifest_data["entries"] = entries

        # 写入临时 manifest 文件
        with open(manifest_path, "w", encoding="utf-8", errors="replace") as f:
            json.dump(manifest_data, f, indent=2, ensure_ascii=False)

        # 重新计算 manifest 文件本身的哈希值
        manifest_sha256 = calculate_sha256(manifest_path)

        # 再次读取并更新 manifest 文件，加入自身哈希
        with open(manifest_path, encoding="utf-8", errors="replace") as f:
            manifest_data = json.load(f)

        # 添加 manifest 自身的哈希
        manifest_data["entries"][manifest_path_norm] = manifest_sha256

        # 最终写入
        with open(manifest_path, "w", encoding="utf-8", errors="replace") as f:
            json.dump(manifest_data, f, indent=2, ensure_ascii=False)

        print(f"[SUCCESS] Manifest 已成功更新到 {manifest_path}")
        print(f"[INFO] 共处理 {len(manifest_data['entries'])} 个受保护文件")
        return 0
    except Exception as e:
        print(f"[ERROR] 生成 Manifest 失败: {e}")
        return 1


def check_manifest(manifest_path):
    """检查 Manifest 文件的完整性"""
    try:
        # 读取 manifest 文件
        with open(manifest_path, encoding="utf-8", errors="replace") as f:
            manifest_data = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        print(f"[ERROR] 无法读取或解析 Manifest 文件 {manifest_path}: {e}")
        return 1

    # 验证必要字段存在
    if "protected_globs" not in manifest_data or "entries" not in manifest_data:
        print(f"[ERROR] Manifest 文件 {manifest_path} 结构不完整，缺少必要字段")
        return 1

    try:
        # 获取所有受保护文件
        protected_files = get_protected_files(manifest_data["protected_globs"])
        entries = manifest_data["entries"]

        # 检查每个文件
        missing_files = []
        mismatch_files = []

        for file_path in protected_files:
            if file_path not in entries:
                missing_files.append(file_path)
                continue

            current_sha256 = calculate_sha256(file_path)
            expected_sha256 = entries[file_path]
            if current_sha256 != expected_sha256:
                mismatch_files.append(file_path)

        # 检查 entries 中是否有不存在的文件
        extra_files = [file_path for file_path in entries if not os.path.exists(file_path)]

        # 输出结果
        if not missing_files and not mismatch_files and not extra_files:
            print(f"[SUCCESS] Manifest 检查通过，所有 {len(entries)} 个文件完整")
            return 0
        else:
            print("[ERROR] Manifest 检查失败")
            if missing_files:
                print("[ERROR] 以下文件在 Manifest 中缺失:")
                for file_path in missing_files:
                    print(f"  - {file_path}")
            if mismatch_files:
                print("[ERROR] 以下文件哈希值不匹配:")
                for file_path in mismatch_files:
                    print(f"  - {file_path}")
            if extra_files:
                print("[ERROR] 以下文件在 Manifest 中存在但实际不存在:")
                for file_path in extra_files:
                    print(f"  - {file_path}")
            return 1
    except Exception as e:
        print(f"[ERROR] 检查 Manifest 失败: {e}")
        return 1


if __name__ == "__main__":
    import sys

    if len(sys.argv) != 3:
        print("Usage: python -m tools.gatekeeper.manifest <--write|--check> <manifest_path>")
        sys.exit(1)

    command = sys.argv[1]
    manifest_path = sys.argv[2]

    if command == "--write":
        sys.exit(write_manifest(manifest_path))
    elif command == "--check":
        sys.exit(check_manifest(manifest_path))
    else:
        print(f"Unknown command: {command}")
        sys.exit(1)
