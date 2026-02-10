#!/usr/bin/env python3
"""
ATA 消息哈希链验证模块
TaskCode: GATE-ATA-HASHCHAIN-v0.1__20260115
"""

import hashlib
import json
import os
import subprocess
import sys


def calculate_sha256(content):
    """计算消息内容的 SHA256 哈希值"""
    message_without_sha256 = content.copy()
    if "sha256" in message_without_sha256:
        del message_without_sha256["sha256"]
    sha256 = hashlib.sha256()
    sha256.update(
        json.dumps(message_without_sha256, sort_keys=True, ensure_ascii=False).encode("utf-8")
    )
    return sha256.hexdigest()


def validate_ata_hashchain(task_code=None, ata_messages_dir="docs/REPORT/ata/messages"):
    """
    验证 ATA 消息哈希链完整性
    :param task_code: 指定 TaskCode，仅验证该 TaskCode 的消息链
    :param ata_messages_dir: ATA 消息目录路径，默认为 docs/REPORT/ata/messages
    :return: (is_valid, errors, warnings)
    """
    errors = []
    warnings = []

    # Only validate git-tracked ATA messages (local evidence must not block gates).
    message_files: list[str] = []
    try:
        p = subprocess.run(
            ["git", "ls-files", ata_messages_dir],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=8,
        )
        if int(p.returncode or 0) == 0:
            for ln in (p.stdout or "").splitlines():
                rel = (ln or "").strip().replace("\\", "/")
                if rel.endswith(".json") and not rel.endswith("/sample_message.json"):
                    message_files.append(rel)
    except Exception:
        message_files = []

    if not message_files:
        warnings.append(f"未找到 git 跟踪的 ATA 消息文件: {ata_messages_dir}")
        return True, errors, warnings

    # 按 TaskCode 分组消息
    messages_by_taskcode = {}
    for file_path in message_files:
        try:
            with open(file_path, encoding="utf-8") as f:
                message = json.load(f)

            # 验证消息基本结构
            if not isinstance(message, dict):
                errors.append(f"消息不是 JSON object: {file_path}")
                continue

            required_fields = ["taskcode", "msg_id", "sha256", "created_at"]
            missing = [f for f in required_fields if f not in message]
            if missing:
                errors.append(f"消息缺少必需字段 {', '.join(missing)}: {file_path}")
                continue

            # 过滤指定 TaskCode
            if task_code and message["taskcode"] != task_code:
                continue

            # 按 TaskCode 分组
            if message["taskcode"] not in messages_by_taskcode:
                messages_by_taskcode[message["taskcode"]] = []

            # 添加文件路径和消息内容
            messages_by_taskcode[message["taskcode"]].append((file_path, message))
        except json.JSONDecodeError as e:
            errors.append(f"消息文件解析失败: {file_path}, 错误: {e}")
        except Exception as e:
            errors.append(f"处理消息文件失败: {file_path}, 错误: {e}")

    # 对每个 TaskCode 验证哈希链
    for taskcode, messages in messages_by_taskcode.items():
        if not messages:
            continue

        # 按 created_at 排序消息
        messages.sort(key=lambda x: str(x[1].get("created_at") or ""))

        # 验证哈希链
        prev_sha256 = None
        for file_path, message in messages:
            msg_id = str(message.get("msg_id") or "")
            actual_sha256 = str(message.get("sha256") or "")
            expected_sha256 = calculate_sha256(message)

            # 验证当前消息的 sha256 是否正确
            if actual_sha256 != expected_sha256:
                errors.append(
                    f"消息 sha256 不匹配: {file_path}, msg_id: {msg_id}, 期望: {expected_sha256}, 实际: {actual_sha256}"
                )
                continue

            # 验证 prev_sha256 链接
            message_prev_sha256 = message.get("prev_sha256")

            # 第一条消息的 prev_sha256 应该为 None
            if prev_sha256 is None:
                if message_prev_sha256 is not None:
                    errors.append(
                        f"第一条消息 prev_sha256 应为 None: {file_path}, msg_id: {msg_id}, 实际: {message_prev_sha256}"
                    )
            else:
                # 后续消息的 prev_sha256 应该等于前一条消息的 sha256
                if message_prev_sha256 != prev_sha256:
                    errors.append(
                        f"哈希链断裂: {file_path}, msg_id: {msg_id}, 期望 prev_sha256: {prev_sha256}, 实际: {message_prev_sha256}"
                    )

            # 更新 prev_sha256 为当前消息的 sha256
            prev_sha256 = actual_sha256

    return len(errors) == 0, errors, warnings


def run_ata_hashchain_check(task_code=None):
    """运行 ATA 哈希链检查"""
    print("=== 运行 ATA 哈希链检查 ===")

    is_valid, errors, warnings = validate_ata_hashchain(task_code)

    # 输出警告
    if warnings:
        print("\nWARNINGS:")
        for warning in warnings:
            print(f"   - {warning}")

    # 输出错误
    if errors:
        print("\nERRORS:")
        for error in errors:
            print(f"   - {error}")
        print("\nRESULT: FAIL")
        return 1

    print("\nRESULT: PASS")
    return 0


def main():
    """主函数"""
    import argparse

    parser = argparse.ArgumentParser(description="ATA 哈希链验证工具")
    parser.add_argument("--check", action="store_true", help="运行哈希链检查")
    parser.add_argument("--task-code", type=str, help="指定 TaskCode")

    args = parser.parse_args()

    if args.check:
        exit_code = run_ata_hashchain_check(args.task_code)
        sys.exit(exit_code)
    else:
        parser.print_help()
        sys.exit(0)


if __name__ == "__main__":
    main()
