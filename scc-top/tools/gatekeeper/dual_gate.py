#!/usr/bin/env python3
"""
Dual Gate Runner with Consensus Engine

This module provides the entry point for the dual gate checks with consensus engine.
"""

import json
import sys
from datetime import datetime

# Import the fast_gate module
from . import fast_gate


class GateOutput:
    """Represents the output of a gate check"""

    def __init__(
        self, result: str, reason_code: str, violations: list[dict], evidence_paths: list[str]
    ):
        self.result = result
        self.pass_fail = "PASS" if result == "GATE_PASS" else "FAIL"
        self.reason_code = reason_code
        self.violations = violations
        self.evidence_paths = evidence_paths
        self.timestamp = datetime.utcnow().isoformat() + "Z"

    def to_dict(self) -> dict:
        """Convert to dictionary"""
        return {
            "result": self.result,
            "pass_fail": self.pass_fail,
            "reason_code": self.reason_code,
            "violations": self.violations,
            "evidence_paths": self.evidence_paths,
            "timestamp": self.timestamp,
        }

    def to_json(self) -> str:
        """Convert to JSON string"""
        return json.dumps(self.to_dict(), indent=2, ensure_ascii=False)


def parse_gate_output(output: str) -> GateOutput:
    """Parse gate check output and extract result, reason_code, violations, and evidence_paths"""
    result = "GATE_FAIL"
    reason_code = "UNKNOWN"
    violations = []
    evidence_paths = []

    # Extract result and reason code
    for line in output.splitlines():
        if line.startswith("RESULT="):
            result_val = line.split("=")[1]
            result = "GATE_PASS" if result_val == "PASS" else "GATE_FAIL"
        elif line.startswith("REASON_CODE="):
            reason_code = line.split("=")[1]
        elif "[ERROR]" in line:
            violations.append({"message": line.strip()})
        elif "evidence_path" in line:
            # Extract evidence paths from error messages
            if "evidence_path" in line:
                parts = line.split("evidence_path")
                if len(parts) > 1:
                    path_part = parts[1].strip()
                    if path_part.startswith("s:"):
                        path = path_part[2:].strip()
                        if path not in evidence_paths:
                            evidence_paths.append(path)

    return GateOutput(result, reason_code, violations, evidence_paths)


def run_consensus_engine(l0_output: GateOutput, l1_output: GateOutput) -> tuple[bool, dict]:
    """Run consensus engine to determine overall result"""
    # Check if results are consistent
    if l0_output.pass_fail != l1_output.pass_fail:
        # Results are inconsistent, return FAIL
        consensus_result = "GATE_FAIL"
        consensus_reason = "DUAL_GATE_INCONSISTENCY"
        consensus_details = {
            "inconsistency_detected": True,
            "l0_result": l0_output.to_dict(),
            "l1_result": l1_output.to_dict(),
            "difference": {
                "result": f"L0: {l0_output.pass_fail}, L1: {l1_output.pass_fail}",
                "reason_code": f"L0: {l0_output.reason_code}, L1: {l1_output.reason_code}",
            },
        }
    else:
        # Results are consistent, return the common result
        consensus_result = l0_output.result
        consensus_reason = (
            l0_output.reason_code if l0_output.result == "GATE_FAIL" else l1_output.reason_code
        )
        consensus_details = {
            "inconsistency_detected": False,
            "l0_result": l0_output.to_dict(),
            "l1_result": l1_output.to_dict(),
            "common_result": l0_output.pass_fail,
        }

    # Create overall output
    overall_output = {
        "consensus_result": consensus_result,
        "consensus_reason": consensus_reason,
        "consensus_details": consensus_details,
        "timestamp": datetime.utcnow().isoformat() + "Z",
    }

    return consensus_result == "GATE_PASS", overall_output


def run_dual_gate_checks():
    """Run dual gate checks with consensus engine"""
    print("Running dual gate checks with consensus engine...")

    # Run L0 checks
    print("\n=== Running L0 Checks ===")
    l0_exit, l0_result, l0_reason = fast_gate.run_l0_gate_checks()

    # Run L1 checks
    print("\n=== Running L1 Checks ===")
    l1_exit, l1_result, l1_reason = fast_gate.run_l1_gate_checks()

    # Create GateOutput objects
    l0_output = GateOutput(l0_result, l0_reason, [], [])
    l1_output = GateOutput(l1_result, l1_reason, [], [])

    # Run consensus engine
    print("\n=== Running Consensus Engine ===")
    consensus_passed, consensus_output = run_consensus_engine(l0_output, l1_output)

    # Print results
    print("\n=== Gate Results ===")
    print(f"L0 Result: {l0_output.result} (Reason: {l0_output.reason_code})")
    print(f"L1 Result: {l1_output.result} (Reason: {l1_output.reason_code})")
    print(
        f"Consensus Result: {consensus_output['consensus_result']} (Reason: {consensus_output['consensus_reason']})"
    )

    # Print inconsistency details if detected
    if consensus_output["consensus_details"]["inconsistency_detected"]:
        print("\n=== Inconsistency Details ===")
        diff = consensus_output["consensus_details"]["difference"]
        print(f"Result Difference: {diff['result']}")
        print(f"Reason Code Difference: {diff['reason_code']}")

    # Print JSON output for each gate
    print("\n=== L0 JSON Output ===")
    print(l0_output.to_json())

    print("\n=== L1 JSON Output ===")
    print(l1_output.to_json())

    print("\n=== Consensus JSON Output ===")
    print(json.dumps(consensus_output, indent=2, ensure_ascii=False))

    # Write output files
    with open("l0_gate_output.json", "w", encoding="utf-8") as f:
        f.write(l0_output.to_json())

    with open("l1_gate_output.json", "w", encoding="utf-8") as f:
        f.write(l1_output.to_json())

    with open("consensus_output.json", "w", encoding="utf-8") as f:
        f.write(json.dumps(consensus_output, indent=2, ensure_ascii=False))

    # Return exit code
    return 0 if consensus_passed else 1


def main():
    """Main function to run dual gate checks with consensus engine"""
    exit_code = run_dual_gate_checks()
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
