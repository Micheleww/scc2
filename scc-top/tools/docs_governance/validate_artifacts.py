#!/usr/bin/env python3
"""
Validate artifacts for REPORT metadata files.

This script validates:
1. Existence of required paths
2. Evidence paths must be in corresponding artifacts directory
3. selftest.log must contain EXIT_CODE=0
4. All paths must be relative to repo root
"""

import argparse
import json
import os
import sys

from jsonschema import ValidationError, validate


def load_schema(schema_path):
    """Load JSON schema from file."""
    with open(schema_path, encoding="utf-8") as f:
        return json.load(f)


def validate_report_metadata(report_metadata, schema):
    """Validate REPORT metadata against schema."""
    try:
        validate(instance=report_metadata, schema=schema)
        return True, None
    except ValidationError as e:
        return False, f"Schema validation failed: {e.message}"


def check_paths_exist(report_metadata, repo_root):
    """Check if all required paths exist."""
    errors = []

    # Check selftest_log exists
    selftest_log_path = os.path.join(repo_root, report_metadata["selftest_log"])
    if not os.path.exists(selftest_log_path):
        errors.append(f"selftest_log not found: {report_metadata['selftest_log']}")

    # Check each evidence path exists
    for evidence_path in report_metadata["evidence_paths"]:
        evidence_full_path = os.path.join(repo_root, evidence_path)
        if not os.path.exists(evidence_full_path):
            errors.append(f"Evidence path not found: {evidence_path}")

    return errors


def check_evidence_paths_in_artifacts(report_metadata):
    """Check if evidence paths are in corresponding artifacts directory."""
    errors = []

    # Get artifacts directory from selftest_log path
    selftest_log = report_metadata["selftest_log"]
    if "artifacts" not in selftest_log:
        errors.append(f"selftest_log path does not contain 'artifacts': {selftest_log}")
        return errors

    artifacts_dir = selftest_log.split("artifacts")[0] + "artifacts"

    # Check each evidence path is in artifacts directory
    for evidence_path in report_metadata["evidence_paths"]:
        if not evidence_path.startswith(artifacts_dir):
            errors.append(f"Evidence path not in artifacts directory: {evidence_path}")

    return errors


def check_selftest_exit_code(report_metadata, repo_root):
    """Check if selftest.log contains EXIT_CODE=0."""
    selftest_log_path = os.path.join(repo_root, report_metadata["selftest_log"])
    try:
        with open(selftest_log_path, encoding="utf-8") as f:
            content = f.read()
            if "EXIT_CODE=0" not in content:
                return [
                    f"selftest.log does not contain EXIT_CODE=0: {report_metadata['selftest_log']}"
                ]
    except Exception as e:
        return [f"Error reading selftest.log: {e}"]

    return []


def check_relative_paths(report_metadata):
    """Check if all paths are relative to repo root."""
    errors = []

    # Check selftest_log is relative
    if report_metadata["selftest_log"].startswith("/"):
        errors.append(f"selftest_log is not a relative path: {report_metadata['selftest_log']}")

    # Check evidence paths are relative
    for evidence_path in report_metadata["evidence_paths"]:
        if evidence_path.startswith("/"):
            errors.append(f"Evidence path is not a relative path: {evidence_path}")

    # Check changed_files are relative
    for changed_file in report_metadata["changed_files"]:
        if changed_file.startswith("/"):
            errors.append(f"Changed file is not a relative path: {changed_file}")

    return errors


def validate_artifacts(report_metadata_path):
    """Validate artifacts for a given REPORT metadata file."""
    # Get repo root (parent directory of this script's directory)
    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))

    # Load report metadata
    try:
        with open(report_metadata_path, encoding="utf-8") as f:
            report_metadata = json.load(f)
    except Exception as e:
        print(f"Error loading report metadata: {e}")
        return False

    # Load schema
    schema_path = os.path.join(os.path.dirname(__file__), "schema_report_metadata.json")
    schema = load_schema(schema_path)

    # Validate against schema
    is_valid, schema_error = validate_report_metadata(report_metadata, schema)
    if not is_valid:
        print(schema_error)
        return False

    # Check all required paths exist
    path_errors = check_paths_exist(report_metadata, repo_root)
    if path_errors:
        for error in path_errors:
            print(error)
        return False

    # Check evidence paths are in artifacts directory
    evidence_errors = check_evidence_paths_in_artifacts(report_metadata)
    if evidence_errors:
        for error in evidence_errors:
            print(error)
        return False

    # Check selftest.log contains EXIT_CODE=0
    selftest_errors = check_selftest_exit_code(report_metadata, repo_root)
    if selftest_errors:
        for error in selftest_errors:
            print(error)
        return False

    # Check all paths are relative
    relative_errors = check_relative_paths(report_metadata)
    if relative_errors:
        for error in relative_errors:
            print(error)
        return False

    print(f"All validations passed for {report_metadata_path}")
    return True


def main():
    """Main function."""
    parser = argparse.ArgumentParser(description="Validate artifacts for REPORT metadata files.")
    parser.add_argument("report_metadata", help="Path to REPORT metadata JSON file")

    args = parser.parse_args()

    if not os.path.exists(args.report_metadata):
        print(f"Report metadata file not found: {args.report_metadata}")
        sys.exit(1)

    if validate_artifacts(args.report_metadata):
        sys.exit(0)
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()
