#!/usr/bin/env python3
"""
Docs Unique Entry Guard Validator
Enforces: 1) docs/ARCH/00_index.md's first link points to project navigation file
           2) No suspicious new entry files exist in the repository
"""

import logging
import os
import re
import sys
from pathlib import Path

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

# Constants
PROJECT_ROOT = Path(os.getcwd())
# Standard: Use lowercase 'arch' directory (aligned with mkdocs.yml)
ARCH_INDEX_FILE = PROJECT_ROOT / "docs" / "arch" / "00_index.md"
# Use ACTIVE version, not DRAFT - ACTIVE is the single source of truth
EXPECTED_NAV_FILE = (
    PROJECT_ROOT / "docs" / "arch" / "project_navigation__v0.1.0__ACTIVE__20260115.md"
)
ARTIFACTS_DIR = (
    PROJECT_ROOT
    / "docs"
    / "REPORT"
    / "docs_gov"
    / "artifacts"
    / "HARDEN-DOCS-UNIQUE-ENTRY-GUARD-v0.1"
)

# Suspicious file patterns
SUSPICIOUS_PATTERNS = [
    r"^.*_navigation.*\.md$",
    r"^.*NAV.*\.md$",
    r"^README_NAV.*\.md$",
    r"^NAV_README.*\.md$",
    r"^navigation.*\.md$",
    r"^.*_nav_.*\.md$",
]

# Allowed files and directories to skip
# Only ACTIVE versions are allowed - DRAFT is deprecated
# Standard: Use lowercase 'arch' directory (aligned with mkdocs.yml)
ALLOWED_FILES = [
    "docs/arch/00_index.md",
    "docs/arch/project_navigation__v0.1.0__ACTIVE__20260115.md",
]

SKIP_DIRS = [".git", "docs/REPORT", "venv", "node_modules", ".vscode", ".idea"]


def check_arch_index():
    """Check if docs/ARCH/00_index.md's first link points to the expected navigation file"""
    logger.info(f"Checking {ARCH_INDEX_FILE.relative_to(PROJECT_ROOT)}...")

    if not ARCH_INDEX_FILE.exists():
        logger.error(f"ERROR: {ARCH_INDEX_FILE.relative_to(PROJECT_ROOT)} not found!")
        return False

    try:
        with open(ARCH_INDEX_FILE, encoding="utf-8") as f:
            content = f.read()

        # Extract all markdown links, excluding anchors
        links = re.findall(r"\[.*?\]\(([^#]+?)\)", content)

        if not links:
            logger.error(f"ERROR: No links found in {ARCH_INDEX_FILE.relative_to(PROJECT_ROOT)}!")
            return False

        # Get the first link
        first_link = links[0].strip()
        logger.info(f"First link found: {first_link}")

        # Resolve the link to an absolute path
        first_link_path = (ARCH_INDEX_FILE.parent / first_link).resolve()
        expected_path = EXPECTED_NAV_FILE.resolve()

        if first_link_path == expected_path:
            logger.info(
                f"PASS: First link correctly points to {EXPECTED_NAV_FILE.relative_to(PROJECT_ROOT)}"
            )
            return True
        else:
            logger.error(
                f"ERROR: First link should point to {EXPECTED_NAV_FILE.relative_to(PROJECT_ROOT)}, but points to {first_link_path.relative_to(PROJECT_ROOT)}"
            )
            return False

    except Exception as e:
        logger.error(f"ERROR: Failed to read {ARCH_INDEX_FILE.relative_to(PROJECT_ROOT)}: {str(e)}")
        return False


def scan_suspicious_files():
    """Scan repository for suspicious entry files"""
    logger.info("Scanning for suspicious entry files...")
    suspicious_files = []

    # Walk through the repository, skipping specified directories
    for root, dirs, files in os.walk(PROJECT_ROOT):
        # Skip allowed directories
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]

        for file in files:
            if file.endswith(".md"):
                file_path = Path(root) / file
                rel_path = file_path.relative_to(PROJECT_ROOT)

                # Normalize path to use forward slashes for comparison
                norm_rel_path = str(rel_path).replace("\\", "/")

                # Skip allowed files (case-insensitive comparison)
                skip = False
                for allowed_file in ALLOWED_FILES:
                    if norm_rel_path.lower() == allowed_file.lower():
                        skip = True
                        break

                if skip:
                    continue

                # Skip files in docs/REPORT directory
                if "docs/REPORT" in norm_rel_path:
                    continue

                # Check if file matches any suspicious pattern
                for pattern in SUSPICIOUS_PATTERNS:
                    if re.match(pattern, file, re.IGNORECASE):
                        suspicious_files.append(rel_path)
                        logger.warning(f"WARNING: Suspicious entry file found: {rel_path}")
                        break

    if not suspicious_files:
        logger.info("PASS: No suspicious entry files found")
        return True
    else:
        logger.error(f"ERROR: Found {len(suspicious_files)} suspicious entry files!")
        return False


def main():
    """Main entry point"""
    logger.info("=== Docs Unique Entry Guard Validator ===")

    # Create artifacts directory if it doesn't exist
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)

    # Run checks
    check1 = check_arch_index()
    check2 = scan_suspicious_files()

    # Write results to self-test log
    selftest_log = ARTIFACTS_DIR / "selftest.log"
    with open(selftest_log, "w", encoding="utf-8") as f:
        f.write("=== Docs Unique Entry Guard Self-Test Results ===\n")
        f.write(f"ARCH Index Check: {'PASS' if check1 else 'FAIL'}\n")
        f.write(f"Suspicious Files Check: {'PASS' if check2 else 'FAIL'}\n")
        f.write(f"Overall Result: {'PASS' if check1 and check2 else 'FAIL'}\n")

    logger.info(f"Self-test log written to {selftest_log.relative_to(PROJECT_ROOT)}")

    # Return appropriate exit code
    if check1 and check2:
        logger.info("=== All checks PASSED ===")
        return 0
    else:
        logger.error("=== Some checks FAILED ===")
        return 1


if __name__ == "__main__":
    sys.exit(main())
