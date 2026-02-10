#!/usr/bin/env python3
"""
签名验证功能简单测试
"""

import hashlib
import json
import os
import shutil

# 添加项目根目录到Python路径
import sys
import tempfile
from pathlib import Path

# 从当前文件位置推断项目根目录
repo_root = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(repo_root))

# 导入需要测试的函数
from tools.gatekeeper.fast_gate import verify_signatures


def calculate_file_hash(file_path):
    """计算文件的SHA256哈希值"""
    with open(file_path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def test_verify_signatures():
    """测试签名验证功能"""
    # 创建临时目录
    temp_dir = tempfile.mkdtemp()
    original_cwd = os.getcwd()

    try:
        os.chdir(temp_dir)

        # 测试1: 缺少sha256_map.json文件
        print("=== 测试1: 缺少sha256_map.json文件 ===")
        rules = {"enabled": True}
        result = verify_signatures(rules)
        print(f"结果: {'FAIL' if result != 0 else 'PASS'}")
        assert result != 0, "测试1失败: 缺少sha256_map.json文件应该返回非0值"

        # 测试2: 正常情况 - 签名验证通过
        print("\n=== 测试2: 签名验证通过 ===")

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

        result = verify_signatures(rules)
        print(f"结果: {'FAIL' if result != 0 else 'PASS'}")
        assert result == 0, "测试2失败: 签名验证通过应该返回0值"

        # 测试3: 签名验证失败 - 文件内容被篡改
        print("\n=== 测试3: 签名验证失败 - 文件内容被篡改 ===")

        # 修改测试文件内容
        with open(test_file, "w") as f:
            f.write("modified content")

        result = verify_signatures(rules)
        print(f"结果: {'FAIL' if result != 0 else 'PASS'}")
        assert result != 0, "测试3失败: 签名验证失败应该返回非0值"

        print("\n所有测试通过!")
        return 0

    except AssertionError as e:
        print(f"\n测试失败: {e}")
        return 1
    except Exception as e:
        print(f"\n测试异常: {e}")
        import traceback

        traceback.print_exc()
        return 1
    finally:
        os.chdir(original_cwd)
        shutil.rmtree(temp_dir)


if __name__ == "__main__":
    exit_code = test_verify_signatures()
    print(f"\nEXIT_CODE={exit_code}")
    exit(exit_code)
