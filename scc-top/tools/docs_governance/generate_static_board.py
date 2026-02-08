#!/usr/bin/env python3
"""
静态Board生成工具

扫描docs/REPORT/**/REPORT__*文件，提取关键字段，生成静态Board。
输出路径：docs/REPORT/_index/PROGRAM_BOARD__STATIC.md
"""

import os
import re
import sys
from datetime import datetime
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).parent.parent.parent
OUTPUT_PATH = REPO_ROOT / "docs/REPORT/_index/PROGRAM_BOARD__STATIC.md"


def extract_frontmatter(content: str) -> dict | None:
    """从Markdown内容中提取YAML frontmatter"""
    if not content.startswith("---"):
        return None

    yaml_end = content.find("---", 3)
    if yaml_end == -1:
        return None

    yaml_content = content[3:yaml_end]
    try:
        return yaml.safe_load(yaml_content)
    except yaml.YAMLError:
        return None


def extract_taskcode(content: str) -> str | None:
    """从Markdown内容中提取TaskCode"""
    match = re.search(r"TaskCode:\s*([\w-]+)", content)
    if match:
        return match.group(1)
    return None


def scan_report_files() -> list[dict]:
    """扫描所有REPORT__*文件并提取信息"""
    report_files = list(REPO_ROOT.glob("docs/REPORT/**/REPORT__*.md"))
    report_files.sort()

    reports = []
    for file_path in report_files:
        try:
            content = file_path.read_text(encoding="utf-8")
            frontmatter = extract_frontmatter(content)
            taskcode = extract_taskcode(content)

            report_info = {
                "file_path": str(file_path.relative_to(REPO_ROOT)),
                "taskcode": taskcode or "N/A",
                "doc_id": frontmatter.get("doc_id", "N/A") if frontmatter else "N/A",
                "kind": frontmatter.get("kind", "N/A") if frontmatter else "N/A",
                "scope": frontmatter.get("scope", "N/A") if frontmatter else "N/A",
                "topic": frontmatter.get("topic", "N/A") if frontmatter else "N/A",
                "version": frontmatter.get("version", "N/A") if frontmatter else "N/A",
                "status": frontmatter.get("status", "N/A") if frontmatter else "N/A",
                "owner": frontmatter.get("owner", "N/A") if frontmatter else "N/A",
                "created": frontmatter.get("created", "N/A") if frontmatter else "N/A",
                "updated": frontmatter.get("updated", "N/A") if frontmatter else "N/A",
            }
            reports.append(report_info)
        except Exception as e:
            print(f"Error processing {file_path}: {e}", file=sys.stderr)

    return reports


def generate_static_board(
    reports: list[dict], gate_result: str | None = None, reason_code: str | None = None
) -> str:
    """生成静态Board的Markdown内容

    Args:
        reports: 报告列表
        gate_result: Gate检查结果，PASS或FAIL
        reason_code: Gate检查失败的原因码

    Returns:
        生成的Markdown内容
    """
    # 按status分组
    status_groups = {"DONE": [], "ACTIVE": [], "BLOCKED": [], "DRAFT": [], "OTHER": []}

    for report in reports:
        status = report["status"].upper()
        if status in status_groups:
            status_groups[status].append(report)
        else:
            status_groups["OTHER"].append(report)

    # 计算各状态计数
    done_count = len(status_groups["DONE"])
    active_count = len(status_groups["ACTIVE"])
    blocked_count = len(status_groups["BLOCKED"])
    draft_count = len(status_groups["DRAFT"])
    other_count = len(status_groups["OTHER"])
    total_count = len(reports)

    # 生成gate状态头
    gate_status_header = ""
    if gate_result:
        gate_status = "PASS" if gate_result == "GATE_PASS" else "FAIL"
        gate_status_header = f"**LAST_GATE={gate_status} | REASON_CODE={reason_code or 'SUCCESS'} | RUN_TIME={datetime.now().isoformat()}**\n\n"

    content = f"""---
doc_id: PROGRAM_BOARD__STATIC
kind: REPORT
scope: program_management
topic: 静态Program Board
version: v1.1
status: ACTIVE
owner: ai-assistant
created: {datetime.now().strftime("%Y-%m-%d")}
updated: {datetime.now().strftime("%Y-%m-%d")}
law_ref: law/QCC-README.md
---

{gate_status_header}# 静态Program Board

## 基本信息

- **生成时间**: {datetime.now().isoformat()}
- **报告数量**: {total_count}
- **状态**: 自动生成，每日更新

## 状态计数

| 状态 | 数量 | 占比 |
|------|------|------|
| DONE | {done_count} | {round(done_count / total_count * 100) if total_count > 0 else 0}% |
| ACTIVE | {active_count} | {round(active_count / total_count * 100) if total_count > 0 else 0}% |
| BLOCKED | {blocked_count} | {round(blocked_count / total_count * 100) if total_count > 0 else 0}% |
| DRAFT | {draft_count} | {round(draft_count / total_count * 100) if total_count > 0 else 0}% |
| OTHER | {other_count} | {round(other_count / total_count * 100) if total_count > 0 else 0}% |

## 报告列表

### DONE ({done_count}个)

| TaskCode | Status | YYYYMMDD | Report链接 | selftest.log链接 |
|----------|--------|----------|------------|-----------------|
"""

    # 生成DONE状态的报告列表
    for report in status_groups["DONE"]:
        # 提取YYYYMMDD格式日期
        yyyymmdd = "N/A"
        if report["created"] and report["created"] != "N/A":
            try:
                if isinstance(report["created"], str):
                    date_obj = datetime.strptime(report["created"], "%Y-%m-%d")
                    yyyymmdd = date_obj.strftime("%Y%m%d")
                else:
                    # 已经是日期对象
                    yyyymmdd = report["created"].strftime("%Y%m%d")
            except ValueError:
                pass

        # 生成selftest.log链接
        selftest_link = "N/A"
        report_dir = os.path.dirname(report["file_path"])
        selftest_path = os.path.join(
            report_dir,
            "artifacts",
            f"{report['taskcode']}" if report["taskcode"] != "N/A" else "",
            "selftest.log",
        )
        selftest_path_relative = selftest_path.replace("\\", "/")
        selftest_full_path = REPO_ROOT / selftest_path
        if selftest_full_path.exists():
            selftest_link = f"[{selftest_path_relative}](/{selftest_path_relative})"

        content += f"| {report['taskcode']} | {report['status']} | {yyyymmdd} | [{report['file_path']}](/{report['file_path'].replace('\\', '/')}) | {selftest_link} |\n"

    # 生成ACTIVE状态的报告列表
    content += f"\n### ACTIVE ({active_count}个)\n\n| TaskCode | Status | YYYYMMDD | Report链接 | selftest.log链接 |\n|----------|--------|----------|------------|-----------------|\n"
    for report in status_groups["ACTIVE"]:
        # 提取YYYYMMDD格式日期
        yyyymmdd = "N/A"
        if report["created"] and report["created"] != "N/A":
            try:
                if isinstance(report["created"], str):
                    date_obj = datetime.strptime(report["created"], "%Y-%m-%d")
                    yyyymmdd = date_obj.strftime("%Y%m%d")
                else:
                    # 已经是日期对象
                    yyyymmdd = report["created"].strftime("%Y%m%d")
            except ValueError:
                pass

        # 生成selftest.log链接
        selftest_link = "N/A"
        report_dir = os.path.dirname(report["file_path"])
        selftest_path = os.path.join(
            report_dir,
            "artifacts",
            f"{report['taskcode']}" if report["taskcode"] != "N/A" else "",
            "selftest.log",
        )
        selftest_path_relative = selftest_path.replace("\\", "/")
        selftest_full_path = REPO_ROOT / selftest_path
        if selftest_full_path.exists():
            selftest_link = f"[{selftest_path_relative}](/{selftest_path_relative})"

        content += f"| {report['taskcode']} | {report['status']} | {yyyymmdd} | [{report['file_path']}](/{report['file_path'].replace('\\', '/')}) | {selftest_link} |\n"

    # 生成BLOCKED状态的报告列表
    content += f"\n### BLOCKED ({blocked_count}个)\n\n| TaskCode | Status | YYYYMMDD | Report链接 | selftest.log链接 |\n|----------|--------|----------|------------|-----------------|\n"
    for report in status_groups["BLOCKED"]:
        # 提取YYYYMMDD格式日期
        yyyymmdd = "N/A"
        if report["created"] and report["created"] != "N/A":
            try:
                if isinstance(report["created"], str):
                    date_obj = datetime.strptime(report["created"], "%Y-%m-%d")
                    yyyymmdd = date_obj.strftime("%Y%m%d")
                else:
                    # 已经是日期对象
                    yyyymmdd = report["created"].strftime("%Y%m%d")
            except ValueError:
                pass

        # 生成selftest.log链接
        selftest_link = "N/A"
        report_dir = os.path.dirname(report["file_path"])
        selftest_path = os.path.join(
            report_dir,
            "artifacts",
            f"{report['taskcode']}" if report["taskcode"] != "N/A" else "",
            "selftest.log",
        )
        selftest_path_relative = selftest_path.replace("\\", "/")
        selftest_full_path = REPO_ROOT / selftest_path
        if selftest_full_path.exists():
            selftest_link = f"[{selftest_path_relative}](/{selftest_path_relative})"

        content += f"| {report['taskcode']} | {report['status']} | {yyyymmdd} | [{report['file_path']}](/{report['file_path'].replace('\\', '/')}) | {selftest_link} |\n"

    # 生成DRAFT状态的报告列表
    content += f"\n### DRAFT ({draft_count}个)\n\n| TaskCode | Status | YYYYMMDD | Report链接 | selftest.log链接 |\n|----------|--------|----------|------------|-----------------|\n"
    for report in status_groups["DRAFT"]:
        # 提取YYYYMMDD格式日期
        yyyymmdd = "N/A"
        if report["created"] and report["created"] != "N/A":
            try:
                if isinstance(report["created"], str):
                    date_obj = datetime.strptime(report["created"], "%Y-%m-%d")
                    yyyymmdd = date_obj.strftime("%Y%m%d")
                else:
                    # 已经是日期对象
                    yyyymmdd = report["created"].strftime("%Y%m%d")
            except ValueError:
                pass

        # 生成selftest.log链接
        selftest_link = "N/A"
        report_dir = os.path.dirname(report["file_path"])
        selftest_path = os.path.join(
            report_dir,
            "artifacts",
            f"{report['taskcode']}" if report["taskcode"] != "N/A" else "",
            "selftest.log",
        )
        selftest_path_relative = selftest_path.replace("\\", "/")
        selftest_full_path = REPO_ROOT / selftest_path
        if selftest_full_path.exists():
            selftest_link = f"[{selftest_path_relative}](/{selftest_path_relative})"

        content += f"| {report['taskcode']} | {report['status']} | {yyyymmdd} | [{report['file_path']}](/{report['file_path'].replace('\\', '/')}) | {selftest_link} |\n"

    # 生成OTHER状态的报告列表
    if other_count > 0:
        content += f"\n### OTHER ({other_count}个)\n\n| TaskCode | Status | YYYYMMDD | Report链接 | selftest.log链接 |\n|----------|--------|----------|------------|-----------------|\n"
        for report in status_groups["OTHER"]:
            # 提取YYYYMMDD格式日期
            yyyymmdd = "N/A"
            if report["created"] and report["created"] != "N/A":
                try:
                    if isinstance(report["created"], str):
                        date_obj = datetime.strptime(report["created"], "%Y-%m-%d")
                        yyyymmdd = date_obj.strftime("%Y%m%d")
                    else:
                        # 已经是日期对象
                        yyyymmdd = report["created"].strftime("%Y%m%d")
                except ValueError:
                    pass

            # 生成selftest.log链接
            selftest_link = "N/A"
            report_dir = os.path.dirname(report["file_path"])
            selftest_path = os.path.join(
                report_dir,
                "artifacts",
                f"{report['taskcode']}" if report["taskcode"] != "N/A" else "",
                "selftest.log",
            )
            selftest_path_relative = selftest_path.replace("\\", "/")
            selftest_full_path = REPO_ROOT / selftest_path
            if selftest_full_path.exists():
                selftest_link = f"[{selftest_path_relative}](/{selftest_path_relative})"

            content += f"| {report['taskcode']} | {report['status']} | {yyyymmdd} | [{report['file_path']}](/{report['file_path'].replace('\\', '/')}) | {selftest_link} |\n"

    content += f"\n## 生成说明\n\n- 本文件由 `tools/docs_governance/generate_static_board.py` 自动生成\n- 扫描范围: `docs/REPORT/**/REPORT__*.md`\n- 包含所有标记为 REPORT 类型的报告\n- 按状态分组显示，各状态计数：DONE={done_count}, ACTIVE={active_count}, BLOCKED={blocked_count}, DRAFT={draft_count}, OTHER={other_count}\n- 总报告数: {total_count}\n"

    return content


def main():
    """主入口"""
    print("=" * 80)
    print("STATIC BOARD GENERATOR")
    print("=" * 80)
    print(f"输出路径: {OUTPUT_PATH}")

    # 解析命令行参数
    import argparse

    parser = argparse.ArgumentParser(description="静态Board生成工具")
    parser.add_argument("--gate-result", choices=["PASS", "FAIL"], help="Gate检查结果")
    parser.add_argument("--reason-code", help="Gate检查失败的原因码")
    args = parser.parse_args()

    # 扫描报告文件
    print("\n[1/2] 扫描报告文件...")
    reports = scan_report_files()
    print(f"找到 {len(reports)} 个报告文件")

    # 生成静态Board
    print("\n[2/2] 生成静态Board...")
    content = generate_static_board(reports, args.gate_result, args.reason_code)

    # 写入文件
    OUTPUT_PATH.write_text(content, encoding="utf-8")
    file_size = os.path.getsize(OUTPUT_PATH)

    print("\n静态Board已生成")
    print(f"输出文件: {OUTPUT_PATH}")
    print(f"文件大小: {file_size} 字节")
    print(f"报告数量: {len(reports)}")
    if args.gate_result:
        print(f"Gate结果: {args.gate_result}")
        print(f"原因码: {args.reason_code or 'SUCCESS'}")
    print("\n" + "=" * 80)

    return 0


if __name__ == "__main__":
    sys.exit(main())
