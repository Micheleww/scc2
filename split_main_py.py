#!/usr/bin/env python3
"""
Split main.py into smaller modules
"""
import re
from pathlib import Path

def analyze_main_py(filepath: Path):
    """Analyze main.py structure and extract route groups"""
    content = filepath.read_text(encoding='utf-8')
    lines = content.split('\n')

    # Find all route definitions
    route_pattern = re.compile(r'^@(app\.\w+)\(["\']([^"\']+)["\']\)')
    func_pattern = re.compile(r'^(async def|def) (\w+)\(')

    routes = []
    current_route = None
    line_num = 0

    for i, line in enumerate(lines):
        line_num = i + 1

        # Check for route decorator
        route_match = route_pattern.match(line)
        if route_match:
            current_route = {
                'decorator': route_match.group(0),
                'method': route_match.group(1),
                'path': route_match.group(2),
                'line_start': line_num,
                'func_name': None
            }
            continue

        # Check for function definition
        func_match = func_pattern.match(line)
        if func_match and current_route:
            current_route['func_name'] = func_match.group(2)
            current_route['func_line'] = line_num
            routes.append(current_route)
            current_route = None

    return routes

def group_routes_by_prefix(routes):
    """Group routes by path prefix"""
    groups = {}

    for route in routes:
        path = route['path']
        # Extract prefix (e.g., /api/alerts/list -> alerts)
        parts = path.strip('/').split('/')

        if len(parts) >= 2 and parts[0] == 'api':
            prefix = parts[1] if len(parts) > 1 else 'other'
        elif len(parts) >= 1:
            prefix = parts[0] if parts[0] else 'root'
        else:
            prefix = 'other'

        if prefix not in groups:
            groups[prefix] = []
        groups[prefix].append(route)

    return groups

def main():
    main_py = Path('c:/scc/projects/quantsys/services/mcp_bus/server/main.py')

    print("Analyzing main.py...")
    routes = analyze_main_py(main_py)
    print(f"Found {len(routes)} routes")

    groups = group_routes_by_prefix(routes)

    print("\nRoute groups:")
    for prefix, group_routes in sorted(groups.items()):
        print(f"\n  {prefix}: {len(group_routes)} routes")
        for r in group_routes[:5]:  # Show first 5
            print(f"    - {r['method']} {r['path']} -> {r['func_name']}")
        if len(group_routes) > 5:
            print(f"    ... and {len(group_routes) - 5} more")

    # Summary
    print("\n" + "="*60)
    print("SUMMARY")
    print("="*60)
    print(f"Total routes: {len(routes)}")
    print(f"Route groups: {len(groups)}")
    print("\nRecommended split:")
    for prefix in sorted(groups.keys()):
        count = len(groups[prefix])
        print(f"  routes/{prefix}.py - {count} routes")

if __name__ == '__main__':
    main()
