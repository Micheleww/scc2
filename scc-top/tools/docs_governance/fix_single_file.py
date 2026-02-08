#!/usr/bin/env python3
"""修复单个文件的编码问题"""

import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

REPO_ROOT = Path(__file__).parent.parent.parent
target_file = (
    REPO_ROOT
    / "docs/REPORT/ci/controlplane/REPORT__CI-E2E-TRIPLEBUS-REQUIRED-v0.2__20260115__20260115.md"
)

if not target_file.exists():
    print(f"File not found: {target_file}")
    sys.exit(1)

# 尝试多种编码
encodings = ["gbk", "gb2312", "gb18030", "latin-1", "cp1252"]

for encoding in encodings:
    try:
        content = target_file.read_text(encoding=encoding)
        target_file.write_text(content, encoding="utf-8")
        print(f"Successfully converted from {encoding} to UTF-8")
        sys.exit(0)
    except Exception:
        continue

print("Failed to convert file")
sys.exit(1)
