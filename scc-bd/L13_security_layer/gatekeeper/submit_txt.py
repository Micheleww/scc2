#!/usr/bin/env python3
"""
SUBMIT.txt 生成与校验模块
TaskCode: GATE-SUBMIT-TXT-STRICT-v0.1__20260115
"""

import os

SUBMIT_REQUIRED_KEYS = [
    "changed_files",
    "report",
    "selftest_log",
    "evidence_paths",
    "selftest_cmds",
    "status",
    "rollback",
    "forbidden_check",
]


SUBMIT_REQUIRED_KEYS = [
    "changed_files",
    "report",
    "selftest_log",
    "evidence_paths",
    "selftest_cmds",
    "status",
    "rollback",
    "forbidden_check",
]


SUBMIT_REQUIRED_KEYS = [
    "changed_files",
    "report",
    "selftest_log",
    "evidence_paths",
    "selftest_cmds",
    "status",
    "rollback",
    "forbidden_check",
]


def generate_submit_txt(task_code, area, submit_content):
    """生成 SUBMIT.txt 文件"""
    submit_dir = f"docs/REPORT/{area}/artifacts/{task_code}"
    submit_path = os.path.join(submit_dir, "SUBMIT.txt")

    # 创建目录
    os.makedirs(submit_dir, exist_ok=True)

    # 写入 SUBMIT.txt
    with open(submit_path, "w", encoding="utf-8") as f:
        f.write(submit_content)

    print(f"[INFO] SUBMIT.txt 已生成: {submit_path}")
    return submit_path


def parse_submit_txt(submit_path):
    """解析 SUBMIT.txt 文件"""
    submit_data = {}

    if not os.path.exists(submit_path):
        return None, f"SUBMIT.txt 文件不存在: {submit_path}"

    if os.path.getsize(submit_path) == 0:
        return None, f"SUBMIT.txt 文件为空: {submit_path}"

    # 读取文件（添加编码容错）
    lines = []
    try:
        with open(submit_path, encoding="utf-8") as f:
            lines = f.readlines()
    except UnicodeDecodeError:
        # 使用更宽松的编码
        with open(submit_path, encoding="latin-1") as f:
            lines = f.readlines()
    except Exception as e:
        return None, f"读取 SUBMIT.txt 文件时出错: {e}"

    for line in lines:
        line = line.strip()
        if not line:
            continue

        # 解析 key: value 格式
        if ": " in line:
            key, value = line.split(": ", 1)
            submit_data[key.strip()] = value.strip()

    return submit_data, None


def validate_submit_txt(submit_path):
    """校验 SUBMIT.txt 文件"""
    errors = []
    warnings = []

    # 1. 检查文件是否存在且非空
    if not os.path.exists(submit_path):
        errors.append(f"SUBMIT.txt 文件不存在: {submit_path}")
        return False, errors, warnings

    if os.path.getsize(submit_path) == 0:
        errors.append(f"SUBMIT.txt 文件为空: {submit_path}")
        return False, errors, warnings

    # 2. 解析文件（添加编码容错）
    submit_data, parse_error = parse_submit_txt(submit_path)
    if parse_error:
        errors.append(parse_error)
        return False, errors, warnings

    # 3. 检查是否包含所有必需的键
    missing_keys = []
    for key in SUBMIT_REQUIRED_KEYS:
        if key not in submit_data:
            missing_keys.append(key)

    if missing_keys:
        errors.append(f"SUBMIT.txt 缺少必需的键: {', '.join(missing_keys)}")

    # 4. 检查 report 路径是否存在且非空
    if "report" in submit_data:
        report_path = submit_data["report"]
        if not os.path.exists(report_path):
            errors.append(f"report 路径不存在: {report_path}")
        elif os.path.getsize(report_path) == 0:
            errors.append(f"report 文件为空: {report_path}")

    # 5. 检查 selftest_log 路径是否存在且非空，并且包含 EXIT_CODE=0
    if "selftest_log" in submit_data:
        selftest_path = submit_data["selftest_log"]
        if not os.path.exists(selftest_path):
            errors.append(f"selftest_log 路径不存在: {selftest_path}")
        elif os.path.getsize(selftest_path) == 0:
            errors.append(f"selftest_log 文件为空: {selftest_path}")
        else:
            # 检查 selftest_log 是否包含 EXIT_CODE=0（添加编码容错）
            try:
                with open(selftest_path, encoding="utf-8") as f:
                    selftest_content = f.read()

                if "EXIT_CODE=0" not in selftest_content:
                    errors.append(f"selftest_log 缺少 EXIT_CODE=0: {selftest_path}")
            except UnicodeDecodeError:
                # 使用更宽松的编码
                with open(selftest_path, encoding="latin-1") as f:
                    selftest_content = f.read()

                if "EXIT_CODE=0" not in selftest_content:
                    errors.append(f"selftest_log 缺少 EXIT_CODE=0: {selftest_path}")
            except Exception as e:
                errors.append(f"读取 selftest_log 文件时出错: {e}")

    # 6. 检查 evidence_paths 中的每个路径是否存在且非空
    if "evidence_paths" in submit_data:
        evidence_paths = submit_data["evidence_paths"]
        if evidence_paths != "-":
            # 解析路径列表（支持逗号分隔）
            paths = [p.strip() for p in evidence_paths.split(",") if p.strip()]
            for path in paths:
                if not os.path.exists(path):
                    errors.append(f"evidence_path 不存在: {path}")
                elif os.path.isfile(path) and os.path.getsize(path) == 0:
                    errors.append(f"evidence 文件为空: {path}")

    # 7. 检查 status 是否为 PASS 或 FAIL
    if "status" in submit_data:
        status = submit_data["status"]
        if status not in ["PASS", "FAIL"]:
            errors.append(f"status 必须为 PASS 或 FAIL，当前值: {status}")

    # 8. 检查 forbidden_check 是否包含所有必需的检查
    if "forbidden_check" in submit_data:
        forbidden_check = submit_data["forbidden_check"]
        required_checks = ["no_law_copy", "no_delete", "relative_paths", "no_new_entry_file"]
        for check in required_checks:
            if check not in forbidden_check:
                warnings.append(f"forbidden_check 建议包含: {check}")

    return len(errors) == 0, errors, warnings


def run_submit_txt_check(task_code=None, area=None):
    """运行 SUBMIT.txt 检查"""
    # 仅检查 git 跟踪的 SUBMIT.txt（本地未跟踪的证据不参与门禁）
    submit_files = []
    try:
        import subprocess

        p = subprocess.run(
            ["git", "ls-files", "docs/REPORT"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=8,
        )
        if int(p.returncode or 0) == 0:
            for ln in (p.stdout or "").splitlines():
                rel = (ln or "").strip().replace("\\", "/")
                if rel.endswith("/SUBMIT.txt"):
                    submit_files.append(rel)
    except Exception:
        submit_files = []

    if not submit_files:
        print("[INFO] 未发现 git 跟踪的 SUBMIT.txt，跳过检查")
        return 0

    overall_exit = 0

    # 如果指定了 TaskCode 和 area，只检查对应的 SUBMIT.txt
    if task_code and area:
        target_submit = f"docs/REPORT/{area}/artifacts/{task_code}/SUBMIT.txt"
        if target_submit in submit_files:
            submit_files = [target_submit]
        else:
            print(f"[ERROR] 指定的 SUBMIT.txt 文件不存在: {target_submit}")
            return 1

    # 检查所有找到的 SUBMIT.txt 文件
    for submit_path in submit_files:
        print("\n=== 检查 SUBMIT.txt 文件 ===")
        print(f"文件: {submit_path}")

        # 执行校验
        is_valid, errors, warnings = validate_submit_txt(submit_path)

        # 打印结果
        if warnings:
            print("\nWARNINGS:")
            for warning in warnings:
                print(f"   - {warning}")

        if errors:
            print("\nERROR:")
            for error in errors:
                print(f"   - {error}")
            print("\nRESULT: FAIL")
            overall_exit = 1
        else:
            print("\nRESULT: PASS")

    return overall_exit


def main():
    """主函数（用于直接运行测试）"""
    import argparse

    parser = argparse.ArgumentParser(description="SUBMIT.txt 生成与校验工具")
    parser.add_argument("--generate", action="store_true", help="生成 SUBMIT.txt")
    parser.add_argument("--validate", action="store_true", help="校验 SUBMIT.txt")
    parser.add_argument("--task-code", type=str, help="TaskCode")
    parser.add_argument("--area", type=str, help="Area")
    parser.add_argument("--content", type=str, help="SUBMIT 内容")
    parser.add_argument("--submit-path", type=str, help="SUBMIT.txt 路径")

    args = parser.parse_args()

    if args.generate:
        if not args.task_code or not args.area or not args.content:
            parser.error("--generate 模式需要 --task-code, --area 和 --content 参数")
        generate_submit_txt(args.task_code, args.area, args.content)
    elif args.validate:
        if not args.submit_path:
            parser.error("--validate 模式需要 --submit-path 参数")
        is_valid, errors, warnings = validate_submit_txt(args.submit_path)
        if is_valid:
            print("SUBMIT.txt 校验通过")
            exit(0)
        else:
            print("SUBMIT.txt 校验失败:")
            for error in errors:
                print(f"   - {error}")
            exit(1)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
