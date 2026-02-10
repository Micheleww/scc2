import sys
import tempfile
from datetime import datetime
from pathlib import Path

# Add the project root to the path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from tools.mcp_bus.server.tools import InboxAppendParams, ToolExecutor


# Mock security and audit logger
class MockSecurity:
    def check_access(self, path, mode):
        return True, ""


class MockAuditLogger:
    def log_tool_call(self, *args, **kwargs):
        pass


def test_version_control():
    """Test version control functionality"""
    print("=== Testing Version Control ===")

    # Create temporary directories
    with tempfile.TemporaryDirectory() as temp_dir:
        repo_root = Path(temp_dir)
        inbox_dir = "inbox"
        board_file = "board.md"

        # Initialize ToolExecutor
        security = MockSecurity()
        audit = MockAuditLogger()
        executor = ToolExecutor(str(repo_root), inbox_dir, board_file, security, audit)

        # Test date
        test_date = datetime.now().strftime("%Y-%m-%d")

        # 1. Get initial rev
        print("1. Getting initial revision...")
        # Use inbox_tail equivalent to get rev
        inbox_file = repo_root / inbox_dir / f"{test_date}.md"
        initial_rev = executor._get_file_rev(inbox_file)
        print(f"   Initial rev: {initial_rev}")

        # 2. Write with correct base_rev - should succeed
        print("2. Writing with correct base_rev...")
        params = InboxAppendParams(
            date=test_date,
            task_code="TEST-123",
            source="test_script",
            text="This is a test message - Version 1",
        )
        result = executor.inbox_append(params, base_rev=initial_rev, request_id="test_req_1")
        assert result["success"] == True
        new_rev = result.get("rev")
        print(f"   Write successful. New rev: {new_rev}")
        assert new_rev != initial_rev

        # 3. Write with wrong base_rev - should fail with 409
        print("3. Writing with wrong base_rev...")
        params = InboxAppendParams(
            date=test_date,
            task_code="TEST-123",
            source="test_script",
            text="This is a test message - Version 2 (should fail)",
        )
        result = executor.inbox_append(params, base_rev=initial_rev, request_id="test_req_2")
        assert result["success"] == False
        assert result.get("status") == 409
        print("   Write failed as expected with 409")

    print("Version control tests passed!\n")


def test_idempotency():
    """Test request idempotency"""
    print("=== Testing Request Idempotency ===")

    # Create temporary directories
    with tempfile.TemporaryDirectory() as temp_dir:
        repo_root = Path(temp_dir)
        inbox_dir = "inbox"
        board_file = "board.md"

        # Initialize ToolExecutor
        security = MockSecurity()
        audit = MockAuditLogger()
        executor = ToolExecutor(str(repo_root), inbox_dir, board_file, security, audit)

        # Test date
        test_date = datetime.now().strftime("%Y-%m-%d")

        # Get initial rev
        inbox_file = repo_root / inbox_dir / f"{test_date}.md"
        initial_rev = executor._get_file_rev(inbox_file)

        # Use the same request_id for two requests
        request_id = "test_idempotent_req_1"

        # First request - should succeed
        print("1. First request with new request_id...")
        params = InboxAppendParams(
            date=test_date,
            task_code="TEST-123",
            source="test_script",
            text="This is a test message - Idempotent request",
        )
        result1 = executor.inbox_append(params, base_rev=initial_rev, request_id=request_id)
        assert result1["success"] == True
        rev1 = result1.get("rev")
        print(f"   First request successful. Rev: {rev1}")

        # Second request with same request_id - should return same result
        print("2. Second request with same request_id...")
        params = InboxAppendParams(
            date=test_date,
            task_code="TEST-123",
            source="test_script",
            text="This is a test message - Idempotent request (should not write again)",
        )
        result2 = executor.inbox_append(params, base_rev=rev1, request_id=request_id)
        assert result2["success"] == True
        rev2 = result2.get("rev")
        print(f"   Second request returned same result. Rev: {rev2}")
        assert rev1 == rev2  # Rev should not change

    print("Idempotency tests passed!\n")


def test_concurrency_control():
    """Test concurrency control with running_run_id"""
    print("=== Testing Concurrency Control ===")

    # Create temporary directories
    with tempfile.TemporaryDirectory() as temp_dir:
        repo_root = Path(temp_dir)
        inbox_dir = "inbox"
        board_file = "board.md"

        # Initialize ToolExecutor
        security = MockSecurity()
        audit = MockAuditLogger()
        executor = ToolExecutor(str(repo_root), inbox_dir, board_file, security, audit)

        # Test date
        test_date = datetime.now().strftime("%Y-%m-%d")

        # Get initial rev
        inbox_file = repo_root / inbox_dir / f"{test_date}.md"
        initial_rev = executor._get_file_rev(inbox_file)

        # 1. First request with running_run_id - should succeed and acquire lock
        print("1. First request with running_run_id...")
        run_id = "test_run_1"
        params = InboxAppendParams(
            date=test_date,
            task_code="TEST-123",
            source="test_script",
            text="This is a test message - First concurrent request",
        )
        result1 = executor.inbox_append(
            params, base_rev=initial_rev, request_id="test_concurrent_req_1", running_run_id=run_id
        )
        assert result1["success"] == True
        print("   First request successful, lock acquired")

        # 2. Second request with different running_run_id - should fail
        print("2. Second request with different running_run_id...")
        params = InboxAppendParams(
            date=test_date,
            task_code="TEST-123",
            source="test_script",
            text="This is a test message - Second concurrent request (should fail)",
        )
        result2 = executor.inbox_append(
            params,
            base_rev=initial_rev,
            request_id="test_concurrent_req_2",
            running_run_id="different_run",
        )
        assert result2["success"] == False
        assert result2.get("status") == 409
        print("   Second request failed as expected due to lock")

    print("Concurrency control tests passed!\n")


if __name__ == "__main__":
    try:
        test_version_control()
        test_idempotency()
        test_concurrency_control()
        print("=== All Tests Passed! ===")
        exit(0)
    except Exception as e:
        print(f"\n=== Test Failed: {e} ===")
        import traceback

        traceback.print_exc()
        exit(1)
