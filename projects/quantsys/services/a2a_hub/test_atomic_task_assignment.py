#!/usr/bin/env python3
"""
Test script to verify atomic task assignment fix

This test verifies that a task can't be assigned to multiple workers simultaneously
"""

import os
import subprocess
import sys
import threading
import time

import requests

# Configuration
HUB_URL = "http://localhost:18788/api"
HUB_SCRIPT = os.path.join(os.path.dirname(__file__), "main.py")
TEST_TASK_CODE = "TEST-ATOMIC-ASSIGNMENT-001"


class TestHub:
    """Test hub wrapper"""

    def __init__(self):
        self.process = None

    def start(self):
        """Start hub server"""
        print("Starting A2A Hub...")
        env = os.environ.copy()
        env["A2A_HUB_SECRET_KEY"] = "test-secret"

        self.process = subprocess.Popen(
            [sys.executable, HUB_SCRIPT],
            env=env,
            cwd=os.path.dirname(__file__),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        time.sleep(3)
        return True

    def stop(self):
        """Stop hub server"""
        print("Stopping A2A Hub...")
        if self.process:
            self.process.terminate()
            self.process.wait()

    def cleanup(self):
        """Clean up database"""
        db_path = os.path.join(os.path.dirname(__file__), "state", "a2a_hub.db")
        if os.path.exists(db_path):
            try:
                os.remove(db_path)
            except:
                pass


def register_agent(agent_id):
    """Register a test agent using unified registration tool"""
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
        # 覆盖A2A Headers
        registrar.a2a_headers = {"X-A2A-Role": "admin"}  # Use admin role for registration
        
        # 调用统一注册方法
        result = registrar.register_a2a_hub(
            agent_id=agent_id,
            name=agent_id,
            owner_role="execution_engine",
            capabilities=["test"],
            worker_type="Shell",
            capacity=1,
            retry_count=3
        )
        
        return result["success"]
    except Exception as e:
        print(f"Unexpected error in unified registration: {e}")
        # 回退到原始注册方法
        print("Falling back to original registration method...")
        response = requests.post(
            f"{HUB_URL}/api/agent/register",
            json={
                "agent_id": agent_id,
                "owner_role": "execution_engine",
                "capabilities": ["test"],
                "allowed_tools": ["python"],
            },
            headers={"X-A2A-Role": "admin"},  # Use admin role for registration
        )
        return response.status_code == 200


def create_test_task():
    """Create a test task"""
    response = requests.post(
        f"{HUB_URL}/api/task/create",
        json={
            "TaskCode": TEST_TASK_CODE,
            "instructions": "echo 'test'",
            "owner_role": "execution_engine",
            "area": "test",
            "how_to_repro": "test",
            "expected": "test",
            "evidence_requirements": "test",
        },
    )
    return response.status_code == 200


def get_next_task(agent_id, results, index):
    """Try to get the next task"""
    response = requests.get(f"{HUB_URL}/api/task/next", params={"agent_id": agent_id})
    results[index] = response.json()


def test_atomic_assignment():
    """Test atomic task assignment"""
    print("=== Testing Atomic Task Assignment ===")

    # Clean up
    hub = TestHub()
    hub.cleanup()

    try:
        # Start hub
        hub.start()

        # Register agents
        print("1. Registering test agents...")
        if not register_agent("agent-1"):
            print("❌ Failed to register agent-1")
            return False
        if not register_agent("agent-2"):
            print("❌ Failed to register agent-2")
            return False
        print("✅ Agents registered successfully")

        # Create test task
        print("2. Creating test task...")
        if not create_test_task():
            print("❌ Failed to create test task")
            return False
        print("✅ Test task created successfully")

        # Simulate race condition with multiple threads
        print("3. Simulating race condition with 2 agents...")
        results = [None, None]
        threads = []

        # Start threads simultaneously
        for i in range(2):
            t = threading.Thread(target=get_next_task, args=(f"agent-{i + 1}", results, i))
            threads.append(t)
            t.start()

        # Wait for all threads to complete
        for t in threads:
            t.join()

        # Analyze results
        success_count = 0
        for i, result in enumerate(results):
            task = result.get("task")
            if task:
                print(f"✅ Agent-{i + 1} got task: {task['id']}")
                success_count += 1
            else:
                print(f"❌ Agent-{i + 1} got no task: {result.get('message')}")

        # Verify only one agent got the task
        if success_count == 1:
            print("✅ SUCCESS: Only one agent got the task (atomic assignment works!)")
            return True
        else:
            print(f"❌ FAILURE: {success_count} agents got the task (expected: 1)")
            return False

    finally:
        hub.stop()
        hub.cleanup()


def main():
    """Main test function"""
    print("Testing Atomic Task Assignment to Prevent Double Execution")
    print("=" * 60)

    success = test_atomic_assignment()

    if success:
        print("\n🎉 All tests passed! EXIT_CODE=0")
        sys.exit(0)
    else:
        print("\n💥 Tests failed! EXIT_CODE=1")
        sys.exit(1)


if __name__ == "__main__":
    main()
