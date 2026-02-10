#!/usr/bin/env python3
"""
Test script for A2A Hub per-agent quota functionality.

Tests that:
1. When capacity=1, the second task is blocked
2. When completion_limit_per_minute=1, the second task is blocked
3. Agent quota is correctly enforced
4. Tasks are properly assigned when quota is available
"""

import sys
import time
from datetime import datetime

import requests

HUB_URL = "http://localhost:18788/api"
AGENT_ID = "test-agent-1"
OWNER_ROLE = "test-role"
CAPABILITIES = ["test-capability"]
ALLOWED_TOOLS = ["test-tool"]


class QuotaTest:
    """Test quota functionality"""

    def __init__(self):
        self.test_results = []

    def log_result(self, test_name, success, message):
        """Log test result"""
        result = {
            "test_name": test_name,
            "success": success,
            "message": message,
            "timestamp": datetime.utcnow().isoformat() + "Z",
        }
        self.test_results.append(result)
        print(f"{test_name}: {'PASS' if success else 'FAIL'} - {message}")

    def register_agent(self, capacity=1, completion_limit=1):
        """Register a test agent"""
        url = f"{HUB_URL}/api/agent/register"
        data = {
            "agent_id": AGENT_ID,
            "owner_role": OWNER_ROLE,
            "capabilities": CAPABILITIES,
            "allowed_tools": ALLOWED_TOOLS,
            "capacity": capacity,
            "completion_limit_per_minute": completion_limit,
        }

        response = requests.post(url, json=data)
        if response.status_code == 200:
            self.log_result("register_agent", True, "Agent registered successfully")
            return True
        else:
            self.log_result("register_agent", False, f"Agent registration failed: {response.text}")
            return False

    def deregister_agent(self):
        """Deregister the test agent"""
        url = f"{HUB_URL}/api/agent/{AGENT_ID}"
        response = requests.delete(url)
        if response.status_code == 200:
            self.log_result("deregister_agent", True, "Agent deregistered successfully")
            return True
        else:
            self.log_result(
                "deregister_agent", False, f"Agent deregistration failed: {response.text}"
            )
            return False

    def create_task(self, task_code, instructions):
        """Create a test task"""
        url = f"{HUB_URL}/api/task/create"
        data = {"TaskCode": task_code, "instructions": instructions, "owner_role": OWNER_ROLE}

        response = requests.post(url, json=data)
        return response

    def test_capacity_limit(self):
        """Test that capacity=1 blocks the second task"""
        print("\n=== Testing Capacity Limit (capacity=1) ===")

        # Generate unique task codes for this test run
        test_suffix = str(int(time.time()))
        task1_code = f"test-task-cap-{test_suffix}-1"
        task2_code = f"test-task-cap-{test_suffix}-2"

        # Register agent with capacity=1
        self.register_agent(capacity=1, completion_limit=100)  # High completion limit for this test

        try:
            # Create first task
            response1 = self.create_task(task1_code, "Test task 1 with test-capability")
            if response1.status_code == 200:
                task1_data = response1.json()
                self.log_result("create_task_1", True, f"First task created: {task1_data}")
            else:
                self.log_result(
                    "create_task_1", False, f"First task creation failed: {response1.text}"
                )
                return False

            # Create second task immediately
            response2 = self.create_task(task2_code, "Test task 2 with test-capability")
            if response2.status_code == 400:
                error_data = response2.json()
                if error_data.get("reason_code") == "AGENT_QUOTA_EXCEEDED":
                    self.log_result(
                        "create_task_2", True, f"Second task correctly blocked: {response2.text}"
                    )
                    return True
                else:
                    self.log_result(
                        "create_task_2",
                        False,
                        f"Second task blocked with wrong reason code: {response2.text}",
                    )
                    return False
            else:
                self.log_result(
                    "create_task_2",
                    False,
                    f"Second task not blocked, should have failed: {response2.text}",
                )
                return False
        finally:
            self.deregister_agent()

    def test_completion_limit(self):
        """Test that completion_limit=1 blocks the second task in the same minute"""
        print("\n=== Testing Completion Limit (completion_limit=1) ===")

        # Generate unique task codes for this test run
        test_suffix = str(int(time.time()))
        task3_code = f"test-task-comp-{test_suffix}-1"
        task4_code = f"test-task-comp-{test_suffix}-2"

        # Register agent with completion_limit=1
        self.register_agent(capacity=100, completion_limit=1)  # High capacity for this test

        try:
            # Create first task
            response1 = self.create_task(task3_code, "Test task 3 with test-capability")
            if response1.status_code == 200:
                task1_data = response1.json()
                self.log_result("create_task_3", True, f"First task created: {task1_data}")
                task_id1 = task1_data["task_id"]
            else:
                self.log_result(
                    "create_task_3", False, f"First task creation failed: {response1.text}"
                )
                return False

            # Complete the first task to increment completion count
            url = f"{HUB_URL}/api/task/result"
            result_data = {"task_code": task3_code, "status": "DONE", "result": {"test": "result"}}
            response_complete = requests.post(url, json=result_data)
            if response_complete.status_code == 200:
                self.log_result("complete_task_3", True, "First task completed successfully")
            else:
                self.log_result(
                    "complete_task_3",
                    False,
                    f"First task completion failed: {response_complete.text}",
                )
                return False

            # Create second task immediately (should be blocked due to completion limit)
            response2 = self.create_task(task4_code, "Test task 4 with test-capability")
            if response2.status_code != 200:
                task2_data = response2.json()
                if task2_data.get("reason_code") == "AGENT_QUOTA_EXCEEDED":
                    self.log_result(
                        "create_task_4",
                        True,
                        f"Second task correctly blocked due to completion limit: {task2_data}",
                    )
                    # Second task is blocked as expected due to completion limit
                    return True
                else:
                    self.log_result(
                        "create_task_4",
                        False,
                        f"Second task failed for unexpected reason: {response2.text}",
                    )
                    return False
            else:
                self.log_result(
                    "create_task_4",
                    False,
                    f"Second task created unexpectedly (should be blocked): {response2.text}",
                )
                return False
        finally:
            self.deregister_agent()

    def run_all_tests(self):
        """Run all tests"""
        print("Starting A2A Hub Quota Tests")
        print(f"Testing Hub at: {HUB_URL}")
        print(f"Agent ID: {AGENT_ID}")
        print(f"Owner Role: {OWNER_ROLE}")
        print("=" * 60)

        self.test_capacity_limit()
        self.test_completion_limit()

        print("\n" + "=" * 60)
        print("Test Results Summary:")
        print("=" * 60)

        total_tests = len(self.test_results)
        passed_tests = sum(1 for r in self.test_results if r["success"])
        failed_tests = total_tests - passed_tests

        print(f"Total Tests: {total_tests}")
        print(f"Passed: {passed_tests}")
        print(f"Failed: {failed_tests}")

        for result in self.test_results:
            status = "PASS" if result["success"] else "FAIL"
            print(f"- {result['test_name']}: {status} - {result['message']}")

        if failed_tests == 0:
            print("\n🎉 All tests passed!")
            return 0
        else:
            print(f"\n❌ {failed_tests} test(s) failed")
            return 1


def main():
    """Main function"""
    test = QuotaTest()
    exit_code = test.run_all_tests()
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
