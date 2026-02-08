#!/usr/bin/env python3
"""
绝对路径检测门禁脚本
TaskCode: GATE-NO-ABSOLUTE-PATH-v0.1__20260115
硬约束: Fail-Closed
"""

import os
import re
import sys


def is_placeholder(text):
    """检查文本是否为允许的占位符"""
    # 只允许 <ABS_PATH> 占位符
    return re.search(r"<ABS_PATH>", text) is not None


def contains_absolute_path(content):
    """检查内容中是否包含绝对路径"""
    violations = []

    # Windows绝对路径: C:\xxx 或 D:\xxx 等
    windows_pattern = r"[A-Za-z]:\\[^\\]"
    for match in re.finditer(windows_pattern, content):
        # 确保匹配的是完整的路径部分
        match_str = match.group()
        # 只匹配驱动器后跟反斜杠的模式
        if len(match_str) >= 2 and match_str[1] == ":":
            context = content[max(0, match.start() - 20) : min(len(content), match.end() + 20)]
            if not is_placeholder(context):
                # 清理上下文，移除可能导致编码问题的字符
                safe_context = context.strip().replace("\n", " ")
                # 移除可能的Unicode表情符号
                safe_context = re.sub(r"[\u2000-\u3000\u2700-\u27bf]", "", safe_context)
                violations.append(
                    {"type": "Windows绝对路径", "match": match_str, "context": safe_context}
                )

    # UNC路径: \\server\share
    unc_pattern = r"\\\\[a-zA-Z0-9]+\\[a-zA-Z0-9_\\-]+"
    for match in re.finditer(unc_pattern, content):
        context = content[max(0, match.start() - 20) : min(len(content), match.end() + 20)]
        if not is_placeholder(context):
            violations.append(
                {
                    "type": "UNC路径",
                    "match": match.group(),
                    "context": context.strip().replace("\n", " "),
                }
            )

    # Linux绝对路径: /home/, /var/, /usr/ 等
    linux_patterns = [
        r"/home/",
        r"/var/",
        r"/usr/",
        r"/etc/",
        r"/root/",
        r"/tmp/",
        r"/opt/",
        r"/lib/",
        r"/bin/",
        r"/sbin/",
        r"/boot/",
        r"/sys/",
        r"/proc/",
        r"/dev/",
    ]

    for pattern in linux_patterns:
        for match in re.finditer(pattern, content):
            context = content[max(0, match.start() - 20) : min(len(content), match.end() + 20)]
            if not is_placeholder(context):
                # 排除URL中的路径（如 https://example.com/path）
                if "://" not in context[: match.start()]:
                    violations.append(
                        {
                            "type": "Linux绝对路径",
                            "match": match.group(),
                            "context": context.strip().replace("\n", " "),
                        }
                    )

    return violations


def scan_directory(directory):
    """扫描目录中的文件，检查绝对路径"""
    violations = []

    if not os.path.exists(directory):
        print(f"[WARNING] 目录不存在: {directory}")
        return violations

    for root, dirs, files in os.walk(directory):
        # 跳过隐藏目录和特定目录
        dirs[:] = [
            d
            for d in dirs
            if not d.startswith(".")
            and d not in ["node_modules", "__pycache__", "venv", ".venv", ".git"]
        ]

        for file in files:
            # 检查文件是否符合要扫描的类型
            should_scan = False

            # 1. 检查扩展名：覆盖REPORT和其他文档
            if file.endswith((".md", ".py", ".yaml", ".yml", ".json", ".txt", ".sh", ".bat")):
                should_scan = True

            # 2. 检查特定文件名：覆盖SUBMIT.txt、selftest.log
            if file in ["SUBMIT.txt", "selftest.log"]:
                should_scan = True

            # 3. 检查文件名模式：覆盖REPORT文件
            if "REPORT__" in file and file.endswith(".md"):
                should_scan = True

            # 4. 检查静态Board文件
            if "BOARD" in file and file.endswith(".md"):
                should_scan = True

            if should_scan:
                file_path = os.path.join(root, file)

                try:
                    with open(file_path, encoding="utf-8", errors="ignore") as f:
                        content = f.read()

                    file_violations = contains_absolute_path(content)

                    for violation in file_violations:
                        violations.append(
                            {
                                "file": file_path,
                                "violation_type": violation["type"],
                                "match": violation["match"],
                                "context": violation["context"],
                            }
                        )

                except Exception as e:
                    print(f"[WARNING] 无法读取文件 {file_path}: {e}")

    return violations


def main():
    """主函数"""

    # 使用固定编码输出，避免Windows编码问题
    def safe_print(message):
        """安全打印函数，处理编码问题"""
        try:
            print(message)
        except UnicodeEncodeError:
            # 移除可能导致编码问题的字符
            safe_message = message.encode("ascii", "ignore").decode("ascii")
            print(safe_message)

    safe_print("[INFO] 开始执行绝对路径检测...")

    # 要扫描的目录 - 扩大覆盖范围
    scan_dirs = ["docs", "tools", "configs", "taskhub"]

    all_violations = []

    for scan_dir in scan_dirs:
        if os.path.exists(scan_dir):
            safe_print(f"[INFO] 扫描目录: {scan_dir}")
            violations = scan_directory(scan_dir)
            all_violations.extend(violations)

    # 打印违规信息
    if all_violations:
        safe_print(f"\n[ERROR] 发现 {len(all_violations)} 个绝对路径违规:")

        for i, violation in enumerate(all_violations, 1):
            safe_print(f"\n  {i}. 文件: {violation['file']}")
            safe_print(f"     类型: {violation['violation_type']}")
            safe_print(f"     匹配: {violation['match']}")
            safe_print(f"     上下文: {violation['context']}")

        safe_print("\n[ERROR] 绝对路径检测失败！")
        safe_print("REASON_CODE=ABS_PATH")
        return 1
    else:
        safe_print("[INFO] 未发现绝对路径违规，检测通过！")
        return 0


if __name__ == "__main__":
    sys.exit(main())
