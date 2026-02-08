
#!/usr/bin/env python3
"""
端口分配管理工具

用于查看和管理统一服务器的端口分配
"""

import sys
import json
import argparse
from pathlib import Path

# 添加路径
current_file = Path(__file__).resolve()
unified_server_dir = current_file.parent
sys.path.insert(0, str(unified_server_dir))

from tools.unified_server.core.port_allocator import get_port_allocator, PortAllocator


def list_ports(allocator: PortAllocator):
    """列出所有端口分配"""
    print("\n=== 端口分配列表 ===")
    allocated = allocator.list_allocated_ports()
    
    if not allocated:
        print("没有已分配的端口")
    else:
        print(f"\n已分配端口 ({len(allocated)} 个):")
        for service_name, port in sorted(allocated.items()):
            print(f"  {service_name:30s} -> {port}")
    
    stats = allocator.get_statistics()
    print(f"\n=== 统计信息 ===")
    print(f"端口范围: {stats['port_range']}")
    print(f"总端口数: {stats['total_ports']}")
    print(f"已分配: {stats['allocated']}")
    print(f"已保留: {stats['reserved']}")
    print(f"可用: {stats['available']}")
    print(f"利用率: {stats['utilization']}")


def allocate_port(allocator: PortAllocator, service_name: str, preferred_port: int = None):
    """为服务分配端口"""
    try:
        if preferred_port:
            port = allocator.allocate_port(service_name, preferred_port)
            print(f"✓ 为服务 '{service_name}' 分配端口: {port} (首选: {preferred_port})")
        else:
            port = allocator.allocate_port(service_name)
            print(f"✓ 为服务 '{service_name}' 分配端口: {port}")
    except Exception as e:
        print(f"✗ 分配端口失败: {e}")
        sys.exit(1)


def release_port(allocator: PortAllocator, service_name: str):
    """释放服务端口"""
    if allocator.release_port(service_name):
        print(f"✓ 已释放服务 '{service_name}' 的端口")
    else:
        print(f"✗ 服务 '{service_name}' 没有分配的端口")
        sys.exit(1)


def reserve_port(allocator: PortAllocator, port: int, reason: str = ""):
    """保留端口"""
    try:
        allocator.reserve_port(port, reason)
        print(f"✓ 已保留端口 {port} (原因: {reason or '未指定'})")
    except Exception as e:
        print(f"✗ 保留端口失败: {e}")
        sys.exit(1)


def unreserve_port(allocator: PortAllocator, port: int):
    """取消端口保留"""
    try:
        allocator.unreserve_port(port)
        print(f"✓ 已取消端口 {port} 的保留")
    except Exception as e:
        print(f"✗ 取消保留失败: {e}")
        sys.exit(1)


def check_port(allocator: PortAllocator, port: int):
    """检查端口是否可用"""
    if allocator.is_port_available(port):
        print(f"✓ 端口 {port} 可用")
    else:
        print(f"✗ 端口 {port} 不可用")
        # 检查原因
        if port in allocator.allocated_ports.values():
            service = [k for k, v in allocator.allocated_ports.items() if v == port][0]
            print(f"  原因: 已被服务 '{service}' 占用")
        elif port in allocator.reserved_ports:
            print(f"  原因: 已被保留")
        elif port < allocator.start_port or port > allocator.end_port:
            print(f"  原因: 不在端口范围内 ({allocator.start_port}-{allocator.end_port})")
        else:
            print(f"  原因: 端口可能被占用或为常用端口")


def export_ports(allocator: PortAllocator, output_file: str):
    """导出端口分配到文件"""
    data = {
        'allocated': allocator.list_allocated_ports(),
        'reserved': list(allocator.reserved_ports),
        'statistics': allocator.get_statistics()
    }
    
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    
    print(f"✓ 端口分配已导出到: {output_file}")


def main():
    parser = argparse.ArgumentParser(description="统一服务器端口分配管理工具")
    subparsers = parser.add_subparsers(dest='command', help='命令')
    
    # list 命令
    subparsers.add_parser('list', help='列出所有端口分配')
    
    # allocate 命令
    allocate_parser = subparsers.add_parser('allocate', help='为服务分配端口')
    allocate_parser.add_argument('service_name', help='服务名称')
    allocate_parser.add_argument('--port', type=int, help='首选端口')
    
    # release 命令
    release_parser = subparsers.add_parser('release', help='释放服务端口')
    release_parser.add_argument('service_name', help='服务名称')
    
    # reserve 命令
    reserve_parser = subparsers.add_parser('reserve', help='保留端口')
    reserve_parser.add_argument('port', type=int, help='端口号')
    reserve_parser.add_argument('--reason', default='', help='保留原因')
    
    # unreserve 命令
    unreserve_parser = subparsers.add_parser('unreserve', help='取消端口保留')
    unreserve_parser.add_argument('port', type=int, help='端口号')
    
    # check 命令
    check_parser = subparsers.add_parser('check', help='检查端口是否可用')
    check_parser.add_argument('port', type=int, help='端口号')
    
    # export 命令
    export_parser = subparsers.add_parser('export', help='导出端口分配')
    export_parser.add_argument('output_file', help='输出文件路径')
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        sys.exit(1)
    
    allocator = get_port_allocator()
    
    if args.command == 'list':
        list_ports(allocator)
    elif args.command == 'allocate':
        allocate_port(allocator, args.service_name, args.port)
    elif args.command == 'release':
        release_port(allocator, args.service_name)
    elif args.command == 'reserve':
        reserve_port(allocator, args.port, args.reason)
    elif args.command == 'unreserve':
        unreserve_port(allocator, args.port)
    elif args.command == 'check':
        check_port(allocator, args.port)
    elif args.command == 'export':
        export_ports(allocator, args.output_file)


if __name__ == "__main__":
    main()
