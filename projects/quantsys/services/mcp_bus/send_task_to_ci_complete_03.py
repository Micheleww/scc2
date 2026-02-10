#!/usr/bin/env python3
"""
Send a hardened ATA communication template task prompt to agent #03 (ci完备).
"""

import requests

MCP_URL = "http://127.0.0.1:18788/mcp"


def main() -> int:
    msg = (
        "@CI完备#03 【任务请求/ATA模板硬化】\n\n"
        "你是03号CI完备（CI完备#03）。请把 ATA 通信模板进一步“硬化”（fail-closed），让所有Agent沟通强制遵循统一格式：握手/发任务/回应任务。\n\n"
        "【Goal】\n"
        "把 ATA 通信模板与校验机制升级为：\n"
        "- 所有 ata_send 必须带 @对方#NN 前缀（已做）\n"
        "- 进一步：对 kind=response 的“任务回应”强制包含 audit_triplet（三件套）字段，否则拒绝写入（fail-closed）\n"
        "- 对 kind=request 的“任务请求”强制包含 task{task_code,area,goal,success_criteria,tasks<=3} 与 constraints{law_ref,allowed_paths}（缺失则拒绝）\n"
        "- 为 handshake（bootstrap/ack）定义最小强制字段集（缺失则拒绝或降级）\n\n"
        "【Success Criteria】\n"
        "- 服务端在 tools/mcp_bus/server/tools.py 中对 ata_send 增加结构化校验：request/response/bootstrap 的必填字段缺失 => success=false（fail-closed）\n"
        "- 文档与模板同步更新：\n"
        "  - docs/ARCH/ops/ATA_COMMUNICATION_RULES__v0.1.0.md（规则描述更明确）\n"
        "  - docs/arch/prompt_blocks/CAPSULE__ATA_COMM_TEMPLATES.md（给AI直接粘贴的模板：握手/发任务/回任务）\n"
        "- 自测：构造 3 条消息：合法request、合法response(含三件套)、非法response(缺三件套)；非法必须被拒绝并产生可解释错误。\n\n"
        "【Tasks (<=3)】\n"
        "1) 在 ToolExecutor.ata_send() 加入对 request/response/bootstrap 的 payload schema 校验（fail-closed）\n"
        "2) 更新两份文档/模板并在导航中可检索（若需）\n"
        "3) 编写/更新一个最小测试脚本，证明校验生效（含非法用例被拒绝）\n\n"
        "【Constraints】\n"
        "- law_ref: [law/QCC-README.md, law/QCC-A.v1.1.md, law/QCC-E.v1.1.md]\n"
        "- 三件套依据：docs/arch/prompt_blocks/SKILL_CALL_RULES.md 1.0\n"
        "- 路径约束：只改 tools/** 与 docs/**（禁止触碰 src/quantsys/**）\n\n"
        "【回应格式（强制三件套审计）】\n"
        "请用 kind=response 回我（ATA系统#01），并在 payload.audit_triplet 中给出：\n"
        "- report_path: docs/REPORT/<area>/REPORT__<TaskCode>__<YYYYMMDD>.md\n"
        "- selftest_log_path: docs/REPORT/<area>/artifacts/<TaskCode>/selftest.log（末行 EXIT_CODE=0）\n"
        "- artifacts_dir: docs/REPORT/<area>/artifacts/<TaskCode>/\n"
        "并给出 status=PASS/FAIL/BLOCKED 与简短 summary。\n"
    )

    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {
            "name": "ata_send",
            "arguments": {
                "taskcode": "TC-ATA-COMM-HARDEN-001",
                "from_agent": "ATA系统",
                "to_agent": "CI完备",
                "kind": "request",
                "priority": "high",
                "requires_response": True,
                "payload": {
                    "message": msg,
                    "text": msg,
                    "purpose": "harden ATA communication templates + fail-closed validation",
                    "law_ref": ["law/QCC-README.md", "law/QCC-A.v1.1.md", "law/QCC-E.v1.1.md"],
                    "template_ref": [
                        "docs/ARCH/ops/ATA_COMMUNICATION_RULES__v0.1.0.md",
                        "docs/arch/prompt_blocks/CAPSULE__ATA_COMM_TEMPLATES.md",
                    ],
                },
            },
        },
    }

    r = requests.post(MCP_URL, json=payload, timeout=15)
    print(r.status_code)
    print(r.text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
