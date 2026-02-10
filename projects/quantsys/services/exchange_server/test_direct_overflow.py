#!/usr/bin/env python3
"""
Direct Queue Overflow Test for SSE Backpressure Buffering

This script directly tests the SSE backpressure buffering by:
1. Creating a very slow consumer
2. Directly filling the queue with messages
3. Verifying queue overflow handling
"""

import asyncio
import json
import sys
import time

import aiohttp


async def direct_overflow_test():
    """
    Directly test queue overflow by filling the queue faster than consumption
    """

    sse_url = "http://localhost:8081/sse"
    max_queue_size = 5

    print("Starting DIRECT SSE Queue Overflow Test")
    print(f"Target URL: {sse_url}")
    print(f"Expected max queue size: {max_queue_size}")
    print("=" * 60)

    try:
        # Create a session
        session = aiohttp.ClientSession()

        # Start a slow consumer
        print("Starting slow consumer...")
        consumer_response = await session.get(sse_url)

        if consumer_response.status != 200:
            print(f"❌ Consumer connection failed with status: {consumer_response.status}")
            return 1

        print("✅ Consumer connected")

        # Wait a moment for connection to establish
        await asyncio.sleep(1)

        # Now send multiple requests quickly to fill the queue
        print("\nSending 20 requests quickly to fill queue...")

        mcp_url = "http://localhost:8081/mcp"

        for i in range(20):
            payload = {
                "jsonrpc": "2.0",
                "id": f"direct-test-{i}",
                "method": "ata.search",
                "params": {"query": f"test-query-{i}"},
            }

            headers = {
                "Content-Type": "application/json",
                "Authorization": "Bearer default_secret_token",
            }

            try:
                response = await session.post(mcp_url, json=payload, headers=headers)
                if response.status == 200:
                    print(f"📤 Sent request {i + 1}/20")
                else:
                    print(f"❌ Request {i + 1}/20 failed: {response.status}")
            except Exception as e:
                print(f"❌ Request {i + 1}/20 error: {e}")

            # Small delay between requests
            await asyncio.sleep(0.1)

        print("\nAll requests sent. Now processing SSE events with slow consumer...")
        print("=" * 60)

        # Now process SSE events with very slow consumer
        events_received = 0
        queue_overflows = 0
        disconnect_events = 0

        start_time = time.time()
        buffer = b""

        async for chunk in consumer_response.content:
            current_time = time.time()
            if current_time - start_time > 60:  # Timeout after 60 seconds
                print("\n⏰ Test timed out after 60 seconds")
                break

            buffer += chunk
            lines = buffer.split(b"\n")
            buffer = lines.pop()

            for line in lines:
                line = line.strip()
                if not line:
                    continue

                if line.startswith(b"data:"):
                    data = line[5:].strip()
                    if data:
                        try:
                            event_data = json.loads(data)
                            events_received += 1

                            event_type = event_data.get("type")

                            if event_type == "heartbeat":
                                # Check for queue overflow in heartbeat
                                queue_overflow = event_data.get("queue_overflow", False)
                                if queue_overflow:
                                    queue_overflows += 1
                                    print("📊 HEARTBEAT WITH QUEUE OVERFLOW DETECTED!")
                                    print(
                                        f"   Queue size: {event_data.get('queue_size', 0)}/{max_queue_size}"
                                    )
                                    print(f"   Timestamp: {event_data.get('timestamp')}")

                                print(
                                    f"💓 Heartbeat: Queue={event_data.get('queue_size', 0)}/{max_queue_size}, Overflow={event_data.get('queue_overflow', False)}"
                                )

                            elif event_type == "disconnect":
                                disconnect_events += 1
                                reason = event_data.get("reason")
                                print("🔌 DISCONNECT EVENT RECEIVED:")
                                print(f"   Reason: {reason}")
                                print(f"   Message: {event_data.get('message')}")

                                if reason == "queue_overflow":
                                    print("✅ QUEUE OVERFLOW DISCONNECT TEST PASSED!")
                                    await session.close()
                                    return 0

                            # Simulate very slow consumption
                            print(f"⏳ Processing event {events_received}, sleeping for 3s...")
                            await asyncio.sleep(3)

                        except json.JSONDecodeError as e:
                            print(f"❌ JSON decode error: {e}")
                            print(f"   Raw data: {data}")

    except aiohttp.ClientError as e:
        print(f"❌ Client error: {e}")
        return 1
    except KeyboardInterrupt:
        print("\n⚠️  Test interrupted by user")
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        import traceback

        traceback.print_exc()
        return 1

    # Print final results
    print("\n" + "=" * 60)
    print("FINAL TEST RESULTS")
    print("=" * 60)
    print(f"Total events received: {events_received}")
    print(f"Queue overflow events: {queue_overflows}")
    print(f"Disconnect events: {disconnect_events}")
    print("=" * 60)

    # Verify outcomes
    if queue_overflows > 0:
        print("✅ Queue overflow detection working correctly")
        return 0
    else:
        print("❌ No queue overflow events detected - test FAILED")
        return 1


if __name__ == "__main__":
    # Run the test
    exit_code = asyncio.run(direct_overflow_test())
    sys.exit(exit_code)
