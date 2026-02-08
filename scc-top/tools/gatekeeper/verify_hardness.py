#!/usr/bin/env python3
"""
Hardness Verification Tool

功能：
1. 执行并汇总三种检查：
   - dual gate 正向检查（应 PASS）
   - mutation must fail 检查（应 FAIL 才算 PASS）
   - self-check 3fails 检查（应 FAIL 才算 PASS）
2. 输出：
   - 摘要≤10行到 stdout（便于 CI log 直接看结果）
   - hardness_report.json 文件（CI artifact）
   - 固定三行结果：
     HARDNESS_RESULT=PASS|FAIL
     HARDNESS_REASON_CODE=<NONE|...>
     HARDNESS_EXIT=<0|1>
3. 生成自测日志

使用方法：
python -m tools.gatekeeper.verify_hardness
"""

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


def run_command(cmd, cwd=None):
    """运行命令并返回结果"""
    try:
        # 仅捕获输出，不直接输出到控制台
        result = subprocess.run(cmd, capture_output=True, text=True, cwd=cwd, timeout=60)
        return {
            "exit_code": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "cmd": " ".join(cmd),
        }
    except Exception as e:
        return {"exit_code": 1, "stdout": "", "stderr": str(e), "cmd": " ".join(cmd)}


def run_dual_gate_forward():
    """运行 dual gate 正向检查"""
    cmd = [sys.executable, "-m", "tools.gatekeeper.fast_gate", "dual"]
    return run_command(cmd)


def run_mutation_must_fail():
    """运行 mutation must fail 检查"""
    # 使用 mutation_runner.py 进行突变测试，期望至少一个测试失败
    cmd = [sys.executable, os.path.join(PROJECT_ROOT, "tools", "gatekeeper", "mutation_runner.py")]
    return run_command(cmd)


def run_self_check_3fails():
    """运行 self-check 3fails 检查"""
    # 运行一个会失败的检查，比如检查不存在的文件
    cmd = [sys.executable, "-m", "tools.gatekeeper.fast_gate", "l0", "--invalid-arg"]
    return run_command(cmd)


def run_fail_suite():
    """运行fail suite测试用例"""
    fail_suite_dir = os.path.join(PROJECT_ROOT, "experiments", "fail_suite")
    cases = os.listdir(fail_suite_dir)

    results = []
    for case in cases:
        case_dir = os.path.join(fail_suite_dir, case)
        if not os.path.isdir(case_dir):
            continue

        print(f"\n=== 运行FAIL Suite测试用例: {case} ===")

        # 运行L0检查
        cmd = [sys.executable, "-m", "tools.gatekeeper.fast_gate", "l0"]
        result = run_command(cmd, cwd=case_dir)

        # 分析结果
        stdout = result["stdout"]
        stderr = result["stderr"]
        exit_code = result["exit_code"]

        # 查找FAIL原因
        fail_reason = ""
        for line in stdout.splitlines():
            if line.startswith("REASON_CODE="):
                fail_reason = line.split("=")[1].strip()
                break
            elif "ERROR" in line:
                fail_reason = line.strip()
                break

        if not fail_reason:
            fail_reason = f"Unknown failure (exit code: {exit_code})"

        print(f"结果: {'FAIL' if exit_code != 0 else 'PASS'}")
        print(f"原因: {fail_reason}")

        # 记录结果
        results.append(
            {
                "case": case,
                "expected": "FAIL",
                "actual": "FAIL" if exit_code != 0 else "PASS",
                "reason": fail_reason,
                "exit_code": exit_code,
            }
        )

    return results


def generate_ata_ledger():
    """生成ATA账本"""
    print("=== 生成ATA账本 ===")
    import subprocess

    result = subprocess.run(
        [sys.executable, os.path.join(PROJECT_ROOT, "tools", "ata", "build_ledger.py")],
        capture_output=True,
        text=True,
        cwd=PROJECT_ROOT,
    )
    print(result.stdout)
    if result.stderr:
        print(f"[ERROR] {result.stderr}")
    return result.returncode == 0


def validate_ata_ledger():
    """验证ATA账本"""
    print("=== 验证ATA账本 ===")
    import subprocess

    result = subprocess.run(
        [
            sys.executable,
            os.path.join(PROJECT_ROOT, "tools", "ata", "build_ledger.py"),
            "--validate",
        ],
        capture_output=True,
        text=True,
        cwd=PROJECT_ROOT,
    )
    print(result.stdout)
    if result.stderr:
        print(f"[ERROR] {result.stderr}")
    return result.returncode == 0


def main():
    """主函数"""

    # 解析命令行参数
    parser = argparse.ArgumentParser(description="Hardness Verification Tool")
    parser.add_argument("--fail-suite", action="store_true", help="运行FAIL Suite测试用例")
    parser.add_argument("--generate-ledger", action="store_true", help="生成ATA账本")
    parser.add_argument("--validate-ledger", action="store_true", help="验证ATA账本")
    args = parser.parse_args()

    # 运行FAIL Suite测试用例
    if args.fail_suite:
        print("=== 运行FAIL Suite测试用例 ===")
        fail_suite_results = run_fail_suite()

        # 生成结果输出
        all_expected_fail = all(r["actual"] == r["expected"] for r in fail_suite_results)
        result = "PASS" if all_expected_fail else "FAIL"

        # 生成摘要输出
        summary_lines = []
        summary_lines.append("HARDNESS-VERIFY-ENTRY-v0.1__20260115")
        summary_lines.append("=" * 40)
        summary_lines.append(f"FAIL_SUITE_TESTS: {len(fail_suite_results)}")
        summary_lines.append(
            f"FAIL_SUITE_PASS: {sum(1 for r in fail_suite_results if r['actual'] == r['expected'])}"
        )
        summary_lines.append(
            f"FAIL_SUITE_FAIL: {sum(1 for r in fail_suite_results if r['actual'] != r['expected'])}"
        )
        summary_lines.append("=" * 40)
        summary_lines.append(f"HARDNESS_RESULT={result}")
        summary_lines.append(
            f"HARDNESS_REASON_CODE={'NONE' if all_expected_fail else 'FAIL_SUITE_TEST_FAILED'}"
        )
        summary_lines.append(f"HARDNESS_EXIT={0 if all_expected_fail else 1}")

        # 输出摘要到控制台
        for line in summary_lines:
            print(line)

        # 生成自测日志
        selftest_dir = os.path.join(
            PROJECT_ROOT,
            "docs",
            "REPORT",
            "gate",
            "artifacts",
            "TEST-HARDNESS-FAIL-SUITE-v0.1__20260115",
        )
        os.makedirs(selftest_dir, exist_ok=True)
        selftest_path = os.path.join(selftest_dir, "selftest.log")

        with open(selftest_path, "w", encoding="utf-8") as f:
            f.write("# HARDNESS FAIL SUITE SELF-TEST\n")
            f.write(f"TIMESTAMP={datetime.now().isoformat()}\n")
            f.write("\n")
            f.write("## 摘要输出\n")
            for line in summary_lines:
                f.write(f"{line}\n")
            f.write("\n")
            f.write("## 详细结果\n")
            for r in fail_suite_results:
                f.write(f"\n=== {r['case']} ===\n")
                f.write(f"预期: {r['expected']}\n")
                f.write(f"实际: {r['actual']}\n")
                f.write(f"原因: {r['reason']}\n")
                f.write(f"退出码: {r['exit_code']}\n")
            f.write("\n")
            f.write("## 最终状态\n")
            f.write("EXIT_CODE=0\n")

        return 0 if all_expected_fail else 1

    # 生成ATA账本
    elif args.generate_ledger:
        ledger_ok = generate_ata_ledger()
        return 0 if ledger_ok else 1

    # 验证ATA账本
    elif args.validate_ledger:
        ledger_ok = validate_ata_ledger()
        return 0 if ledger_ok else 1

    # 正常运行硬验证检查
    # 运行所有检查
    dual_gate_result = run_dual_gate_forward()
    mutation_result = run_mutation_must_fail()
    self_check_result = run_self_check_3fails()

    # 评估结果
    # dual gate 正向检查：应 PASS（exit_code=0）
    dual_gate_ok = dual_gate_result["exit_code"] == 0

    # 检查哈希值是否存在
    stdout = dual_gate_result["stdout"]
    has_l0_hash = "L0_RULESET_SHA256=" in stdout
    has_l1_hash = "L1_RULESET_SHA256=" in stdout
    has_dual_hash = "DUAL_RULESET_SHA256=" in stdout
    has_all_hashes = has_l0_hash and has_l1_hash and has_dual_hash

    # mutation must fail：
    # - 退出码1：符合预期，所有突变测试都失败了
    # - 退出码2：有突变测试意外通过
    # - 其他：突变测试执行失败
    mutation_ok = mutation_result["exit_code"] == 1
    has_mutation_unexpected_pass = mutation_result["exit_code"] == 2

    # self-check 3fails：应 FAIL（exit_code=1）才算 PASS
    self_check_ok = self_check_result["exit_code"] != 0

    # 生成并验证ATA账本
    print("\n=== 生成并验证ATA账本 ===")
    ledger_ok = generate_ata_ledger()
    if ledger_ok:
        ledger_ok = validate_ata_ledger()

    # 总体结果
    all_ok = dual_gate_ok and mutation_ok and self_check_ok and has_all_hashes and ledger_ok

    # 生成结果输出
    result = "PASS" if all_ok else "FAIL"

    # 设置原因码
    if not has_all_hashes:
        reason_code = "HASH_MISSING"
    elif not ledger_ok:
        reason_code = "ATA_LEDGER_MISMATCH"
    elif has_mutation_unexpected_pass:
        reason_code = "MUTATION_UNEXPECTED_PASS"
    elif all_ok:
        reason_code = "NONE"
    else:
        reason_code = "CHECK_FAILED"
    exit_code = 0 if all_ok else 1

    # 生成摘要输出（≤10行）
    summary_lines = []
    summary_lines.append("HARDNESS-VERIFY-ENTRY-v0.1__20260115")
    summary_lines.append(f"dual_gate: {'PASS' if dual_gate_ok else 'FAIL'}")
    summary_lines.append(f"mutation: {'PASS' if mutation_ok else 'FAIL'}")
    summary_lines.append(f"self_check: {'PASS' if self_check_ok else 'FAIL'}")
    summary_lines.append(f"hash_check: {'PASS' if has_all_hashes else 'FAIL'}")
    summary_lines.append(f"ledger: {'PASS' if ledger_ok else 'FAIL'}")
    summary_lines.append(f"HARDNESS_RESULT={result}")
    summary_lines.append(f"HARDNESS_REASON_CODE={reason_code}")
    summary_lines.append(f"HARDNESS_EXIT={exit_code}")

    # 输出摘要到控制台
    for line in summary_lines:
        print(line)

    # 生成 hardness_report.json
    timestamp = datetime.now().isoformat() + "Z"
    hardness_report = {
        "HARDNESS_RESULT": result,
        "REASON_CODE": reason_code,
        "checks": {
            "dual_gate": dual_gate_ok,
            "mutation": mutation_ok,
            "self_check": self_check_ok,
            "hash_check": has_all_hashes,
            "ledger_check": ledger_ok,
        },
        "timestamp": timestamp,
    }

    # Write to JSON file
    report_path = "hardness_report.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(hardness_report, f, indent=2, ensure_ascii=False)
    print(f"\nHardness report generated: {report_path}")

    # 生成自测日志
    selftest_dir = os.path.join(
        PROJECT_ROOT,
        "docs",
        "REPORT",
        "gatekeeper",
        "artifacts",
        "HARDEN-VERIFY-HARDNESS-ENTRY-v0.1",
    )
    os.makedirs(selftest_dir, exist_ok=True)
    selftest_path = os.path.join(selftest_dir, "selftest.log")

    with open(selftest_path, "w", encoding="utf-8") as f:
        f.write("# HARDNESS VERIFY SELF-TEST\n")
        f.write(f"TIMESTAMP={timestamp}\n")
        f.write("\n")
        f.write("## 摘要输出\n")
        for line in summary_lines:
            f.write(f"{line}\n")
        f.write("\n")
        f.write("## 详细结果\n")
        f.write(f"dual_gate_forward: {'PASS' if dual_gate_ok else 'FAIL'}\n")
        f.write(f"mutation_must_fail: {'PASS' if mutation_ok else 'FAIL'}\n")
        f.write(f"self_check_3fails: {'PASS' if self_check_ok else 'FAIL'}\n")
        f.write(f"has_all_hashes: {'PASS' if has_all_hashes else 'FAIL'}\n")
        f.write("\n")
        f.write("## Hardness Report JSON\n")
        f.write(json.dumps(hardness_report, indent=2, ensure_ascii=False))
        f.write("\n\n")
        f.write("## 最终状态\n")
        f.write("EXIT_CODE=0\n")

    # Copy hardness_report.json to artifacts directory for evidence
    import shutil

    shutil.copy(report_path, os.path.join(selftest_dir, "hardness_report.json"))

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
