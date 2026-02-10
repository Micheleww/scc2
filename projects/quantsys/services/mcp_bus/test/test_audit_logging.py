#!/usr/bin/env python3
"""
Test script for MCP access audit logging

This script tests the audit logging functionality by calling 3 different tools
and verifying that the logs are generated correctly in JSONL format with all
required fields and proper sanitization.
"""

import hashlib
import json
import os
import time
from datetime import datetime

import requests

# Configuration
BASE_URL = "http://localhost:18788/"
MCP_TOKEN = os.getenv("MCP_BUS_TOKEN", "test_token")

# Test data
TEST_DATE = datetime.now().strftime("%Y-%m-%d")
TEST_TASK_CODE = "TEST-20260117-001"
TEST_SOURCE = "test_script"
TEST_TEXT = "Test content for audit logging verification"


def generate_trace_id():
    """Generate a unique trace ID for testing"""
    return hashlib.md5(str(time.time()).encode()).hexdigest()


def call_mcp_tool(tool_name, arguments, trace_id=None):
    """Call an MCP tool using the JSON-RPC endpoint"""
    url = f"{BASE_URL}/mcp"
    headers = {
        "Authorization": f"Bearer {MCP_TOKEN}",
        "Content-Type": "application/json",
        "x-trace-id": trace_id or generate_trace_id(),
    }
    payload = {
        "jsonrpc": "2.0",
        "method": "tools/call",
        "params": {"name": tool_name, "arguments": arguments},
    }

    response = requests.post(url, headers=headers, json=payload)
    return response.json()


def call_rest_api(endpoint, method="post", data=None, trace_id=None):
    """Call an MCP tool using the REST API endpoint"""
    url = f"{BASE_URL}/api/{endpoint}"
    headers = {
        "Authorization": f"Bearer {MCP_TOKEN}",
        "Content-Type": "application/json",
        "x-trace-id": trace_id or generate_trace_id(),
    }

    if method == "post":
        response = requests.post(url, headers=headers, json=data)
    else:
        response = requests.get(url, headers=headers)

    return response.json()


def check_log_file(log_path):
    """Check that the log file contains valid JSONL entries with all required fields"""
    print(f"Checking log file: {log_path}")

    if not os.path.exists(log_path):
        print(f"ERROR: Log file {log_path} does not exist")
        return False

    required_fields = [
        "timestamp",
        "tool",
        "client_hash",
        "scope",
        "trace_id",
        "result",
        "reason_code",
        "latency_ms",
    ]

    log_entries = []
    with open(log_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    entry = json.loads(line)
                    log_entries.append(entry)
                except json.JSONDecodeError as e:
                    print(f"ERROR: Invalid JSON in log file: {e}")
                    return False

    if not log_entries:
        print("ERROR: No log entries found")
        return False

    print(f"Found {len(log_entries)} log entries")

    # Check each entry has all required fields
    for i, entry in enumerate(log_entries):
        missing_fields = [field for field in required_fields if field not in entry]
        if missing_fields:
            print(f"ERROR: Log entry {i} missing required fields: {missing_fields}")
            return False

        # Check sensitive information is sanitized
        if isinstance(entry.get("params_summary"), str):
            if any(
                sensitive in entry["params_summary"] for sensitive in ["auth", "token", "secret"]
            ):
                if "******" not in entry["params_summary"]:
                    print(f"ERROR: Log entry {i} contains unsanitized sensitive information")
                    return False

    print("✓ All log entries have required fields")
    print("✓ Sensitive information is properly sanitized")
    return True


def main():
    """Main test function"""
    print("=== MCP Access Audit Logging Test ===")

    # Get today's log file path
    today = datetime.now().strftime("%Y-%m-%d")
    log_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "docs",
        "LOG",
        "mcp_bus",
        f"{today}.jsonl",
    )

    # Clear existing log file for clean test
    if os.path.exists(log_path):
        os.remove(log_path)
        print(f"Cleared existing log file: {log_path}")

    # Test 1: Call inbox_append tool
    print("\n1. Testing inbox_append tool...")
    result = call_mcp_tool(
        "inbox_append",
        {"date": TEST_DATE, "task_code": TEST_TASK_CODE, "source": TEST_SOURCE, "text": TEST_TEXT},
    )
    print(f"Result: {result.get('result', {}).get('content', [{}])[0].get('text', 'No content')}")

    # Test 2: Call inbox_tail tool
    print("\n2. Testing inbox_tail tool...")
    result = call_mcp_tool("inbox_tail", {"date": TEST_DATE, "n": 10})
    print(f"Result: {result.get('result', {}).get('content', [{}])[0].get('text', 'No content')}")

    # Test 3: Call board_get tool via REST API
    print("\n3. Testing board_get tool via REST API...")
    result = call_rest_api("board_get", method="get")
    print(f"Result: {'Success' if result.get('success') else 'Failed'}")

    # Wait for logs to be written
    time.sleep(1)

    # Check log file
    print("\n=== Verifying Logs ===")
    if check_log_file(log_path):
        print("\n✅ All tests passed! Audit logging is working correctly.")
        return 0
    else:
        print("\n❌ Tests failed! Audit logging has issues.")
        return 1


if __name__ == "__main__":
    exit_code = main()
    exit(exit_code)
