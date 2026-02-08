
#!/usr/bin/env python3
"""
扫描所有直接访问端口的代码

查找所有使用旧端口（8080, 5001, 8001, 8002, 8000）的代码，
准备迁移到统一服务器（18788端口）
"""

import os
import re
from pathlib import Path
from typing import List, Dict, Tuple
from collections import defaultdict

# 要扫描的端口
OLD_PORTS = [8000, 8001, 8002, 5001, 8080]
UNIFIED_PORT = 18788

# 端口映射规则
PORT_MAPPING = {
    8080: "/exchange",
    5001: "/api",
    8001: "/mcp",
    8002: "/",  # 主应用，可能需要根据具体路径调整
    8000: "/",  # 反向代理
}

# 排除的目录和文件
EXCLUDE_DIRS = {
    ".git",
    ".pytest_cache",
    "__pycache__",
    "node_modules",
    ".venv",
    "venv",
    "env",
    "dist",
    "build",
    "isolated_observatory",
    ".cursor",
}

EXCLUDE_FILES = {
    ".pyc",
    ".pyo",
    ".pyd",
    ".so",
    ".dll",
    ".exe",
    ".log",
}

# 要扫描的文件扩展名
SCAN_EXTENSIONS = {
    ".py",
    ".js",
    ".ts",
    ".json",
    ".yaml",
    ".yml",
    ".md",
    ".sh",
    ".ps1",
    ".bat",
    ".conf",
    ".config",
}


def should_scan_file(file_path: Path) -> bool:
    """判断是否应该扫描该文件"""
    # 检查扩展名
    if file_path.suffix not in SCAN_EXTENSIONS:
        return False
    
    # 检查排除的文件
    if any(file_path.name.endswith(ext) for ext in EXCLUDE_FILES):
        return False
    
    # 检查文件大小（跳过大于10MB的文件）
    try:
        if file_path.stat().st_size > 10 * 1024 * 1024:
            return False
    except:
        pass
    
    return True


def should_scan_dir(dir_path: Path) -> bool:
    """判断是否应该扫描该目录"""
    return dir_path.name not in EXCLUDE_DIRS


def find_port_references(content: str, file_path: Path) -> List[Dict]:
    """在文件内容中查找端口引用"""
    references = []
    
    # 匹配模式
    patterns = [
        # http://localhost:PORT
        (r'http://localhost:(\d+)', 'localhost'),
        # http://127.0.0.1:PORT
        (r'http://127\.0\.0\.1:(\d+)', '127.0.0.1'),
        # :PORT (单独端口号)
        (r':(\d{4,5})\b', 'port_only'),
        # PORT (单独端口号，在特定上下文中)
        (r'\b(8080|5001|8001|8002|8000)\b', 'port_number'),
    ]
    
    lines = content.split('\n')
    for line_num, line in enumerate(lines, 1):
        for pattern, pattern_type in patterns:
            matches = re.finditer(pattern, line)
            for match in matches:
                port_str = match.group(1) if match.groups() else match.group(0)
                try:
                    port = int(port_str)
                    if port in OLD_PORTS:
                        references.append({
                            'line': line_num,
                            'content': line.strip(),
                            'match': match.group(0),
                            'port': port,
                            'pattern_type': pattern_type,
                            'column': match.start(),
                        })
                except ValueError:
                    # 如果不是数字，可能是其他匹配
                    if port_str in ['8080', '5001', '8001', '8002', '8000']:
                        references.append({
                            'line': line_num,
                            'content': line.strip(),
                            'match': match.group(0),
                            'port': int(port_str),
                            'pattern_type': pattern_type,
                            'column': match.start(),
                        })
    
    return references


def scan_directory(root_dir: Path) -> Dict[str, List[Dict]]:
    """扫描目录，查找所有端口引用（内存优化版）"""
    results = defaultdict(list)
    file_count = 0
    processed_files = 0
    
    # 首先收集所有需要扫描的文件
    files_to_scan = []
    for root, dirs, files in os.walk(root_dir):
        # 过滤目录
        dirs[:] = [d for d in dirs if should_scan_dir(Path(root) / d)]
        
        for file in files:
            file_path = Path(root) / file
            if should_scan_file(file_path):
                files_to_scan.append(file_path)
    
    total_files = len(files_to_scan)
    print(f"找到 {total_files} 个需要扫描的文件")
    
    # 分批处理文件
    batch_size = 100
    for i in range(0, total_files, batch_size):
        batch_files = files_to_scan[i:i+batch_size]
        print(f"处理批次 {i//batch_size + 1}/{(total_files + batch_size - 1)//batch_size}，文件数: {len(batch_files)}")
        
        for file_path in batch_files:
            processed_files += 1
            if processed_files % 100 == 0:
                print(f"已处理 {processed_files}/{total_files} 文件")
            
            try:
                # 读取文件内容
                with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read()
                
                # 查找端口引用
                references = find_port_references(content, file_path)
                if references:
                    results[str(file_path.relative_to(root_dir))] = references
                    file_count += 1
            except Exception as e:
                # 跳过错误文件
                pass
        
        # 清理内存
        import gc
        gc.collect()
    
    print(f"扫描完成，找到 {file_count} 个包含端口引用的文件")
    return results


def generate_report(results: Dict[str, List[Dict]], output_file: str = None):
    """生成扫描报告（内存优化版）"""
    # 首先计算统计信息
    port_stats = defaultdict(int)
    file_count = len(results)
    total_refs = 0
    
    for file_path, refs in results.items():
        for ref in refs:
            port_stats[ref['port']] += 1
            total_refs += 1
    
    # 生成报告头部和统计信息
    report_lines = []
    report_lines.append("# 端口引用扫描报告")
    report_lines.append("")
    report_lines.append(f"统一服务器端口: {UNIFIED_PORT}")
    report_lines.append(f"扫描的旧端口: {', '.join(map(str, OLD_PORTS))}")
    report_lines.append("")
    
    report_lines.append("## 统计信息")
    report_lines.append("")
    report_lines.append(f"- 扫描文件数: {file_count}")
    report_lines.append(f"- 总引用数: {total_refs}")
    report_lines.append("")
    report_lines.append("### 按端口分类")
    report_lines.append("")
    for port in sorted(port_stats.keys()):
        count = port_stats[port]
        new_path = PORT_MAPPING.get(port, "/")
        report_lines.append(f"- 端口 {port}: {count} 处引用 → 统一服务器 {UNIFIED_PORT}{new_path}")
    report_lines.append("")
    
    # 生成详细列表（内存优化）
    report_lines.append("## 详细引用列表")
    report_lines.append("")
    
    # 分批写入文件，避免内存不足
    if output_file:
        # 先写入头部
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write('\n'.join(report_lines))
            f.write('\n')
        
        # 分批写入详细内容
        with open(output_file, 'a', encoding='utf-8') as f:
            for file_path in sorted(results.keys()):
                refs = results[file_path]
                f.write(f"### {file_path}\n\n")
                
                for ref in refs:
                    port = ref['port']
                    new_path = PORT_MAPPING.get(port, "/")
                    f.write(f"**行 {ref['line']}, 列 {ref['column']}** (端口 {port})\n")
                    f.write(f"```\n")
                    f.write(f"{ref['content']}\n")
                    f.write(f"```\n")
                    f.write(f"**建议替换为**: `http://localhost:{UNIFIED_PORT}{new_path}`\n\n")
        
        print(f"报告已保存到: {output_file}")
        return "报告已生成（内存优化版）"
    else:
        # 如果不输出文件，只显示统计信息
        report = '\n'.join(report_lines)
        report += "\n\n**注意**: 详细列表未显示以节省内存"
        print(report)
        return report


def main():
    """主函数"""
    import sys
    
    # 获取项目根目录
    if len(sys.argv) > 1:
        root_dir = Path(sys.argv[1])
    else:
        # 默认使用当前脚本所在目录的父目录的父目录（项目根）
        root_dir = Path(__file__).parent.parent.parent
    
    if not root_dir.exists():
        print(f"错误: 目录不存在: {root_dir}")
        sys.exit(1)
    
    print(f"扫描目录: {root_dir}")
    print("正在扫描...")
    
    results = scan_directory(root_dir)
    
    # 生成报告
    output_file = root_dir / "tools" / "unified_server" / "PORT_SCAN_REPORT.md"
    generate_report(results, str(output_file))
    
    # 输出摘要
    print(f"\n扫描完成！")
    print(f"找到 {len(results)} 个文件包含端口引用")
    print(f"详细报告: {output_file}")


if __name__ == "__main__":
    main()
