#!/usr/bin/env python3
"""
Direct test script for the files module
"""

import json
import os
import sys
import time

from files import FilesModule

# Add the current directory to the path to import files module
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


class FilesModuleTester:
    """Direct tester for the Files module"""

    def __init__(self):
        self.files_module = FilesModule()
        self.test_results = {}

    def test_generate_presigned_url(self):
        """Test generating presigned URLs"""
        print("\n=== Testing generate_presigned_url ===")

        # Test 1: Valid upload URL
        file_id = f"test_file_{time.time()}"
        result = self.files_module.generate_presigned_url(file_id, "upload", "test_client_1")
        print(f"Upload URL result: {json.dumps(result, indent=2)}")

        if "presigned_url" in result and "upload_id" in result:
            print("✓ Valid upload URL generation")
            self.test_results["test_generate_presigned_url_upload"] = True
        else:
            print("✗ Invalid upload URL generation")
            self.test_results["test_generate_presigned_url_upload"] = False

        # Test 2: Valid download URL
        result = self.files_module.generate_presigned_url(file_id, "download", "test_client_1")
        print(f"Download URL result: {json.dumps(result, indent=2)}")

        if "presigned_url" in result and "upload_id" not in result:
            print("✓ Valid download URL generation")
            self.test_results["test_generate_presigned_url_download"] = True
        else:
            print("✗ Invalid download URL generation")
            self.test_results["test_generate_presigned_url_download"] = False

        return file_id

    def test_revoke_file(self, file_id):
        """Test revoking file access"""
        print("\n=== Testing revoke ===")

        result = self.files_module.revoke(file_id)
        print(f"Revoke result: {json.dumps(result, indent=2)}")

        if result.get("status") == "success":
            print("✓ File revocation successful")
            self.test_results["test_revoke_file"] = True
        else:
            print("✗ File revocation failed")
            self.test_results["test_revoke_file"] = False

    def test_access_revoked_file(self, file_id):
        """Test access to revoked files"""
        print("\n=== Testing access to revoked files ===")

        result = self.files_module.generate_presigned_url(file_id, "download", "test_client_1")
        print(f"Access to revoked file result: {json.dumps(result, indent=2)}")

        if result.get("error_code") == "FILE_REVOKED":
            print("✓ Revoked file properly blocked")
            self.test_results["test_access_revoked_file"] = True
        else:
            print("✗ Revoked file not blocked")
            self.test_results["test_access_revoked_file"] = False

    def test_client_isolation(self):
        """Test client isolation"""
        print("\n=== Testing client isolation ===")

        file_id = f"shared_file_{time.time()}"

        # Generate URL for client 1
        result1 = self.files_module.generate_presigned_url(file_id, "download", "test_client_1")

        # Generate URL for client 2
        result2 = self.files_module.generate_presigned_url(file_id, "download", "test_client_2")

        print(f"Client 1 URL: {result1['presigned_url']}")
        print(f"Client 2 URL: {result2['presigned_url']}")

        if (
            "test_client_1" in result1["presigned_url"]
            and "test_client_2" in result2["presigned_url"]
        ):
            print("✓ Client isolation maintained")
            self.test_results["test_client_isolation"] = True
        else:
            print("✗ Client isolation failed")
            self.test_results["test_client_isolation"] = False

    def test_error_codes(self):
        """Test error codes"""
        print("\n=== Testing error codes ===")

        # Test 1: Invalid operation
        result = self.files_module.generate_presigned_url(
            "test_file", "invalid_op", "test_client_1"
        )
        print(f"Invalid operation result: {json.dumps(result, indent=2)}")

        if result.get("error_code") == "INVALID_OPERATION":
            print("✓ Invalid operation error code correct")
        else:
            print("✗ Invalid operation error code incorrect")

        # Test 2: Invalid client ID
        result = self.files_module.generate_presigned_url("test_file", "upload", "")
        print(f"Invalid client ID result: {json.dumps(result, indent=2)}")

        if result.get("error_code") == "INVALID_CLIENT_ID":
            print("✓ Invalid client ID error code correct")
            self.test_results["test_error_codes"] = True
        else:
            print("✗ Invalid client ID error code incorrect")
            self.test_results["test_error_codes"] = False

    def run_all_tests(self):
        """Run all tests"""
        print("Running Files Module Tests")
        print("=" * 50)

        try:
            # Test 1: Generate presigned URLs
            file_id = self.test_generate_presigned_url()

            # Test 2: Client isolation
            self.test_client_isolation()

            # Test 3: Error codes
            self.test_error_codes()

            # Test 4: Revoke file
            self.test_revoke_file(file_id)

            # Test 5: Access revoked file
            self.test_access_revoked_file(file_id)

            # Test 6: Check denylist persistence
            print("\n=== Testing denylist persistence ===")

            # Create new instance to test loading from disk
            new_files_module = FilesModule()
            denylist = new_files_module.get_denylist()
            print(f"Denylist after reload: {denylist}")

            if file_id in denylist:
                print("✓ Denylist properly persisted")
                self.test_results["test_denylist_persistence"] = True
            else:
                print("✗ Denylist not persisted")
                self.test_results["test_denylist_persistence"] = False

            # Cleanup
            new_files_module.clear_denylist()
            print("\n=== Cleanup ===")
            print("✓ Denylist cleared")

            # Print final results
            print("\n" + "=" * 50)
            print("Test Results Summary")
            print("=" * 50)

            all_passed = True
            for test, result in self.test_results.items():
                status = "✓ PASS" if result else "✗ FAIL"
                print(f"{status} {test}")
                if not result:
                    all_passed = False

            print("\n" + "=" * 50)

            if all_passed:
                print("🎉 All tests passed!")
                return 0
            else:
                print("❌ Some tests failed!")
                return 1

        except Exception as e:
            print(f"\n❌ Test failed with exception: {e}")
            import traceback

            traceback.print_exc()
            return 1


if __name__ == "__main__":
    tester = FilesModuleTester()
    exit_code = tester.run_all_tests()
    sys.exit(exit_code)
