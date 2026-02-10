#!/usr/bin/env python3
"""
A2A Hub Full Flow Test
Tests the complete flow: agent registration → task create → status → result
"""

import json
import os
import subprocess
import sys
import time
import uuid
from datetime import datetime

import requests

# Configuration
HUB_URL = "http://localhost:18788/api"
ARTIFACTS_DIR = "D:/quantsys/docs/REPORT/a2a/artifacts/A2A-HUB-MVP-ENDPOINTS-v0.1__20260115"
LOG_FILE = os.path.join(ARTIFACTS_DIR, "selftest.log")
CONTEXT_FILE = os.path.join(ARTIFACTS_DIR, "ata/context.json")

# Ensure artifacts directory exists
os.makedirs(ARTIFACTS_DIR, exist_ok=True)
os.makedirs(os.path.join(ARTIFACTS_DIR, "ata"), exist_ok=True)


# Log function
def log(message):
    """Log message to console and file"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_entry = f"[{timestamp}] {message}"
    print(log_entry)
    with open(LOG_FILE, "a") as f:
        f.write(log_entry + "\n")


# Start the A2A Hub
def start_hub():
    """Start the A2A Hub in the background"""
    log("Starting A2A Hub...")
    hub_process = subprocess.Popen(
        [sys.executable, "main.py"],
        cwd="D:/quantsys/tools/a2a_hub",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    # Wait for hub to start
    time.sleep(3)

    # Check if hub is running
    try:
        response = requests.get(f"{HUB_URL}/task/status", params={"task_code": "test"}, timeout=5)
        log(f"A2A Hub started successfully, response: {response.status_code}")
        return hub_process
    except requests.exceptions.RequestException:
        log("Failed to start A2A Hub!")
        # Print hub logs
        stdout, stderr = hub_process.communicate()
        log(f"Hub stdout: {stdout}")
        log(f"Hub stderr: {stderr}")
        raise


# Register an agent
def register_agent():
    """Register a test agent using unified registration tool"""
    log("Registering test agent using unified registration tool...")
    
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
            agent_id="test-agent-123",
            name="Test Agent",
            owner_role="test_role",
            capabilities=["task_execution"],
            worker_type="Shell",
            capacity=1,
            retry_count=3
        )
        
        if result["success"]:
            log("Agent registered successfully")
            return True
        else:
            log(f"Failed to register agent: {result.get('error', 'Unknown error')}")
            return False
    except Exception as e:
        log(f"Unexpected error in unified registration: {e}")
        # 回退到原始注册方法
        log("Falling back to original registration method...")
        agent_data = {
            "agent_id": "test-agent-123",
            "name": "Test Agent",
            "owner_role": "test_role",
            "capabilities": ["task_execution"],
            "allowed_tools": ["curl", "python"],
        }

        response = requests.post(f"{HUB_URL}/api/agent/register", json=agent_data)
        if response.status_code == 200:
            log("Agent registered successfully")
            return True
        else:
            log(f"Failed to register agent: {response.status_code}, {response.text}")
            return False


# Test task creation
def create_task():
    """Test task creation endpoint"""
    log("Creating test task...")
    task_data = {
        "TaskCode": f"TEST-TASK-{uuid.uuid4()}",
        "instructions": "Test task instructions",
        "owner_role": "test_role",
    }

    response = requests.post(f"{HUB_URL}/task/create", json=task_data)
    if response.status_code == 200:
        result = response.json()
        log(
            f"Task created successfully: task_id={result['task_id']}, task_code={result['task_code']}"
        )
        return result
    else:
        log(f"Failed to create task: {response.status_code}, {response.text}")
        return None


# Test task status
def get_task_status(task_code, task_id):
    """Test task status endpoint"""
    log(f"Getting task status for task_code={task_code}, task_id={task_id}...")

    # Try with task_code first
    response = requests.get(f"{HUB_URL}/task/status", params={"task_code": task_code})
    if response.status_code == 200:
        result = response.json()
        log(f"Task status retrieved successfully using task_code: {result['task']['status']}")
        return result
    else:
        # Try with task_id
        response = requests.get(f"{HUB_URL}/task/status", params={"task_id": task_id})
        if response.status_code == 200:
            result = response.json()
            log(f"Task status retrieved successfully using task_id: {result['task']['status']}")
            return result
        else:
            log(f"Failed to get task status: {response.status_code}, {response.text}")
            return None


# Test result submission
def submit_task_result(task_code):
    """Test task result submission endpoint"""
    log(f"Submitting task result for task_code={task_code}...")
    result_data = {
        "task_code": task_code,
        "status": "DONE",
        "result": {"message": "Task completed successfully", "test_key": "test_value"},
    }

    response = requests.post(f"{HUB_URL}/task/result", json=result_data)
    if response.status_code == 200:
        result = response.json()
        log(f"Task result submitted successfully: {result['message']}, status={result['status']}")
        return True
    else:
        log(f"Failed to submit task result: {response.status_code}, {response.text}")
        return False


# Generate context.json
def generate_context_json(task_result):
    """Generate context.json artifact"""
    log("Generating context.json...")
    context = {
        "task_id": task_result["task_id"],
        "task_code": task_result["task_code"],
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "status": "success",
        "endpoints": {
            "create_task": f"{HUB_URL}/task/create",
            "get_status": f"{HUB_URL}/task/status",
            "submit_result": f"{HUB_URL}/task/result",
        },
        "test_result": "PASS",
    }

    with open(CONTEXT_FILE, "w") as f:
        json.dump(context, f, indent=2)

    log(f"Context file generated: {CONTEXT_FILE}")


# Main test function
def main():
    """Run the full test flow"""
    hub_process = None

    try:
        # Start with clean log file
        open(LOG_FILE, "w").close()

        log("=== A2A Hub Full Flow Test ===")
        log(f"Test Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        log(f"HUB_URL: {HUB_URL}")

        # Start hub
        hub_process = start_hub()

        # Register agent
        if not register_agent():
            raise Exception("Failed to register agent")

        # Create task
        task_result = create_task()
        if not task_result:
            raise Exception("Failed to create task")

        task_code = task_result["task_code"]
        task_id = task_result["task_id"]

        # Get task status
        status_result = get_task_status(task_code, task_id)
        if not status_result:
            raise Exception("Failed to get task status")

        # Submit task result
        if not submit_task_result(task_code):
            raise Exception("Failed to submit task result")

        # Get final status
        final_status = get_task_status(task_code, task_id)
        if not final_status or final_status["task"]["status"] != "DONE":
            raise Exception("Task did not complete successfully")

        # Generate context.json
        generate_context_json(task_result)

        log("=== Test Summary ===")
        log("PASS: Agent Registration")
        log("PASS: Task Creation")
        log("PASS: Task Status")
        log("PASS: Result Submission")
        log("PASS: Final Status")
        log("PASS: Full Flow")

        # Write exit code to log
        with open(LOG_FILE, "a") as f:
            f.write("\nEXIT_CODE=0\n")

        log("Test completed successfully!")
        return 0

    except Exception as e:
        log(f"ERROR: Test failed - {str(e)}")
        with open(LOG_FILE, "a") as f:
            f.write(f"\nERROR: {str(e)}\n")
            f.write("EXIT_CODE=1\n")
        return 1

    finally:
        # Cleanup
        if hub_process:
            log("Stopping A2A Hub...")
            hub_process.terminate()
            try:
                hub_process.wait(timeout=5)
                log("A2A Hub stopped successfully")
            except subprocess.TimeoutExpired:
                hub_process.kill()
                log("A2A Hub killed after timeout")


if __name__ == "__main__":
    sys.exit(main())
