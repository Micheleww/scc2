#!/usr/bin/env python3
"""
Test script for ATA Routing Rules

This script tests the routing rules functionality with various scenarios
"""

import json
import logging
import os
import subprocess
import sys

# Set up logging
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

# Path to the a2a hub main.py
main_py = os.path.join(os.path.dirname(__file__), "main.py")

# Test server URL
TEST_URL = "http://localhost:5000/api/task/routing"


def test_routing_rules():
    """Test the routing rules with various scenarios"""
    logger.info("=" * 60)
    logger.info("Running ATA Routing Rules Tests")
    logger.info("=" * 60)

    test_cases = [
        {
            "name": "Test 1: area=ci/exchange (should route to Trae)",
            "input": {
                "task_code": "TEST-EXCHANGE-001",
                "area": "ci/exchange",
                "owner_role": "Integration Engineer",
                "priority": 0,
            },
            "expected_worker_type": "Trae",
        },
        {
            "name": "Test 2: owner_role=SRE Engineer (should route to Cursor)",
            "input": {
                "task_code": "TEST-SRE-001",
                "area": "other",
                "owner_role": "SRE Engineer",
                "priority": 1,
            },
            "expected_worker_type": "Cursor",
        },
        {
            "name": "Test 3: priority>=2 (should route to Trae)",
            "input": {
                "task_code": "TEST-HIGH-PRI-001",
                "area": "other",
                "owner_role": "Engineer",
                "priority": 3,
            },
            "expected_worker_type": "Trae",
        },
        {
            "name": "Test 4: area=ci/controlplane (should route to Trae)",
            "input": {
                "task_code": "TEST-CONTROLPLANE-001",
                "area": "ci/controlplane",
                "owner_role": "CI Engineer",
                "priority": 0,
            },
            "expected_worker_type": "Trae",
        },
        {
            "name": "Test 5: task_code starts with ATA- (should route to Trae)",
            "input": {
                "task_code": "ATA-TEST-001",
                "area": "other",
                "owner_role": "Engineer",
                "priority": 0,
            },
            "expected_worker_type": "Trae",
        },
        {
            "name": "Test 6: Default rule (should route to Other)",
            "input": {
                "task_code": "TEST-DEFAULT-001",
                "area": "other",
                "owner_role": "Engineer",
                "priority": 0,
            },
            "expected_worker_type": "Other",
        },
    ]

    passed = 0
    total = len(test_cases)

    for i, test_case in enumerate(test_cases, 1):
        logger.info(f"\nTest {i}/{total}: {test_case['name']}")

        # Create a simple test script to call the routing function
        test_script = """
import sys
import json
import uuid

# Add the parent directory to path
sys.path.insert(0, r'%s')

from main import get_routing_decision, init_db

# Initialize the database
try:
    init_db()
except Exception as e:
    print(f"Database initialization error: {e}")
    sys.exit(1)

# Test data
input_data = %s
# Convert to create_task format
create_task_data = {
    'TaskCode': input_data['task_code'],
    'area': input_data['area'],
    'owner_role': input_data['owner_role'],
    'priority': input_data['priority']
}

# Debug print
print(f"Debug: create_task_data={create_task_data}")

# Call the routing function
worker_type, routing_decision, trace_id = get_routing_decision(create_task_data)

print(f"Worker Type: {worker_type}")
print(f"Routing Decision: {routing_decision}")
print(f"Trace ID: {trace_id}")

# Return exit code 0 if correct, 1 otherwise
expected_worker = '%s'
if worker_type == expected_worker:
    sys.exit(0)
else:
    sys.exit(1)
""" % (os.path.dirname(main_py), json.dumps(test_case["input"]), test_case["expected_worker_type"])

        # Write the test script to a temporary file
        temp_script = f"temp_test_routing_{i}.py"
        with open(temp_script, "w") as f:
            f.write(test_script)

        # Run the test script
        result = subprocess.run([sys.executable, temp_script], capture_output=True, text=True)

        # Print output for debugging
        if result.stdout:
            logger.info(f"  Output: {result.stdout.strip()}")
        if result.stderr:
            logger.error(f"  Stderr: {result.stderr.strip()}")

        # Check result
        if result.returncode == 0:
            logger.info("  ✅ PASS: Routing decision is correct")
            passed += 1
        else:
            logger.error(
                f"  ❌ FAIL: Expected worker_type {test_case['expected_worker_type']}, got {result.stdout.split('Worker Type: ')[1].split('\n')[0]}"
            )

        # Clean up
        os.remove(temp_script)

    logger.info("\n" + "=" * 60)
    logger.info(f"Test Results: {passed}/{total} tests passed")
    logger.info("=" * 60)

    if passed == total:
        logger.info("🎉 All tests passed!")
        logger.info("EXIT_CODE=0")
        return 0
    else:
        logger.error("💥 Some tests failed!")
        logger.info("EXIT_CODE=1")
        return 1


if __name__ == "__main__":
    sys.exit(test_routing_rules())
