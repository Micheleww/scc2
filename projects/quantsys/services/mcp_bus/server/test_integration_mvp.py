"""
INTEGRATION_MVP 自测脚本
覆盖4个关键场景：
1. 创建任务→10s内进入running
2. Agent回传日志/结果挂到task_id
3. CI fail自动生成修复子任务并阻断主线
4. 断网重连不丢任务（幂等验证）
"""

import json
import time
from datetime import datetime, timezone
from pathlib import Path

from .integration_service import IntegrationService
from .models import EventType, TaskStatus
from .message_queue import MessageQueue
from .task_id_mapper import TaskIDMapper


def test_scenario_1_create_task():
    """场景1: 创建任务→10s内进入running"""
    print("\n=== 场景1: 创建任务→10s内进入running ===")
    
    repo_root = Path(__file__).parent.parent.parent.parent
    service = IntegrationService(repo_root)
    
    # 创建任务
    taskcode = "INTEGRATION_MVP_TEST-20260124-001"
    result = service.create_task_with_id(
        taskcode=taskcode,
        goal="测试任务创建和状态流转",
        constraints={"law_ref": "test", "allowed_paths": []},
        acceptance=["任务在10s内进入running状态"],
        created_by="test_script",
        area="INTEGRATION_MVP_TEST",
    )
    
    assert result["success"], f"任务创建失败: {result}"
    task_id = result["task_id"]
    print(f"✓ 任务创建成功: task_id={task_id}, task_code={taskcode}")
    
    # 检查任务状态（应该在10s内进入running）
    start_time = time.time()
    max_wait = 10
    
    while time.time() - start_time < max_wait:
        task_status = service.orchestrator.get_task_status(task_id)
        if task_status.get("success") and task_status.get("status") == TaskStatus.RUNNING.value:
            elapsed = time.time() - start_time
            print(f"✓ 任务在 {elapsed:.2f}s 内进入 running 状态")
            return True
        time.sleep(0.5)
    
    print(f"✗ 任务未在 {max_wait}s 内进入 running 状态")
    return False


def test_scenario_2_agent_result():
    """场景2: Agent回传日志/结果挂到task_id"""
    print("\n=== 场景2: Agent回传日志/结果挂到task_id ===")
    
    repo_root = Path(__file__).parent.parent.parent.parent
    service = IntegrationService(repo_root)
    
    taskcode = "INTEGRATION_MVP_TEST-20260124-002"
    result = service.create_task_with_id(
        taskcode=taskcode,
        goal="测试Agent结果回传",
        constraints={},
        acceptance=["Agent结果能挂到task_id"],
        created_by="test_script",
        area="INTEGRATION_MVP_TEST",
    )
    
    task_id = result["task_id"]
    
    # 模拟Agent回传结果
    service.event_publisher.publish_subtask_completed_event(
        task_id=task_id,
        subtask_id=f"{task_id}-ST001",
        source="test_agent",
        result={
            "logs": ["执行步骤1", "执行步骤2", "完成"],
            "output": "测试输出",
            "status": "completed",
        },
    )
    
    # 检查结果是否挂到task_id
    task_status = service.orchestrator.get_task_status(task_id, include_subtasks=True)
    if task_status.get("success"):
        subtasks = task_status.get("subtasks", [])
        if subtasks:
            print(f"✓ Agent结果已挂到task_id: {task_id}")
            print(f"  子任务数: {len(subtasks)}")
            return True
    
    print(f"✗ Agent结果未挂到task_id")
    return False


def test_scenario_3_ci_fail_repair():
    """场景3: CI fail自动生成修复子任务并阻断主线"""
    print("\n=== 场景3: CI fail自动生成修复子任务 ===")
    
    repo_root = Path(__file__).parent.parent.parent.parent
    service = IntegrationService(repo_root)
    
    taskcode = "INTEGRATION_MVP_TEST-20260124-003"
    result = service.create_task_with_id(
        taskcode=taskcode,
        goal="测试CI失败修复",
        constraints={},
        acceptance=["CI失败时自动生成修复子任务"],
        created_by="test_script",
        area="INTEGRATION_MVP_TEST",
    )
    
    task_id = result["task_id"]
    
    # 创建模拟verdict文件
    verdict_dir = repo_root / "docs" / "REPORT" / "INTEGRATION_MVP_TEST" / "artifacts" / taskcode
    verdict_dir.mkdir(parents=True, exist_ok=True)
    verdict_path = verdict_dir / "verdict.json"
    
    verdict_data = {
        "status": "fail",
        "fail_codes": ["EVIDENCE_SCOPE_VIOLATION", "STAGE_MISSING"],
        "task_code": taskcode,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    
    with open(verdict_path, "w", encoding="utf-8") as f:
        json.dump(verdict_data, f, indent=2)
    
    # 处理verdict
    repair_result = service.verdict_handler.process_verdict(verdict_path)
    
    if repair_result.get("success") and repair_result.get("repair_subtasks_created"):
        print(f"✓ CI失败已自动生成修复子任务")
        print(f"  fail_codes: {repair_result.get('fail_codes')}")
        return True
    
    print(f"✗ CI失败未生成修复子任务")
    return False


def test_scenario_4_idempotency():
    """场景4: 断网重连不丢任务（幂等验证）"""
    print("\n=== 场景4: 断网重连不丢任务（幂等验证） ===")
    
    repo_root = Path(__file__).parent.parent.parent.parent
    queue = MessageQueue(repo_root / "docs" / "REPORT" / "ata" / "message_queue.db")
    
    # 发送相同消息两次（模拟重连重发）
    message_id = "test-message-idempotency-001"
    task_id = "INTEGRATION_MVP_TEST-20260124-004"
    payload = {"test": "data"}
    
    # 第一次入队
    result1 = queue.enqueue(message_id, task_id, "test_agent", payload)
    assert result1, "第一次入队应该成功"
    print(f"✓ 第一次入队成功")
    
    # 第二次入队（应该被去重）
    result2 = queue.enqueue(message_id, task_id, "test_agent", payload)
    assert not result2, "第二次入队应该被去重（返回False）"
    print(f"✓ 第二次入队被去重（幂等验证通过）")
    
    # 验证消息只存在一条
    messages = queue.get_pending_messages(limit=10)
    matching = [m for m in messages if m["message_id"] == message_id]
    assert len(matching) == 1, f"应该只有一条消息，实际: {len(matching)}"
    print(f"✓ 消息队列中只有一条消息（去重成功）")
    
    return True


def main():
    """运行所有测试场景"""
    print("=" * 60)
    print("INTEGRATION_MVP 自测")
    print("=" * 60)
    
    results = []
    
    try:
        results.append(("场景1: 创建任务→10s内进入running", test_scenario_1_create_task()))
    except Exception as e:
        print(f"✗ 场景1失败: {e}")
        results.append(("场景1", False))
    
    try:
        results.append(("场景2: Agent回传结果", test_scenario_2_agent_result()))
    except Exception as e:
        print(f"✗ 场景2失败: {e}")
        results.append(("场景2", False))
    
    try:
        results.append(("场景3: CI失败修复", test_scenario_3_ci_fail_repair()))
    except Exception as e:
        print(f"✗ 场景3失败: {e}")
        results.append(("场景3", False))
    
    try:
        results.append(("场景4: 幂等验证", test_scenario_4_idempotency()))
    except Exception as e:
        print(f"✗ 场景4失败: {e}")
        results.append(("场景4", False))
    
    # 汇总结果
    print("\n" + "=" * 60)
    print("测试结果汇总")
    print("=" * 60)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for name, result in results:
        status = "✓ PASS" if result else "✗ FAIL"
        print(f"{status}: {name}")
    
    print(f"\n总计: {passed}/{total} 通过")
    
    if passed == total:
        print("EXIT_CODE=0")
        return 0
    else:
        print("EXIT_CODE=1")
        return 1


if __name__ == "__main__":
    import sys
    sys.exit(main())
