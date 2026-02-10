import time
from datetime import datetime

import requests

BASE_URL = "http://localhost:18788/"
TEST_DATE = datetime.now().strftime("%Y-%m-%d")
TEST_TASK_CODE = "TEST-123"
TEST_SOURCE = "test_script"
TEST_TEXT = "This is a test message"


def test_version_control():
    """Test version control functionality"""
    print("=== Testing Version Control ===")

    # 1. Get initial rev
    print("1. Getting initial revision...")
    tail_response = requests.post(f"{BASE_URL}/api/inbox_tail", json={"date": TEST_DATE})
    assert tail_response.status_code == 200
    tail_data = tail_response.json()
    initial_rev = tail_data.get("rev", "0")
    print(f"   Initial rev: {initial_rev}")

    # 2. Write with correct base_rev - should succeed
    print("2. Writing with correct base_rev...")
    append_response = requests.post(
        f"{BASE_URL}/api/inbox_append?base_rev={initial_rev}&request_id=test_req_{time.time()}_1",
        json={
            "date": TEST_DATE,
            "task_code": TEST_TASK_CODE,
            "source": TEST_SOURCE,
            "text": f"{TEST_TEXT} - Version 1",
        },
    )
    assert append_response.status_code == 200
    append_data = append_response.json()
    assert append_data["success"] == True
    new_rev = append_data.get("rev")
    print(f"   Write successful. New rev: {new_rev}")
    assert new_rev != initial_rev

    # 3. Write with wrong base_rev - should fail with 409
    print("3. Writing with wrong base_rev...")
    append_response = requests.post(
        f"{BASE_URL}/api/inbox_append?base_rev={initial_rev}&request_id=test_req_{time.time()}_2",
        json={
            "date": TEST_DATE,
            "task_code": TEST_TASK_CODE,
            "source": TEST_SOURCE,
            "text": f"{TEST_TEXT} - Version 2 (should fail)",
        },
    )
    assert append_response.status_code == 200
    append_data = append_response.json()
    assert append_data["success"] == False
    assert append_data.get("status") == 409
    print("   Write failed as expected with 409")

    print("Version control tests passed!\n")


def test_idempotency():
    """Test request idempotency"""
    print("=== Testing Request Idempotency ===")

    # Get current rev
    tail_response = requests.post(f"{BASE_URL}/api/inbox_tail", json={"date": TEST_DATE})
    current_rev = tail_response.json().get("rev", "0")

    # Use the same request_id for two requests
    request_id = f"test_idempotent_req_{time.time()}"

    # First request - should succeed
    print("1. First request with new request_id...")
    append_response1 = requests.post(
        f"{BASE_URL}/api/inbox_append?base_rev={current_rev}&request_id={request_id}",
        json={
            "date": TEST_DATE,
            "task_code": TEST_TASK_CODE,
            "source": TEST_SOURCE,
            "text": f"{TEST_TEXT} - Idempotent request",
        },
    )
    assert append_response1.status_code == 200
    data1 = append_response1.json()
    assert data1["success"] == True
    rev1 = data1.get("rev")
    print(f"   First request successful. Rev: {rev1}")

    # Second request with same request_id - should return same result
    print("2. Second request with same request_id...")
    append_response2 = requests.post(
        f"{BASE_URL}/api/inbox_append?base_rev={rev1}&request_id={request_id}",
        json={
            "date": TEST_DATE,
            "task_code": TEST_TASK_CODE,
            "source": TEST_SOURCE,
            "text": f"{TEST_TEXT} - Idempotent request (should not write again)",
        },
    )
    assert append_response2.status_code == 200
    data2 = append_response2.json()
    assert data2["success"] == True
    rev2 = data2.get("rev")
    print(f"   Second request returned same result. Rev: {rev2}")
    assert rev1 == rev2  # Rev should not change

    print("Idempotency tests passed!\n")


def test_concurrency_control():
    """Test concurrency control with running_run_id"""
    print("=== Testing Concurrency Control ===")

    # Get current rev
    tail_response = requests.post(f"{BASE_URL}/api/inbox_tail", json={"date": TEST_DATE})
    current_rev = tail_response.json().get("rev", "0")

    # First request with running_run_id - should succeed and acquire lock
    print("1. First request with running_run_id...")
    run_id = f"test_run_{time.time()}"
    append_response1 = requests.post(
        f"{BASE_URL}/api/inbox_append?base_rev={current_rev}&request_id=test_concurrent_req_1_{time.time()}&running_run_id={run_id}",
        json={
            "date": TEST_DATE,
            "task_code": TEST_TASK_CODE,
            "source": TEST_SOURCE,
            "text": f"{TEST_TEXT} - First concurrent request",
        },
    )
    assert append_response1.status_code == 200
    data1 = append_response1.json()
    assert data1["success"] == True
    print("   First request successful, lock acquired")

    # Second request with different running_run_id - should fail
    print("2. Second request with different running_run_id...")
    append_response2 = requests.post(
        f"{BASE_URL}/api/inbox_append?base_rev={current_rev}&request_id=test_concurrent_req_2_{time.time()}&running_run_id=different_run_{time.time()}",
        json={
            "date": TEST_DATE,
            "task_code": TEST_TASK_CODE,
            "source": TEST_SOURCE,
            "text": f"{TEST_TEXT} - Second concurrent request (should fail)",
        },
    )
    assert append_response2.status_code == 200
    data2 = append_response2.json()
    assert data2["success"] == False
    assert data2.get("status") == 409
    print("   Second request failed as expected due to lock")

    print("Concurrency control tests passed!\n")


if __name__ == "__main__":
    try:
        test_version_control()
        test_idempotency()
        test_concurrency_control()
        print("\n=== All Tests Passed! ===")
        exit(0)
    except Exception as e:
        print(f"\n=== Test Failed: {e} ===")
        import traceback

        traceback.print_exc()
        exit(1)
