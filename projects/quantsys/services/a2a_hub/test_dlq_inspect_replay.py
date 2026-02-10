#!/usr/bin/env python3
"""
Test script for DLQ inspect and replay functionality

This script tests:
1. Constructing a task that fails and enters DLQ
2. GET /api/dlq/list (pagination)
3. POST /api/dlq/replay (reset to PENDING and redispatch)
4. Verifying task is replayed and can be completed
"""

import json
import os
import sys
import time
from datetime import datetime

import requests

# Configuration
BASE_URL = "http://localhost:18788/api"
TEST_ARTIFACTS_DIR = os.path.join(
    "..", "..", "docs", "REPORT", "a2a", "artifacts", "A2A-DLQ-INSPECT-REPLAY-v0.1__20260116"
)
ATA_DIR = os.path.join(TEST_ARTIFACTS_DIR, "ata")
LOG_FILE = "selftest.log"

# Test agent info
TEST_AGENT_ID = "dlq_test_agent"
TEST_OWNER_ROLE = "test_role"
TEST_CAPABILITIES = ["test_capability"]
TEST_ALLOWED_TOOLS = ["test_tool"]

# Test task info
TEST_TASK_CODE = f"TEST-DLQ-INSPECT-REPLAY-{int(time.time())}"
TEST_INSTRUCTIONS = "Test DLQ inspect and replay functionality"

# Test results
TEST_RESULTS = {
    "test_name": "A2A-DLQ-INSPECT-REPLAY-v0.1__20260116",
    "test_version": "v0.1",
    "test_date": datetime.utcnow().isoformat() + "Z",
    "results": [],
    "exit_code": 0,
}


# Initialize log file
def init_log():
    """Initialize the log file"""
    # Create artifacts directory structure
    os.makedirs(TEST_ARTIFACTS_DIR, exist_ok=True)
    os.makedirs(ATA_DIR, exist_ok=True)

    # Write initial log
    with open(LOG_FILE, "w", encoding="utf-8") as f:
        f.write(f"# {TEST_RESULTS['test_name']} Selftest Log\n")
        f.write(f"Test started: {datetime.utcnow().isoformat() + 'Z'}\n\n")


def log(message, status="INFO"):
    """Log a message to stdout and file"""
    timestamp = datetime.utcnow().isoformat() + "Z"
    log_line = f"[{timestamp}] [{status}] {message}"
    print(log_line)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(f"{log_line}\n")


def add_test_result(name, passed, message):
    """Add test result to the results list"""
    TEST_RESULTS["results"].append({"test_name": name, "passed": passed, "message": message})
    if not passed:
        TEST_RESULTS["exit_code"] = 1


def run_test(name, func):
    """Run a test function and log result"""
    log(f"=== {name} ===")
    try:
        result = func()
        if result["passed"]:
            log(f"✓ PASS: {name}")
        else:
            log(f"✗ FAIL: {name} - {result['message']}")
        add_test_result(name, result["passed"], result["message"])
        return result["passed"]
    except Exception as e:
        log(f"✗ ERROR: {name} - {str(e)}")
        add_test_result(name, False, str(e))
        return False


def register_test_agent():
    """Register a test agent"""
    try:
        response = requests.post(
            f"{BASE_URL}/api/agent/register",
            json={
                "agent_id": TEST_AGENT_ID,
                "owner_role": TEST_OWNER_ROLE,
                "capabilities": TEST_CAPABILITIES,
                "allowed_tools": TEST_ALLOWED_TOOLS,
                "capacity": 5,
                "available_capacity": 5,
            },
        )
        response_data = response.json()
        if response.status_code == 200 and response_data["success"]:
            return {"passed": True, "message": "Register test agent"}
        else:
            return {
                "passed": False,
                "message": f"Failed to register agent: {response_data.get('error')}",
            }
    except Exception as e:
        return {"passed": False, "message": f"Exception registering agent: {str(e)}"}


def create_test_task():
    """Create a test task that will fail"""
    try:
        response = requests.post(
            f"{BASE_URL}/api/task/create",
            json={
                "TaskCode": TEST_TASK_CODE,
                "instructions": TEST_INSTRUCTIONS,
                "owner_role": TEST_OWNER_ROLE,
                "max_retries": 1,  # Will enter DLQ after 2 failures
                "priority": 0,
            },
        )
        response_data = response.json()
        if response.status_code == 200 and response_data["success"]:
            log(f"Created task: {response_data.get('task_id')} with max_retries=1")
            return {"passed": True, "message": "Create test task"}
        else:
            return {
                "passed": False,
                "message": f"Failed to create task: {response_data.get('error')}",
            }
    except Exception as e:
        return {"passed": False, "message": f"Exception creating task: {str(e)}"}


def submit_fail_result(task_code, retry_attempt):
    """Submit a FAIL result for a task"""
    try:
        response = requests.post(
            f"{BASE_URL}/api/task/result",
            json={
                "task_code": task_code,
                "status": "FAIL",
                "reason_code": "TEST_FAILURE",
                "last_error": f"Test failure #{retry_attempt}",
            },
        )
        response_data = response.json()
        if response.status_code == 200:
            return {"passed": True, "message": f"Submit FAIL result ({retry_attempt}st attempt)"}
        else:
            return {
                "passed": False,
                "message": f"Failed to submit FAIL result: {response_data.get('error')}",
            }
    except Exception as e:
        return {"passed": False, "message": f"Exception submitting FAIL result: {str(e)}"}


def check_task_status(task_code, expected_status):
    """Check task status"""
    try:
        response = requests.get(f"{BASE_URL}/api/task/status", params={"task_code": task_code})
        response_data = response.json()
        if response.status_code == 200 and response_data["success"]:
            current_status = response_data["task"]["status"]
            log(f"Current task status: {current_status}, Expected: {expected_status}")
            if current_status == expected_status:
                return {"passed": True, "message": f"Check task status={expected_status}"}
            else:
                return {
                    "passed": False,
                    "message": f"Task status mismatch: expected {expected_status}, got {current_status}",
                }
        else:
            return {
                "passed": False,
                "message": f"Failed to get task status: {response_data.get('error')}",
            }
    except Exception as e:
        return {"passed": False, "message": f"Exception getting task status: {str(e)}"}


def check_dlq_entry_exists(task_code):
    """Check if DLQ entry exists"""
    try:
        response = requests.get(f"{BASE_URL}/api/dlq/task/{task_code}")
        response_data = response.json()
        if response.status_code == 200 and response_data["success"]:
            log(f"Found DLQ entry: {response_data['dlq_entry']['id']}")
            return {
                "passed": True,
                "message": "Check DLQ entry exists",
                "dlq_id": response_data["dlq_entry"]["id"],
            }
        else:
            return {
                "passed": False,
                "message": f"DLQ entry not found: {response_data.get('error')}",
            }
    except Exception as e:
        return {"passed": False, "message": f"Exception checking DLQ entry: {str(e)}"}


def test_dlq_list_endpoint():
    """Test GET /api/dlq/list endpoint with pagination"""
    try:
        # Test with default pagination
        response = requests.get(f"{BASE_URL}/api/dlq/list")
        log(f"GET /api/dlq/list response status: {response.status_code}")
        log(f"GET /api/dlq/list response text: {response.text}")
        response_data = response.json()
        if response.status_code == 200 and response_data["success"]:
            log(f"GET /api/dlq/list: Found {len(response_data['dlq_entries'])} entries")
            log(
                f"Pagination info: page={response_data['pagination']['page']}, page_size={response_data['pagination']['page_size']}"
            )
            return {"passed": True, "message": "Test GET /api/dlq/list endpoint"}
        else:
            return {
                "passed": False,
                "message": f"Failed GET /api/dlq/list: {response_data.get('error', 'Unknown error')}",
            }
    except json.JSONDecodeError as e:
        log(f"JSON decode error: {e}, response text: {response.text}")
        return {"passed": False, "message": f"JSON decode error in GET /api/dlq/list: {str(e)}"}
    except Exception as e:
        return {"passed": False, "message": f"Exception in GET /api/dlq/list: {str(e)}"}


def test_dlq_list_pagination():
    """Test GET /api/dlq/list with custom pagination"""
    try:
        # Test with custom pagination
        response = requests.get(f"{BASE_URL}/api/dlq/list", params={"page": 1, "page_size": 2})
        log(f"GET /api/dlq/list?page=1&page_size=2 response status: {response.status_code}")
        log(f"GET /api/dlq/list?page=1&page_size=2 response text: {response.text}")
        response_data = response.json()
        if response.status_code == 200 and response_data["success"]:
            log(
                f"GET /api/dlq/list?page=1&page_size=2: Found {len(response_data['dlq_entries'])} entries"
            )
            return {"passed": True, "message": "Test GET /api/dlq/list with custom pagination"}
        else:
            return {
                "passed": False,
                "message": f"Failed GET /api/dlq/list with pagination: {response_data.get('error', 'Unknown error')}",
            }
    except json.JSONDecodeError as e:
        log(f"JSON decode error: {e}, response text: {response.text}")
        return {
            "passed": False,
            "message": f"JSON decode error in GET /api/dlq/list pagination: {str(e)}",
        }
    except Exception as e:
        return {"passed": False, "message": f"Exception in GET /api/dlq/list pagination: {str(e)}"}


def test_dlq_replay(dlq_id, task_code):
    """Test POST /api/dlq/replay endpoint"""
    try:
        log(f"Attempting to replay DLQ entry: {dlq_id}")
        log(f"Task code: {task_code}")

        payload = {"dlq_id": dlq_id, "who": "test_user", "why": "Testing DLQ replay functionality"}
        log(f"Request payload: {json.dumps(payload)}")

        response = requests.post(f"{BASE_URL}/api/dlq/replay", json=payload)
        log(f"POST /api/dlq/replay response status: {response.status_code}")
        log(f"POST /api/dlq/replay response headers: {dict(response.headers)}")
        log(f"POST /api/dlq/replay response text: {response.text}")

        response_data = response.json()
        if response.status_code == 200 and response_data["success"]:
            log(f"Replayed DLQ entry: {dlq_id}")
            if "audit" in response_data:
                log(
                    f"Audit info: who={response_data['audit']['who']}, when={response_data['audit']['when']}, why={response_data['audit']['why']}"
                )
            return {
                "passed": True,
                "message": "Test POST /api/dlq/replay endpoint",
                "task_code": task_code,
            }
        else:
            return {
                "passed": False,
                "message": f"Failed POST /api/dlq/replay: {response_data.get('error', 'Unknown error')}",
            }
    except json.JSONDecodeError as e:
        log(f"JSON decode error: {e}, response text: {response.text}")
        return {"passed": False, "message": f"JSON decode error in POST /api/dlq/replay: {str(e)}"}
    except Exception as e:
        log(f"Exception in POST /api/dlq/replay: {type(e).__name__}: {str(e)}")
        import traceback

        log(f"Traceback: {traceback.format_exc()}")
        return {"passed": False, "message": f"Exception in POST /api/dlq/replay: {str(e)}"}


def test_task_replayed(task_code):
    """Test that the replayed task is now PENDING"""
    try:
        # Wait a bit for the task to be updated
        time.sleep(1)
        response = requests.get(f"{BASE_URL}/api/task/status", params={"task_code": task_code})
        response_data = response.json()
        if response.status_code == 200 and response_data["success"]:
            current_status = response_data["task"]["status"]
            current_retry_count = response_data["task"]["retry_count"]
            log(f"Replayed task status: {current_status}, retry_count: {current_retry_count}")
            if current_status == "PENDING" and current_retry_count == 0:
                return {"passed": True, "message": "Test task replayed correctly"}
            else:
                return {
                    "passed": False,
                    "message": f"Task not replayed correctly: status={current_status}, retry_count={current_retry_count}",
                }
        else:
            return {
                "passed": False,
                "message": f"Failed to check replayed task: {response_data.get('error')}",
            }
    except Exception as e:
        return {"passed": False, "message": f"Exception checking replayed task: {str(e)}"}


def complete_replayed_task(task_code):
    """Complete the replayed task"""
    try:
        response = requests.post(
            f"{BASE_URL}/api/task/result",
            json={
                "task_code": task_code,
                "status": "DONE",
                "result": {"message": "Task completed successfully after DLQ replay"},
            },
        )
        response_data = response.json()
        if response.status_code == 200:
            # Check if task is now DONE
            time.sleep(1)
            status_response = requests.get(
                f"{BASE_URL}/api/task/status", params={"task_code": task_code}
            )
            status_data = status_response.json()
            if status_data["task"]["status"] == "DONE":
                return {"passed": True, "message": "Complete replayed task"}
            else:
                return {
                    "passed": False,
                    "message": f"Task not completed: {status_data['task']['status']}",
                }
        else:
            return {
                "passed": False,
                "message": f"Failed to complete task: {response_data.get('error')}",
            }
    except Exception as e:
        return {"passed": False, "message": f"Exception completing task: {str(e)}"}


def deregister_test_agent():
    """Deregister the test agent"""
    try:
        response = requests.delete(f"{BASE_URL}/api/agent/{TEST_AGENT_ID}")
        response_data = response.json()
        if response.status_code == 200 and response_data["success"]:
            return {"passed": True, "message": "Deregister test agent"}
        else:
            return {
                "passed": False,
                "message": f"Failed to deregister agent: {response_data.get('error')}",
            }
    except Exception as e:
        return {"passed": False, "message": f"Exception deregistering agent: {str(e)}"}


def generate_artifacts():
    """Generate test artifacts"""
    # Create directories if they don't exist
    os.makedirs(TEST_ARTIFACTS_DIR, exist_ok=True)
    os.makedirs(ATA_DIR, exist_ok=True)

    # Write selftest.log to artifacts
    if os.path.exists(LOG_FILE):
        import shutil

        shutil.copy2(LOG_FILE, os.path.join(TEST_ARTIFACTS_DIR, "selftest.log"))

    # Write context.json
    context = {
        "test_name": TEST_RESULTS["test_name"],
        "test_version": TEST_RESULTS["test_version"],
        "test_date": TEST_RESULTS["test_date"],
        "result": "PASS" if TEST_RESULTS["exit_code"] == 0 else "FAIL",
        "exit_code": TEST_RESULTS["exit_code"],
        "total_tests": len(TEST_RESULTS["results"]),
        "passed_tests": sum(1 for r in TEST_RESULTS["results"] if r["passed"]),
        "failed_tests": sum(1 for r in TEST_RESULTS["results"] if not r["passed"]),
        "test_results": TEST_RESULTS["results"],
    }

    with open(os.path.join(ATA_DIR, "context.json"), "w", encoding="utf-8") as f:
        json.dump(context, f, indent=2, ensure_ascii=False)

    # Write SUBMIT.txt
    submit_content = f"""
TEST_NAME: {TEST_RESULTS["test_name"]}
TEST_DATE: {datetime.now().strftime("%Y-%m-%d")}
RESULT: {"PASS" if TEST_RESULTS["exit_code"] == 0 else "FAIL"}
EXIT_CODE: {TEST_RESULTS["exit_code"]}
"""

    with open(os.path.join(TEST_ARTIFACTS_DIR, "SUBMIT.txt"), "w", encoding="utf-8") as f:
        f.write(submit_content.strip())

    log(f"Generated selftest.log at: {os.path.join(TEST_ARTIFACTS_DIR, 'selftest.log')}")
    log(f"Generated ATA context.json at: {os.path.join(ATA_DIR, 'context.json')}")
    log(f"Generated SUBMIT.txt at: {os.path.join(TEST_ARTIFACTS_DIR, 'SUBMIT.txt')}")


def main():
    """Main test function"""
    log("=== A2A Hub DLQ Inspect and Replay Test ===")
    log(f"Testing against: {BASE_URL}")

    # Register test agent
    run_test("Register test agent", register_test_agent)

    # Create test task with max_retries=1
    run_test("Create test task with max_retries=1", create_test_task)

    # Submit FAIL result (1st attempt)
    run_test("Submit FAIL result (1st attempt)", lambda: submit_fail_result(TEST_TASK_CODE, 1))

    # Check task status=PENDING after first FAIL
    run_test(
        "Check task status=PENDING after first FAIL",
        lambda: check_task_status(TEST_TASK_CODE, "PENDING"),
    )

    # Submit FAIL result (2nd attempt)
    run_test("Submit FAIL result (2nd attempt)", lambda: submit_fail_result(TEST_TASK_CODE, 2))

    # Check task status=DLQ after max retries
    run_test(
        "Check task status=DLQ after max retries", lambda: check_task_status(TEST_TASK_CODE, "DLQ")
    )

    # Check DLQ entry exists
    dlq_check_result = run_test(
        "Check DLQ entry exists", lambda: check_dlq_entry_exists(TEST_TASK_CODE)
    )

    # Test GET /api/dlq/list endpoint
    run_test("Test GET /api/dlq/list endpoint", test_dlq_list_endpoint)

    # Test GET /api/dlq/list with custom pagination
    run_test("Test GET /api/dlq/list with custom pagination", test_dlq_list_pagination)

    # Test POST /api/dlq/replay endpoint
    dlq_id = None
    if dlq_check_result:
        for result in TEST_RESULTS["results"]:
            if result["test_name"] == "Check DLQ entry exists" and result["passed"]:
                # Get dlq_id from the function result
                # In the run_test function, we store the function's return value in the result dict
                # So we need to look for the dlq_id in the function result, not in the test result
                # For this test, we'll directly get the dlq_id by making the request again
                try:
                    response = requests.get(f"{BASE_URL}/api/dlq/task/{TEST_TASK_CODE}")
                    response_data = response.json()
                    if response.status_code == 200 and response_data["success"]:
                        dlq_id = response_data["dlq_entry"]["id"]
                        break
                except Exception as e:
                    log(f"Error getting dlq_id: {e}")
                    continue

    if dlq_id:
        run_test(
            "Test POST /api/dlq/replay endpoint", lambda: test_dlq_replay(dlq_id, TEST_TASK_CODE)
        )

        # Test that the replayed task is now PENDING
        run_test("Test task replayed correctly", lambda: test_task_replayed(TEST_TASK_CODE))

        # Complete the replayed task
        run_test("Complete replayed task", lambda: complete_replayed_task(TEST_TASK_CODE))
    else:
        log("✗ SKIP: Test POST /api/dlq/replay - DLQ entry not found")
        add_test_result("Test POST /api/dlq/replay endpoint", False, "DLQ entry not found")

    # Deregister test agent
    run_test("Deregister test agent", deregister_test_agent)

    # Generate artifacts
    generate_artifacts()

    # Print test summary
    log("\n=== TEST SUMMARY ===")
    log(f"Total Tests: {len(TEST_RESULTS['results'])}")
    log(f"Passed: {sum(1 for r in TEST_RESULTS['results'] if r['passed'])}")
    log(f"Failed: {sum(1 for r in TEST_RESULTS['results'] if not r['passed'])}")

    if TEST_RESULTS["exit_code"] == 0:
        log("\n✓ ALL TESTS PASSED!")
    else:
        log("\n✗ SOME TESTS FAILED!")

    sys.exit(TEST_RESULTS["exit_code"])


if __name__ == "__main__":
    init_log()
    main()
