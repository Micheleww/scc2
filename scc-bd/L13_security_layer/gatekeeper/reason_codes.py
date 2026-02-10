#!/usr/bin/env python3
"""
统一门禁原因码枚举定义
TaskCode: GATE-REASON-CODE-DICT-v0.1
"""


# 原因码定义
class GateReasonCode:
    """门禁原因码枚举类"""

    # 成功
    SUCCESS = "SUCCESS"

    # 报告相关
    MISSING_REPORT = "MISSING_REPORT"  # 缺少报告文件
    MISSING_SELFTEST = "MISSING_SELFTEST"  # 缺少自测日志
    REPORT_PARSE_FAIL = "REPORT_PARSE_FAIL"  # 报告解析失败
    EVIDENCE_MISSING = "EVIDENCE_MISSING"  # 缺少证据文件
    EVIDENCE_EMPTY = "EVIDENCE_EMPTY"  # 证据文件为空
    DATE_MISMATCH = "DATE_MISMATCH"  # 报告日期与文件名日期不一致

    # 静态Board相关
    BOARD_STALE = "BOARD_STALE"  # 静态Board过期

    # 法律相关
    LAW_COPY = "LAW_COPY"  # 法源正文复制

    # 文件操作相关
    FILE_DELETE = "FILE_DELETE"  # 删除受保护文件
    ABS_PATH = "ABS_PATH"  # 使用绝对路径
    NEW_ENTRYFILE = "NEW_ENTRYFILE"  # 引入新的入口文件

    # Gatekeeper相关
    GATEKEEPER_ERROR = "GATEKEEPER_ERROR"  # Gatekeeper检查失败
    MANIFEST_ERROR = "MANIFEST_ERROR"  # Manifest检查失败
    IMPORT_ERROR = "IMPORT_ERROR"  # Import扫描失败
    LAW_ERROR = "LAW_ERROR"  # Law扫描失败
    FASTGATE_ERROR = "FASTGATE_ERROR"  # 快速门禁检查失败

    # 文档治理相关
    DOCS_ERROR = "DOCS_ERROR"  # 文档治理检查失败

    # Broker相关
    BROKER_ERROR = "BROKER_ERROR"  # Broker Bypass扫描失败

    # Fail-Closed相关
    FAILCLOSED_ERROR = "FAILCLOSED_ERROR"  # Fail-Closed检查失败

    # PR模板相关
    PRTEMPLATE_ERROR = "PRTEMPLATE_ERROR"  # PR模板检查失败
    PR_TEMPLATE_GATE_BIND_ERROR = "PR_TEMPLATE_GATE_BIND_ERROR"  # PR模板与CI Gate绑定错误
    PR_FIELDS_VALIDATION_ERROR = "PR_FIELDS_VALIDATION_ERROR"  # PR模板必填字段缺失

    # 快速门禁相关
    DELETE_PROTECTED_ERROR = "DELETE_PROTECTED_ERROR"  # 受保护文件删除
    LAW_REPLICATE_ERROR = "LAW_REPLICATE_ERROR"  # 法源正文复制
    REPORT_VALIDATION_ERROR = "REPORT_VALIDATION_ERROR"  # REPORT文件校验失败
    BLOCKED_FIELDS_MISSING = "BLOCKED_FIELDS_MISSING"  # BLOCKED状态缺少必需字段

    # 一键验证相关
    FAST_GATE_ERROR = "FAST_GATE_ERROR"  # 快速门禁检查失败
    LIVE_GATE_ERROR = "LIVE_GATE_ERROR"  # 实盘门禁检查失败

    # 静态Board相关
    STATICBOARD_ERROR = "STATICBOARD_ERROR"  # 静态Board检查失败
    BOARD_LINKS_ERROR = "BOARD_LINKS_ERROR"  # 静态Board链接错误

    # ATA相关
    ATA_ORPHAN_MESSAGES = "ATA_ORPHAN_MESSAGES"  # 存在孤立的ATA消息目录
    ATA_LEDGER_STALE = "ATA_LEDGER_STALE"  # ATA消息变更但未更新分类账
    ATA_LEDGER_LINKS_ERROR = "ATA_LEDGER_LINKS_ERROR"  # ATA分类账中存在无效链接
    ATA_CONTEXT_EVIDENCE_ERROR = (
        "ATA_CONTEXT_EVIDENCE_ERROR"  # ATA context.json中evidence_paths校验失败
    )
    ATA_CONTEXT_MISSING = "ATA_CONTEXT_MISSING"  # 缺少ATA上下文文件
    ATA_CONTEXT_INVALID = "ATA_CONTEXT_INVALID"  # ATA上下文文件格式无效
    ATA_CONTEXT_MISSING_FIELDS = "ATA_CONTEXT_MISSING_FIELDS"  # ATA上下文文件缺少必填字段

    # A2A / TaskChain 回归（P0：正确性与不发散）
    A2A_ENV_FAILURE = "A2A_ENV_FAILURE"  # 环境失败（依赖/端口/网络/权限/配置）
    A2A_TEST_FAILURE = "A2A_TEST_FAILURE"  # 测试失败（selftest/smoke/e2e/phase4）
    A2A_BUSINESS_FAILURE = "A2A_BUSINESS_FAILURE"  # 业务逻辑失败（状态机/协议/一致性）
    AUTO_EXEC_DISABLED = "AUTO_EXEC_DISABLED"  # auto-execute / kill switch 关闭，必须拒绝执行

    # 迁移相关
    MIGRATION_RECORD_MISSING = (
        "MIGRATION_RECORD_MISSING"  # 文件迁移到legacy/experiments/但未更新迁移登记
    )

    # Mutation测试相关
    MUTATION_UNEXPECTED_PASS = "MUTATION_UNEXPECTED_PASS"  # Mutation测试意外通过

    # 签名验证相关
    MISSING_SIGNATURE_MAP = "MISSING_SIGNATURE_MAP"  # 缺少sha256_map.json文件
    INVALID_SIGNATURE = "INVALID_SIGNATURE"  # 签名验证失败


# 原因码描述映射
REASON_CODE_DESC = {
    GateReasonCode.SUCCESS: "所有检查通过",
    GateReasonCode.MISSING_REPORT: "缺少报告文件",
    GateReasonCode.MISSING_SELFTEST: "缺少自测日志",
    GateReasonCode.REPORT_PARSE_FAIL: "报告解析失败",
    GateReasonCode.EVIDENCE_MISSING: "缺少证据文件",
    GateReasonCode.EVIDENCE_EMPTY: "证据文件为空",
    GateReasonCode.DATE_MISMATCH: "报告日期与文件名日期不一致",
    GateReasonCode.BOARD_STALE: "静态Board过期",
    GateReasonCode.LAW_COPY: "法源正文复制",
    GateReasonCode.FILE_DELETE: "删除受保护文件",
    GateReasonCode.ABS_PATH: "使用绝对路径",
    GateReasonCode.NEW_ENTRYFILE: "引入新的入口文件",
    GateReasonCode.GATEKEEPER_ERROR: "Gatekeeper检查失败",
    GateReasonCode.MANIFEST_ERROR: "Manifest检查失败",
    GateReasonCode.IMPORT_ERROR: "Import扫描失败",
    GateReasonCode.LAW_ERROR: "Law扫描失败",
    GateReasonCode.FASTGATE_ERROR: "快速门禁检查失败",
    GateReasonCode.DOCS_ERROR: "文档治理检查失败",
    GateReasonCode.BROKER_ERROR: "Broker Bypass扫描失败",
    GateReasonCode.FAILCLOSED_ERROR: "Fail-Closed检查失败",
    GateReasonCode.PRTEMPLATE_ERROR: "PR模板检查失败",
    GateReasonCode.PR_TEMPLATE_GATE_BIND_ERROR: "PR模板与CI Gate绑定错误",
    GateReasonCode.PR_FIELDS_VALIDATION_ERROR: "PR模板必填字段缺失",
    GateReasonCode.DELETE_PROTECTED_ERROR: "受保护文件删除",
    GateReasonCode.LAW_REPLICATE_ERROR: "法源正文复制",
    GateReasonCode.REPORT_VALIDATION_ERROR: "REPORT文件校验失败",
    GateReasonCode.BLOCKED_FIELDS_MISSING: "BLOCKED状态缺少必需字段",
    GateReasonCode.FAST_GATE_ERROR: "快速门禁检查失败",
    GateReasonCode.LIVE_GATE_ERROR: "实盘门禁检查失败",
    GateReasonCode.STATICBOARD_ERROR: "静态Board检查失败",
    GateReasonCode.BOARD_LINKS_ERROR: "静态Board链接错误",
    GateReasonCode.ATA_ORPHAN_MESSAGES: "存在孤立的ATA消息目录",
    GateReasonCode.ATA_LEDGER_STALE: "ATA消息变更但未更新分类账",
    GateReasonCode.ATA_LEDGER_LINKS_ERROR: "ATA分类账中存在无效链接",
    GateReasonCode.ATA_CONTEXT_EVIDENCE_ERROR: "ATA context.json中evidence_paths校验失败",
    GateReasonCode.ATA_CONTEXT_MISSING: "缺少ATA上下文文件",
    GateReasonCode.ATA_CONTEXT_INVALID: "ATA上下文文件格式无效",
    GateReasonCode.ATA_CONTEXT_MISSING_FIELDS: "ATA上下文文件缺少必填字段",
    GateReasonCode.A2A_ENV_FAILURE: "A2A任务链路：环境失败（依赖/端口/网络/权限/配置）",
    GateReasonCode.A2A_TEST_FAILURE: "A2A任务链路：测试失败（selftest/smoke/e2e/phase4）",
    GateReasonCode.A2A_BUSINESS_FAILURE: "A2A任务链路：业务逻辑失败（状态机/协议/一致性）",
    GateReasonCode.AUTO_EXEC_DISABLED: "Auto-execute 已关闭（kill switch/控制面开关）",
    GateReasonCode.MIGRATION_RECORD_MISSING: "文件迁移到legacy/experiments/但未更新迁移登记",
    GateReasonCode.MUTATION_UNEXPECTED_PASS: "Mutation测试意外通过",
    GateReasonCode.MISSING_SIGNATURE_MAP: "缺少sha256_map.json文件",
    GateReasonCode.INVALID_SIGNATURE: "签名验证失败",
}


# 原因码分组
REASON_CODE_GROUPS = {
    "ATA": [
        GateReasonCode.ATA_ORPHAN_MESSAGES,
        GateReasonCode.ATA_LEDGER_STALE,
        GateReasonCode.ATA_LEDGER_LINKS_ERROR,
        GateReasonCode.ATA_CONTEXT_EVIDENCE_ERROR,
    ],
    "A2A": [
        GateReasonCode.A2A_ENV_FAILURE,
        GateReasonCode.A2A_TEST_FAILURE,
        GateReasonCode.A2A_BUSINESS_FAILURE,
        GateReasonCode.AUTO_EXEC_DISABLED,
    ],
    "REPORT": [
        GateReasonCode.MISSING_REPORT,
        GateReasonCode.MISSING_SELFTEST,
        GateReasonCode.REPORT_PARSE_FAIL,
        GateReasonCode.EVIDENCE_MISSING,
        GateReasonCode.EVIDENCE_EMPTY,
        GateReasonCode.BLOCKED_FIELDS_MISSING,
        GateReasonCode.DATE_MISMATCH,
    ],
    "BOARD": [
        GateReasonCode.BOARD_STALE,
        GateReasonCode.STATICBOARD_ERROR,
        GateReasonCode.BOARD_LINKS_ERROR,
    ],
    "LAW": [
        GateReasonCode.LAW_COPY,
    ],
    "FILE": [
        GateReasonCode.FILE_DELETE,
        GateReasonCode.ABS_PATH,
        GateReasonCode.NEW_ENTRYFILE,
        GateReasonCode.MIGRATION_RECORD_MISSING,
    ],
    "GATEKEEPER": [
        GateReasonCode.GATEKEEPER_ERROR,
        GateReasonCode.MANIFEST_ERROR,
        GateReasonCode.IMPORT_ERROR,
        GateReasonCode.LAW_ERROR,
        GateReasonCode.FASTGATE_ERROR,
    ],
    "OTHER": [
        GateReasonCode.DOCS_ERROR,
        GateReasonCode.BROKER_ERROR,
        GateReasonCode.FAILCLOSED_ERROR,
        GateReasonCode.PRTEMPLATE_ERROR,
        GateReasonCode.PR_TEMPLATE_GATE_BIND_ERROR,
        GateReasonCode.PR_FIELDS_VALIDATION_ERROR,
        GateReasonCode.DELETE_PROTECTED_ERROR,
        GateReasonCode.LAW_REPLICATE_ERROR,
        GateReasonCode.REPORT_VALIDATION_ERROR,
        GateReasonCode.FAST_GATE_ERROR,
        GateReasonCode.LIVE_GATE_ERROR,
    ],
}

# L0到L1原因码映射表
# 将L0原因码映射到统一的L1原因码集合
L0_TO_L1_REASON_CODE_MAP = {
    # REPORT相关
    "MISSING_REPORT": GateReasonCode.MISSING_REPORT,
    "REPORT_PARSE_FAIL": GateReasonCode.REPORT_PARSE_FAIL,
    "MISSING_SELFTEST": GateReasonCode.MISSING_SELFTEST,
    "EVIDENCE_MISSING": GateReasonCode.EVIDENCE_MISSING,
    "EVIDENCE_EMPTY": GateReasonCode.EVIDENCE_EMPTY,
    "FIELD_FORMAT_ERROR": GateReasonCode.REPORT_PARSE_FAIL,
    "DATE_MISMATCH": GateReasonCode.DATE_MISMATCH,
    # 文件操作相关
    "FILE_DELETE": GateReasonCode.FILE_DELETE,
    "ABS_PATH": GateReasonCode.ABS_PATH,
    "SUBMIT_CONTENT_ERROR": GateReasonCode.REPORT_VALIDATION_ERROR,
    "ARTIFACTS_ERROR": GateReasonCode.FAST_GATE_ERROR,
    # 法律相关
    "LAW_COPY": GateReasonCode.LAW_COPY,
    # 成功状态
    "SUCCESS": GateReasonCode.SUCCESS,
    # 默认映射
    "UNKNOWN_ERROR": GateReasonCode.FAST_GATE_ERROR,
}

# L1到L1归一化映射（用于确保L1原因码也使用统一集合）
L1_TO_L1_REASON_CODE_MAP = {
    # 确保L1原因码使用统一集合
    # 这里主要处理可能的别名或旧原因码
    "LAW_REPLICATE_ERROR": GateReasonCode.LAW_COPY,
    "DELETE_PROTECTED_ERROR": GateReasonCode.FILE_DELETE,
    "REPORT_VALIDATION_ERROR": GateReasonCode.REPORT_PARSE_FAIL,
}


# 归一化原因码函数
def normalize_reason_code(reason_code, is_l0=True):
    """
    将原因码归一化到统一集合

    Args:
        reason_code: 原始原因码
        is_l0: 是否为L0原因码

    Returns:
        str: 归一化后的原因码
    """
    if is_l0:
        return L0_TO_L1_REASON_CODE_MAP.get(reason_code, GateReasonCode.FAST_GATE_ERROR)
    else:
        return L1_TO_L1_REASON_CODE_MAP.get(reason_code, reason_code)


def reason_code_taxonomy(reason_code: str) -> str:
    """
    三元失败分类（P0）：env / test / business

    - env：环境/依赖/权限/配置/端口/网络
    - test：自测/冒烟/e2e/phase checks
    - business：业务逻辑/状态机/协议一致性
    """
    rc = normalize_reason_code(str(reason_code).strip(), is_l0=False)
    if rc in (GateReasonCode.A2A_ENV_FAILURE, GateReasonCode.AUTO_EXEC_DISABLED, GateReasonCode.LIVE_GATE_ERROR):
        return "env"
    if rc in (
        GateReasonCode.A2A_TEST_FAILURE,
        GateReasonCode.MISSING_SELFTEST,
        GateReasonCode.EVIDENCE_MISSING,
        GateReasonCode.EVIDENCE_EMPTY,
        GateReasonCode.FAILCLOSED_ERROR,
        GateReasonCode.REPORT_VALIDATION_ERROR,
    ):
        return "test"
    if rc in (GateReasonCode.A2A_BUSINESS_FAILURE,):
        return "business"
    return "unknown"


if __name__ == "__main__":
    # 打印所有原因码
    print("=== 门禁原因码枚举 ===")
    for code in dir(GateReasonCode):
        if not code.startswith("_"):
            value = getattr(GateReasonCode, code)
            desc = REASON_CODE_DESC.get(value, "无描述")
            print(f"{value}: {desc}")

    print("\n=== 原因码分组 ===")
    for group, codes in REASON_CODE_GROUPS.items():
        print(f"{group}:")
        for code in codes:
            print(f"  - {code}: {REASON_CODE_DESC[code]}")
