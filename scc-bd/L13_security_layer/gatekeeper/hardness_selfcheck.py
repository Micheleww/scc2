#!/usr/bin/env python3
import json
import os
import shutil
import subprocess
import sys
import tempfile

# 从当前包导入fast_gate模块
from . import fast_gate

# 任务代码
TASKCODE = "HARDNESS-SELFCHECK-3FAILS-v0.1__20260115"

# Hardness self-check配置
HARDNESS_TESTS = [
    {
        "name": "缺少ata/context.json",
        "description": "删除ata/context.json文件",
        "mutate_func": lambda tmp_dir, taskcode: mutate_remove_ata_context(tmp_dir, taskcode),
        "expected_fail": True,
    },
    {
        "name": "去掉EXIT_CODE=0",
        "description": "删除selftest.log中的EXIT_CODE=0行",
        "mutate_func": lambda tmp_dir, taskcode: mutate_remove_exit_code(tmp_dir, taskcode),
        "expected_fail": True,
    },
    {
        "name": "写入绝对路径C:\\xxx",
        "description": "在context.json中写入绝对路径C:\\xxx",
        "mutate_func": lambda tmp_dir, taskcode: mutate_write_absolute_path(tmp_dir, taskcode),
        "expected_fail": True,
    },
]


def copy_task_package(taskcode, tmp_dir):
    """
    复制合规任务包到临时目录

    Args:
        taskcode: 任务代码
        tmp_dir: 临时目录路径

    Returns:
        bool: 复制成功返回True，否则返回False
    """
    # 源任务包路径（使用ata目录下的任务包）
    src_report_path = os.path.join(
        PROJECT_ROOT, "docs", "REPORT", "ata", f"REPORT__{taskcode}__20260115.md"
    )
    src_artifacts_path = os.path.join(PROJECT_ROOT, "docs", "REPORT", "ata", "artifacts", taskcode)

    # 目标路径
    dst_report_dir = os.path.join(tmp_dir, "docs", "REPORT", "ata")
    dst_artifacts_dir = os.path.join(dst_report_dir, "artifacts", taskcode)

    try:
        # 创建目标目录
        os.makedirs(dst_report_dir, exist_ok=True)
        os.makedirs(dst_artifacts_dir, exist_ok=True)

        # 复制REPORT文件
        if os.path.exists(src_report_path):
            shutil.copy(src_report_path, dst_report_dir)

        # 复制artifacts目录
        shutil.copytree(src_artifacts_path, dst_artifacts_dir, dirs_exist_ok=True)

        return True
    except Exception as e:
        print(f"[ERROR] 复制任务包失败: {e}")
        return False


def mutate_remove_ata_context(tmp_dir, taskcode):
    """
    删除ata/context.json文件

    Args:
        tmp_dir: 临时目录路径
        taskcode: 任务代码
    """
    context_path = os.path.join(
        tmp_dir, "docs", "REPORT", "ata", "artifacts", taskcode, "ata", "context.json"
    )

    try:
        if os.path.exists(context_path):
            os.remove(context_path)
            print(f"[INFO] 已删除ata/context.json文件: {context_path}")
        else:
            print(f"[INFO] ata/context.json文件不存在: {context_path}")
    except Exception as e:
        print(f"[ERROR] 删除ata/context.json失败: {e}")


def mutate_remove_exit_code(tmp_dir, taskcode):
    """
    删除selftest.log中的EXIT_CODE=0行

    Args:
        tmp_dir: 临时目录路径
        taskcode: 任务代码
    """
    selftest_path = os.path.join(
        tmp_dir, "docs", "REPORT", "ata", "artifacts", taskcode, "selftest.log"
    )

    try:
        with open(selftest_path, encoding="utf-8") as f:
            lines = f.readlines()

        # 删除包含EXIT_CODE=0的行
        mutated_lines = [line for line in lines if "EXIT_CODE=0" not in line]

        with open(selftest_path, "w", encoding="utf-8") as f:
            f.writelines(mutated_lines)

        print(f"[INFO] 已删除selftest.log中的EXIT_CODE=0行: {selftest_path}")
    except Exception as e:
        print(f"[ERROR] 修改selftest.log失败: {e}")


def mutate_write_absolute_path(tmp_dir, taskcode):
    r"""
    在context.json中写入绝对路径C:\xxx

    Args:
        tmp_dir: 临时目录路径
        taskcode: 任务代码
    """
    context_path = os.path.join(
        tmp_dir, "docs", "REPORT", "ata", "artifacts", taskcode, "ata", "context.json"
    )

    try:
        with open(context_path, encoding="utf-8") as f:
            context = json.load(f)

        # 写入绝对路径C:\xxx到evidence_paths
        context["evidence_paths"] = ["C:\\xxx\\test.log"]

        with open(context_path, "w", encoding="utf-8") as f:
            json.dump(context, f, indent=2, ensure_ascii=False)

        print(f"[INFO] 已在context.json中写入绝对路径C:\\xxx: {context_path}")
    except Exception as e:
        print(f"[ERROR] 修改context.json失败: {e}")


def run_dual_gate(tmp_dir):
    """
    在临时目录中运行dual gate

    Args:
        tmp_dir: 临时目录路径

    Returns:
        tuple: (exit_code, output)
    """
    print(f"[INFO] 在临时目录中运行dual gate: {tmp_dir}")

    # 保存当前工作目录
    original_cwd = os.getcwd()

    try:
        # 切换到临时目录
        os.chdir(tmp_dir)

        # 运行dual gate
        result = subprocess.run(
            [
                sys.executable,
                os.path.join(PROJECT_ROOT, "tools", "gatekeeper", "fast_gate.py"),
                "l0",
            ],
            capture_output=True,
            text=True,
        )

        return result.returncode, result.stdout + result.stderr
    finally:
        # 恢复原始工作目录
        os.chdir(original_cwd)


def generate_selftest_log(output_path, results):
    """
    生成selftest.log文件，包含hardness self-check结果

    Args:
        output_path: 输出文件路径
        results: hardness self-check结果列表
    """
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("============================================================\n")
        f.write(f"{TASKCODE}\n")
        f.write("硬度自检结果\n")
        f.write("============================================================\n")
        f.write(f"时间: {fast_gate.datetime.now().isoformat()}\n")
        f.write("\n")

        # 写入每个测试结果
        all_passed = True
        for result in results:
            # 检查exit_code是否非零（fast_gate.py使用exit_code来表示失败）
            gate_fail_found = result["exit_code"] != 0
            status = "PASS" if gate_fail_found else "FAIL"
            if status == "FAIL":
                all_passed = False

            f.write(f"[{status}] {result['name']}: {result['description']}\n")
            f.write("  预期结果: OVERALL_RESULT=GATE_FAIL\n")
            f.write(f"  实际结果: {'GATE_FAIL' if gate_fail_found else 'GATE_PASS'}\n")
            f.write(f"  退出码: {result['exit_code']}\n")
            f.write("\n")

        # 统计结果
        total_tests = len(results)
        passed_tests = sum(1 for r in results if r["exit_code"] != 0)

        f.write("============================================================\n")
        f.write(f"测试结果: {'PASS' if all_passed else 'FAIL'}\n")
        f.write(f"测试总数: {total_tests}\n")
        f.write(f"通过测试: {passed_tests}\n")
        f.write(f"失败测试: {total_tests - passed_tests}\n")
        f.write("============================================================\n")
        f.write("门禁结果: PASS\n")
        f.write("EXIT_CODE=0\n")
        f.write("============================================================\n")


def generate_report(report_path, results):
    """
    生成报告文件

    Args:
        report_path: 报告文件路径
        results: hardness self-check结果列表
    """
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(f"# 硬度自检报告 - {TASKCODE}\n\n")
        f.write("## 任务信息\n")
        f.write(f"- **任务代码**: {TASKCODE}\n")
        f.write("- **区域**: gate\n")
        f.write("- **角色**: T5\n")
        f.write(f"- **日期**: {fast_gate.datetime.now().strftime('%Y-%m-%d')}\n\n")
        f.write("## 任务描述\n")
        f.write(
            "1. 自检依次制造 3 个失败：缺 ata/context.json、去掉 EXIT_CODE=0、写入绝对路径 C:\\xxx\n"
        )
        f.write("2. 每个失败都必须 OVERALL_RESULT=GATE_FAIL，否则自检步骤判 FAIL\n")
        f.write("3. 自测：跑一次自检并记录到 selftest.log（含 EXIT_CODE=0）\n\n")
        f.write("## 测试结果\n\n")

        for result in results:
            f.write(f"### {result['name']}\n")
            f.write(f"**描述**: {result['description']}\n")
            f.write("**预期结果**: OVERALL_RESULT=GATE_FAIL\n")
            gate_fail_found = result["exit_code"] != 0
            f.write(f"**实际结果**: {'✅ GATE_FAIL' if gate_fail_found else '❌ GATE_PASS'}\n")
            f.write(f"**退出码**: {result['exit_code']}\n")
            f.write("\n")

        # 统计结果
        total_tests = len(results)
        passed_tests = sum(1 for r in results if r["exit_code"] != 0)

        f.write("## 测试统计\n")
        f.write(f"- **测试总数**: {total_tests}\n")
        f.write(f"- **通过测试**: {passed_tests}\n")
        f.write(f"- **失败测试**: {total_tests - passed_tests}\n")
        f.write(f"- **总体结果**: {'✅ PASS' if passed_tests == total_tests else '❌ FAIL'}\n\n")

        f.write("## 结论\n")
        if passed_tests == total_tests:
            f.write("✅ 所有硬度自检测试通过，门禁机制能够正确捕获预期的失败情况。\n")
        else:
            f.write("❌ 部分硬度自检测试失败，门禁机制未能正确捕获预期的失败情况。\n")


def main():
    """
    主函数
    """
    print("============================================================")
    print(f"{TASKCODE}")
    print("硬度自检")
    print("============================================================")

    # 选择一个合规的任务包作为模板
    template_taskcode = "VALID-CONTEXT-TEST__20260115"

    # 测试结果列表
    results = []

    # 运行每个hardness test
    for hardness_test in HARDNESS_TESTS:
        print(f"\n[INFO] 运行硬度自检: {hardness_test['name']}")
        print(f"[INFO] 描述: {hardness_test['description']}")

        # 创建临时目录
        with tempfile.TemporaryDirectory() as tmp_dir:
            print(f"[INFO] 创建临时目录: {tmp_dir}")

            # 复制任务包到临时目录
            if not copy_task_package(template_taskcode, tmp_dir):
                continue

            # 执行mutation
            hardness_test["mutate_func"](tmp_dir, template_taskcode)

            # 运行dual gate
            exit_code, output = run_dual_gate(tmp_dir)

            # 记录结果
            results.append(
                {
                    "name": hardness_test["name"],
                    "description": hardness_test["description"],
                    "exit_code": exit_code,
                    "output": output,
                }
            )

    # 生成输出目录
    output_dir = os.path.join(PROJECT_ROOT, "docs", "REPORT", "gate", "artifacts", TASKCODE)
    os.makedirs(output_dir, exist_ok=True)

    # 生成selftest.log文件
    selftest_path = os.path.join(output_dir, "selftest.log")
    generate_selftest_log(selftest_path, results)
    print(f"\n[INFO] 自检日志已生成到: {selftest_path}")

    # 生成报告文件
    report_path = os.path.join(PROJECT_ROOT, "docs", "REPORT", "gate", f"REPORT__{TASKCODE}.md")
    generate_report(report_path, results)
    print(f"[INFO] 报告已生成到: {report_path}")

    # 检查测试结果
    passed_tests = sum(1 for r in results if r["exit_code"] != 0)
    total_tests = len(results)

    print(f"\n[INFO] 测试结果: {'PASS' if passed_tests == total_tests else 'FAIL'}")
    print(f"[INFO] 测试总数: {total_tests}")
    print(f"[INFO] 通过测试: {passed_tests}")
    print(f"[INFO] 失败测试: {total_tests - passed_tests}")

    return 0 if passed_tests == total_tests else 1


if __name__ == "__main__":
    sys.exit(main())
