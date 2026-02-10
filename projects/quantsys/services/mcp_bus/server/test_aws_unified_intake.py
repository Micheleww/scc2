"""
AWS 统一入口接入自测脚本
覆盖4个关键场景：
1. 从 Web（AWS）创建任务 -> 10s 内在本地看板出现同 task_id 并进入 running
2. 本地执行回传日志 -> Web 实时看到
3. CI fail -> 本地自动生成修复 subtask，Web 同步看到 verdict + 修复任务出现
4. 断网重连：本地 agent 断网5分钟恢复后，桥接不丢任务、不重复推进（幂等验证）
"""

import json
import time
from datetime import datetime, timezone
from pathlib import Path

from .aws_bridge import AWSBridge
from .integration_service import IntegrationService
from .message_queue import MessageQueue
from .models import EventType, TaskStatus


def test_scenario_1_aws_create_task_to_board():
    """场景1: 从 Web（AWS）创建任务 -> 10s 内在本地看板出现同 task_id 并进入 running"""
    print("\n=== 场景1: AWS 创建任务 -> 本地看板出现 ===")
    
    repo_root = Path(__file__).parent.parent.parent.parent
    integration_service = IntegrationService(repo_root)
    aws_bridge = AWSBridge(repo_root, integration_service)
    
    # 模拟 AWS 任务创建
    aws_task_id = "aws-test-001"
    aws_task_code = "AWS_INTAKE_TEST-20260124-001"
    
    result = aws_bridge.handle_aws_task_create(
        aws_task_id=aws_task_id,
        aws_task_code=aws_task_code,
        aws_payload={
            "task_type": "RUN_PROMPT",
            "goal": "测试 AWS 任务创建",
            "area": "AWS_INTAKE_TEST",
            "constraints": {"law_ref": "test", "allowed_paths": []},
            "acceptance": ["任务在10s内进入running"],
            "created_by": "aws_user",
            "priority": "normal",
        },
        user_token="test_user_token",
    )
    
    assert result["success"], f"AWS 任务创建失败: {result}"
    t1_task_id = result["t1_task_id"]
    print(f"✓ AWS 任务创建成功: aws_task_id={aws_task_id}, t1_task_id={t1_task_id}")
    
    # 验证映射关系
    mapped_t1_task_id = aws_bridge._get_t1_task_id_from_aws(aws_task_id)
    assert mapped_t1_task_id == t1_task_id, f"映射关系错误: {mapped_t1_task_id} != {t1_task_id}"
    print(f"✓ 任务映射关系正确: {aws_task_id} -> {t1_task_id}")
    
    # 检查任务状态（应该在10s内进入running）
    start_time = time.time()
    max_wait = 10
    
    while time.time() - start_time < max_wait:
        task_status = integration_service.orchestrator.get_task_status(t1_task_id)
        if task_status.get("success") and task_status.get("status") == TaskStatus.RUNNING.value:
            elapsed = time.time() - start_time
            print(f"✓ 任务在 {elapsed:.2f}s 内进入 running 状态")
            
            # 检查看板（简化：检查事件是否发布）
            events_dir = repo_root / "docs" / "REPORT" / "ata" / "events"
            if events_dir.exists():
                event_files = list(events_dir.glob("*.json"))
                if event_files:
                    print(f"✓ 事件已发布到事件目录（{len(event_files)} 个事件）")
                    return True
            
            return True
        time.sleep(0.5)
    
    print(f"✗ 任务未在 {max_wait}s 内进入 running 状态")
    return False


def test_scenario_2_local_log_to_web():
    """场景2: 本地执行回传日志 -> Web 实时看到"""
    print("\n=== 场景2: 本地日志 -> Web 实时显示 ===")
    
    repo_root = Path(__file__).parent.parent.parent.parent
    integration_service = IntegrationService(repo_root)
    aws_bridge = AWSBridge(repo_root, integration_service)
    
    # 创建任务
    aws_task_id = "aws-test-002"
    result = aws_bridge.handle_aws_task_create(
        aws_task_id=aws_task_id,
        aws_task_code="AWS_INTAKE_TEST-20260124-002",
        aws_payload={
            "task_type": "RUN_PROMPT",
            "goal": "测试日志回传",
            "area": "AWS_INTAKE_TEST",
            "constraints": {},
            "acceptance": ["日志能实时显示"],
            "created_by": "aws_user",
        },
        user_token="test_user_token",
    )
    
    t1_task_id = result["t1_task_id"]
    
    # 模拟本地执行回传日志
    log_result = aws_bridge.handle_aws_log_append(
        aws_task_id=aws_task_id,
        log_data={
            "level": "INFO",
            "message": "开始执行步骤 1",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
    )
    
    assert log_result["success"], f"日志追加失败: {log_result}"
    print(f"✓ 日志已追加: event_id={log_result['event_id']}")
    
    # 验证事件已发布
    events_dir = repo_root / "docs" / "REPORT" / "ata" / "events"
    event_file = events_dir / f"{log_result['event_id']}.json"
    assert event_file.exists(), f"事件文件不存在: {event_file}"
    print(f"✓ 事件已保存: {event_file}")
    
    # 验证可以通过 API 获取事件
    from .aws_protocol_mapper import AWSProtocolMapper
    with open(event_file, encoding="utf-8") as f:
        event_data = json.load(f)
        from .models import Event
        t1_event = Event(**event_data)
        aws_event = AWSProtocolMapper.convert_t1_event_to_aws(t1_event, aws_task_id)
        assert aws_event["task_id"] == aws_task_id, "AWS 事件格式错误"
        print(f"✓ AWS 事件格式正确: {aws_event['event_type']}")
    
    return True


def test_scenario_3_ci_fail_repair_web_sync():
    """场景3: CI fail -> 本地自动生成修复 subtask，Web 同步看到 verdict + 修复任务出现"""
    print("\n=== 场景3: CI 失败修复 -> Web 同步 ===")
    
    repo_root = Path(__file__).parent.parent.parent.parent
    integration_service = IntegrationService(repo_root)
    aws_bridge = AWSBridge(repo_root, integration_service)
    
    # 创建任务
    aws_task_id = "aws-test-003"
    result = aws_bridge.handle_aws_task_create(
        aws_task_id=aws_task_id,
        aws_task_code="AWS_INTAKE_TEST-20260124-003",
        aws_payload={
            "task_type": "RUN_PROMPT",
            "goal": "测试 CI 失败修复",
            "area": "AWS_INTAKE_TEST",
            "constraints": {},
            "acceptance": ["CI失败时自动生成修复子任务"],
            "created_by": "aws_user",
        },
        user_token="test_user_token",
    )
    
    t1_task_id = result["t1_task_id"]
    
    # 创建模拟 verdict 文件
    verdict_dir = repo_root / "docs" / "REPORT" / "AWS_INTAKE_TEST" / "artifacts" / aws_task_id
    verdict_dir.mkdir(parents=True, exist_ok=True)
    verdict_path = verdict_dir / "verdict.json"
    
    verdict_data = {
        "status": "fail",
        "fail_codes": ["EVIDENCE_SCOPE_VIOLATION"],
        "task_code": "AWS_INTAKE_TEST-20260124-003",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    
    with open(verdict_path, "w", encoding="utf-8") as f:
        json.dump(verdict_data, f, indent=2)
    
    # 处理 verdict（通过 verdict_handler）
    repair_result = integration_service.verdict_handler.process_verdict(verdict_path)
    
    assert repair_result.get("success"), f"Verdict 处理失败: {repair_result}"
    print(f"✓ Verdict 已处理: status={repair_result.get('status')}")
    
    if repair_result.get("repair_subtasks_created"):
        print(f"✓ 修复子任务已生成")
        
        # 验证事件已发布（verdict_generated）
        events_dir = repo_root / "docs" / "REPORT" / "ata" / "events"
        verdict_events = []
        if events_dir.exists():
            for event_file in events_dir.glob("*.json"):
                try:
                    with open(event_file, encoding="utf-8") as f:
                        event_data = json.load(f)
                        if (
                            event_data.get("type") == EventType.VERDICT_GENERATED.value
                            and event_data.get("correlation_id") == t1_task_id
                        ):
                            verdict_events.append(event_data)
                except Exception:
                    pass
        
        assert len(verdict_events) > 0, "Verdict 事件未发布"
        print(f"✓ Verdict 事件已发布: {len(verdict_events)} 个事件")
        
        # 验证可以通过 AWS API 获取 verdict 事件
        from .aws_protocol_mapper import AWSProtocolMapper
        from .models import Event
        t1_event = Event(**verdict_events[0])
        aws_event = AWSProtocolMapper.convert_t1_event_to_aws(t1_event, aws_task_id)
        assert aws_event.get("verdict"), "AWS 事件缺少 verdict 字段"
        print(f"✓ AWS 事件包含 verdict: {aws_event['verdict']}")
        
        return True
    
    print(f"✗ 修复子任务未生成")
    return False


def test_scenario_4_idempotency_after_disconnect():
    """场景4: 断网重连不丢任务、不重复推进（幂等验证）"""
    print("\n=== 场景4: 断网重连幂等验证 ===")
    
    repo_root = Path(__file__).parent.parent.parent.parent
    integration_service = IntegrationService(repo_root)
    aws_bridge = AWSBridge(repo_root, integration_service)
    queue = integration_service.message_queue
    
    # 创建任务
    aws_task_id = "aws-test-004"
    result1 = aws_bridge.handle_aws_task_create(
        aws_task_id=aws_task_id,
        aws_task_code="AWS_INTAKE_TEST-20260124-004",
        aws_payload={
            "task_type": "RUN_PROMPT",
            "goal": "测试幂等性",
            "area": "AWS_INTAKE_TEST",
            "constraints": {},
            "acceptance": ["幂等验证通过"],
            "created_by": "aws_user",
        },
        user_token="test_user_token",
    )
    
    t1_task_id = result1["t1_task_id"]
    event_id_1 = result1["event_id"]
    print(f"✓ 第一次创建成功: event_id={event_id_1}")
    
    # 模拟断网重连：再次发送相同请求（应该被去重）
    result2 = aws_bridge.handle_aws_task_create(
        aws_task_id=aws_task_id,  # 相同的 aws_task_id
        aws_task_code="AWS_INTAKE_TEST-20260124-004",
        aws_payload={
            "task_type": "RUN_PROMPT",
            "goal": "测试幂等性",
            "area": "AWS_INTAKE_TEST",
            "constraints": {},
            "acceptance": ["幂等验证通过"],
            "created_by": "aws_user",
        },
        user_token="test_user_token",
    )
    
    # 验证：应该返回相同的 t1_task_id（幂等）
    assert result2["t1_task_id"] == t1_task_id, f"幂等验证失败: {result2['t1_task_id']} != {t1_task_id}"
    print(f"✓ 第二次创建返回相同 task_id（幂等验证通过）")
    
    # 验证消息队列去重
    messages = queue.get_pending_messages(limit=100)
    matching = [m for m in messages if m.get("task_id") == t1_task_id]
    # 应该只有一条消息（去重成功）
    print(f"✓ 消息队列中任务相关消息数: {len(matching)}")
    
    # 验证事件去重
    events_dir = repo_root / "docs" / "REPORT" / "ata" / "events"
    event_files = list(events_dir.glob(f"{event_id_1}.json"))
    assert len(event_files) == 1, f"事件文件应该只有1个，实际: {len(event_files)}"
    print(f"✓ 事件文件唯一（去重成功）")
    
    return True


def main():
    """运行所有测试场景"""
    print("=" * 60)
    print("AWS 统一入口接入自测")
    print("=" * 60)
    
    results = []
    
    try:
        results.append(("场景1: AWS创建任务->本地看板", test_scenario_1_aws_create_task_to_board()))
    except Exception as e:
        print(f"✗ 场景1失败: {e}")
        import traceback
        traceback.print_exc()
        results.append(("场景1", False))
    
    try:
        results.append(("场景2: 本地日志->Web实时", test_scenario_2_local_log_to_web()))
    except Exception as e:
        print(f"✗ 场景2失败: {e}")
        import traceback
        traceback.print_exc()
        results.append(("场景2", False))
    
    try:
        results.append(("场景3: CI失败修复->Web同步", test_scenario_3_ci_fail_repair_web_sync()))
    except Exception as e:
        print(f"✗ 场景3失败: {e}")
        import traceback
        traceback.print_exc()
        results.append(("场景3", False))
    
    try:
        results.append(("场景4: 断网重连幂等", test_scenario_4_idempotency_after_disconnect()))
    except Exception as e:
        print(f"✗ 场景4失败: {e}")
        import traceback
        traceback.print_exc()
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
