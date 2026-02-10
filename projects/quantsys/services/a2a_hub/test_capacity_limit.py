#!/usr/bin/env python3
"""
Focused test script for A2A Hub capacity limit functionality.
Tests that when capacity=1, the second task is blocked with AGENT_QUOTA_EXCEEDED.
"""

import sys
import time

import requests

HUB_URL = "http://localhost:18788/api"
AGENT_ID = "test-agent-" + str(int(time.time()))
OWNER_ROLE = "test-role"
CAPABILITIES = ["test-capability"]
ALLOWED_TOOLS = ["test-tool"]


def register_agent():
    """Register agent with capacity=1 using unified registration tool"""
    try:
        # 导入统一注册工具
        import sys
        import os
        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        from tools.register_agent import AgentRegistrar
        
        # 创建注册器实例
        registrar = AgentRegistrar()
        # 覆盖A2A Hub URL
        registrar.a2a_hub_url = HUB_URL
        
        # 调用统一注册方法
        result = registrar.register_a2a_hub(
            agent_id=AGENT_ID,
            name=AGENT_ID,
            owner_role=OWNER_ROLE,
            capabilities=CAPABILITIES,
            worker_type="Shell",
            capacity=1,
            retry_count=3
        )
        
        return result["success"]
    except Exception as e:
        print(f"Unexpected error in unified registration: {e}")
        # 回退到原始注册方法
        print("Falling back to original registration method...")
        url = f"{HUB_URL}/api/agent/register"
        data = {
            "agent_id": AGENT_ID,
            "owner_role": OWNER_ROLE,
            "capabilities": CAPABILITIES,
            "allowed_tools": ALLOWED_TOOLS,
            "capacity": 1,
            "completion_limit_per_minute": 60,
        }
        response = requests.post(url, json=data)
        return response.status_code == 200


def deregister_agent():
    """Deregister the test agent"""
    url = f"{HUB_URL}/api/agent/{AGENT_ID}"
    response = requests.delete(url)
    return response.status_code == 200


def create_task(task_code):
    """Create a test task"""
    url = f"{HUB_URL}/api/task/create"
    data = {
        "TaskCode": task_code,
        "instructions": "Test task with test-capability",
        "owner_role": OWNER_ROLE,
    }
    return requests.post(url, json=data)


def main():
    """Main test function"""
    print("Starting A2A Hub Capacity Limit Test")
    print(f"Testing Hub at: {HUB_URL}")
    print(f"Agent ID: {AGENT_ID}")
    print("=" * 50)

    try:
        # Register agent with capacity=1
        print("1. Registering agent with capacity=1...")
        if not register_agent():
            print("FAIL: Agent registration failed")
            return 1
        print("PASS: Agent registered successfully")

        # Generate unique task codes
        test_suffix = str(int(time.time()))
        task1_code = f"task-cap-{test_suffix}-1"
        task2_code = f"task-cap-{test_suffix}-2"

        # Create first task
        print(f"2. Creating first task: {task1_code}...")
        response1 = create_task(task1_code)
        if response1.status_code != 200:
            print(f"FAIL: First task creation failed: {response1.text}")
            return 1
        print("PASS: First task created successfully")

        # Create second task (should be blocked)
        print(f"3. Creating second task: {task2_code}...")
        response2 = create_task(task2_code)
        if response2.status_code == 400:
            error_data = response2.json()
            if error_data.get("reason_code") == "AGENT_QUOTA_EXCEEDED":
                print("PASS: Second task correctly blocked with AGENT_QUOTA_EXCEEDED")
                print(f"   Error message: {response2.text}")
                return 0
            else:
                print(f"FAIL: Second task blocked with wrong reason code: {response2.text}")
                return 1
        else:
            print(f"FAIL: Second task not blocked, should have failed: {response2.text}")
            return 1

    finally:
        # Cleanup
        print("4. Deregistering agent...")
        deregister_agent()
        print("Cleanup complete")


if __name__ == "__main__":
    sys.exit(main())
