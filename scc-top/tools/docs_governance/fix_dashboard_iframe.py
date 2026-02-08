#!/usr/bin/env python3
"""
修复Dashboard iframe配置，使用MCP代理路由而不是直接端口
"""

import re
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

REPO_ROOT = Path(__file__).parent.parent.parent
DASHBOARD_HTML = REPO_ROOT / "tools" / "mcp_bus" / "web_viewer" / "dashboard.html"


def fix_dashboard_iframe():
    """修复Dashboard iframe配置，使用代理路由"""
    if not DASHBOARD_HTML.exists():
        print(f"❌ 文件不存在: {DASHBOARD_HTML}")
        return False

    content = DASHBOARD_HTML.read_text(encoding="utf-8")
    original_content = content

    # 替换直接端口访问为代理路由
    # 从 http://127.0.0.1:8051 改为 /dashboard
    content = re.sub(r'src="http://127\.0\.0\.1:8051([^"]*)"', r'src="/dashboard\1"', content)

    # 替换新标签页打开URL
    content = re.sub(
        r"'dashboard': 'http://127\.0\.0\.1:8051'", r"'dashboard': '/dashboard'", content
    )
    content = re.sub(
        r"'config': 'http://127\.0\.0\.1:8051'", r"'config': '/dashboard#tab-config'", content
    )

    if content != original_content:
        DASHBOARD_HTML.write_text(content, encoding="utf-8")
        print(f"✅ 已修复: {DASHBOARD_HTML}")
        print("   变更:")
        print("   - Dashboard iframe: http://127.0.0.1:8051 -> /dashboard")
        print("   - 配置管理 iframe: http://127.0.0.1:8051#tab-config -> /dashboard#tab-config")
        return True
    else:
        print(f"ℹ️ 无需修改: {DASHBOARD_HTML}")
        return False


if __name__ == "__main__":
    print("=" * 80)
    print("修复Dashboard iframe配置")
    print("=" * 80)
    print()

    if fix_dashboard_iframe():
        print()
        print("✅ 修复完成")
        print()
        print("现在Dashboard将通过MCP服务器代理访问:")
        print("  - Dashboard: /dashboard")
        print("  - 配置管理: /dashboard#tab-config")
        print()
        print("优势:")
        print("  - 统一通过8000端口访问")
        print("  - 避免跨域问题")
        print("  - 更好的错误处理")
    else:
        print()
        print("ℹ️ 配置已是最新")
