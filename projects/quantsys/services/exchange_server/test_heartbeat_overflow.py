#!/usr/bin/env python3
"""
Simple Heartbeat Queue Overflow Test for SSE Backpressure Buffering

This script tests the SSE backpressure buffering by:
1. Connecting to the SSE endpoint
2. Processing messages VERY slowly
3. Allowing heartbeat messages to fill the queue
4. Verifying queue overflow handling
"""

import asyncio
import json
import sys
import time

import aiohttp


async def heartbeat_overflow_test(max_queue_size=5, process_delay=4, test_duration=20):
    """
    Test queue overflow using only heartbeat messages

    Args:
        max_queue_size: Expected max queue size from server config
        process_delay: Delay between processing messages (seconds) - longer than heartbeat interval
        test_duration: Duration of test (seconds)
    """

    sse_url = "http://localhost:8081/sse"

    print("Starting HEARTBEAT QUEUE OVERFLOW TEST")
    print(f"Target URL: {sse_url}")
    print(f"Message processing delay: {process_delay}s (longer than heartbeat interval)")
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

                                    event_type = event_data.get("type")

                                    if event_type == "heartbeat":
                                        heartbeats_received += 1

                                        # Check for queue overflow
                                        queue_overflow = event_data.get("queue_overflow", False)
                                        if queue_overflow:
                                            queue_overflows += 1
                                            print("📊 HEARTBEAT WITH QUEUE OVERFLOW DETECTED!")
                                            print(
                                                f"   Queue size: {event_data.get('queue_size', 0)}/{max_queue_size}"
                                            )
                                            print(f"   Timestamp: {event_data.get('timestamp')}")
                                            print(
                                                f"   Heartbeat delay: {event_data.get('heartbeat_delay', 0):.2f}s"
                                            )
                                            print(
                                                f"   Delay anomaly: {event_data.get('heartbeat_delay_anomaly', False)}"
                                            )
                                            print(
                                                f"   Proxy buffering risk: {event_data.get('proxy_buffering_risk', False)}"
                                            )

                                        print(
                                            f"💓 Heartbeat #{heartbeats_received}: Queue={event_data.get('queue_size', 0)}/{max_queue_size}, Overflow={event_data.get('queue_overflow', False)}"
                                        )

                                    elif event_type == "disconnect":
                                        disconnect_events += 1
                                        reason = event_data.get("reason")
                                        print("🔌 DISCONNECT EVENT RECEIVED:")
                                        print(f"   Reason: {reason}")
                                        print(f"   Message: {event_data.get('message')}")

                                        if reason == "queue_overflow":
                                            print("✅ QUEUE OVERFLOW DISCONNECT TEST PASSED!")
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

                                    # Simulate VERY slow consumption (slower than heartbeat interval)
                                    print(
                                        f"⏳ Processing event {events_received}, sleeping for {process_delay}s..."
                                    )
                                    await asyncio.sleep(process_delay)

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
    print("=" * 60)

    # Verify test outcomes
    if queue_overflows > 0:
        print("✅ Queue overflow detection working correctly")
        return 0
    else:
        print("❌ No queue overflow events detected - test FAILED")
        return 1


if __name__ == "__main__":
    # Run the test
    exit_code = asyncio.run(
        heartbeat_overflow_test(max_queue_size=5, process_delay=4, test_duration=20)
    )
    sys.exit(exit_code)
