#!/usr/bin/env python3
import ast
import glob
import os

import yaml

# 默认代码根目录
CODE_ROOT = "src"

# 模块前缀映射表（根据仓库实际目录结构）
MODULE_PREFIX_MAP = {
    "strategy": "user_data/strategies",
    "factors": "src/quantsys/factors",
    "execution": "src/quantsys/execution",
    "risk": "src/quantsys/risk",
    "tools": "tools",
    "contracts": "docs/contracts",
}


def load_import_rules():
    """加载导入规则"""
    rules_path = "configs/current/import_rules.yaml"
    try:
        with open(rules_path, encoding="utf-8") as f:
            rules = yaml.safe_load(f)
        return rules
    except (OSError, yaml.YAMLError) as e:
        print(f"[ERROR] 无法加载导入规则文件 {rules_path}: {e}")
        return None


def get_python_files(scan_files=None):
    """获取要扫描的 Python 文件列表"""
    if scan_files:
        # 只扫描指定文件
        python_files = []
        for file_path in scan_files:
            if file_path.endswith(".py") and os.path.isfile(file_path):
                python_files.append(file_path)
        return python_files
    else:
        # 扫描 src/**/*.py, user_data/strategies/**/*.py 和 experiments/**/*.py
        python_files = []
        glob_pattern = os.path.join(CODE_ROOT, "**", "*.py")
        python_files.extend(glob.glob(glob_pattern, recursive=True))

        # 添加 user_data/strategies 目录
        strategy_pattern = os.path.join("user_data", "strategies", "**", "*.py")
        python_files.extend(glob.glob(strategy_pattern, recursive=True))

        # 添加 experiments 目录用于隔离检查
        experiments_pattern = os.path.join("experiments", "**", "*.py")
        python_files.extend(glob.glob(experiments_pattern, recursive=True))

        return python_files


def normalize_module_path(module_path):
    """标准化模块路径，应用映射表"""
    # 统一使用正斜杠
    module_path = module_path.replace("\\", "/")

    # 将点号转换为斜杠（用于模块导入路径）
    module_path = module_path.replace(".", "/")

    for prefix, mapped_path in MODULE_PREFIX_MAP.items():
        # 统一使用正斜杠
        mapped_path = mapped_path.replace("\\", "/")
        if module_path.startswith(mapped_path):
            # 替换为标准前缀
            return module_path.replace(mapped_path, prefix)
    return module_path


def check_import_violation(file_path, import_from, import_name, rules):
    """检查单个导入是否违反规则"""
    # 保留原始文件路径用于匹配 from_prefix
    file_path_normalized = file_path.replace("\\", "/")

    # 标准化模块路径
    if import_from:
        import_from = normalize_module_path(import_from)
    if import_name:
        import_name = normalize_module_path(import_name)

    # 获取规则列表
    deny_rules = rules.get("deny_rules", [])
    allow_rules = rules.get("allow_rules", [])

    # 先检查允许规则（优先级高）
    for rule in allow_rules:
        from_prefix = rule.get("from_prefix", "").replace("\\", "/")
        import_prefix = rule.get("import_prefix", "").replace("\\", "/")

        # 允许规则检查逻辑
        is_allowed = False
        if import_from:
            # from import 语句
            if not from_prefix or file_path_normalized.startswith(from_prefix):
                if (
                    not import_prefix
                    or import_from.startswith(import_prefix)
                    or import_name.startswith(import_prefix)
                ):
                    is_allowed = True
        else:
            # import 语句
            if not import_prefix or import_name.startswith(import_prefix):
                is_allowed = True

        if is_allowed:
            return None

    # 检查拒绝规则
    for rule in deny_rules:
        from_prefix = rule.get("from_prefix", "").replace("\\", "/")
        import_prefix = rule.get("import_prefix", "").replace("\\", "/")
        rule_id = rule.get("id", "unknown")
        reason = rule.get("reason", "")

        # 拒绝规则检查逻辑
        is_denied = False
        if import_from:
            # from import 语句
            # 检查 file_path 是否匹配 from_prefix
            if not from_prefix or file_path_normalized.startswith(from_prefix):
                # 检查 import_from 或 import_name 是否匹配 import_prefix
                if import_from.startswith(import_prefix) or import_name.startswith(import_prefix):
                    is_denied = True
        else:
            # import 语句
            # 检查 file_path 是否匹配 from_prefix
            if not from_prefix or file_path_normalized.startswith(from_prefix):
                # 检查 import_name 是否匹配 import_prefix
                if import_name.startswith(import_prefix):
                    is_denied = True

        if is_denied:
            return {
                "file": file_path,
                "from": import_from,
                "import": import_name,
                "rule_id": rule_id,
                "reason": reason,
            }

    return None


def parse_python_file(file_path):
    """解析 Python 文件，提取导入语句"""
    try:
        # Robust decoding: avoid failing the whole scan due to a single non-UTF8 file.
        b = b""
        with open(file_path, "rb") as f:
            b = f.read()
        try:
            content = b.decode("utf-8")
        except UnicodeDecodeError:
            # Common Windows fallback for legacy files.
            try:
                content = b.decode("gbk")
            except Exception:
                content = b.decode("utf-8", errors="replace")

        # 解析 AST
        tree = ast.parse(content, filename=file_path)

        # 提取导入语句
        imports = []
        for node in ast.walk(tree):
            # 处理 import 语句（如：import module）
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.append((None, alias.name, node.lineno))
            # 处理 from import 语句（如：from module import name）
            elif isinstance(node, ast.ImportFrom):
                # node.module 可能为 None（如：from . import name）
                for alias in node.names:
                    imports.append((node.module, alias.name, node.lineno))

        return imports
    except (OSError, SyntaxError, UnicodeDecodeError) as e:
        print(f"[ERROR] 无法解析文件 {file_path}: {e}")
        return []


def scan_imports(scan_files=None):
    """扫描导入违规"""
    # 加载规则
    rules = load_import_rules()
    if not rules:
        return 1

    # 获取要扫描的文件
    python_files = get_python_files(scan_files)
    if not python_files:
        if scan_files:
            print(f"[INFO] 没有找到要扫描的 Python 文件: {scan_files}")
        else:
            print(f"[INFO] 在 {CODE_ROOT}/ 下没有找到 Python 文件")
        return 0

    print(f"[INFO] 扫描 {len(python_files)} 个 Python 文件...")

    # 扫描所有文件
    violations = []
    for file_path in python_files:
        imports = parse_python_file(file_path)
        for import_from, import_name, line_no in imports:
            if import_from:
                # 处理 from import
                violation = check_import_violation(file_path, import_from, import_name, rules)
                if violation:
                    violations.append((line_no, violation))
            else:
                # 处理 import 语句
                violation = check_import_violation(file_path, import_from, import_name, rules)
                if violation:
                    violations.append((line_no, violation))

    # 输出结果
    if violations:
        print(f"[ERROR] 发现 {len(violations)} 个导入违规:")
        for line_no, violation in violations:
            file_path = violation["file"]
            import_from = violation["from"]
            import_name = violation["import"]
            rule_id = violation["rule_id"]
            reason = violation["reason"]

            print(
                f"{file_path}:{line_no} from {import_from} import {import_name} [rule={rule_id}] {reason}"
            )
        return 1
    else:
        print("[SUCCESS] 没有发现导入违规")
        return 0
