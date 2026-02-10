#!/usr/bin/env python3
"""
测试可靠投递机制
测试ack/nack、指数退避重试、SQLite离线队列、message_id去重和DLQ功能
"""

import json
import sys
import time
from pathlib import Path

# 添加当前目录到路径
sys.path.insert(0, str(Path(__file__).parent))

# 使用绝对导入
from message_queue import MessageQueue
from event_publisher import EventPublisher
from models import Event, EventType

def test_message_queue():
    """测试消息队列的基本功能"""
    print("=== 测试消息队列基本功能 ===")
    
    # 创建临时消息队列
    test_db = Path("test_message_queue.db")
    if test_db.exists():
        test_db.unlink()
    
    queue = MessageQueue(test_db)
    
    # 测试1: 基本入队和出队
    print("\n1. 测试基本入队和出队:")
    message_id = "test-001"
    success = queue.enqueue(message_id, "task-001", "board", {"test": "data"})
    assert success == True, "入队失败"
    print(f"   ✓ 入队成功: {message_id}")
    
    messages = queue.get_pending_messages()
    assert len(messages) == 1, "出队失败"
    print(f"   ✓ 出队成功: {messages[0]['message_id']}")
    
    # 测试2: 重复消息去重
    print("\n2. 测试重复消息去重:")
    success = queue.enqueue(message_id, "task-001", "board", {"test": "data"})
    assert success == False, "重复消息没有被拒绝"
    print(f"   ✓ 重复消息被正确拒绝")
    
    messages = queue.get_pending_messages()
    assert len(messages) == 1, "重复消息导致队列长度错误"
    print(f"   ✓ 队列长度保持正确")
    
    # 测试3: 消息确认
    print("\n3. 测试消息确认:")
    queue.mark_acked(message_id)
    messages = queue.get_pending_messages()
    assert len(messages) == 0, "已确认消息没有被移除"
    print(f"   ✓ 已确认消息被正确移除")
    
    # 测试4: 消息重试
    print("\n4. 测试消息重试:")
    message_id2 = "test-002"
    queue.enqueue(message_id2, "task-002", "board", {"test": "data"})
    
    # 第一次nack
    queue.mark_nacked(message_id2, "测试失败")
    messages = queue.get_pending_messages()
    assert len(messages) == 1, "nack后消息没有进入重试队列"
    print(f"   ✓ 第一次nack后消息进入重试队列")
    
    # 查看重试次数
    assert messages[0]["retry_count"] == 1, "重试次数错误"
    print(f"   ✓ 重试次数正确: {messages[0]['retry_count']}")
    
    # 第二次nack
    queue.mark_nacked(message_id2, "测试失败")
    messages = queue.get_pending_messages()
    assert messages[0]["retry_count"] == 2, "重试次数错误"
    print(f"   ✓ 第二次nack后重试次数正确")
    
    # 第三次nack（应该进入DLQ）
    queue.mark_nacked(message_id2, "测试失败")
    messages = queue.get_pending_messages()
    assert len(messages) == 0, "三次nack后消息没有进入DLQ"
    print(f"   ✓ 三次nack后消息进入DLQ")
    
    # 测试5: DLQ功能
    print("\n5. 测试DLQ功能:")
    dlq_messages = queue.get_dlq_messages()
    assert len(dlq_messages) == 1, "消息没有进入DLQ"
    print(f"   ✓ 消息成功进入DLQ")
    
    # 测试6: 重放DLQ消息
    print("\n6. 测试重放DLQ消息:")
    dlq_message = dlq_messages[0]
    success = queue.replay_dlq_message(dlq_message["message_id"])
    assert success == True, "重放DLQ消息失败"
    print(f"   ✓ DLQ消息重放成功")
    
    # 检查重放后的消息
    messages = queue.get_pending_messages()
    assert len(messages) == 1, "重放后的消息没有进入队列"
    print(f"   ✓ 重放后的消息成功进入队列")
    
    # 清理
    test_db.unlink()
    print("\n=== 所有测试通过！ ===")
    return True

def test_event_publishing():
    """测试事件发布功能"""
    print("\n=== 测试事件发布功能 ===")
    
    # 创建临时消息队列
    test_db = Path("test_event_publishing.db")
    if test_db.exists():
        test_db.unlink()
    
    queue = MessageQueue(test_db)
    publisher = EventPublisher(Path("test_repo"), queue)
    
    # 创建测试事件
    event = Event(
        type=EventType.TASK_CREATED,
        correlation_id="test-task-001",
        payload={
            "task_id": "test-task-001",
            "task_code": "TEST_TASK_001",
            "task_data": {"test": "data"}
        },
        source="test"
    )
    
    # 发布事件
    success = publisher.publish_event(event)
    assert success == True, "事件发布失败"
    print("✓ 事件发布成功")
    
    # 检查消息是否被发布到队列
    messages = queue.get_pending_messages()
    assert len(messages) >= 1, "事件没有被发布到队列"
    print(f"✓ 事件被发布到队列，队列中有 {len(messages)} 条消息")
    
    # 验证消息内容
    message_ids = [msg["message_id"] for msg in messages]
    assert event.event_id in message_ids, "事件ID不在队列中"
    print(f"✓ 事件ID {event.event_id} 存在于队列中")
    
    # 清理
    test_db.unlink()
    return True

def test_retry_mechanism():
    """测试重试机制"""
    print("\n=== 测试重试机制 ===")
    
    # 创建临时消息队列
    test_db = Path("test_retry_mechanism.db")
    if test_db.exists():
        test_db.unlink()
    
    queue = MessageQueue(test_db)
    
    # 入队消息
    message_id = "test-retry-001"
    queue.enqueue(message_id, "task-retry-001", "board", {"test": "data"})
    
    # 测试重试延迟
    print("测试重试延迟:")
    for i in range(1, 4):
        queue.mark_nacked(message_id, f"测试失败 {i}")
        messages = queue.get_pending_messages()
        if messages:
            print(f"  第 {i} 次nack后，消息状态: {messages[0]['status']}")
            print(f"  重试次数: {messages[0]['retry_count']}")
            print(f"  下次重试时间: {messages[0]['next_retry_at']}")
        else:
            print(f"  第 {i} 次nack后，消息进入DLQ")
    
    # 检查DLQ
    dlq_messages = queue.get_dlq_messages()
    assert len(dlq_messages) == 1, "消息没有进入DLQ"
    print(f"✓ 消息在3次重试后成功进入DLQ")
    
    # 清理
    test_db.unlink()
    return True

def main():
    """主测试函数"""
    try:
        # 运行所有测试
        test_message_queue()
        test_event_publishing()
        test_retry_mechanism()
        
        print("\n🎉 所有测试通过！可靠投递机制正常工作。")
        return 0
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    sys.exit(main())
