#!/usr/bin/env python3
"""
Conftest执行入口脚本
用于运行OPA/Rego规则检查仓库关键文件
"""

import os
import subprocess
import sys


def check_conftest_installed():
    """检查conftest是否已安装"""
    try:
        result = subprocess.run(["conftest", "--version"], capture_output=True, text=True)
        return result.returncode == 0
    except FileNotFoundError:
        return False


def run_conftest_test(files, policy_dir, output_file=None):
    """运行conftest测试"""
    cmd = ["conftest", "test", "--policy", policy_dir, "--output", "json"] + files

    print(f"运行命令: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True)

    if output_file:
        with open(output_file, "w") as f:
            f.write(result.stdout)

    return result


def main():
    """主函数"""
    # 检查conftest是否安装
    if not check_conftest_installed():
        print("错误: conftest未安装。请访问https://www.conftest.dev/install/安装。")
        sys.exit(1)

    # 定义策略目录和测试文件
    policy_dir = "policy/rego/qcc"

    # 测试文件集
    test_files = [
        "SUBMIT.txt",
        "docs/ARCH/project_navigation__v0.1.0__DRAFT__20260115.md",
        "docs/REPORT/gatekeeper/REPORT__HARDEN-OPA-CONFTEST-v0.1__20260115.md",
    ]

    # 检查文件是否存在
    existing_files = [f for f in test_files if os.path.exists(f)]

    if not existing_files:
        print("错误: 没有找到要测试的文件。")
        sys.exit(1)

    # 创建输出目录
    output_dir = "docs/REPORT/gatekeeper/artifacts/HARDEN-OPA-CONFTEST-v0.1"
    os.makedirs(output_dir, exist_ok=True)

    # 运行conftest测试
    output_file = os.path.join(output_dir, "conftest_results.json")
    result = run_conftest_test(existing_files, policy_dir, output_file)

    # 打印结果
    print("\n=== Conftest测试结果 ===")
    print(result.stdout)

    if result.stderr:
        print("\n=== 错误信息 ===")
        print(result.stderr)

    # 处理退出码
    print(f"\n退出码: {result.returncode}")

    return result.returncode


if __name__ == "__main__":
    sys.exit(main())
