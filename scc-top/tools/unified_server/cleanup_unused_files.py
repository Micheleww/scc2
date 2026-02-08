#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
清理不需要的文件

将不需要的文件移到隔离区或删除
"""

import os
import shutil
import sys
from pathlib import Path
from datetime import datetime

# 设置Windows控制台编码
if sys.platform == 'win32':
    try:
        import codecs
        sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
        sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')
    except:
        pass

# 使用ASCII字符
SUCCESS = "[OK]"
FAIL = "[FAIL]"

# 获取项目根目录
current_file = Path(__file__).resolve()
unified_server_dir = current_file.parent
repo_root = unified_server_dir.parent.parent

# 隔离区目录
ISOLATED_DIR = repo_root / "isolated_observatory" / "tools" / "unified_server"
ISOLATED_DIR.mkdir(parents=True, exist_ok=True)


def create_index_file(original_path: Path, reason: str):
    """创建索引占位文件"""
    index_path = original_path.parent / f"{original_path.name}.index"
    
    index_content = f"""# 索引占位文件 - {original_path.name}

原始文件已迁移到隔离观察区

- 文件名: {original_path.name}
- 文件大小: {original_path.stat().st_size if original_path.exists() else 0} bytes
- 修改时间: {datetime.now().timestamp()}
- 存储位置: {ISOLATED_DIR.relative_to(repo_root) / original_path.name}
- 迁移原因: {reason}

## 内容摘要
{_get_file_summary(original_path) if original_path.exists() else "文件不存在"}
"""
    
    with open(index_path, "w", encoding="utf-8") as f:
        f.write(index_content)


def _get_file_summary(file_path: Path, max_lines: int = 20) -> str:
    """获取文件摘要"""
    try:
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()[:max_lines]
            return "".join(lines)
    except:
        return "无法读取文件内容"


def move_to_isolated(file_path: Path, reason: str):
    """移动文件到隔离区"""
    if not file_path.exists():
        return
    
    # 目标路径
    target_path = ISOLATED_DIR / file_path.name
    
    # 如果目标已存在，添加时间戳
    if target_path.exists():
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        target_path = ISOLATED_DIR / f"{file_path.stem}_{timestamp}{file_path.suffix}"
    
    # 移动文件
    try:
        shutil.move(str(file_path), str(target_path))
        print(f"{SUCCESS} 已移动: {file_path.name} -> {target_path.relative_to(repo_root)}")
        
        # 创建索引文件
        create_index_file(file_path, reason)
    except Exception as e:
        print(f"{FAIL} 移动失败 {file_path.name}: {e}")


def main():
    """主函数"""
    print("=== 清理统一服务器不需要的文件 ===")
    print()
    
    # 需要清理的文件列表
    files_to_cleanup = [
        # 重复的文档（保留最重要的）
        {
            "path": unified_server_dir / "SUMMARY.md",
            "reason": "内容已整合到其他文档",
            "action": "move"
        },
        {
            "path": unified_server_dir / "INTEGRATION_STATUS.md",
            "reason": "内容已整合到其他文档",
            "action": "move"
        },
        {
            "path": unified_server_dir / "ADAPTATION_SUMMARY.md",
            "reason": "内容已整合到CLIENT_ADAPTATION_GUIDE.md",
            "action": "move"
        },
        {
            "path": unified_server_dir / "COMPLETION_SUMMARY.md",
            "reason": "内容已整合到FINAL_SUMMARY.md",
            "action": "move"
        },
    ]
    
    moved_count = 0
    for item in files_to_cleanup:
        file_path = item["path"]
        if file_path.exists():
            if item["action"] == "move":
                move_to_isolated(file_path, item["reason"])
                moved_count += 1
            elif item["action"] == "delete":
                try:
                    file_path.unlink()
                    print(f"{SUCCESS} 已删除: {file_path.name}")
                except Exception as e:
                    print(f"{FAIL} 删除失败 {file_path.name}: {e}")
    
    print()
    print(f"总计: 移动 {moved_count} 个文件到隔离区")
    print(f"隔离区位置: {ISOLATED_DIR.relative_to(repo_root)}")


if __name__ == "__main__":
    main()
