"""
AWS Bridge 自测脚本
验证双向事件桥接、幂等性、task_id映射
"""

import json
import sys
import time
from pathlib import Path

# 添加repo root到路径
repo_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(repo_root))

# 直接导入（假设在repo root运行）
from tools.mcp_bus.server.aws_bridge import AWSBridge
from tools.mcp_bus.server.event_publisher import EventPublisher
from tools.mcp_bus.server.message_queue import MessageQueue
from tools.mcp_bus.server.models import Event, EventType

# 初始化（使用上面定义的repo_root）
db_path = repo_root / "docs" / "REPORT" / "ata" / "message_queue.db"
message_queue = MessageQueue(db_path)
event_publisher = EventPublisher(repo_root, message_queue)
aws_bridge = AWSBridge(repo_root, message_queue, event_publisher)

print("=" * 60)
print("AWS Bridge 自测")
print("=" * 60)

# 测试1: AWS创建任务 -> T1事件
print("\n[测试1] AWS创建任务 -> T1事件")
aws_payload = {
    "request_id": "test-req-001",
    "task_id": "aws-task-test-001",
    "task_code": "AWS_INTAKE__20260124",
    "goal": "测试AWS任务创建",
    "acceptance": ["任务出现在看板", "task_id正确"],
    "created_by": "test_user",
    "task_type": "TASK_CREATION",
}
result = aws_bridge.handle_aws_task_creation(aws_payload)
print(f"结果: {json.dumps(result, indent=2, ensure_ascii=False)}")
assert result["success"], "任务创建失败"
t1_task_id = result["task_id"]
print(f"[OK] T1 task_id: {t1_task_id}")

# 测试2: 幂等性（重复请求）
print("\n[测试2] 幂等性验证（重复请求）")
result2 = aws_bridge.handle_aws_task_creation(aws_payload)
print(f"结果: {json.dumps(result2, indent=2, ensure_ascii=False)}")
assert result2["success"], "幂等请求应该成功"
assert result2["message"] == "Duplicate request (idempotent)", "应该识别为重复请求"
print("[OK] 幂等性验证通过")

# 测试3: AWS日志追加
print("\n[测试3] AWS日志追加")
log_payload = {
    "request_id": "test-req-002",
    "task_id": "aws-task-test-001",  # 使用AWS task_id
    "log_level": "info",
    "message": "任务开始执行",
}
result3 = aws_bridge.handle_aws_log_append(log_payload)
print(f"结果: {json.dumps(result3, indent=2, ensure_ascii=False)}")
assert result3["success"], "日志追加失败"
print("[OK] 日志追加成功")

# 测试4: AWS状态更新
print("\n[测试4] AWS状态更新")
status_payload = {
    "request_id": "test-req-003",
    "task_id": "aws-task-test-001",
    "status": "running",
    "progress": 50,
}
result4 = aws_bridge.handle_aws_status_update(status_payload)
print(f"结果: {json.dumps(result4, indent=2, ensure_ascii=False)}")
assert result4["success"], "状态更新失败"
print("[OK] 状态更新成功")

# 测试5: T1事件 -> AWS通知（模拟）
print("\n[测试5] T1事件 -> AWS通知")
# 发布一个T1事件
event = Event(
    type=EventType.VERDICT_GENERATED,
    correlation_id=t1_task_id,
    payload={
        "status": "fail",
        "fail_codes": ["ATTACK-001"],
        "task_code": "AWS_INTAKE__20260124",
    },
    source="ci_gate",
)
event_publisher.publish_event(event)
print(f"[OK] 已发布T1 Verdict事件: {event.event_id}")

# 等待消息入队
time.sleep(1)

# 消费并转换为AWS格式
processed = aws_bridge.consume_t1_events_for_aws(limit=10)
print(f"[OK] 处理了 {processed} 个事件")

# 测试6: 白名单检查
print("\n[测试6] 白名单检查（拒绝未授权任务类型）")
invalid_payload = {
    "request_id": "test-req-004",
    "task_code": "INVALID__20260124",
    "goal": "测试",
    "task_type": "INVALID_TYPE",  # 不在白名单
}
result6 = aws_bridge.handle_aws_task_creation(invalid_payload)
print(f"结果: {json.dumps(result6, indent=2, ensure_ascii=False)}")
assert not result6["success"], "应该拒绝未授权任务类型"
assert "not in whitelist" in result6["message"], "错误消息应该包含白名单提示"
print("[OK] 白名单检查通过")

print("\n" + "=" * 60)
print("所有测试通过！")
print("=" * 60)
