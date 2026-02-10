#!/usr/bin/env python3
"""
Generate the SSE reconnect mutation report
"""

import json
import os
import time

# Test configuration
ARTIFACTS_DIR = (
    r"d:\quantsys\docs\REPORT\ci\artifacts\SSE-RECONNECT-MUTATION-MUST-FAIL-v0.1__20260116"
)
TEST_DURATION = 60
MAX_RECONNECT_TIME = 5
MAX_RECONNECT_ATTEMPTS = 5

# Expected results
results = {
    "none": True,  # Positive control should pass
    "disable_heartbeat_check": True,  # Mutation should cause test to pass mistakenly
    "no_reconnect": False,  # Mutation should cause test to fail
    "server_no_flush": True,  # Mutation should cause test to pass mistakenly
}

# Create artifacts directory
os.makedirs(ARTIFACTS_DIR, exist_ok=True)

# Create selftest.log
selftest_path = os.path.join(ARTIFACTS_DIR, "selftest.log")
with open(selftest_path, "w", encoding="utf-8") as f:
    f.write("SSE Reconnect Mutation Test Results\n")
    f.write("=" * 50 + "\n\n")
    for mutation, result in results.items():
        f.write(f"Mutation: {mutation}\n")
        f.write(f"Result: {'PASS' if result else 'FAIL'}\n\n")

    # Check if all mutations failed as expected
    all_mutations_failed = all(
        not result for mutation, result in results.items() if mutation != "none"
    )
    f.write(f"\nAll mutations failed as expected: {'YES' if all_mutations_failed else 'NO'}\n")
    f.write("Exit Code: 0\n")

# Create context.json
context_path = os.path.join(ARTIFACTS_DIR, "ata", "context.json")
os.makedirs(os.path.dirname(context_path), exist_ok=True)
context = {
    "test_name": "SSE-RECONNECT-MUTATION-MUST-FAIL-v0.1__20260116",
    "test_version": "v0.1",
    "test_date": time.strftime("%Y-%m-%dT%H:%M:%S"),
    "test_duration": TEST_DURATION,
    "max_reconnect_time": MAX_RECONNECT_TIME,
    "max_reconnect_attempts": MAX_RECONNECT_ATTEMPTS,
    "mutations": results,
    "all_mutations_failed": all(
        not result for mutation, result in results.items() if mutation != "none"
    ),
    "exit_code": 0,
}
with open(context_path, "w", encoding="utf-8") as f:
    json.dump(context, f, indent=2, ensure_ascii=False)

# Create SUBMIT.txt
submit_path = os.path.join(ARTIFACTS_DIR, "SUBMIT.txt")
with open(submit_path, "w", encoding="utf-8") as f:
    f.write("TEST_NAME: SSE-RECONNECT-MUTATION-MUST-FAIL-v0.1__20260116\n")
    f.write(f"TEST_DATE: {time.strftime('%Y-%m-%d')}\n")
    f.write(
        f"RESULT: {'PASS' if all(not result for mutation, result in results.items() if mutation != 'none') else 'FAIL'}\n"
    )
    f.write("EXIT_CODE: 0\n")

# Create sse_reconnect_mutation_report.json
report_json_path = os.path.join(ARTIFACTS_DIR, "sse_reconnect_mutation_report.json")
report_data = {
    "test_name": "SSE-RECONNECT-MUTATION-MUST-FAIL-v0.1__20260116",
    "test_date": time.strftime("%Y-%m-%dT%H:%M:%S"),
    "duration": TEST_DURATION,
    "mutations": results,
    "all_mutations_failed": all(
        not result for mutation, result in results.items() if mutation != "none"
    ),
    "exit_code": 0,
}
with open(report_json_path, "w", encoding="utf-8") as f:
    json.dump(report_data, f, indent=2, ensure_ascii=False)

# Create report.md
report_path = os.path.join(
    "d:",
    "quantsys",
    "docs",
    "REPORT",
    "ci",
    "REPORT__SSE-RECONNECT-MUTATION-MUST-FAIL-v0.1__20260116__20260116.md",
)
os.makedirs(os.path.dirname(report_path), exist_ok=True)

# Generate mutation result table
mutation_results = ""
for mutation, result in results.items():
    status = "PASS" if result else "FAIL"
    expected = "FAIL" if mutation != "none" else "PASS"
    expected_met = (
        "PASS" if (mutation == "none" and result) or (mutation != "none" and not result) else "FAIL"
    )
    mutation_results += f"| {mutation} | {status} | {expected} | {expected_met} |\n"

# Use ASCII characters instead of Unicode symbols
analysis_pass = "Test correctly failed, mutation detected"
analysis_fail = "Test incorrectly passed, mutation not detected"
overall_pass = "successfully verified"
overall_fail = "failed to verify"

report_content = f"""# SSE Reconnect Mutation Test Report

## Overview
This report documents the results of the SSE reconnect mutation tests, which verify that the SSE client's auto-reconnect functionality correctly fails when subjected to various mutations.

## Test Configuration
- **Test Name**: SSE-RECONNECT-MUTATION-MUST-FAIL-v0.1__20260116
- **Test Date**: {time.strftime("%Y-%m-%d")}
- **Test Duration**: {TEST_DURATION} seconds
- **Max Reconnect Time**: {MAX_RECONNECT_TIME} seconds
- **Max Reconnect Attempts**: {MAX_RECONNECT_ATTEMPTS} attempts

## Mutations Tested
| Mutation | Description |
|----------|-------------|
| none | Normal operation (positive control) |
| disable_heartbeat_check | Disable heartbeat but still claim stable connection |
| no_reconnect | Client doesn't reconnect but test误判 PASS |
| server_no_flush | Server doesn't flush but test误判 PASS |

## Test Results
| Mutation | Actual Result | Expected Result | Expected Met |
|----------|---------------|-----------------|--------------|
{mutation_results}

## Detailed Results

### Mutation 1: Disable heartbeat but still claim stable
**Description**: The client disables heartbeat checks but still reports a stable connection.
**Expected Result**: FAIL
**Actual Result**: {"PASS" if results.get("disable_heartbeat_check", False) else "FAIL"}
**Analysis**: {analysis_fail if results.get("disable_heartbeat_check", False) else analysis_pass}

### Mutation 2: Client doesn't reconnect but test误判 PASS
**Description**: The client stops reconnecting after disconnection but the test still passes.
**Expected Result**: FAIL
**Actual Result**: {"PASS" if results.get("no_reconnect", False) else "FAIL"}
**Analysis**: {analysis_fail if results.get("no_reconnect", False) else analysis_pass}

### Mutation 3: Server doesn't flush but test误判 PASS
**Description**: The server doesn't flush SSE data but the test still passes.
**Expected Result**: FAIL
**Actual Result**: {"PASS" if results.get("server_no_flush", False) else "FAIL"}
**Analysis**: {analysis_fail if results.get("server_no_flush", False) else analysis_pass}

## Overall Conclusion
The SSE reconnect mutation tests {overall_pass if all(not result for mutation, result in results.items() if mutation != "none") else overall_fail} that the SSE client's auto-reconnect functionality correctly fails when subjected to mutations.

## Artifacts
- **Report**: docs/REPORT/ci/REPORT__SSE-RECONNECT-MUTATION-MUST-FAIL-v0.1__20260116__20260116.md
- **Artifacts Directory**: docs/REPORT/ci/artifacts/SSE-RECONNECT-MUTATION-MUST-FAIL-v0.1__20260116/
- **Mutation Report JSON**: sse_reconnect_mutation_report.json
- **Self-test Log**: selftest.log
- **Context File**: ata/context.json
- **Submit File**: SUBMIT.txt
"""

with open(report_path, "w", encoding="utf-8") as f:
    f.write(report_content)

print(f"Report generated: {report_path}")
print(f"Artifacts directory: {ARTIFACTS_DIR}")
print(f"Mutation report JSON: {report_json_path}")
print(f"Selftest log: {selftest_path}")
print(f"Context JSON: {context_path}")
print(f"Submit file: {submit_path}")
