#!/usr/bin/env python3
"""
Self-test script for A2A Hub AWS deployment
Tests create/status/result functionality
"""

import sys
import time

import requests

base_url = "http://localhost:18788/api"


def test_register_agent():
    """Test agent registration using unified registration tool"""
    print("1. Testing agent registration...")
    try:
        # 导入统一注册工具
        import sys
        import os
        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        from tools.register_agent import AgentRegistrar
        
        # 创建注册器实例
        registrar = AgentRegistrar()
        # 覆盖A2A Hub URL
        registrar.a2a_hub_url = base_url
        
        # 调用统一注册方法
        result = registrar.register_a2a_hub(
            agent_id="test-agent-01",
            name="test-agent-01",
            owner_role="test",
            capabilities=["test"],
            worker_type="Shell",
            capacity=1,
            retry_count=3
        )
        
        if result["success"]:
            print(f"   ✓ Agent registered successfully: {result}")
            return True
        else:
            print(f"   ✗ Agent registration failed: {result.get('error', 'Unknown error')}")
            # 回退到原始注册方法
            print("   Falling back to original registration method...")
            payload = {
                "agent_id": "test-agent-01",
                "owner_role": "test",
                "capabilities": ["test"],
                "allowed_tools": ["ata.search", "ata.fetch"],
            }
            response = requests.post(f"{base_url}/api/agent/register", json=payload)
            if response.status_code == 200:
                result = response.json()
                print(f"   ✓ Agent registered successfully: {result}")
                return True
            else:
                print(f"   ✗ Agent registration failed: {response.status_code} {response.text}")
                return False
    except Exception as e:
        print(f"   ✗ Unexpected error in unified registration: {e}")
        # 回退到原始注册方法
        print("   Falling back to original registration method...")
        payload = {
            "agent_id": "test-agent-01",
            "owner_role": "test",
            "capabilities": ["test"],
            "allowed_tools": ["ata.search", "ata.fetch"],
        }
        response = requests.post(f"{base_url}/api/agent/register", json=payload)
        if response.status_code == 200:
            result = response.json()
            print(f"   ✓ Agent registered successfully: {result}")
            return True
        else:
            print(f"   ✗ Agent registration failed: {response.status_code} {response.text}")
            return False


def test_create_task():
    """Test task creation"""
    print("2. Testing task creation...")

    payload = {
        "TaskCode": "TEST-AWS-DEPLOY-01",
        "instructions": "Test task for AWS deployment",
        "owner_role": "test",
    }

    response = requests.post(f"{base_url}/api/task/create", json=payload)

    if response.status_code == 200:
        result = response.json()
        print(f"   ✓ Task created successfully: {result}")
        return result.get("task_id")
    else:
        print(f"   ✗ Task creation failed: {response.status_code} {response.text}")
        return None


def test_get_status(task_id):
    """Test task status retrieval"""
    print(f"3. Testing task status for {task_id}...")

    response = requests.get(f"{base_url}/api/task/status?task_id={task_id}")

    if response.status_code == 200:
        result = response.json()
        print(f"   ✓ Task status retrieved: {result['task']['status']}")
        return True
    else:
        print(f"   ✗ Task status retrieval failed: {response.status_code} {response.text}")
        return False


def test_submit_result(task_id):
    """Test task result submission"""
    print(f"4. Testing result submission for {task_id}...")

    payload = {
        "task_code": "TEST-AWS-DEPLOY-01",
        "status": "DONE",
        "result": {"message": "Test result for AWS deployment", "success": True},
    }

    response = requests.post(f"{base_url}/api/task/result", json=payload)

    if response.status_code == 200:
        result = response.json()
        print(f"   ✓ Result submitted successfully: {result}")
        return True
    else:
        print(f"   ✗ Result submission failed: {response.status_code} {response.text}")
        return False


def test_get_result(task_id):
    """Test getting task result"""
    print(f"5. Testing getting task result for {task_id}...")

    response = requests.get(f"{base_url}/api/task/status?task_id={task_id}")

    if response.status_code == 200:
        result = response.json()
        if result["task"]["status"] == "DONE" and result["task"]["result"]:
            print(f"   ✓ Task result retrieved successfully: {result['task']['result']}")
            return True
        else:
            print(f"   ✗ Task result not found or task not completed: {result['task']['status']}")
            return False
    else:
        print(f"   ✗ Task result retrieval failed: {response.status_code} {response.text}")
        return False


def test_health_check():
    """Test health check endpoint"""
    print("5. Testing health check...")

    response = requests.get(f"{base_url}/api/health")

    if response.status_code == 200:
        result = response.json()
        if result["status"] == "healthy":
            print(f"   ✓ Health check passed: {result['status']}")
            return True
        else:
            print(f"   ✗ Health check failed: {result['status']}")
            return False
    else:
        print(f"   ✗ Health check endpoint failed: {response.status_code} {response.text}")
        return False


def main():
    """Main test function"""
    print("=== A2A Hub AWS Deployment Self-Test ===")
    print(f"Testing against: {base_url}")
    print("=" * 50)

    try:
        # Wait for service to be ready
        print("0. Waiting for service to be ready...")
        time.sleep(5)

        # Test health check first
        if not test_health_check():
            print("Service not healthy, exiting...")
            return 1

        # Test agent registration
        if not test_register_agent():
            return 1

        # Test task creation
        task_id = test_create_task()
        if not task_id:
            return 1

        # Test task status
        if not test_get_status(task_id):
            return 1

        # Test result submission
        if not test_submit_result(task_id):
            return 1

        # Test getting result
        if not test_get_result(task_id):
            return 1

        print("\n" + "=" * 50)
        print("🎉 All tests passed!")
        print("EXIT_CODE=0")
        return 0

    except Exception as e:
        print(f"\n❌ Test failed with exception: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
