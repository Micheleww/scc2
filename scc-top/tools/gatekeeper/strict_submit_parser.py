#!/usr/bin/env python3
"""
Strict SUBMIT.txt Parser for Gatekeeper

TaskCode: SUBMIT-TXT-PARSER-STRICT-v0.1__20260116

This parser enforces strict rules for SUBMIT.txt files:
1. Fixed keys (≤8 lines)
2. FAIL if missing keys, extra keys, line count exceeded, or paths don't exist
3. Outputs machine-readable submit_parse.json to artifacts
4. Self-test functionality
"""

import argparse
import json
import os
from datetime import datetime

# Fixed set of required keys (exactly 8 keys)
REQUIRED_KEYS = ["TEST_NAME", "TEST_DATE", "RESULT", "EXIT_CODE"]

# Maximum allowed lines in SUBMIT.txt
MAX_LINES = 8


def parse_submit_txt_strict(submit_path):
    """
    Parse SUBMIT.txt with strict validation

    Args:
        submit_path (str): Path to SUBMIT.txt file

    Returns:
        tuple: (is_valid, parsed_data, errors, warnings)
    """
    errors = []
    warnings = []
    parsed_data = {}

    # 1. Check if file exists
    if not os.path.exists(submit_path):
        errors.append(f"SUBMIT file not found: {submit_path}")
        return False, parsed_data, errors, warnings

    # 2. Read file content
    try:
        with open(submit_path, encoding="utf-8") as f:
            lines = [line.strip() for line in f if line.strip()]
    except Exception as e:
        errors.append(f"Failed to read SUBMIT.txt: {e}")
        return False, parsed_data, errors, warnings

    # 3. Check line count
    if len(lines) > MAX_LINES:
        errors.append(f"SUBMIT.txt has too many lines: {len(lines)} (max: {MAX_LINES})")

    # 4. Parse key-value pairs
    found_keys = []
    for line in lines:
        if ": " not in line:
            errors.append(f"Invalid line format (missing ': '): {line}")
            continue

        key, value = line.split(": ", 1)
        key = key.strip()
        value = value.strip()

        # Check for duplicate keys
        if key in found_keys:
            errors.append(f"Duplicate key found: {key}")

        found_keys.append(key)
        parsed_data[key] = value

    # 5. Check for missing keys
    missing_keys = [key for key in REQUIRED_KEYS if key not in parsed_data]
    if missing_keys:
        errors.append(f"Missing required keys: {', '.join(missing_keys)}")

    # 6. Check for extra keys
    extra_keys = [key for key in parsed_data if key not in REQUIRED_KEYS]
    if extra_keys:
        errors.append(f"Extra keys found: {', '.join(extra_keys)}")

    # 7. Validate field values
    if "TEST_NAME" in parsed_data:
        test_name = parsed_data["TEST_NAME"]
        if not test_name or not isinstance(test_name, str):
            errors.append("TEST_NAME must be a non-empty string")

    if "TEST_DATE" in parsed_data:
        test_date = parsed_data["TEST_DATE"]
        try:
            datetime.strptime(test_date, "%Y-%m-%d")
        except ValueError:
            errors.append(f"TEST_DATE must be in YYYY-MM-DD format, got: {test_date}")

    if "RESULT" in parsed_data:
        result = parsed_data["RESULT"]
        if result not in ["PASS", "FAIL"]:
            errors.append(f"RESULT must be either PASS or FAIL, got: {result}")

    if "EXIT_CODE" in parsed_data:
        exit_code = parsed_data["EXIT_CODE"]
        try:
            exit_code_int = int(exit_code)
            if exit_code_int != 0 and parsed_data.get("RESULT") == "PASS":
                errors.append(f"EXIT_CODE must be 0 when RESULT is PASS, got: {exit_code}")
        except ValueError:
            errors.append(f"EXIT_CODE must be an integer, got: {exit_code}")

    # 8. Check paths if they exist in the submit (for backward compatibility with old format)
    if "report" in parsed_data:
        report_path = parsed_data["report"]
        if not os.path.exists(report_path):
            errors.append(f"Report path does not exist: {report_path}")

    if "selftest_log" in parsed_data:
        selftest_path = parsed_data["selftest_log"]
        if not os.path.exists(selftest_path):
            errors.append(f"Selftest log path does not exist: {selftest_path}")

    if "evidence_paths" in parsed_data:
        evidence_paths = parsed_data["evidence_paths"]
        if evidence_paths != "-":
            paths = [p.strip() for p in evidence_paths.split(",") if p.strip()]
            for path in paths:
                if not os.path.exists(path):
                    errors.append(f"Evidence path does not exist: {path}")

    is_valid = len(errors) == 0
    return is_valid, parsed_data, errors, warnings


def generate_parse_json(submit_path, parsed_data, is_valid, errors, warnings):
    """
    Generate machine-readable submit_parse.json file

    Args:
        submit_path (str): Path to SUBMIT.txt file
        parsed_data (dict): Parsed data from SUBMIT.txt
        is_valid (bool): Whether the SUBMIT.txt is valid
        errors (list): List of errors
        warnings (list): List of warnings

    Returns:
        str: Path to generated submit_parse.json file
    """
    # Determine artifacts directory based on SUBMIT.txt path
    artifacts_dir = os.path.dirname(submit_path)

    # Create parse result
    parse_result = {
        "parser_name": "SUBMIT-TXT-PARSER-STRICT-v0.1",
        "parse_timestamp": datetime.utcnow().isoformat() + "Z",
        "submit_path": submit_path,
        "is_valid": is_valid,
        "parsed_data": parsed_data,
        "errors": errors,
        "warnings": warnings,
        "validation_rules": {
            "required_keys": REQUIRED_KEYS,
            "max_lines": MAX_LINES,
            "strict_key_check": True,
            "path_validation": True,
        },
    }

    # Write to submit_parse.json
    parse_json_path = os.path.join(artifacts_dir, "submit_parse.json")
    try:
        with open(parse_json_path, "w", encoding="utf-8") as f:
            json.dump(parse_result, f, indent=2, ensure_ascii=False)
        return parse_json_path
    except Exception as e:
        print(f"Error writing submit_parse.json: {e}")
        return None


def run_strict_parser(submit_path):
    """
    Run strict parser on SUBMIT.txt

    Args:
        submit_path (str): Path to SUBMIT.txt file

    Returns:
        int: Exit code (0 for success, 1 for failure)
    """
    print("=== Running Strict SUBMIT.txt Parser ===")
    print(f"SUBMIT.txt path: {submit_path}")
    print(f"Required keys: {REQUIRED_KEYS}")
    print(f"Max lines allowed: {MAX_LINES}")
    print()

    # Parse with strict validation
    is_valid, parsed_data, errors, warnings = parse_submit_txt_strict(submit_path)

    # Generate parse JSON
    parse_json_path = generate_parse_json(submit_path, parsed_data, is_valid, errors, warnings)

    # Print results
    print("=== Parse Results ===")
    print(f"Validation: {'PASS' if is_valid else 'FAIL'}")
    print(f"Parsed keys: {list(parsed_data.keys())}")
    print(f"Lines parsed: {len(parsed_data)}")

    if parse_json_path:
        print(f"Parse JSON generated: {parse_json_path}")

    print()

    if warnings:
        print(f"=== Warnings ({len(warnings)}) ===")
        for warning in warnings:
            print(f"  - {warning}")
        print()

    if errors:
        print(f"=== Errors ({len(errors)}) ===")
        for error in errors:
            print(f"  - {error}")
        print()
        return 1

    print("✅ SUBMIT.txt passed all strict validation checks!")
    return 0


def run_selftest():
    """
    Run self-test to verify parser functionality

    Returns:
        int: Exit code (0 for success, 1 for failure)
    """
    import shutil
    import tempfile

    print("=== Running Self-Test for Strict SUBMIT Parser ===")

    temp_dir = tempfile.mkdtemp()
    results = []

    try:
        # Test 1: Valid SUBMIT.txt (4 keys format)
        print("\n1. Testing Valid SUBMIT.txt (4 keys format)...")
        valid_content = """
TEST_NAME: TEST-VALID-4KEYS
TEST_DATE: 2026-01-16
RESULT: PASS
EXIT_CODE: 0
"""
        valid_path = os.path.join(temp_dir, "valid_submit.txt")
        with open(valid_path, "w", encoding="utf-8") as f:
            f.write(valid_content.strip())

        is_valid, _, errors, _ = parse_submit_txt_strict(valid_path)
        results.append(("Valid 4-keys SUBMIT.txt", is_valid, errors))

        # Test 2: Missing key
        print("\n2. Testing Missing Key...")
        missing_key_content = """
TEST_NAME: TEST-MISSING-KEY
TEST_DATE: 2026-01-16
RESULT: PASS
# Missing EXIT_CODE
"""
        missing_key_path = os.path.join(temp_dir, "missing_key.txt")
        with open(missing_key_path, "w", encoding="utf-8") as f:
            f.write(missing_key_content.strip())

        is_valid, _, errors, _ = parse_submit_txt_strict(missing_key_path)
        results.append(("Missing key", not is_valid and len(errors) > 0, errors))

        # Test 3: Extra key
        print("\n3. Testing Extra Key...")
        extra_key_content = """
TEST_NAME: TEST-EXTRA-KEY
TEST_DATE: 2026-01-16
RESULT: PASS
EXIT_CODE: 0
EXTRA_KEY: extra_value
"""
        extra_key_path = os.path.join(temp_dir, "extra_key.txt")
        with open(extra_key_path, "w", encoding="utf-8") as f:
            f.write(extra_key_content.strip())

        is_valid, _, errors, _ = parse_submit_txt_strict(extra_key_path)
        results.append(("Extra key", not is_valid and len(errors) > 0, errors))

        # Test 4: Too many lines
        print("\n4. Testing Too Many Lines...")
        too_many_lines_content = """
TEST_NAME: TEST-TOO-MANY-LINES
TEST_DATE: 2026-01-16
RESULT: PASS
EXIT_CODE: 0
LINE5: value5
LINE6: value6
LINE7: value7
LINE8: value8
LINE9: value9
"""
        too_many_lines_path = os.path.join(temp_dir, "too_many_lines.txt")
        with open(too_many_lines_path, "w", encoding="utf-8") as f:
            f.write(too_many_lines_content.strip())

        is_valid, _, errors, _ = parse_submit_txt_strict(too_many_lines_path)
        results.append(("Too many lines", not is_valid and len(errors) > 0, errors))

        # Test 5: Invalid EXIT_CODE with PASS result
        print("\n5. Testing Invalid EXIT_CODE with PASS...")
        invalid_exit_content = """
TEST_NAME: TEST-INVALID-EXIT
TEST_DATE: 2026-01-16
RESULT: PASS
EXIT_CODE: 1
"""
        invalid_exit_path = os.path.join(temp_dir, "invalid_exit.txt")
        with open(invalid_exit_path, "w", encoding="utf-8") as f:
            f.write(invalid_exit_content.strip())

        is_valid, _, errors, _ = parse_submit_txt_strict(invalid_exit_path)
        results.append(("Invalid EXIT_CODE with PASS", not is_valid and len(errors) > 0, errors))

        # Print results
        print("\n=== Self-Test Results ===")
        passed = 0
        failed = 0

        for test_name, expected, errors in results:
            status = "✅ PASS" if expected else "❌ FAIL"
            print(f"{status}: {test_name}")
            if not expected:
                for error in errors:
                    print(f"    Error: {error}")
                failed += 1
            else:
                passed += 1

        print("\n=== Summary ===")
        print(f"Passed: {passed}")
        print(f"Failed: {failed}")

        if failed == 0:
            print("\n🎉 All self-tests passed!")
            return 0
        else:
            print(f"\n💥 {failed} self-tests failed!")
            return 1

    finally:
        shutil.rmtree(temp_dir)


def main():
    """
    Main entry point
    """
    parser = argparse.ArgumentParser(description="Strict SUBMIT.txt Parser")
    parser.add_argument("--submit-path", type=str, help="Path to SUBMIT.txt file")
    parser.add_argument("--selftest", action="store_true", help="Run self-test")

    args = parser.parse_args()

    if args.selftest:
        exit_code = run_selftest()
        sys.exit(exit_code)

    if not args.submit_path:
        parser.print_help()
        sys.exit(1)

    exit_code = run_strict_parser(args.submit_path)
    sys.exit(exit_code)


if __name__ == "__main__":
    import sys

    main()
