#!/usr/bin/env python3
"""
Aggressive Queue Overflow Test for SSE Backpressure Buffering

This script tests the SSE backpressure buffering by:
1. Connecting to the SSE endpoint
2. Simulating a very slow consumer
3. Forcing message queue overflow
4. Verifying the server handles backpressure correctly
"""

import asyncio
import json
import sys
import time

import aiohttp


async def aggressive_overflow_test(max_queue_size=5, delay=2, test_duration=30):
    """
    Test SSE backpressure with an aggressive slow consumer to force queue overflow

    Args:
        max_queue_size: Expected max queue size from server config (set to small value)
        delay: Delay between processing messages (seconds) - longer delay
        test_duration: Duration of test (seconds)
    """

    sse_url = "http://localhost:8081/sse"

    print("Starting AGGRESSIVE SSE Queue Overflow Test")
    print(f"Target URL: {sse_url}")
    print(f"Message processing delay: {delay}s")
    print(f"Test duration: {test_duration}s")
    print(f"Expected max queue size: {max_queue_size}")
    print("=" * 60)

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(sse_url) as response:
                if response.status != 200:
                    print(f"❌ Connection failed with status: {response.status}")
                    return 1

                print("✅ Connected to SSE endpoint")
                print(f"Headers: {dict(response.headers)}")
                print("\nListening for SSE events...")
                print("=" * 60)

                # Event counters
                events_received = 0
                heartbeats_received = 0
                queue_overflows = 0
                disconnect_events = 0

                start_time = time.time()
                buffer = b""

                async for chunk in response.content:
                    current_time = time.time()
                    if current_time - start_time > test_duration:
                        print("\n✅ Test completed successfully")
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

                                    # Handle different event types
                                    event_type = event_data.get("type")
                                    if event_type == "heartbeat":
                                        heartbeats_received += 1

                                        # Check for queue overflow events
                                        queue_overflow = event_data.get("queue_overflow", False)
                                        if queue_overflow:
                                            queue_overflows += 1
                                            print("📊 Heartbeat with queue overflow detected!")
                                            print(
                                                f"   Queue size: {event_data.get('queue_size', 0)}/{max_queue_size}"
                                            )
                                            print(f"   Timestamp: {event_data.get('timestamp')}")

                                        # Print heartbeat info
                                        print(f"💓 Heartbeat #{heartbeats_received}:")
                                        print(
                                            f"   Queue size: {event_data.get('queue_size', 0)}/{max_queue_size}"
                                        )
                                        print(
                                            f"   Queue overflow: {event_data.get('queue_overflow', False)}"
                                        )
                                        print(
                                            f"   Heartbeat delay: {event_data.get('heartbeat_delay', 0):.2f}s"
                                        )
                                        print(
                                            f"   Delay anomaly: {event_data.get('heartbeat_delay_anomaly', False)}"
                                        )
                                        print(
                                            f"   Proxy buffering risk: {event_data.get('proxy_buffering_risk', False)}"
                                        )

                                    elif event_type == "disconnect":
                                        disconnect_events += 1
                                        reason = event_data.get("reason")
                                        print("🔌 Disconnect event received:")
                                        print(f"   Reason: {reason}")
                                        print(f"   Message: {event_data.get('message')}")

                                        if reason == "queue_overflow":
                                            print("✅ Queue overflow disconnect test PASSED")
                                            # Test complete if we got disconnect event
                                            return 0

                                    elif event_type == "connection":
                                        print("🔗 Connection established:")
                                        print(f"   Auth mode: {event_data.get('auth_mode')}")
                                        print(f"   Trace ID: {event_data.get('trace_id')}")
                                        print(f"   Client ID: {event_data.get('client_id')}")
                                        print(
                                            f"   Connection count: {event_data.get('connection_count')}"
                                        )
                                        print(
                                            f"   Max queue size: {event_data.get('max_queue_size')}"
                                        )

                                    # Simulate very slow consumer by adding long delay
                                    print(f"⏳ Processing message, sleeping for {delay}s...")
                                    await asyncio.sleep(delay)

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
    print(f"Heartbeats received: {heartbeats_received}")
    print(f"Queue overflow events: {queue_overflows}")
    print(f"Disconnect events: {disconnect_events}")
    print(f"Test duration: {test_duration}s")
    print("=" * 60)

    # Verify test outcomes
    if queue_overflows > 0:
        print("✅ Queue overflow detection working correctly")
    else:
        print("❌ No queue overflow events detected - test FAILED")
        return 1

    if disconnect_events > 0:
        print("✅ Disconnect on queue overflow working correctly")
        return 0
    else:
        print(
            "⚠️  No disconnect events detected - server may not be configured to disconnect on overflow"
        )
        return 1


async def message_generator():
    """
    Generate test messages to send to SSE endpoint to fill queue
    """
    sse_url = "http://localhost:8081/mcp"

    try:
        async with aiohttp.ClientSession() as session:
            # Create multiple tasks to generate messages
            for i in range(20):
                # Send JSON-RPC requests to trigger messages
                payload = {
                    "jsonrpc": "2.0",
                    "id": f"test-{i}",
                    "method": "ata.search",
                    "params": {"query": f"test-query-{i}"},
                }

                headers = {
                    "Content-Type": "application/json",
                    "Authorization": "Bearer default_secret_token",
                }

                async with session.post(sse_url, json=payload, headers=headers) as response:
                    if response.status == 200:
                        print(f"📤 Message generator sent request {i + 1}/20")
                    await asyncio.sleep(0.5)  # Small delay between requests
    except Exception as e:
        print(f"❌ Message generator error: {e}")


async def main():
    """
    Run both consumer and message generator in parallel
    """
    # Create tasks for both consumer and generator
    consumer_task = aggressive_overflow_test(max_queue_size=5, delay=2, test_duration=30)
    generator_task = message_generator()

    # Run both tasks in parallel
    await asyncio.gather(consumer_task, generator_task)


if __name__ == "__main__":
    # Run the test
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
