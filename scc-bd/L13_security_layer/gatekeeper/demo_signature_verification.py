#!/usr/bin/env python3
"""
签名验证演示脚本
"""

import hashlib
import json
import os
import shutil


def calculate_file_hash(file_path):
    """计算文件的SHA256哈希值"""
    with open(file_path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def create_signature_map(directory, output_path):
    """为目录中的所有文件创建签名映射文件"""
    signature_map = {}

    for root, _, files in os.walk(directory):
        for file in files:
            if file == "sha256_map.json":
                continue

            file_path = os.path.join(root, file)
            rel_path = os.path.relpath(file_path, directory)
            signature_map[rel_path] = calculate_file_hash(file_path)

    with open(output_path, "w") as f:
        json.dump(signature_map, f, indent=2)

    print(f"签名映射文件已创建: {output_path}")
    print(f"包含 {len(signature_map)} 个文件的签名")


def demo_signature_verification():
    """演示签名验证功能"""
    print("=== 签名验证演示 ===")

    # 创建演示目录和文件
    demo_dir = "demo_signature"
    if not os.path.exists(demo_dir):
        os.makedirs(demo_dir)

    # 创建演示文件
    file1 = os.path.join(demo_dir, "file1.txt")
    file2 = os.path.join(demo_dir, "file2.txt")

    with open(file1, "w") as f:
        f.write("这是文件1的内容")

    with open(file2, "w") as f:
        f.write("这是文件2的内容")

    print("\n1. 创建演示文件:")
    print(f"   - {file1}")
    print(f"   - {file2}")

    # 创建签名映射文件
    signature_map_path = os.path.join(demo_dir, "sha256_map.json")
    create_signature_map(demo_dir, signature_map_path)

    print("\n2. 查看签名映射文件内容:")
    with open(signature_map_path) as f:
        print(f.read())

    # 运行签名验证
    print("\n3. 运行签名验证:")
    os.system(f"python tools/gatekeeper/fast_gate.py l1 --signature-map {signature_map_path}")

    # 修改文件内容
    print("\n4. 修改文件内容:")
    with open(file1, "w") as f:
        f.write("这是修改后的文件1内容")
    print(f"   - {file1} 内容已修改")

    # 再次运行签名验证
    print("\n5. 再次运行签名验证:")
    os.system(f"python tools/gatekeeper/fast_gate.py l1 --signature-map {signature_map_path}")

    # 清理
    print("\n6. 清理演示文件")
    shutil.rmtree(demo_dir)

    print("\n=== 演示结束 ===")


if __name__ == "__main__":
    demo_signature_verification()
