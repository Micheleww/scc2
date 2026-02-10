#!/usr/bin/env python3
"""
Self-test script for Files module with S3 presigned URL functionality
"""

import asyncio
import json
import logging
import os
import sys
import time
from pathlib import Path

from aiohttp import ClientSession

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

# Constants
TEST_NAME = "FILES-S3-PRESIGN-ROTATION-v0.1__20260117"
ARTIFACTS_DIR = (
    Path(__file__).parent.parent.parent.parent
    / "docs"
    / "REPORT"
    / "ci"
    / "exchange"
    / "artifacts"
    / TEST_NAME
)
LOG_FILE = Path("files_selftest.log")
API_BASE_URL = "http://localhost:8081"
JSONRPC_ENDPOINT = f"{API_BASE_URL}/mcp"


class FilesSelftestRunner:
    """Runs files module self-test"""

    def __init__(self):
        self.test_start_time = None
        self.test_end_time = None
        self.test_passed = False
        self.events = []
        self.test_results = {}

    def log_event(self, event_type, message, **kwargs):
        """Log test event"""
        event = {"event_type": event_type, "timestamp": time.time(), "message": message, **kwargs}
        self.events.append(event)
        logger.info(f"[{event_type}] {message}")

        # Write to log file with UTF-8 encoding
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} [{event_type}] {message}")
            if kwargs:
                f.write(f" {json.dumps(kwargs, ensure_ascii=False)}")
            f.write("\n")

    async def jsonrpc_call(self, session, method, params, trace_id):
        """Make JSON-RPC call to the exchange server"""
        headers = {
            "Content-Type": "application/json",
            "Authorization": "Bearer default_secret_token",
            "X-Trace-ID": trace_id,
            "X-Request-Nonce": f"test_nonce_{time.time()}_{os.urandom(4).hex()}",
            "X-Request-Ts": str(int(time.time())),
        }

        payload = {
            "jsonrpc": "2.0",
            "id": trace_id,
            "method": "tools.call",
            "params": {"name": method, "params": params},
        }

        async with session.post(JSONRPC_ENDPOINT, json=payload, headers=headers) as response:
            return await response.json()

    async def test_files_generate_presigned_url(self, session, trace_id):
        """Test generating presigned URLs"""
        self.log_event("INFO", "Testing files.generate_presigned_url")

        # Test case 1: Valid upload URL generation
        file_id = f"test_file_{time.time()}"
        result = await self.jsonrpc_call(
            session,
            "files.generate_presigned_url",
            {"file_id": file_id, "operation": "upload", "client_id": "test_client_1"},
            trace_id,
        )

        self.log_event("INFO", f"Upload URL generation result: {json.dumps(result)}")

        if "result" in result and "presigned_url" in result["result"]:
            self.log_event("PASS", "✓ Valid upload URL generation")
            self.test_results["test_files_generate_presigned_url_upload"] = True
        else:
            self.log_event("FAIL", "✗ Invalid upload URL generation")
            self.test_results["test_files_generate_presigned_url_upload"] = False

        # Test case 2: Valid download URL generation
        result = await self.jsonrpc_call(
            session,
            "files.generate_presigned_url",
            {"file_id": file_id, "operation": "download", "client_id": "test_client_1"},
            trace_id,
        )

        self.log_event("INFO", f"Download URL generation result: {json.dumps(result)}")

        if "result" in result and "presigned_url" in result["result"]:
            self.log_event("PASS", "✓ Valid download URL generation")
            self.test_results["test_files_generate_presigned_url_download"] = True
        else:
            self.log_event("FAIL", "✗ Invalid download URL generation")
            self.test_results["test_files_generate_presigned_url_download"] = False

        return file_id

    async def test_files_revoke(self, session, trace_id, file_id):
        """Test revoking file access"""
        self.log_event("INFO", "Testing files.revoke")

        # Test revocation
        result = await self.jsonrpc_call(session, "files.revoke", {"file_id": file_id}, trace_id)

        self.log_event("INFO", f"Revocation result: {json.dumps(result)}")

        if "result" in result and result["result"].get("status") == "success":
            self.log_event("PASS", "✓ File revocation successful")
            self.test_results["test_files_revoke"] = True
        else:
            self.log_event("FAIL", "✗ File revocation failed")
            self.test_results["test_files_revoke"] = False

        return True

    async def test_files_revoked_access(self, session, trace_id, file_id):
        """Test access to revoked files"""
        self.log_event("INFO", "Testing access to revoked files")

        # Try to generate URL for revoked file
        result = await self.jsonrpc_call(
            session,
            "files.generate_presigned_url",
            {"file_id": file_id, "operation": "download", "client_id": "test_client_1"},
            trace_id,
        )

        self.log_event("INFO", f"Revoked file access result: {json.dumps(result)}")

        if (
            "result" in result
            and "error_code" in result["result"]
            and result["result"]["error_code"] == "FILE_REVOKED"
        ):
            self.log_event("PASS", "✓ Revoked file properly blocked")
            self.test_results["test_files_revoked_access"] = True
        else:
            self.log_event("FAIL", "✗ Revoked file not blocked")
            self.test_results["test_files_revoked_access"] = False

        return True

    async def test_files_client_isolation(self, session, trace_id):
        """Test client isolation"""
        self.log_event("INFO", "Testing client isolation")

        # Generate URL for client 1
        file_id = f"shared_file_{time.time()}"
        result1 = await self.jsonrpc_call(
            session,
            "files.generate_presigned_url",
            {"file_id": file_id, "operation": "download", "client_id": "test_client_1"},
            trace_id,
        )

        # Generate URL for client 2
        result2 = await self.jsonrpc_call(
            session,
            "files.generate_presigned_url",
            {"file_id": file_id, "operation": "download", "client_id": "test_client_2"},
            trace_id,
        )

        if "result" in result1 and "result" in result2:
            url1 = result1["result"]["presigned_url"]
            url2 = result2["result"]["presigned_url"]

            # URLs should have different client prefixes
            if "test_client_1" in url1 and "test_client_2" in url2:
                self.log_event("PASS", "✓ Client isolation maintained")
                self.test_results["test_files_client_isolation"] = True
            else:
                self.log_event("FAIL", "✗ Client isolation failed")
                self.test_results["test_files_client_isolation"] = False
        else:
            self.log_event("FAIL", "✗ Client isolation test failed due to API error")
            self.test_results["test_files_client_isolation"] = False

        return True

    async def test_files_error_codes(self, session, trace_id):
        """Test error codes"""
        self.log_event("INFO", "Testing error codes")

        # Test case 1: Invalid operation
        result = await self.jsonrpc_call(
            session,
            "files.generate_presigned_url",
            {"file_id": "test_file", "operation": "invalid_op", "client_id": "test_client"},
            trace_id,
        )

        if "result" in result and result["result"].get("error_code") == "INVALID_OPERATION":
            self.log_event("PASS", "✓ Invalid operation error code correct")
        else:
            self.log_event("FAIL", "✗ Invalid operation error code incorrect")

        # Test case 2: Invalid client ID
        result = await self.jsonrpc_call(
            session,
            "files.generate_presigned_url",
            {"file_id": "test_file", "operation": "upload", "client_id": ""},
            trace_id,
        )

        if "result" in result and result["result"].get("error_code") == "INVALID_CLIENT_ID":
            self.log_event("PASS", "✓ Invalid client ID error code correct")
            self.test_results["test_files_error_codes"] = True
        else:
            self.log_event("FAIL", "✗ Invalid client ID error code incorrect")
            self.test_results["test_files_error_codes"] = False

        return True

    async def run(self):
        """Run all self-tests"""
        # Clear previous log with UTF-8 encoding
        with open(LOG_FILE, "w", encoding="utf-8") as f:
            f.write(f"# {TEST_NAME} Self-Test Log\n")
            f.write(f"Test started: {time.strftime('%Y-%m-%d %H:%M:%S')}\n\n")

        self.test_start_time = time.time()
        self.log_event("INFO", f"Starting {TEST_NAME} Self-Test")

        try:
            async with ClientSession() as session:
                trace_id = f"test_trace_{time.time()}_{os.urandom(4).hex()}"

                # Test 1: Generate presigned URLs
                file_id = await self.test_files_generate_presigned_url(session, trace_id)

                # Test 2: Client isolation
                await self.test_files_client_isolation(session, trace_id)

                # Test 3: Error codes
                await self.test_files_error_codes(session, trace_id)

                # Test 4: Revoke file access
                await self.test_files_revoke(session, trace_id, file_id)

                # Test 5: Test access to revoked file
                await self.test_files_revoked_access(session, trace_id, file_id)

            # Evaluate test results
            all_tests_passed = all(result for result in self.test_results.values())

            if all_tests_passed:
                self.log_event("PASS", "All tests passed!")
                self.test_passed = True
            else:
                failed_tests = [test for test, result in self.test_results.items() if not result]
                self.log_event("FAIL", f"Some tests failed: {', '.join(failed_tests)}")
                self.test_passed = False

            return all_tests_passed

        except Exception as e:
            self.log_event("ERROR", f"Test failed with exception: {e}")
            import traceback

            self.log_event("ERROR", f"Traceback: {traceback.format_exc()}")
            return False

        finally:
            self.test_end_time = time.time()
            await self._generate_artifacts()

    async def _generate_artifacts(self):
        """Generate test artifacts"""
        try:
            # Create artifacts directory structure
            ata_dir = ARTIFACTS_DIR / "ata"
            ata_dir.mkdir(parents=True, exist_ok=True)

            # Copy log file to artifacts
            artifact_log = ARTIFACTS_DIR / "files_selftest.log"
            import shutil

            shutil.copy2(LOG_FILE, artifact_log)

            # Create context.json
            context = {
                "test_name": TEST_NAME,
                "test_version": "v0.1",
                "test_date": time.strftime("%Y-%m-%dT%H:%M:%S"),
                "result": "PASS" if self.test_passed else "FAIL",
                "exit_code": 0 if self.test_passed else 1,
                "duration_seconds": round(self.test_end_time - self.test_start_time, 2),
                "events": self.events,
                "test_results": self.test_results,
                "config": {"api_base_url": API_BASE_URL, "exit_code": 0 if self.test_passed else 1},
            }

            context_path = ata_dir / "context.json"
            with open(context_path, "w", encoding="utf-8") as f:
                json.dump(context, f, ensure_ascii=False, indent=2)

            # Create SUBMIT.txt
            submit_content = f"""
TEST_NAME: {TEST_NAME}
TEST_DATE: {time.strftime("%Y-%m-%d")}
RESULT: {"PASS" if self.test_passed else "FAIL"}
EXIT_CODE: {"0" if self.test_passed else "1"}
"""

            submit_path = ARTIFACTS_DIR / "SUBMIT.txt"
            with open(submit_path, "w", encoding="utf-8") as f:
                f.write(submit_content.strip())

            # Write exit code to log file
            with open(LOG_FILE, "a", encoding="utf-8") as f:
                f.write(f"\nEXIT_CODE={'0' if self.test_passed else '1'}\n")

            self.log_event("INFO", f"Artifacts generated in: {ARTIFACTS_DIR}")

        except Exception as e:
            self.log_event("ERROR", f"Failed to generate artifacts: {e}")
            import traceback

            self.log_event("ERROR", f"Artifacts generation traceback: {traceback.format_exc()}")


async def main():
    """Main function"""
    runner = FilesSelftestRunner()
    success = await runner.run()

    if success:
        logger.info("✓ Self-test passed!")
        sys.exit(0)
    else:
        logger.error("✗ Self-test failed!")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
