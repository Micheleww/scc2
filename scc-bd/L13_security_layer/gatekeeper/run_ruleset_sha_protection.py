#!/usr/bin/env python3
"""
Direct run script for Ruleset SHA Protection

This script demonstrates the ruleset SHA protection functionality
"""

import os
import sys
from pathlib import Path

# Now we can import correctly
try:
    from .ruleset_sha_protection import RulesetSHAProtection

    def main():
        """Main function"""
        print("Running Ruleset SHA Protection Demo...")
        print("=" * 60)

        # Initialize the protection
        protection = RulesetSHAProtection()

        # Calculate and display ruleset hashes
        print("\n1. Calculating Ruleset Hashes:")
        hashes = protection.calculate_ruleset_hashes()
        for hash_type, hash_value in hashes.items():
            print(f"   {hash_type}: {hash_value}")

        # Write hashes to reports
        print("\n2. Writing Ruleset Hashes to Reports:")
        updated_files = protection.write_ruleset_sha_to_reports()
        print(f"   Updated {len(updated_files)} report files")

        # Check consistency
        print("\n3. Checking Consistency:")
        consistent, inconsistencies = protection.check_ruleset_sha_consistency()
        print(f"   Consistency Check: {'PASS' if consistent else 'FAIL'}")
        if inconsistencies:
            print(f"   Inconsistencies found: {len(inconsistencies)}")
            for inconsistency in inconsistencies[:3]:  # Show first 3
                print(f"     - {inconsistency}")

        # Run complete protection
        print("\n4. Running Complete Protection:")
        passed, results = protection.run_protection()

        print("\n" + "=" * 60)
        print("Demo Complete!")
        print("=" * 60)
        return 0

except Exception as e:
    print(f"Error: {e}")
    import traceback

    traceback.print_exc()
    return 1

if __name__ == "__main__":
    sys.exit(main())
