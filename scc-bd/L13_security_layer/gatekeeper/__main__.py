#!/usr/bin/env python3
import argparse
import json
import os
from datetime import datetime

from . import manifest


def generate_json_report(
    report_path,
    manifest_exit,
    import_exit,
    law_exit,
    fast_gate_exit=0,
    submit_exit=0,
    ata_hashchain_exit=0,
    manifest_entries_count=None,
):
    """生成 JSON 报告"""
    import subprocess

    # 获取 git 信息（如果可用）
    git_available = False
    git_commit = None
    repo_root = "UNKNOWN"

    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0:
            git_available = True
            git_commit = result.stdout.strip()
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass

    if git_available:
        try:
            result = subprocess.run(
                ["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0:
                repo_root = result.stdout.strip()
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass

    # 计算综合结果
    overall_result = (
        "PASS"
        if (
            manifest_exit == 0
            and import_exit == 0
            and law_exit == 0
            and fast_gate_exit == 0
            and submit_exit == 0
            and ata_hashchain_exit == 0
        )
        else "FAIL"
    )

    report = {
        "gatekeeper_version": "v0.1",
        "timestamp_utc": datetime.utcnow().isoformat() + "Z",
        "git_available": git_available,
        "git_commit": git_commit,
        "repo_root": repo_root,
        "manifest_entries_count": manifest_entries_count,
        "overall_result": overall_result,
        "checks": {
            "manifest": {
                "exit_code": manifest_exit,
                "result": "PASS" if manifest_exit == 0 else "FAIL",
            },
            "import_scan": {
                "exit_code": import_exit,
                "result": "PASS" if import_exit == 0 else "FAIL",
            },
            "law_scan": {"exit_code": law_exit, "result": "PASS" if law_exit == 0 else "FAIL"},
            "fast_gate": {
                "exit_code": fast_gate_exit,
                "result": "PASS" if fast_gate_exit == 0 else "FAIL",
            },
            "submit_txt": {
                "exit_code": submit_exit,
                "result": "PASS" if submit_exit == 0 else "FAIL",
            },
            "ata_hashchain": {
                "exit_code": ata_hashchain_exit,
                "result": "PASS" if ata_hashchain_exit == 0 else "FAIL",
            },
        },
    }

    # 确保目录存在
    report_dir = os.path.dirname(report_path)
    if report_dir:
        os.makedirs(report_dir, exist_ok=True)

    # 写入报告
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    print(f"[INFO] JSON 报告已生成: {report_path}")


def main():
    parser = argparse.ArgumentParser(description="QCC Gatekeeper - 门禁检查工具")
    subparsers = parser.add_subparsers(dest="command", help="可用子命令")

    parser_manifest = subparsers.add_parser("manifest", help="Manifest 检查")
    parser_manifest.add_argument("--check", action="store_true", help="检查 manifest")
    parser_manifest.add_argument("--write", action="store_true", help="写入 manifest")

    parser_law = subparsers.add_parser("law-scan", help="Law 扫描")
    parser_law.add_argument("--check", action="store_true", help="检查 law")
    parser_law.add_argument("--changed", nargs="*", help="只扫描指定文件")

    parser_import = subparsers.add_parser("import-scan", help="Import 扫描")
    parser_import.add_argument("--check", action="store_true", help="检查 import")
    parser_import.add_argument("--changed", nargs="*", help="只扫描指定文件")

    parser_fast_gate = subparsers.add_parser("fast-gate", help="快速门禁检查")
    parser_fast_gate.add_argument("--check", action="store_true", help="运行快速门禁检查")

    parser_dual = subparsers.add_parser("dual", help="双阶段门禁检查 (L0 + L1)")
    parser_dual.add_argument("--check", action="store_true", help="运行双阶段门禁检查")

    parser_all = subparsers.add_parser("all", help="运行所有检查")
    parser_all.add_argument("--check", action="store_true", help="检查所有")
    parser_all.add_argument("--report-json", type=str, help="生成 JSON 报告到指定路径")

    parser_submit = subparsers.add_parser("submit-txt", help="SUBMIT.txt 检查")
    parser_submit.add_argument("--check", action="store_true", help="检查 SUBMIT.txt")
    parser_submit.add_argument("--task-code", type=str, help="TaskCode")
    parser_submit.add_argument("--area", type=str, help="Area")

    parser_ata_hashchain = subparsers.add_parser("ata-hashchain", help="ATA 哈希链检查")
    parser_ata_hashchain.add_argument("--check", action="store_true", help="检查 ATA 消息哈希链")
    parser_ata_hashchain.add_argument("--task-code", type=str, help="TaskCode")

    # ATA validate-ata command (used by CI phase checks)
    parser_validate_ata = subparsers.add_parser(
        "validate-ata", help="ATA context/schema + registry invariants 校验"
    )
    parser_validate_ata.add_argument("--check", action="store_true", help="运行 ATA 校验")
    parser_validate_ata.add_argument(
        "--path",
        type=str,
        help="单个 ATA context.json 文件路径（不填则扫描 docs/REPORT/**/artifacts/**/ata/context.json）",
    )

    # Agent registry invariants (CI hard-gate for MCP/ATA)
    parser_agent_registry = subparsers.add_parser(
        "agent-registry", help="Agent registry invariants 校验（编号唯一/范围/send_enabled类型）"
    )
    parser_agent_registry.add_argument(
        "--check", action="store_true", help="运行 agent_registry.json 校验"
    )

    # Dual drift sensor command
    parser_dual_drift = subparsers.add_parser("dual-drift", help="Dual Consensus Drift Sensor")
    parser_dual_drift.add_argument(
        "--check", action="store_true", help="Run dual consensus drift detection"
    )
    parser_dual_drift.add_argument(
        "--self-test", action="store_true", help="Run self-test for drift sensor"
    )

    # Fastcheck 命令：先跑 L0，再跑 verify_hardness
    parser_fastcheck = subparsers.add_parser(
        "fastcheck", help="快速检查：先跑 L0，再跑 verify_hardness"
    )
    parser_fastcheck.add_argument("--check", action="store_true", help="运行快速检查")

    # Global Greenbar command: runs all required checks in sequence
    parser_global_greenbar = subparsers.add_parser(
        "global-greenbar", help="全局绿条检查：一键跑完所有必检项"
    )
    parser_global_greenbar.add_argument("--check", action="store_true", help="运行全局绿条检查")
    parser_global_greenbar.add_argument("--report-json", type=str, help="生成 JSON 报告到指定路径")

    args = parser.parse_args()

    # Manifest 命令
    if args.command == "manifest":
        manifest_path = "configs/current/qcc_manifest.json"
        if args.check:
            exit_code = manifest.check_manifest(manifest_path)
            exit(exit_code)
        elif args.write:
            exit_code = manifest.write_manifest(manifest_path)
            exit(exit_code)
    # Import-scan 命令
    elif args.command == "import-scan":
        if args.check:
            from . import import_scan

            scan_files = args.changed if args.changed else None
            exit_code = import_scan.scan_imports(scan_files)
            exit(exit_code)
    # Law-scan 命令
    elif args.command == "law-scan":
        if args.check:
            from . import law_pointer_scan

            scan_files = args.changed if args.changed else None
            exit_code = law_pointer_scan.scan_law_pointers(None, scan_files)
            exit(exit_code)
    # Fast Gate 命令
    elif args.command == "fast-gate":
        if args.check:
            from . import fast_gate

            exit_code = fast_gate.run_fast_gate_checks()
            exit(exit_code)
    # Dual Gate 命令
    elif args.command == "dual":
        if args.check:
            from . import fast_gate

            exit_code = fast_gate.run_dual_gate_checks()
            exit(exit_code)
    # Submit-txt 命令
    elif args.command == "submit-txt":
        if args.check:
            from . import submit_txt

            submit_path = args.submit_path if hasattr(args, "submit_path") else None
            exit_code = submit_txt.run_submit_txt_check()
            exit(exit_code)
    # ATA Hashchain 命令
    elif args.command == "ata-hashchain":
        if args.check:
            from . import ata_hashchain

            exit_code = ata_hashchain.run_ata_hashchain_check(args.task_code)
            exit(exit_code)
    # ATA 校验命令
    elif args.command == "validate-ata":
        if args.check:
            from .commands.validate_ata import (
                validate_all_ata_contexts,
                validate_ata_context,
            )

            if args.path:
                # 校验单个文件
                passed, reason_code = validate_ata_context(args.path)
                exit(0 if passed else 1)
            else:
                # 校验所有文件
                passed, reason_code = validate_all_ata_contexts()
                exit(0 if passed else 1)
    # Agent registry invariants command
    elif args.command == "agent-registry":
        if args.check:
            from .commands.validate_agent_registry import (
                validate_agent_registry_invariants,
            )

            passed, reason_code = validate_agent_registry_invariants()
            exit(0 if passed else 1)
    # Dual drift sensor command
    elif args.command == "dual-drift":
        if args.check or args.self_test:
            from . import dual_drift_sensor

            sensor = dual_drift_sensor.DualDriftSensor()
            if args.self_test:
                passed, message = sensor.run_self_test()
                print(f"\nSelf-test result: {'PASS' if passed else 'FAIL'}")
                print(f"Message: {message}")
                exit(0 if passed else 1)
            else:
                passed, _ = sensor.run_drift_detection()
                exit(0 if passed else 1)
    # All 命令
    elif args.command == "all":
        if args.check:
            print("Running all checks...")

            # 运行 manifest 检查
            print("\n1. manifest --check")
            manifest_path = "configs/current/qcc_manifest.json"
            manifest_exit = manifest.check_manifest(manifest_path)

            # 获取 manifest entries count
            manifest_entries_count = None
            try:
                with open(manifest_path, encoding="utf-8") as f:
                    manifest_data = json.load(f)
                manifest_entries_count = len(manifest_data.get("entries", []))
            except (OSError, json.JSONDecodeError, UnicodeDecodeError):
                pass

            # 运行 import-scan 检查
            print("\n2. import-scan --check")
            from . import import_scan

            import_exit = import_scan.scan_imports(None)

            # 运行 law-scan 检查
            print("\n3. law-scan --check")
            from . import law_pointer_scan

            law_exit = law_pointer_scan.scan_law_pointers(None)

            # 运行 fast-gate 检查
            print("\n4. fast-gate --check")
            from . import fast_gate

            fast_gate_exit = fast_gate.run_fast_gate_checks()

            # 运行 submit-txt 检查
            print("\n5. submit-txt --check")
            from . import submit_txt

            submit_exit = submit_txt.run_submit_txt_check()

            # 运行 ata-hashchain 检查
            print("\n6. ata-hashchain --check")
            from . import ata_hashchain

            ata_hashchain_exit = ata_hashchain.run_ata_hashchain_check()

            # 综合退出码
            overall_exit = (
                manifest_exit
                or import_exit
                or law_exit
                or fast_gate_exit
                or submit_exit
                or ata_hashchain_exit
            )
            print(f"\nOverall result: {'PASS' if overall_exit == 0 else 'FAIL'}")

            # 生成 JSON 报告（如果指定）
            if args.report_json:
                generate_json_report(
                    args.report_json,
                    manifest_exit,
                    import_exit,
                    law_exit,
                    fast_gate_exit,
                    submit_exit,
                    ata_hashchain_exit,
                    manifest_entries_count,
                )

            exit(overall_exit)
    # Fastcheck 命令：先跑 L0，再跑 verify_hardness
    elif args.command == "fastcheck":
        if args.check:
            import subprocess
            import sys

            # 1. 运行 L0 检查
            print("Running L0 gate check...")
            l0_cmd = [sys.executable, "-m", "tools.gatekeeper.fast_gate", "l0"]
            l0_result = subprocess.run(l0_cmd, capture_output=True, text=True)

            # 提取 L0 的信号行
            l0_result_line = ""
            l0_reason_code_line = ""
            for line in l0_result.stdout.splitlines():
                if line.startswith("RESULT="):
                    l0_result_line = line
                elif line.startswith("REASON_CODE="):
                    l0_reason_code_line = line

            # 打印 L0 结果
            if l0_result_line:
                print(l0_result_line)
            if l0_reason_code_line:
                print(l0_reason_code_line)

            # 检查 L0 是否失败
            if l0_result.returncode != 0:
                print(f"L0 check failed, exiting with code {l0_result.returncode}")
                exit(l0_result.returncode)

            # 2. 运行 verify_hardness 检查
            print("\nRunning verify_hardness check...")
            hardness_cmd = [sys.executable, "-m", "tools.gatekeeper.verify_hardness"]
            hardness_result = subprocess.run(hardness_cmd, capture_output=True, text=True)

            # 提取 verify_hardness 的信号行
            hardness_result_line = ""
            for line in hardness_result.stdout.splitlines():
                if line.startswith("HARDNESS_RESULT="):
                    hardness_result_line = line
                elif line.startswith("HARDNESS_REASON_CODE=") or line.startswith("HARDNESS_EXIT="):
                    print(line)

            # 打印 HARDNESS_RESULT
            if hardness_result_line:
                print(hardness_result_line)

            # 检查 verify_hardness 是否失败
            if hardness_result.returncode != 0:
                print(
                    f"verify_hardness check failed, exiting with code {hardness_result.returncode}"
                )
                exit(hardness_result.returncode)

            exit(0)
    # Global Greenbar command: runs all required checks in sequence
    elif args.command == "global-greenbar":
        if args.check:
            import subprocess
            import sys
            from datetime import datetime

            print("============================================================")
            print("CI-HARDNESS-GLOBAL-GREENBAR-v0.1__20260116")
            print("全局绿条检查 - 一键跑完所有必检项")
            print("============================================================")

            # 存储所有检查结果
            results = []

            # 1. 运行 dual 正向 PASS 检查
            print("\n1. 运行 dual 正向 PASS 检查...")
            dual_cmd = [sys.executable, "-m", "tools.gatekeeper.dual", "--check"]
            dual_result = subprocess.run(dual_cmd, capture_output=True, text=True)
            dual_ok = dual_result.returncode == 0
            results.append(
                {
                    "name": "dual_forward",
                    "result": "PASS" if dual_ok else "FAIL",
                    "exit_code": dual_result.returncode,
                }
            )
            print(f"   结果: {'✅ PASS' if dual_ok else '❌ FAIL'}")

            # 2. 运行 verify_hardness 检查（含 mutation must fail 与 self-check 3fails）
            print("\n2. 运行 verify_hardness 检查...")
            hardness_cmd = [sys.executable, "-m", "tools.gatekeeper.verify_hardness"]
            hardness_result = subprocess.run(hardness_cmd, capture_output=True, text=True)
            hardness_ok = hardness_result.returncode == 0
            results.append(
                {
                    "name": "verify_hardness",
                    "result": "PASS" if hardness_ok else "FAIL",
                    "exit_code": hardness_result.returncode,
                }
            )
            # 打印 verify_hardness 的关键输出
            for line in hardness_result.stdout.splitlines():
                if any(
                    prefix in line
                    for prefix in ["HARDNESS_RESULT=", "HARDNESS_REASON_CODE=", "HARDNESS_EXIT="]
                ):
                    print(f"   {line}")

            # 3. 运行 E2E triplebus 检查（exchange+hub+stub worker）
            print("\n3. 运行 E2E triplebus 检查...")
            triplebus_cmd = [sys.executable, "-m", "tools.triplebus_e2e_test"]
            triplebus_result = subprocess.run(triplebus_cmd, capture_output=True, text=True)
            triplebus_ok = triplebus_result.returncode == 0
            results.append(
                {
                    "name": "triplebus_e2e",
                    "result": "PASS" if triplebus_ok else "FAIL",
                    "exit_code": triplebus_result.returncode,
                }
            )
            print(f"   结果: {'✅ PASS' if triplebus_ok else '❌ FAIL'}")

            # 汇总结果
            all_ok = all(r["result"] == "PASS" for r in results)

            # 生成摘要输出（≤10行）
            print("\n============================================================")
            print("全局绿条检查摘要")
            print("============================================================")
            print(f"检查总数: {len(results)}")
            print(f"通过检查: {sum(1 for r in results if r['result'] == 'PASS')}")
            print(f"失败检查: {sum(1 for r in results if r['result'] == 'FAIL')}")
            print(f"总体结果: {'✅ PASS' if all_ok else '❌ FAIL'}")
            print("============================================================")

            # 生成结果信号行
            print(f"HARDNESS_RESULT={'PASS' if all_ok else 'FAIL'}")
            print(f"REASON_CODE={'NONE' if all_ok else 'CHECK_FAILED'}")
            print(f"TRACE_ID={datetime.now().strftime('%Y%m%d%H%M%S%f')[:-3]}")

            # 生成 JSON 报告（如果指定）
            if args.report_json:
                # 确保目录存在
                import os

                report_dir = os.path.dirname(args.report_json)
                if report_dir:
                    os.makedirs(report_dir, exist_ok=True)

                # 生成报告
                report = {
                    "version": "v0.1",
                    "timestamp_utc": datetime.utcnow().isoformat() + "Z",
                    "task_code": "CI-HARDNESS-GLOBAL-GREENBAR-v0.1__20260116",
                    "overall_result": "PASS" if all_ok else "FAIL",
                    "checks": results,
                    "summary": {
                        "total": len(results),
                        "passed": sum(1 for r in results if r["result"] == "PASS"),
                        "failed": sum(1 for r in results if r["result"] == "FAIL"),
                    },
                }

                with open(args.report_json, "w", encoding="utf-8") as f:
                    json.dump(report, f, indent=2, ensure_ascii=False)
                print(f"\nJSON 报告已生成: {args.report_json}")

            exit(0 if all_ok else 1)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
