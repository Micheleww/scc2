#!/usr/bin/env python3
"""
Comprehensive test script for agent capacity lease functionality

This script tests the agent capacity lease feature with various scenarios:
1. Basic capacity restriction
2. Task completion releases capacity
3. Task failure releases capacity
4. Lease expiration releases capacity
5. Multiple agents with different capacities
"""

import time

import requests

# A2A Hub API endpoint
hub_url = "http://localhost:18788/api"


class TestCapacityLease:
    """Test class for agent capacity lease functionality"""

    def __init__(self):
        self.test_results = {
            "basic_capacity_restriction": False,
            "task_completion_releases_capacity": False,
            "task_failure_releases_capacity": False,
            "lease_expiration_releases_capacity": False,
            "multiple_agents_different_capacities": False,
        }

    def register_agent(self, agent_id, capacity=1):
        """Register a test agent using unified registration tool"""
        try:
            # 导入统一注册工具
            import sys
            import os
            sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            from tools.register_agent import AgentRegistrar
            
            # 创建注册器实例
            registrar = AgentRegistrar()
            
            # 调用统一注册方法
            result = registrar.register_a2a_hub(
                agent_id=agent_id,
                name=agent_id,
                owner_role="test_role",
                capabilities=["test_capability"],
                worker_type="Shell",
                capacity=capacity,
                retry_count=3
            )
            
            return result["success"]
        except Exception as e:
            print(f"Unexpected error in unified registration: {e}")
            # 回退到原始注册方法
            print("Falling back to original registration method...")
            agent_config = {
                "agent_id": agent_id,
                "owner_role": "test_role",
                "capabilities": ["test_capability"],
                "allowed_tools": ["test_tool"],
                "capacity": capacity,
            }
            response = requests.post(f"{hub_url}/api/agent/register", json=agent_config)
            return response.status_code == 200

    def create_task(self, task_code):
        """Create a test task"""
        task_config = {
            "TaskCode": task_code,
            "instructions": "Test task with test_capability",
            "owner_role": "test_role",
            "timeout_seconds": 300,
            "max_retries": 1,
        }
        response = requests.post(f"{hub_url}/api/task/create", json=task_config)
        return response.status_code == 200, response.json()

    def get_agent_available_capacity(self, agent_id):
        """Get agent's available capacity"""
        response = requests.get(f"{hub_url}/api/agent/{agent_id}")
        if response.status_code == 200:
            agent_data = response.json()
            return agent_data.get("agent", {}).get("available_capacity", -1)
        return -1

    def complete_task(self, task_code):
        """Complete a test task"""
        response = requests.post(
            f"{hub_url}/api/task/result",
            json={"task_code": task_code, "status": "DONE", "result": {"test_key": "test_value"}},
        )
        return response.status_code == 200

    def fail_task(self, task_code):
        """Fail a test task"""
        response = requests.post(
            f"{hub_url}/api/task/result",
            json={
                "task_code": task_code,
                "status": "FAIL",
                "reason_code": "TEST_FAILURE",
                "last_error": "Test error message",
            },
        )
        return response.status_code == 200

    def test_basic_capacity_restriction(self):
        """Test basic capacity restriction"""
        print("\n=== Test 1: Basic Capacity Restriction ===")

        # Register agent with capacity=1
        if not self.register_agent("test_agent_001", capacity=1):
            print("Failed to register agent")
            return False

        # Create first task - should succeed
        success, _ = self.create_task("test_task_101")
        if not success:
            print("Failed to create first task")
            return False

        # Check available capacity is 0
        capacity = self.get_agent_available_capacity("test_agent_001")
        if capacity != 0:
            print(f"Expected available_capacity=0, got {capacity}")
            return False

        # Create second task - should fail
        success, _ = self.create_task("test_task_102")
        if success:
            print("Second task should have failed due to capacity constraint")
            return False

        print("✓ Basic capacity restriction test passed")
        self.test_results["basic_capacity_restriction"] = True
        return True

    def test_task_completion_releases_capacity(self):
        """Test that task completion releases capacity"""
        print("\n=== Test 2: Task Completion Releases Capacity ===")

        # Complete the first task
        if not self.complete_task("test_task_101"):
            print("Failed to complete task")
            return False

        # Check available capacity is 1 again
        capacity = self.get_agent_available_capacity("test_agent_001")
        if capacity != 1:
            print(f"Expected available_capacity=1 after task completion, got {capacity}")
            return False

        # Create another task - should succeed
        success, _ = self.create_task("test_task_103")
        if not success:
            print("Failed to create task after capacity release")
            return False

        print("✓ Task completion releases capacity test passed")
        self.test_results["task_completion_releases_capacity"] = True
        return True

    def test_task_failure_releases_capacity(self):
        """Test that task failure releases capacity"""
        print("\n=== Test 3: Task Failure Releases Capacity ===")

        # Fail the current task
        if not self.fail_task("test_task_103"):
            print("Failed to fail task")
            return False

        # Check available capacity is 1 again
        capacity = self.get_agent_available_capacity("test_agent_001")
        if capacity != 1:
            print(f"Expected available_capacity=1 after task failure, got {capacity}")
            return False

        print("✓ Task failure releases capacity test passed")
        self.test_results["task_failure_releases_capacity"] = True
        return True

    def test_lease_expiration_releases_capacity(self):
        """Test that lease expiration releases capacity"""
        print("\n=== Test 4: Lease Expiration Releases Capacity ===")

        # Register agent with short lease time
        if not self.register_agent("test_agent_002", capacity=1):
            print("Failed to register agent")
            return False

        # Create task
        success, task_result = self.create_task("test_task_201")
        if not success:
            print("Failed to create task")
            return False

        # Get task details including task_id
        task_id = task_result.get("task_id")
        if not task_id:
            print("Failed to get task_id from response")
            return False

        # Get agent status
        capacity = self.get_agent_available_capacity("test_agent_002")
        if capacity != 0:
            print(f"Expected available_capacity=0, got {capacity}")
            return False

        # Manually set the task to RUNNING with a very short lease
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        now = datetime.datetime.utcnow().isoformat() + "Z"
        cursor.execute(
            """
        UPDATE tasks
        SET status = 'RUNNING', lease_expiry_ts = ?, updated_at = ?
        WHERE id = ?
        """,
            (now, now, task_id),
        )
        conn.commit()
        conn.close()

        # Wait for lease checker to run (default interval is 10 seconds)
        print("Waiting for lease to expire (15 seconds)...")
        time.sleep(15)

        # Check available capacity is 1 again
        capacity = self.get_agent_available_capacity("test_agent_002")
        if capacity != 1:
            print(f"Expected available_capacity=1 after lease expiration, got {capacity}")
            return False

        print("✓ Lease expiration releases capacity test passed")
        self.test_results["lease_expiration_releases_capacity"] = True
        return True

    def test_multiple_agents_different_capacities(self):
        """Test multiple agents with different capacities"""
        print("\n=== Test 5: Multiple Agents with Different Capacities ===")

        # Register agents with different capacities
        if not self.register_agent("test_agent_003", capacity=2):
            print("Failed to register agent with capacity=2")
            return False

        if not self.register_agent("test_agent_004", capacity=3):
            print("Failed to register agent with capacity=3")
            return False

        # Create multiple tasks - should distribute across agents
        task_count = 4
        success_count = 0

        for i in range(task_count):
            success, _ = self.create_task(f"test_task_30{i + 1}")
            if success:
                success_count += 1

        # We expect at least 2 tasks to be created (one agent has capacity=2)
        if success_count < 2:
            print(f"Expected at least 2 successful tasks, got {success_count}")
            return False

        print("✓ Multiple agents with different capacities test passed")
        self.test_results["multiple_agents_different_capacities"] = True
        return True

    def run_all_tests(self):
        """Run all comprehensive tests"""
        print("=== Running Comprehensive Capacity Lease Tests ===")

        # Import required modules for lease expiration test
        global sqlite3, datetime, DB_PATH
        import sqlite3
        from datetime import datetime

        from main import DB_PATH

        # Run all tests
        self.test_basic_capacity_restriction()
        self.test_task_completion_releases_capacity()
        self.test_task_failure_releases_capacity()
        # Skip lease expiration test for now (requires DB access)
        # self.test_lease_expiration_releases_capacity()
        self.test_multiple_agents_different_capacities()

        # Print summary
        print("\n=== Test Results Summary ===")
        total_tests = len(self.test_results)
        passed_tests = sum(1 for result in self.test_results.values() if result)

        for test_name, result in self.test_results.items():
            status = "✓ PASSED" if result else "✗ FAILED"
            print(f"{status} {test_name}")

        print(f"\nTotal Tests: {total_tests}")
        print(f"Passed: {passed_tests}")
        print(f"Failed: {total_tests - passed_tests}")

        if passed_tests == total_tests:
            print("\n🎉 All tests passed!")
            return 0
        else:
            print(f"\n❌ {total_tests - passed_tests} test(s) failed")
            return 1


if __name__ == "__main__":
    tester = TestCapacityLease()
    exit(tester.run_all_tests())
