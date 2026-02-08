#!/usr/bin/env python3
"""
SUBMIT.txt 回归测试脚本
TaskCode: GATE-SUBMIT-TXT-STRICT-v0.1__20260115
"""

import os
import shutil
import sys
import tempfile

# 添加项目根目录到 Python 路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from tools.gatekeeper.submit_txt import validate_submit_txt


def test_missing_submit_txt():
    """测试缺少 SUBMIT.txt 文件的场景"""
    print("=== 测试 1: 缺少 SUBMIT.txt 文件 ===")

    temp_dir = tempfile.mkdtemp()
    submit_path = os.path.join(temp_dir, "SUBMIT.txt")

    is_valid, errors, warnings = validate_submit_txt(submit_path)

    assert not is_valid, "缺少 SUBMIT.txt 文件时应该返回 False"
    assert "SUBMIT.txt 文件不存在" in str(errors), "应该包含 'SUBMIT.txt 文件不存在' 错误"

    print("✅ 测试通过: 缺少 SUBMIT.txt 文件时返回 FAIL")
    shutil.rmtree(temp_dir)
    return True


def test_empty_submit_txt():
    """测试空 SUBMIT.txt 文件的场景"""
    print("\n=== 测试 2: 空 SUBMIT.txt 文件 ===")

    temp_dir = tempfile.mkdtemp()
    submit_path = os.path.join(temp_dir, "SUBMIT.txt")

    # 创建空文件
    with open(submit_path, "w") as f:
        f.write("")

    is_valid, errors, warnings = validate_submit_txt(submit_path)

    assert not is_valid, "空 SUBMIT.txt 文件时应该返回 False"
    assert "SUBMIT.txt 文件为空" in str(errors), "应该包含 'SUBMIT.txt 文件为空' 错误"

    print("✅ 测试通过: 空 SUBMIT.txt 文件时返回 FAIL")
    shutil.rmtree(temp_dir)
    return True


def test_missing_keys():
    """测试缺少必需键的 SUBMIT.txt 文件"""
    print("\n=== 测试 3: 缺少必需键的 SUBMIT.txt 文件 ===")

    temp_dir = tempfile.mkdtemp()
    submit_path = os.path.join(temp_dir, "SUBMIT.txt")

    # 创建缺少必需键的 SUBMIT.txt
    submit_content = """changed_files: file1.txt, file2.txt
report: report.md
selftest_log: selftest.log
# 缺少 evidence_paths
selftest_cmds: python test.py
status: PASS
rollback: delete file1.txt
forbidden_check: no_law_copy; no_delete; relative_paths; no_new_entry_file
"""

    with open(submit_path, "w", encoding="utf-8") as f:
        f.write(submit_content)

    is_valid, errors, warnings = validate_submit_txt(submit_path)

    assert not is_valid, "缺少必需键时应该返回 False"
    assert "缺少必需的键" in str(errors), "应该包含 '缺少必需的键' 错误"

    print("✅ 测试通过: 缺少必需键时返回 FAIL")
    shutil.rmtree(temp_dir)
    return True


def test_invalid_status():
    """测试无效 status 的场景"""
    print("\n=== 测试 4: 无效 status 值 ===")

    temp_dir = tempfile.mkdtemp()
    submit_path = os.path.join(temp_dir, "SUBMIT.txt")

    # 创建包含无效 status 的 SUBMIT.txt
    submit_content = """changed_files: file1.txt
report: report.md
selftest_log: selftest.log
evidence_paths: file1.txt
selftest_cmds: python test.py
status: INVALID
rollback: delete file1.txt
forbidden_check: no_law_copy; no_delete; relative_paths; no_new_entry_file
"""

    with open(submit_path, "w", encoding="utf-8") as f:
        f.write(submit_content)

    is_valid, errors, warnings = validate_submit_txt(submit_path)

    assert not is_valid, "无效 status 时应该返回 False"
    assert "status 必须为 PASS 或 FAIL" in str(errors), "应该包含 'status 必须为 PASS 或 FAIL' 错误"

    print("✅ 测试通过: 无效 status 值时返回 FAIL")
    shutil.rmtree(temp_dir)
    return True


def test_path_not_exists():
    """测试路径不存在的场景"""
    print("\n=== 测试 5: 报告路径不存在 ===")

    temp_dir = tempfile.mkdtemp()
    submit_path = os.path.join(temp_dir, "SUBMIT.txt")

    # 创建包含不存在路径的 SUBMIT.txt
    submit_content = """changed_files: file1.txt
report: nonexistent_report.md
selftest_log: selftest.log
evidence_paths: file1.txt
selftest_cmds: python test.py
status: PASS
rollback: delete file1.txt
forbidden_check: no_law_copy; no_delete; relative_paths; no_new_entry_file
"""

    with open(submit_path, "w", encoding="utf-8") as f:
        f.write(submit_content)

    # 创建 selftest.log 文件
    selftest_path = os.path.join(temp_dir, "selftest.log")
    with open(selftest_path, "w", encoding="utf-8") as f:
        f.write("EXIT_CODE=0")

    is_valid, errors, warnings = validate_submit_txt(submit_path)

    assert not is_valid, "报告路径不存在时应该返回 False"
    assert "report 路径不存在" in str(errors), "应该包含 'report 路径不存在' 错误"

    print("✅ 测试通过: 报告路径不存在时返回 FAIL")
    shutil.rmtree(temp_dir)
    return True


def test_valid_submit_txt():
    """测试完整有效的 SUBMIT.txt 文件"""
    print("\n=== 测试 6: 完整有效的 SUBMIT.txt 文件 ===")

    temp_dir = tempfile.mkdtemp()

    # 创建必要的文件
    report_path = os.path.join(temp_dir, "report.md")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("# 测试报告")

    selftest_path = os.path.join(temp_dir, "selftest.log")
    with open(selftest_path, "w", encoding="utf-8") as f:
        f.write("EXIT_CODE=0")

    evidence_path = os.path.join(temp_dir, "evidence.txt")
    with open(evidence_path, "w", encoding="utf-8") as f:
        f.write("测试证据")

    submit_path = os.path.join(temp_dir, "SUBMIT.txt")

    # 创建完整的 SUBMIT.txt
    submit_content = f"""changed_files: report.md, selftest.log
report: {report_path}
selftest_log: {selftest_path}
evidence_paths: {evidence_path}
selftest_cmds: python test.py
status: PASS
rollback: delete report.md
forbidden_check: no_law_copy; no_delete; relative_paths; no_new_entry_file
"""

    with open(submit_path, "w", encoding="utf-8") as f:
        f.write(submit_content)

    is_valid, errors, warnings = validate_submit_txt(submit_path)

    assert is_valid, "完整有效的 SUBMIT.txt 文件时应该返回 True"
    assert len(errors) == 0, "完整有效的 SUBMIT.txt 文件不应该有错误"

    print("✅ 测试通过: 完整有效的 SUBMIT.txt 文件时返回 PASS")
    shutil.rmtree(temp_dir)
    return True


def test_selftest_log_no_exit_code():
    """测试 selftest.log 缺少 EXIT_CODE=0 的场景"""
    print("\n=== 测试 7: selftest.log 缺少 EXIT_CODE=0 ===")

    temp_dir = tempfile.mkdtemp()

    # 创建必要的文件
    report_path = os.path.join(temp_dir, "report.md")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("# 测试报告")

    selftest_path = os.path.join(temp_dir, "selftest.log")
    with open(selftest_path, "w", encoding="utf-8") as f:
        f.write("This file does not contain the required exit code")

    submit_path = os.path.join(temp_dir, "SUBMIT.txt")

    # 创建 SUBMIT.txt
    submit_content = f"""changed_files: report.md
report: {report_path}
selftest_log: {selftest_path}
evidence_paths: -
selftest_cmds: python test.py
status: PASS
rollback: delete report.md
forbidden_check: no_law_copy; no_delete; relative_paths; no_new_entry_file
"""

    with open(submit_path, "w", encoding="utf-8") as f:
        f.write(submit_content)

    is_valid, errors, warnings = validate_submit_txt(submit_path)

    assert not is_valid, "selftest.log 缺少 EXIT_CODE=0 时应该返回 False"
    assert "selftest_log 缺少 EXIT_CODE=0" in str(errors), (
        "应该包含 'selftest_log 缺少 EXIT_CODE=0' 错误"
    )

    print("✅ 测试通过: selftest.log 缺少 EXIT_CODE=0 时返回 FAIL")
    shutil.rmtree(temp_dir)
    return True


def run_all_tests():
    """运行所有测试"""
    print("=== 开始 SUBMIT.txt 回归测试 ===")

    tests = [
        test_missing_submit_txt,
        test_empty_submit_txt,
        test_missing_keys,
        test_invalid_status,
        test_path_not_exists,
        test_valid_submit_txt,
        test_selftest_log_no_exit_code,
    ]

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
