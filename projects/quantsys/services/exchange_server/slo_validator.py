#!/usr/bin/env python3
"""
SLO Alerts Local Validator

This script validates SLO requirements based on Prometheus metrics snapshot.
Input: Metrics snapshot in Prometheus format
Output: JSON with alert status and reason_code

SLO Requirements:
- SSE disconnection rate: < 10%
- Reconnect time p95: < 1000ms
- 401/429 ratio: < 5%
- gate_fail ratio: < 5%
"""

import json
import re
import sys
from typing import Any


def parse_prometheus_metrics(metrics_text: str) -> dict[str, Any]:
    """Parse Prometheus metrics text into a structured dictionary.

    Args:
        metrics_text: Prometheus format metrics text

    Returns:
        Structured dictionary with metrics data
    """
    metrics = {}

    # Split text into lines and process each line
    for line in metrics_text.splitlines():
        line = line.strip()

        # Skip comments and empty lines
        if not line or line.startswith("#"):
            continue

        # Parse metric line
        # Example: exchange_requests_total 100
        # Example: exchange_latency_ms_bucket{le="10"} 50

        # Extract metric name, labels, and value
        match = re.match(r"([a-zA-Z_][a-zA-Z0-9_]*)(?:\{([^\}]+)\})?\s+([0-9.]+)", line)
        if match:
            metric_name = match.group(1)
            labels_str = match.group(2)
            value = float(match.group(3))

            # Parse labels if present
            labels = {}
            if labels_str:
                label_pairs = labels_str.split(",")
                for pair in label_pairs:
                    key, val = pair.strip().split("=", 1)
                    # Remove quotes from value
                    val = val.strip('"')
                    labels[key] = val

            # Add to metrics dictionary
            if metric_name not in metrics:
                metrics[metric_name] = []

            metrics[metric_name].append({"labels": labels, "value": value})

    return metrics


def calculate_sse_disconnection_rate(metrics: dict[str, Any]) -> float:
    """Calculate SSE disconnection rate.

    Formula: (reconnect_attempts_total - reconnect_success_total) / reconnect_attempts_total * 100

    Args:
        metrics: Parsed metrics dictionary

    Returns:
        Disconnection rate as percentage
    """
    try:
        reconnect_attempts = sum(
            item["value"] for item in metrics.get("exchange_reconnect_attempts_total", [])
        )
        reconnect_success = sum(
            item["value"] for item in metrics.get("exchange_reconnect_success_total", [])
        )

        if reconnect_attempts == 0:
            return 0.0

        return ((reconnect_attempts - reconnect_success) / reconnect_attempts) * 100
    except (KeyError, TypeError, ZeroDivisionError):
        return 0.0


def calculate_reconnect_time_p95(metrics: dict[str, Any]) -> float:
    """Calculate reconnect time p95 from histogram buckets.

    Args:
        metrics: Parsed metrics dictionary

    Returns:
        p95 reconnect time in milliseconds
    """
    try:
        # Get all reconnect time buckets
        buckets = []
        for item in metrics.get("exchange_reconnect_time_ms_bucket", []):
            if "le" in item["labels"]:
                le = item["labels"]["le"]
                buckets.append((float(le) if le != "+Inf" else float("inf"), item["value"]))

        # Sort buckets by le value
        buckets.sort(key=lambda x: x[0])

        # Get total count from the +Inf bucket (histogram buckets are cumulative)
        total_count = 0.0
        for le, count in buckets:
            if le == float("inf"):
                total_count = count
                break

        if total_count == 0:
            return 0.0

        # Find p95 bucket
        p95_threshold = total_count * 0.95

        for le, count in buckets:
            if le == float("inf"):
                continue
            if count >= p95_threshold:
                return le

        # If p95 not found in buckets, return max bucket (shouldn't happen)
        return buckets[-2][0] if len(buckets) >= 2 else 0.0
    except (KeyError, TypeError, IndexError):
        return 0.0


def calculate_error_ratio(metrics: dict[str, Any]) -> float:
    """Calculate ratio of 401/429 errors to total requests.

    Note: We're using auth_fail_total as a proxy for 401/429 errors

    Args:
        metrics: Parsed metrics dictionary

    Returns:
        Error ratio as percentage
    """
    try:
        total_requests = sum(item["value"] for item in metrics.get("exchange_requests_total", []))
        auth_fail = sum(item["value"] for item in metrics.get("exchange_auth_fail_total", []))

        if total_requests == 0:
            return 0.0

        return (auth_fail / total_requests) * 100
    except (KeyError, TypeError, ZeroDivisionError):
        return 0.0


def calculate_gate_fail_ratio(metrics: dict[str, Any]) -> float:
    """Calculate ratio of gate failures to total requests.

    Args:
        metrics: Parsed metrics dictionary

    Returns:
        Gate fail ratio as percentage
    """
    try:
        total_requests = sum(item["value"] for item in metrics.get("exchange_requests_total", []))
        gate_fail = sum(item["value"] for item in metrics.get("exchange_gate_fail_total", []))

        if total_requests == 0:
            return 0.0

        return (gate_fail / total_requests) * 100
    except (KeyError, TypeError, ZeroDivisionError):
        return 0.0


def validate_slo(metrics: dict[str, Any]) -> dict[str, Any]:
    """Validate SLO requirements against metrics.

    Args:
        metrics: Parsed metrics dictionary

    Returns:
        JSON-serializable dictionary with alert status and reason_code
    """
    # Calculate all SLO metrics
    disconnection_rate = calculate_sse_disconnection_rate(metrics)
    reconnect_time_p95 = calculate_reconnect_time_p95(metrics)
    error_ratio = calculate_error_ratio(metrics)
    gate_fail_ratio = calculate_gate_fail_ratio(metrics)

    # Define SLO thresholds
    thresholds = {
        "disconnection_rate": 10.0,  # < 10%
        "reconnect_time_p95": 1000.0,  # < 1000ms
        "error_ratio": 5.0,  # < 5%
        "gate_fail_ratio": 5.0,  # < 5%
    }

    # Check SLO requirements
    violations = []

    if disconnection_rate >= thresholds["disconnection_rate"]:
        violations.append(
            {
                "metric": "sse_disconnection_rate",
                "value": disconnection_rate,
                "threshold": thresholds["disconnection_rate"],
                "reason_code": "SSE_DISCONNECTION_RATE_EXCEEDED",
            }
        )

    if reconnect_time_p95 >= thresholds["reconnect_time_p95"]:
        violations.append(
            {
                "metric": "reconnect_time_p95",
                "value": reconnect_time_p95,
                "threshold": thresholds["reconnect_time_p95"],
                "reason_code": "RECONNECT_TIME_P95_EXCEEDED",
            }
        )

    if error_ratio >= thresholds["error_ratio"]:
        violations.append(
            {
                "metric": "error_ratio",
                "value": error_ratio,
                "threshold": thresholds["error_ratio"],
                "reason_code": "ERROR_RATIO_EXCEEDED",
            }
        )

    if gate_fail_ratio >= thresholds["gate_fail_ratio"]:
        violations.append(
            {
                "metric": "gate_fail_ratio",
                "value": gate_fail_ratio,
                "threshold": thresholds["gate_fail_ratio"],
                "reason_code": "GATE_FAIL_RATIO_EXCEEDED",
            }
        )

    # Generate result
    if violations:
        return {
            "alert": True,
            "reason_code": violations[0]["reason_code"],  # Return first violation reason
            "violations": violations,
            "details": {
                "sse_disconnection_rate": disconnection_rate,
                "reconnect_time_p95": reconnect_time_p95,
                "error_ratio": error_ratio,
                "gate_fail_ratio": gate_fail_ratio,
                "thresholds": thresholds,
            },
        }
    else:
        return {
            "alert": False,
            "reason_code": "SLO_COMPLIANT",
            "violations": [],
            "details": {
                "sse_disconnection_rate": disconnection_rate,
                "reconnect_time_p95": reconnect_time_p95,
                "error_ratio": error_ratio,
                "gate_fail_ratio": gate_fail_ratio,
                "thresholds": thresholds,
            },
        }


def main():
    """Main function to run the SLO validator.

    Reads metrics from stdin, validates SLO, and outputs JSON result.
    """
    # Read metrics from stdin
    if len(sys.argv) > 1 and sys.argv[1] == "--test":
        # Run test mode with sample data
        run_test()
        return

    metrics_text = sys.stdin.read()
    if not metrics_text:
        print(
            json.dumps(
                {
                    "alert": False,
                    "reason_code": "NO_METRICS_PROVIDED",
                    "violations": [],
                    "details": {},
                }
            )
        )
        sys.exit(0)

    # Parse metrics
    parsed_metrics = parse_prometheus_metrics(metrics_text)

    # Validate SLO
    result = validate_slo(parsed_metrics)

    # Output JSON result
    print(json.dumps(result, indent=2))


def run_test():
    """Run test with sample metrics data (normal and abnormal)."""
    # Sample 1: Normal metrics (should pass SLO)
    normal_metrics = """# HELP exchange_requests_total Total number of requests
# TYPE exchange_requests_total counter
exchange_requests_total 1000

# HELP exchange_auth_fail_total Total number of authentication failures
# TYPE exchange_auth_fail_total counter
exchange_auth_fail_total 20

# HELP exchange_gate_fail_total Total number of gate check failures
# TYPE exchange_gate_fail_total counter
exchange_gate_fail_total 30

# HELP exchange_sse_connections Current number of SSE connections
# TYPE exchange_sse_connections gauge
exchange_sse_connections 5

# HELP exchange_reconnect_attempts_total Total number of reconnect attempts
# TYPE exchange_reconnect_attempts_total counter
exchange_reconnect_attempts_total{client_id="client1"} 100

# HELP exchange_reconnect_success_total Total number of successful reconnects
# TYPE exchange_reconnect_success_total counter
exchange_reconnect_success_total{client_id="client1"} 95

# HELP exchange_reconnect_time_ms_bucket Reconnect time in milliseconds
# TYPE exchange_reconnect_time_ms_bucket histogram
exchange_reconnect_time_ms_bucket{client_id="client1", le="0"} 10
exchange_reconnect_time_ms_bucket{client_id="client1", le="10"} 30
exchange_reconnect_time_ms_bucket{client_id="client1", le="50"} 50
exchange_reconnect_time_ms_bucket{client_id="client1", le="100"} 70
exchange_reconnect_time_ms_bucket{client_id="client1", le="200"} 85
exchange_reconnect_time_ms_bucket{client_id="client1", le="500"} 95
exchange_reconnect_time_ms_bucket{client_id="client1", le="1000"} 100
exchange_reconnect_time_ms_bucket{client_id="client1", le="5000"} 100
exchange_reconnect_time_ms_bucket{client_id="client1", le="+Inf"} 100
"""

    # Sample 2: Abnormal metrics (should fail SLO)
    abnormal_metrics = """# HELP exchange_requests_total Total number of requests
# TYPE exchange_requests_total counter
exchange_requests_total 1000

# HELP exchange_auth_fail_total Total number of authentication failures
# TYPE exchange_auth_fail_total counter
exchange_auth_fail_total 100

# HELP exchange_gate_fail_total Total number of gate check failures
# TYPE exchange_gate_fail_total counter
exchange_gate_fail_total 80

# HELP exchange_sse_connections Current number of SSE connections
# TYPE exchange_sse_connections gauge
exchange_sse_connections 5

# HELP exchange_reconnect_attempts_total Total number of reconnect attempts
# TYPE exchange_reconnect_attempts_total counter
exchange_reconnect_attempts_total{client_id="client1"} 100

# HELP exchange_reconnect_success_total Total number of successful reconnects
# TYPE exchange_reconnect_success_total counter
exchange_reconnect_success_total{client_id="client1"} 70

# HELP exchange_reconnect_time_ms_bucket Reconnect time in milliseconds
# TYPE exchange_reconnect_time_ms_bucket histogram
exchange_reconnect_time_ms_bucket{client_id="client1", le="0"} 5
exchange_reconnect_time_ms_bucket{client_id="client1", le="10"} 15
exchange_reconnect_time_ms_bucket{client_id="client1", le="50"} 25
exchange_reconnect_time_ms_bucket{client_id="client1", le="100"} 35
exchange_reconnect_time_ms_bucket{client_id="client1", le="200"} 45
exchange_reconnect_time_ms_bucket{client_id="client1", le="500"} 55
exchange_reconnect_time_ms_bucket{client_id="client1", le="1000"} 65
exchange_reconnect_time_ms_bucket{client_id="client1", le="5000"} 100
exchange_reconnect_time_ms_bucket{client_id="client1", le="+Inf"} 100
"""

    print("=== Test 1: Normal Metrics (Should Pass) ===")
    parsed_normal = parse_prometheus_metrics(normal_metrics)
    result_normal = validate_slo(parsed_normal)
    print(json.dumps(result_normal, indent=2))
    print()

    print("=== Test 2: Abnormal Metrics (Should Fail) ===")
    parsed_abnormal = parse_prometheus_metrics(abnormal_metrics)
    result_abnormal = validate_slo(parsed_abnormal)
    print(json.dumps(result_abnormal, indent=2))
    print()

    # Verify results
    if not result_normal["alert"] and result_abnormal["alert"]:
        print("✅ Test passed: Normal metrics pass SLO, abnormal metrics fail SLO")
        sys.exit(0)
    else:
        print("❌ Test failed: Results don't match expected")
        sys.exit(1)


if __name__ == "__main__":
    main()
