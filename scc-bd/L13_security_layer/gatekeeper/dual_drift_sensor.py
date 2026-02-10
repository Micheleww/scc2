#!/usr/bin/env python3
"""
Dual Consensus Drift Sensor

Runs L0 and L1 gate checks on the same input and detects drift between them.
"""

import json
import os
import sys
from datetime import datetime

from . import fast_gate


class DualDriftSensor:
    """Dual Consensus Drift Sensor"""

    def __init__(self):
        self.artifacts_dir = (
            "docs/REPORT/gatekeeper/artifacts/GATE-DUAL-DRIFT-SENSOR-v0.1__20260116"
        )
        self.drift_report_path = os.path.join(self.artifacts_dir, "dual_drift_report.json")

    def run_drift_detection(self) -> tuple[bool, dict]:
        """Run drift detection by comparing L0 and L1 results"""
        print("Running Dual Consensus Drift Sensor...")

        # Get changed files for input
        changed_files = fast_gate.get_changed_files()

        # Run L0 gate checks
        print("\n=== Running L0 Gate Checks ===")
        l0_exit, l0_result, l0_reason = fast_gate.run_l0_gate_checks()

        # Run L1 gate checks
        print("\n=== Running L1 Gate Checks ===")
        l1_exit, l1_result, l1_reason = fast_gate.run_l1_gate_checks()

        # Create detailed results
        l0_detailed = {
            "exit_code": l0_exit,
            "result": l0_result,
            "reason_code": l0_reason,
            "timestamp": datetime.utcnow().isoformat() + "Z",
        }

        l1_detailed = {
            "exit_code": l1_exit,
            "result": l1_result,
            "reason_code": l1_reason,
            "timestamp": datetime.utcnow().isoformat() + "Z",
        }

        # Detect drift
        drift_detected = False
        differences = []

        # Compare results
        if l0_result != l1_result:
            drift_detected = True
            differences.append(
                {
                    "field": "result",
                    "l0_value": l0_result,
                    "l1_value": l1_result,
                    "reason": "L0 and L1 gate results are inconsistent",
                }
            )

        # Compare reason codes
        if l0_reason != l1_reason:
            drift_detected = True
            differences.append(
                {
                    "field": "reason_code",
                    "l0_value": l0_reason,
                    "l1_value": l1_reason,
                    "reason": "L0 and L1 reason codes are different",
                }
            )

        # Compare exit codes
        if l0_exit != l1_exit:
            drift_detected = True
            differences.append(
                {
                    "field": "exit_code",
                    "l0_value": l0_exit,
                    "l1_value": l1_exit,
                    "reason": "L0 and L1 exit codes are different",
                }
            )

        # Create drift report
        drift_report = {
            "version": "v0.1",
            "timestamp_utc": datetime.utcnow().isoformat() + "Z",
            "input": {"changed_files": changed_files},
            "l0_result": l0_detailed,
            "l1_result": l1_detailed,
            "drift_detected": drift_detected,
            "differences": differences,
            "summary": {
                "total_differences": len(differences),
                "status": "DRIFT_DETECTED" if drift_detected else "CONSISTENT",
            },
        }

        # Ensure artifacts directory exists
        os.makedirs(self.artifacts_dir, exist_ok=True)

        # Write drift report
        with open(self.drift_report_path, "w", encoding="utf-8") as f:
            json.dump(drift_report, f, indent=2, ensure_ascii=False)

        print(f"\nDrift report written to: {self.drift_report_path}")

        # Print summary
        print("\n=== Drift Detection Summary ===")
        print(f"Status: {'DRIFT_DETECTED' if drift_detected else 'CONSISTENT'}")
        print(f"Total Differences: {len(differences)}")

        if differences:
            print("\nDifferences Found:")
            for diff in differences:
                print(
                    f"  - {diff['field']}: L0={diff['l0_value']}, L1={diff['l1_value']} ({diff['reason']})"
                )

        return not drift_detected, drift_report

    def run_self_test(self) -> tuple[bool, str]:
        """Run self-test to verify the drift sensor works correctly"""
        print("Running Dual Drift Sensor Self-Test...")

        # Test 1: Consistent case (should PASS)
        print("\n=== Test 1: Consistent Case ===")
        consistent_passed, _ = self.run_drift_detection()
        print(f"Test 1 Result: {'PASS' if consistent_passed else 'FAIL'}")

        # Test 2: Create intentional drift (should FAIL and generate report)
        print("\n=== Test 2: Intentional Drift Case ===")

        # Create a test file that should cause different behavior between L0 and L1
        test_dir = "test_drift_scenario"
        test_file = os.path.join(test_dir, "test_report.md")

        os.makedirs(test_dir, exist_ok=True)

        # Create a report file that will pass L0 but fail L1
        with open(test_file, "w", encoding="utf-8") as f:
            f.write(
                "# Test Report\ntitle: Test\ndate: 2026-01-16\nauthor: Test Author\nversion: v0.1\nstatus: DRAFT\n"
            )

        try:
            # Run drift detection again with the test file
            drift_passed, drift_report = self.run_drift_detection()
            print(f"Test 2 Result: {'FAIL' if not drift_passed else 'PASS'}")

            # Verify report was generated
            if os.path.exists(self.drift_report_path):
                print("✓ Drift report generated successfully")
            else:
                print("✗ Drift report not generated")
                return False, "Drift report not generated"

            # Check if drift was detected
            if drift_report["drift_detected"]:
                print("✓ Intentional drift correctly detected")
            else:
                print("✗ Intentional drift not detected")
                return False, "Intentional drift not detected"

            # Clean up test files
            os.remove(test_file)
            os.rmdir(test_dir)

            return consistent_passed and not drift_passed, "Self-test completed successfully"

        finally:
            # Clean up test files
            if os.path.exists(test_file):
                os.remove(test_file)
            if os.path.exists(test_dir):
                os.rmdir(test_dir)


def main():
    """Main function for standalone execution"""
    sensor = DualDriftSensor()
    passed, _ = sensor.run_drift_detection()
    sys.exit(0 if passed else 1)


if __name__ == "__main__":
    main()
