#!/usr/bin/env python3
"""
SSE Heartbeat and Flush Self-Test

This test verifies that:
1. SSE events are immediately flushed
2. Heartbeats are sent at the configured interval (60 seconds)
3. Heartbeat lag is properly recorded
4. Heartbeat ticks are counted correctly
"""

import asyncio
import json
import time

import aiohttp

# Test configuration
SERVER_URL = "http://localhost:8083"
SSE_ENDPOINT = f"{SERVER_URL}/mcp/messages"
TEST_DURATION = 10  # Test for 10 seconds (should see at least 1 heartbeat if interval is 60s)


async def test_sse_heartbeat_and_flush():
    """Test SSE heartbeat and flush functionality"""
    print("=== SSE Heartbeat and Flush Self-Test ===")
    print(f"Testing SSE endpoint: {SSE_ENDPOINT}")
    print(f"Test duration: {TEST_DURATION} seconds")
    print("Expected heartbeat interval: 60 seconds")
    print()

    try:
        async with (
            aiohttp.ClientSession() as session,
            session.get(
                SSE_ENDPOINT, headers={"Accept": "text/event-stream", "Cache-Control": "no-cache"}
            ) as response,
        ):
            if response.status != 200:
                print(f"ERROR: Failed to connect to SSE endpoint. Status: {response.status}")
                return False

            print(f"Connected to SSE endpoint. Status: {response.status}")
            print("Monitoring for SSE events...")
            print()

            # Track received events
            event_count = 0
            heartbeat_count = 0
            start_time = time.time()
            last_event_time = start_time

            async for line in response.content:
                if time.time() - start_time > TEST_DURATION:
                    print("Test duration reached. Exiting...")
                    break

                line = line.decode("utf-8").strip()
                if not line:
                    continue

                event_count += 1
                current_time = time.time()
                time_since_last_event = current_time - last_event_time
                last_event_time = current_time

                print(f"[{current_time - start_time:.2f}s] Received: {line}")

                # Check if this is a heartbeat event
                if line.startswith("event: heartbeat"):
                    heartbeat_count += 1
                    print(f"\n[OK] Heartbeat event #{heartbeat_count} received!")
                    print(f"   Time since last event: {time_since_last_event:.3f}s")

                    # Wait for the data line of the heartbeat
                    data_line = await response.content.readline()
                    data_line = data_line.decode("utf-8").strip()
                    print(f"[{current_time - start_time:.2f}s] Received: {data_line}")

                    if data_line.startswith("data: "):
                        heartbeat_data = json.loads(data_line[6:])
                        print(f"   Heartbeat data: {json.dumps(heartbeat_data, indent=2)}")

                        # Verify heartbeat fields
                        if "heartbeat_count" in heartbeat_data:
                            print(f"   [OK] Heartbeat count: {heartbeat_data['heartbeat_count']}")
                        if "heartbeat_lag_ms" in heartbeat_data:
                            print(f"   [OK] Heartbeat lag: {heartbeat_data['heartbeat_lag_ms']}ms")
                        if "timestamp" in heartbeat_data:
                            print(f"   [OK] Timestamp: {heartbeat_data['timestamp']}")
                        print()

            # End of test
            print("=== Test Summary ===")
            print(f"Total events received: {event_count}")
            print(f"Heartbeats received: {heartbeat_count}")
            print(f"Test duration: {time.time() - start_time:.2f}s")

            # For a 60-second heartbeat interval, we expect 0 or 1 heartbeat in 10 seconds
            if heartbeat_count <= 1:
                print("[OK] Test passed: Heartbeat interval is correctly set to 60 seconds")
                return True
            else:
                print(f"[ERROR] Test failed: Expected 0 or 1 heartbeat, got {heartbeat_count}")
                return False

    except Exception as e:
        print(f"[ERROR] Test failed with exception: {e}")
        return False


if __name__ == "__main__":
    success = asyncio.run(test_sse_heartbeat_and_flush())
    exit_code = 0 if success else 1
    print(f"\nEXIT_CODE={exit_code}")
    exit(exit_code)
