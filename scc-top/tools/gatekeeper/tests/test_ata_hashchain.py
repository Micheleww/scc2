#!/usr/bin/env python3
"""
ATA 哈希链回归测试脚本
TaskCode: GATE-ATA-HASHCHAIN-v0.1__20260115
"""

import json
import os
import shutil
import sys
import tempfile

# 添加项目根目录到 Python 路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from tools.gatekeeper.ata_hashchain import validate_ata_hashchain


def test_ata_hashchain_broken():
    """测试断链情况 - 应该 FAIL"""
    print("\n=== 测试 1: ATA 哈希链断链情况 ===")

    temp_dir = tempfile.mkdtemp()
    ata_messages_dir = os.path.join(temp_dir, "ata", "messages", "TEST-TASK-v0.1__20260115")
    os.makedirs(ata_messages_dir, exist_ok=True)

    # 创建第一条消息
    msg1 = {
        "msg_id": "TEST-MSG-001",
        "taskcode": "TEST-TASK-v0.1__20260115",
        "from_agent": "test-agent",
        "to_agent": "test-agent",
        "created_at": "2026-01-15T10:00:00Z",
        "kind": "test",
        "payload": {"test": "message1"},
        "prev_sha256": None,
    }

    # 计算 sha256
    from tools.gatekeeper.ata_hashchain import calculate_sha256

    msg1["sha256"] = calculate_sha256(msg1)

    # 创建第二条消息，但是 prev_sha256 不正确（断链）
    msg2 = {
        "msg_id": "TEST-MSG-002",
        "taskcode": "TEST-TASK-v0.1__20260115",
        "from_agent": "test-agent",
        "to_agent": "test-agent",
        "created_at": "2026-01-15T10:05:00Z",
        "kind": "test",
        "payload": {"test": "message2"},
        "prev_sha256": "invalid_prev_sha256",  # 故意设置错误的 prev_sha256
    }
    msg2["sha256"] = calculate_sha256(msg2)

    # 写入消息文件
    with open(os.path.join(ata_messages_dir, "msg_001.json"), "w", encoding="utf-8") as f:
        json.dump(msg1, f, indent=2, ensure_ascii=False)

    with open(os.path.join(ata_messages_dir, "msg_002.json"), "w", encoding="utf-8") as f:
        json.dump(msg2, f, indent=2, ensure_ascii=False)

    # 保存原始的 ata_messages_dir 路径
    original_dir = os.getcwd()

    try:
        # 运行验证，直接传递 ATA 消息目录路径
        is_valid, errors, warnings = validate_ata_hashchain(
            "TEST-TASK-v0.1__20260115", ata_messages_dir=os.path.join(temp_dir, "ata", "messages")
        )

        # 断言结果
        assert not is_valid, "哈希链断链时应该返回 False"
        assert any("哈希链断裂" in error for error in errors), "应该包含 '哈希链断裂' 错误"

        print("✅ 测试通过: 哈希链断链时返回 FAIL")
        return True
    finally:
        # 恢复原始工作目录
        os.chdir(original_dir)
        shutil.rmtree(temp_dir)


def test_ata_hashchain_continuous():
    """测试连续链情况 - 应该 PASS"""
    print("\n=== 测试 2: ATA 哈希链连续情况 ===")

    temp_dir = tempfile.mkdtemp()
    ata_messages_dir = os.path.join(temp_dir, "ata", "messages", "TEST-TASK-v0.1__20260115")
    os.makedirs(ata_messages_dir, exist_ok=True)

    # 创建第一条消息
    msg1 = {
        "msg_id": "TEST-MSG-001",
        "taskcode": "TEST-TASK-v0.1__20260115",
        "from_agent": "test-agent",
        "to_agent": "test-agent",
        "created_at": "2026-01-15T10:00:00Z",
        "kind": "test",
        "payload": {"test": "message1"},
        "prev_sha256": None,
    }

    # 计算 sha256
    from tools.gatekeeper.ata_hashchain import calculate_sha256

    msg1["sha256"] = calculate_sha256(msg1)

    # 创建第二条消息，使用正确的 prev_sha256
    msg2 = {
        "msg_id": "TEST-MSG-002",
        "taskcode": "TEST-TASK-v0.1__20260115",
        "from_agent": "test-agent",
        "to_agent": "test-agent",
        "created_at": "2026-01-15T10:05:00Z",
        "kind": "test",
        "payload": {"test": "message2"},
        "prev_sha256": msg1["sha256"],
    }
    msg2["sha256"] = calculate_sha256(msg2)

    # 创建第三条消息，使用正确的 prev_sha256
    msg3 = {
        "msg_id": "TEST-MSG-003",
        "taskcode": "TEST-TASK-v0.1__20260115",
        "from_agent": "test-agent",
        "to_agent": "test-agent",
        "created_at": "2026-01-15T10:10:00Z",
        "kind": "test",
        "payload": {"test": "message3"},
        "prev_sha256": msg2["sha256"],
    }
    msg3["sha256"] = calculate_sha256(msg3)

    # 写入消息文件
    with open(os.path.join(ata_messages_dir, "msg_001.json"), "w", encoding="utf-8") as f:
        json.dump(msg1, f, indent=2, ensure_ascii=False)

    with open(os.path.join(ata_messages_dir, "msg_002.json"), "w", encoding="utf-8") as f:
        json.dump(msg2, f, indent=2, ensure_ascii=False)

    with open(os.path.join(ata_messages_dir, "msg_003.json"), "w", encoding="utf-8") as f:
        json.dump(msg3, f, indent=2, ensure_ascii=False)

    # 保存原始的 ata_messages_dir 路径
    original_dir = os.getcwd()

    try:
        # 运行验证，直接传递 ATA 消息目录路径
        is_valid, errors, warnings = validate_ata_hashchain(
            "TEST-TASK-v0.1__20260115", ata_messages_dir=os.path.join(temp_dir, "ata", "messages")
        )

        # 断言结果
        assert is_valid, "连续哈希链时应该返回 True"
        assert len(errors) == 0, "连续哈希链不应该有错误"

        print("✅ 测试通过: 连续哈希链时返回 PASS")
        return True
    finally:
        # 恢复原始工作目录
        os.chdir(original_dir)
        shutil.rmtree(temp_dir)


def run_all_tests():
    """运行所有测试"""
    print("=== 开始 ATA 哈希链回归测试 ===")

    tests = [test_ata_hashchain_broken, test_ata_hashchain_continuous]

    passed = 0
    failed = 0

    for test in tests:
        try:
            if test():
                passed += 1
            else:
                failed += 1
        except Exception as e:
            print(f"\n❌ 测试失败: {test.__name__}")
            print(f"   错误信息: {e}")
            failed += 1

    print("\n=== 测试结果总结 ===")
    print(f"通过测试: {passed}")
    print(f"失败测试: {failed}")

    if failed == 0:
        print("\n🎉 所有测试通过!")
        return 0
    else:
        print(f"\n💥 有 {failed} 个测试失败")
        return 1


if __name__ == "__main__":
    exit_code = run_all_tests()
    sys.exit(exit_code)
