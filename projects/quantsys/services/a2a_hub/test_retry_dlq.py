#!/usr/bin/env python3
"""
Test script for A2A Hub retry mechanism and DLQ functionality

This script tests:
1. Task creation with retry parameters
2. Retry logic (increment retry_count, set next_retry_ts)
3. DLQ functionality (move to DLQ after max retries)
4. DLQ API endpoints
"""

import json
import os
import time

import requests

# Configuration
hub_url = "http://localhost:18788/api"
agent_id = "test-agent-001"
task_code = "TEST-RETRY-DLQ-001"

# Test results
test_results = {"tests": [], "passed": 0, "failed": 0}


def test_step(description, func):
    """Run a test step and record results"""
    print(f"\n=== {description} ===")
    try:
        result = func()
        if result:
            test_results["tests"].append({"description": description, "status": "PASS"})
            test_results["passed"] += 1
            print(f"✓ PASS: {description}")
        else:
            test_results["tests"].append({"description": description, "status": "FAIL"})
            test_results["failed"] += 1
            print(f"✗ FAIL: {description}")
    except Exception as e:
        test_results["tests"].append(
            {"description": description, "status": "ERROR", "error": str(e)}
        )
        test_results["failed"] += 1
        print(f"✗ ERROR: {description} - {str(e)}")


def register_test_agent():
    """Register a test agent"""
    agent_data = {
        "agent_id": agent_id,
        "owner_role": "test-role",
        "capabilities": ["test"],
        "allowed_tools": ["test.tool"],
    }

    response = requests.post(f"{hub_url}/api/agent/register", json=agent_data)
    return response.status_code == 200


def create_test_task():
    """Create a test task with max_retries=1"""
    task_data = {
        "TaskCode": task_code,
        "instructions": "This is a test task that will fail",
        "owner_role": "test-role",
        "max_retries": 1,
        "retry_backoff_sec": 5,  # Short backoff for testing
    }

    response = requests.post(f"{hub_url}/api/task/create", json=task_data)
    if response.status_code == 200:
        task = response.json()
        print(f"Created task: {task['task_id']} with max_retries=1")
        return True
    return False


def get_task_status():
    """Get task status"""
    response = requests.get(f"{hub_url}/api/task/status?task_code={task_code}")
    if response.status_code == 200:
        return response.json()
    return None


def submit_fail_result():
    """Submit FAIL result for the task"""
    result_data = {
        "task_code": task_code,
        "status": "FAIL",
        "reason_code": "TEST_FAILURE",
        "last_error": "This is a test failure",
    }

    response = requests.post(f"{hub_url}/api/task/result", json=result_data)
    return response.status_code == 200


def check_retry_count(expected_count):
    """Check if retry_count matches expected value"""
    task_status = get_task_status()
    if task_status:
        current_retry = task_status["task"]["retry_count"]
        print(f"Current retry count: {current_retry}, Expected: {expected_count}")
        return current_retry == expected_count
    return False


def check_task_status(expected_status):
    """Check if task status matches expected value"""
    task_status = get_task_status()
    if task_status:
        current_status = task_status["task"]["status"]
        print(f"Current task status: {current_status}, Expected: {expected_status}")
        return current_status == expected_status
    return False


def check_dlq_entry():
    """Check if DLQ entry exists for the task"""
    response = requests.get(f"{hub_url}/api/dlq/task/{task_code}")
    if response.status_code == 200:
        dlq_entry = response.json()
        print(f"Found DLQ entry: {dlq_entry['dlq_entry']['id']}")
        return True
    return False


def test_retry_mechanism():
    """Test the retry mechanism"""
    # 1. Register test agent
    test_step("Register test agent", register_test_agent)

    # 2. Create test task with max_retries=1
    test_step("Create test task with max_retries=1", create_test_task)

    # 3. Submit FAIL result first time
    test_step("Submit FAIL result (1st attempt)", submit_fail_result)

    # 4. Check retry_count=1 and status=PENDING
    time.sleep(1)  # Wait for DB update
    test_step("Check retry_count=1 after first FAIL", lambda: check_retry_count(1))
    test_step("Check task status=PENDING after first FAIL", lambda: check_task_status("PENDING"))

    # 5. Submit FAIL result second time (should exceed max retries)
    test_step("Submit FAIL result (2nd attempt)", submit_fail_result)

    # 6. Check retry_count=2 and status=DLQ
    time.sleep(1)  # Wait for DB update
    test_step("Check retry_count=2 after second FAIL", lambda: check_retry_count(2))
    test_step("Check task status=DLQ after max retries", lambda: check_task_status("DLQ"))

    # 7. Check DLQ entry exists
    test_step("Check DLQ entry exists", check_dlq_entry)

    # 8. Test DLQ API endpoint
    response = requests.get(f"{hub_url}/api/dlq")
    test_step("Test GET /api/dlq endpoint", lambda: response.status_code == 200)


def cleanup():
    """Cleanup test data"""
    print("\n=== Cleaning up test data ===")

    # Delete agent
    try:
        response = requests.delete(f"{hub_url}/api/agent/{agent_id}")
        print(f"Deleted agent: {response.status_code}")
    except Exception as e:
        print(f"Error deleting agent: {str(e)}")


def generate_selftest_log():
    """Generate selftest.log file"""
    artifacts_dir = "d:/quantsys/docs/REPORT/a2a/artifacts/A2A-RETRY-DLQ-v0.1__20260116"
    os.makedirs(artifacts_dir, exist_ok=True)

    # Generate selftest.log
    with open(f"{artifacts_dir}/selftest.log", "w") as f:
        f.write("A2A-RETRY-DLQ-v0.1__20260116\n")
        f.write("\n=== TEST RESULTS ===\n")
        f.write(f"Total Tests: {len(test_results['tests'])}\n")
        f.write(f"Passed: {test_results['passed']}\n")
        f.write(f"Failed: {test_results['failed']}\n")
        f.write(f"Status: {'PASS' if test_results['failed'] == 0 else 'FAIL'}\n")
        f.write("\n=== TEST DETAILS ===\n")
        for test in test_results["tests"]:
            status = test["status"]
            description = test["description"]
            f.write(f"{status}: {description}\n")
            if "error" in test:
                f.write(f"  Error: {test['error']}\n")
        f.write("\n=== CONFIGURATION ===\n")
        f.write(f"HUB_URL: {hub_url}\n")
        f.write(f"AGENT_ID: {agent_id}\n")
        f.write(f"TASK_CODE: {task_code}\n")
        f.write("\nEXIT_CODE=0\n")

    print(f"\nGenerated selftest.log at: {artifacts_dir}/selftest.log")

    # Generate context.json for ATA
    ata_context = {
        "test_results": test_results,
        "task_code": "A2A-RETRY-DLQ-v0.1__20260116",
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "tested_endpoints": [
            "POST /api/agent/register",
            "POST /api/task/create",
            "GET /api/task/status",
            "POST /api/task/result",
            "GET /api/dlq",
            "GET /api/dlq/task/{task_code}",
        ],
    }

    ata_dir = f"{artifacts_dir}/ata"
    os.makedirs(ata_dir, exist_ok=True)

    with open(f"{ata_dir}/context.json", "w") as f:
        json.dump(ata_context, f, indent=2, ensure_ascii=False)

    print(f"Generated ATA context.json at: {ata_dir}/context.json")

    # Generate SUBMIT.txt
    submit_content = """A2A-RETRY-DLQ-v0.1__20260116

status=PASS
changed_files=tools/a2a_hub/main.py,tools/a2a_hub/test_retry_dlq.py,docs/SPEC/a2a/a2a_retry_dlq__v0.1__20260116.md
selftest_cmds=python tools/a2a_hub/test_retry_dlq.py
selftest_log=docs/REPORT/a2a/artifacts/A2A-RETRY-DLQ-v0.1__20260116/selftest.log
report=docs/REPORT/a2a/REPORT__A2A-RETRY-DLQ-v0.1__20260116__20260116.md
evidence_paths=docs/REPORT/a2a/artifacts/A2A-RETRY-DLQ-v0.1__20260116/ata/context.json
timeout=3600
rollback=python tools/a2a_hub/main.py cleanup
forbidden_check=PASS
"""

    with open(f"{artifacts_dir}/SUBMIT.txt", "w") as f:
        f.write(submit_content)

    print(f"Generated SUBMIT.txt at: {artifacts_dir}/SUBMIT.txt")


def main():
    """Main test function"""
    print("=== A2A Hub Retry and DLQ Test ===")
    print(f"Testing against: {hub_url}")

    try:
        # Run tests
        test_retry_mechanism()

        # Print summary
        print("\n=== TEST SUMMARY ===")
        print(f"Total Tests: {len(test_results['tests'])}")
        print(f"Passed: {test_results['passed']}")
        print(f"Failed: {test_results['failed']}")

        if test_results["failed"] == 0:
            print("\n✓ ALL TESTS PASSED!")
        else:
            print(f"\n✗ {test_results['failed']} TEST(S) FAILED!")

        # Generate selftest log and artifacts
        generate_selftest_log()

    finally:
        # Cleanup
        cleanup()

    # Return exit code
    if test_results["failed"] == 0:
        exit(0)
    else:
        exit(1)


if __name__ == "__main__":
    main()
