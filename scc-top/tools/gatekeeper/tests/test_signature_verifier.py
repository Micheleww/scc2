#!/usr/bin/env python3
"""
签名验证适配器层测试
"""

import hashlib
import json
import os
import shutil
import subprocess

# 添加项目根目录到Python路径
import sys
import tempfile

sys.path.insert(0, "d:/quantsys")

from tools.gatekeeper.reason_codes import GateReasonCode
from tools.gatekeeper.signature_verifier import (
    KMSSignatureVerifier,
    LocalSignatureVerifier,
    SignatureVerifierFactory,
)


def calculate_file_hash(file_path):
    """计算文件的SHA256哈希值"""
    with open(file_path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def test_local_signature_verifier():
    """测试本地签名验证器"""
    print("=== 测试本地签名验证器 ===")

    # 创建临时目录
    temp_dir = tempfile.mkdtemp()
    original_cwd = os.getcwd()

    try:
        os.chdir(temp_dir)
        verifier = LocalSignatureVerifier()
        rules = {"enabled": True}

        # 测试1: 缺少签名映射文件
        print("\n1. 测试缺少签名映射文件")
        exit_code, reason_code, message = verifier.verify_signatures("sha256_map.json", rules)
        print(f"结果: {exit_code}, 原因码: {reason_code}, 消息: {message}")
        assert exit_code == 1, "测试1失败: 缺少签名映射文件应该返回非0值"
        assert reason_code == GateReasonCode.MISSING_SIGNATURE_MAP, (
            "测试1失败: 原因码应该是 MISSING_SIGNATURE_MAP"
        )

        # 测试2: 正常情况 - 签名验证通过
        print("\n2. 测试签名验证通过")

        # 创建测试文件
        test_file = "test_file.txt"
        with open(test_file, "w") as f:
            f.write("test content")

        # 计算测试文件的哈希值
        test_file_hash = calculate_file_hash(test_file)

        # 创建sha256_map.json文件
        signature_map = {test_file: test_file_hash}
        with open("sha256_map.json", "w") as f:
            json.dump(signature_map, f)

        exit_code, reason_code, message = verifier.verify_signatures("sha256_map.json", rules)
        print(f"结果: {exit_code}, 原因码: {reason_code}, 消息: {message}")
        assert exit_code == 0, "测试2失败: 签名验证通过应该返回0值"
        assert reason_code == GateReasonCode.SUCCESS, "测试2失败: 原因码应该是 SUCCESS"

        # 测试3: 签名验证失败 - 文件内容被篡改
        print("\n3. 测试签名验证失败 - 文件内容被篡改")

        # 修改测试文件内容
        with open(test_file, "w") as f:
            f.write("modified content")

        exit_code, reason_code, message = verifier.verify_signatures("sha256_map.json", rules)
        print(f"结果: {exit_code}, 原因码: {reason_code}, 消息: {message}")
        assert exit_code == 1, "测试3失败: 签名验证失败应该返回非0值"
        assert reason_code == GateReasonCode.INVALID_SIGNATURE, (
            "测试3失败: 原因码应该是 INVALID_SIGNATURE"
        )

        # 测试4: 禁用签名验证
        print("\n4. 测试禁用签名验证")
        rules = {"enabled": False}
        exit_code, reason_code, message = verifier.verify_signatures("sha256_map.json", rules)
        print(f"结果: {exit_code}, 原因码: {reason_code}, 消息: {message}")
        assert exit_code == 0, "测试4失败: 禁用签名验证应该返回0值"

        print("\n本地签名验证器测试通过!")
        return True

    except Exception as e:
        print(f"\n测试失败: {e}")
        import traceback

        traceback.print_exc()
        return False
    finally:
        os.chdir(original_cwd)
        shutil.rmtree(temp_dir)


def test_kms_signature_verifier():
    """测试KMS签名验证器"""
    print("\n=== 测试KMS签名验证器 ===")

    # 创建临时目录
    temp_dir = tempfile.mkdtemp()
    original_cwd = os.getcwd()

    try:
        os.chdir(temp_dir)
        rules = {"enabled": True}

        # 测试1: 缺少签名映射文件
        print("\n1. 测试缺少签名映射文件")
        verifier = KMSSignatureVerifier()
        exit_code, reason_code, message = verifier.verify_signatures("sha256_map.json", rules)
        print(f"结果: {exit_code}, 原因码: {reason_code}, 消息: {message}")
        assert exit_code == 1, "测试1失败: 缺少签名映射文件应该返回非0值"
        assert reason_code == GateReasonCode.MISSING_SIGNATURE_MAP, (
            "测试1失败: 原因码应该是 MISSING_SIGNATURE_MAP"
        )

        # 测试2: 正常情况 - 签名验证通过
        print("\n2. 测试签名验证通过")

        # 创建测试文件
        test_file = "test_file.txt"
        with open(test_file, "w") as f:
            f.write("test content")

        # 计算测试文件的哈希值
        test_file_hash = calculate_file_hash(test_file)

        # 创建sha256_map.json文件
        signature_map = {test_file: test_file_hash}
        with open("sha256_map.json", "w") as f:
            json.dump(signature_map, f)

        # 设置KMS_KEY_ID环境变量
        os.environ["KMS_KEY_ID"] = "test-key-id"

        # 重新创建验证器实例以读取新的环境变量
        verifier = KMSSignatureVerifier()

        exit_code, reason_code, message = verifier.verify_signatures("sha256_map.json", rules)
        print(f"结果: {exit_code}, 原因码: {reason_code}, 消息: {message}")
        assert exit_code == 0, "测试2失败: 签名验证通过应该返回0值"
        assert reason_code == GateReasonCode.SUCCESS, "测试2失败: 原因码应该是 SUCCESS"

        # 测试3: 签名验证失败 - 文件内容被篡改
        print("\n3. 测试签名验证失败 - 文件内容被篡改")

        # 修改测试文件内容
        with open(test_file, "w") as f:
            f.write("modified content")

        exit_code, reason_code, message = verifier.verify_signatures("sha256_map.json", rules)
        print(f"结果: {exit_code}, 原因码: {reason_code}, 消息: {message}")
        assert exit_code == 1, "测试3失败: 签名验证失败应该返回非0值"
        assert reason_code == GateReasonCode.INVALID_SIGNATURE, (
            "测试3失败: 原因码应该是 INVALID_SIGNATURE"
        )

        # 测试4: 缺少KMS_KEY_ID环境变量
        print("\n4. 测试缺少KMS_KEY_ID环境变量")
        if "KMS_KEY_ID" in os.environ:
            del os.environ["KMS_KEY_ID"]

        exit_code, reason_code, message = verifier.verify_signatures("sha256_map.json", rules)
        print(f"结果: {exit_code}, 原因码: {reason_code}, 消息: {message}")
        assert exit_code == 1, "测试4失败: 缺少KMS_KEY_ID环境变量应该返回非0值"
        assert reason_code == GateReasonCode.INVALID_SIGNATURE, (
            "测试4失败: 原因码应该是 INVALID_SIGNATURE"
        )

        print("\nKMS签名验证器测试通过!")
        return True

    except Exception as e:
        print(f"\n测试失败: {e}")
        import traceback

        traceback.print_exc()
        return False
    finally:
        os.chdir(original_cwd)
        shutil.rmtree(temp_dir)
        # 清理环境变量
        if "KMS_KEY_ID" in os.environ:
            del os.environ["KMS_KEY_ID"]


def test_signature_verifier_factory():
    """测试签名验证器工厂类"""
    print("\n=== 测试签名验证器工厂类 ===")

    try:
        # 测试1: 默认使用本地验证器
        print("\n1. 测试默认使用本地验证器")
        if "SIGNATURE_VERIFIER_TYPE" in os.environ:
            del os.environ["SIGNATURE_VERIFIER_TYPE"]

        verifier = SignatureVerifierFactory.get_verifier()
        assert isinstance(verifier, LocalSignatureVerifier), (
            "测试1失败: 默认应该使用LocalSignatureVerifier"
        )
        print("  ✓ 默认使用本地验证器")

        # 测试2: 使用环境变量选择本地验证器
        print("\n2. 测试使用环境变量选择本地验证器")
        os.environ["SIGNATURE_VERIFIER_TYPE"] = "local"

        verifier = SignatureVerifierFactory.get_verifier()
        assert isinstance(verifier, LocalSignatureVerifier), (
            "测试2失败: 环境变量设置为local时应该使用LocalSignatureVerifier"
        )
        print("  ✓ 环境变量设置为local时使用本地验证器")

        # 测试3: 使用环境变量选择KMS验证器
        print("\n3. 测试使用环境变量选择KMS验证器")
        os.environ["SIGNATURE_VERIFIER_TYPE"] = "kms"

        verifier = SignatureVerifierFactory.get_verifier()
        assert isinstance(verifier, KMSSignatureVerifier), (
            "测试3失败: 环境变量设置为kms时应该使用KMSSignatureVerifier"
        )
        print("  ✓ 环境变量设置为kms时使用KMS验证器")

        # 测试4: 使用环境变量选择无效验证器类型，应该使用默认值
        print("\n4. 测试使用环境变量选择无效验证器类型")
        os.environ["SIGNATURE_VERIFIER_TYPE"] = "invalid_type"

        verifier = SignatureVerifierFactory.get_verifier()
        assert isinstance(verifier, LocalSignatureVerifier), (
            "测试4失败: 无效验证器类型应该使用默认的LocalSignatureVerifier"
        )
        print("  ✓ 无效验证器类型使用默认的本地验证器")

        print("\n签名验证器工厂类测试通过!")
        return True

    except Exception as e:
        print(f"\n测试失败: {e}")
        import traceback

        traceback.print_exc()
        return False
    finally:
        # 清理环境变量
        if "SIGNATURE_VERIFIER_TYPE" in os.environ:
            del os.environ["SIGNATURE_VERIFIER_TYPE"]


def test_integration_with_fast_gate():
    """测试与fast_gate.py的集成"""
    print("\n=== 测试与fast_gate.py的集成 ===")

    # 创建临时目录
    temp_dir = tempfile.mkdtemp()
    original_cwd = os.getcwd()

    try:
        os.chdir(temp_dir)

        # 创建测试文件
        test_file = "test_file.txt"
        with open(test_file, "w") as f:
            f.write("test content")

        # 计算测试文件的哈希值
        test_file_hash = calculate_file_hash(test_file)

        # 创建sha256_map.json文件
        signature_map = {test_file: test_file_hash}
        with open("sha256_map.json", "w") as f:
            json.dump(signature_map, f)

        # 测试使用本地验证器
        print("\n1. 测试使用本地验证器")
        result = subprocess.run(
            ["python", "d:/quantsys/tools/gatekeeper/fast_gate.py", "l1"],
            cwd="d:/quantsys",
            capture_output=True,
            text=True,
            timeout=30,
        )

        print(f"退出码: {result.returncode}")
        print(f"输出: {result.stdout}")
        print(f"错误: {result.stderr}")

        # 测试使用KMS验证器
        print("\n2. 测试使用KMS验证器")
        env = os.environ.copy()
        env["SIGNATURE_VERIFIER_TYPE"] = "kms"
        env["KMS_KEY_ID"] = "test-key-id"

        result = subprocess.run(
            ["python", "d:/quantsys/tools/gatekeeper/fast_gate.py", "l1"],
            cwd="d:/quantsys",
            capture_output=True,
            text=True,
            timeout=30,
            env=env,
        )

        print(f"退出码: {result.returncode}")
        print(f"输出: {result.stdout}")
        print(f"错误: {result.stderr}")

        print("\n与fast_gate.py的集成测试完成!")
        return True

    except Exception as e:
        print(f"\n测试失败: {e}")
        import traceback

        traceback.print_exc()
        return False
    finally:
        os.chdir(original_cwd)
        shutil.rmtree(temp_dir)


def test_signature_verifier():
    """运行所有签名验证器测试"""
    print("开始测试签名验证适配器层...")

    all_passed = True

    # 运行本地签名验证器测试
    if not test_local_signature_verifier():
        all_passed = False

    # 运行KMS签名验证器测试
    if not test_kms_signature_verifier():
        all_passed = False

    # 运行签名验证器工厂测试
    if not test_signature_verifier_factory():
        all_passed = False

    # 运行与fast_gate.py的集成测试
    # if not test_integration_with_fast_gate():
    #     all_passed = False

    if all_passed:
        print("\n🎉 所有测试通过!")
        return 0
    else:
        print("\n❌ 部分测试失败!")
        return 1


if __name__ == "__main__":
    exit_code = test_signature_verifier()
    print(f"\nEXIT_CODE={exit_code}")
    exit(exit_code)
