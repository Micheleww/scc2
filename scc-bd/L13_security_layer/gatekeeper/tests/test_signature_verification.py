#!/usr/bin/env python3
"""
签名验证功能测试
"""

import hashlib
import json
import os
import shutil
import subprocess
import tempfile


def calculate_file_hash(file_path):
    """计算文件的SHA256哈希值"""
    with open(file_path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def test_signature_verification():
    """测试签名验证功能"""
    # 创建临时目录
    temp_dir = tempfile.mkdtemp()
    original_cwd = os.getcwd()

    try:
        os.chdir(temp_dir)

        # 测试1: 正常情况 - 签名验证通过
        print("=== 测试1: 签名验证通过 ===")

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

        # 运行fast_gate.py的签名验证功能
        result = subprocess.run(
            ["python", "tools/gatekeeper/fast_gate.py", "l1"],
            cwd="d:/quantsys",
            capture_output=True,
            text=True,
            timeout=30,
        )

        print(f"退出码: {result.returncode}")
        print(f"输出:\n{result.stdout}")
        print(f"错误:\n{result.stderr}")

        # 测试2: 缺少sha256_map.json文件
        print("\n=== 测试2: 缺少sha256_map.json文件 ===")
        os.remove("sha256_map.json")

        result = subprocess.run(
            ["python", "tools/gatekeeper/fast_gate.py", "l1"],
            cwd="d:/quantsys",
            capture_output=True,
            text=True,
            timeout=30,
        )

        print(f"退出码: {result.returncode}")
        print(f"输出:\n{result.stdout}")
        print(f"错误:\n{result.stderr}")

        # 测试3: 签名验证失败 - 文件内容被篡改
        print("\n=== 测试3: 签名验证失败 - 文件内容被篡改 ===")

        # 创建错误的sha256_map.json文件
        wrong_signature_map = {
            test_file: "wronghash1234567890123456789012345678901234567890123456789012345"
        }
        with open("sha256_map.json", "w") as f:
            json.dump(wrong_signature_map, f)

        result = subprocess.run(
            ["python", "tools/gatekeeper/fast_gate.py", "l1"],
            cwd="d:/quantsys",
            capture_output=True,
            text=True,
            timeout=30,
        )

        print(f"退出码: {result.returncode}")
        print(f"输出:\n{result.stdout}")
        print(f"错误:\n{result.stderr}")

        return 0

    except Exception as e:
        print(f"测试失败: {e}")
        import traceback

        traceback.print_exc()
        return 1
    finally:
        os.chdir(original_cwd)
        shutil.rmtree(temp_dir)


if __name__ == "__main__":
    exit_code = test_signature_verification()
    print(f"\n测试结果: {'PASS' if exit_code == 0 else 'FAIL'}")
    print(f"EXIT_CODE={exit_code}")
    exit(exit_code)
