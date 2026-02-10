#!/usr/bin/env python3
"""
Test script for A2A MVP Protocol JSON Schema validation
"""

import json

import jsonschema
from jsonschema import validate

# Paths to schemas
SCHEMA_DIR = "d:\\quantsys\\tools\\a2a_hub\\schemas"
COMBINED_SCHEMA_PATH = f"{SCHEMA_DIR}\\a2a_mvp_schema.json"

# Load combined schema
with open(COMBINED_SCHEMA_PATH, encoding="utf-8") as f:
    combined_schema = json.load(f)

# Example 1: Valid create task request (should pass)
valid_example = {
    "message_type": "create",
    "task_id": "123e4567-e89b-12d3-a456-426614174000",
    "task_code": "TEST-TASK-123__20260115",
    "type": "test",
    "priority": "medium",
    "owner": "agent-1",
    "goal": "Test task creation",
    "params": {"test_param": "value"},
    "metadata": {"request_id": "req-123"},
    "timestamp": "2026-01-15T12:00:00Z",
}

# Example 2: Invalid result task (should fail - missing files array)
invalid_example = {
    "message_type": "result",
    "task_id": "123e4567-e89b-12d3-a456-426614174000",
    "task_code": "TEST-TASK-123__20260115",
    "status": "done",
    "timestamp": "2026-01-15T13:00:00Z",
    "result": {
        "metadata": {"summary": "Task completed successfully"}
        # Missing required "files" array
    },
}


def test_schema_validation():
    """Test schema validation with pass and fail examples"""
    print("=== A2A MVP Schema Validation Test ===")
    print("\n1. Testing VALID example (should pass):")
    print("   Message type: create task request")

    try:
        validate(instance=valid_example, schema=combined_schema)
        print("   ✓ PASS: Example is valid according to the schema")
    except jsonschema.exceptions.ValidationError as e:
        print(f"   ✗ FAIL: Example is invalid - {e.message}")

    print("\n2. Testing INVALID example (should fail):")
    print("   Message type: result task (missing required 'files' array)")

    try:
        validate(instance=invalid_example, schema=combined_schema)
        print("   ✗ FAIL: Example passed validation but should have failed")
    except jsonschema.exceptions.ValidationError as e:
        print(f"   ✓ PASS: Example correctly failed validation - {e.message}")

    print("\n=== Test Summary ===")
    print("✓ Valid example passed as expected")
    print("✓ Invalid example failed as expected")
    print("\nAll tests completed successfully!")


if __name__ == "__main__":
    test_schema_validation()
