#!/usr/bin/env python3
"""
Slow Consumer Test for SSE Backpressure Buffering

This script tests the SSE backpressure buffering by:
1. Connecting to the SSE endpoint
2. Simulating a slow consumer by adding delays
3. Monitoring queue overflow events
4. Verifying the server handles backpressure correctly
"""

import asyncio
import json
import sys
import time

import aiohttp


async def slow_consumer_test(max_queue_size=100, delay=0.5, test_duration=60):
    """
    Test SSE backpressure with a slow consumer

    Args:
        max_queue_size: Expected max queue size from server config
        delay: Delay between processing messages (seconds)
        test_duration: Duration of test (seconds)
    """

    sse_url = "http://localhost:8081/sse"

    print("Starting SSE Slow Consumer Test")
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

                                        # Check for heartbeat delay anomaly
                                        if event_data.get("heartbeat_delay_anomaly", False):
                                            print("⚠️  Heartbeat delay anomaly detected!")
                                            print(
                                                f"   Delay: {event_data.get('heartbeat_delay', 0):.2f}s"
                                            )

                                        # Check for proxy buffering risk
                                        if event_data.get("proxy_buffering_risk", False):
                                            print("⚠️  Proxy buffering risk detected!")

                                        # Print heartbeat info every 5 seconds
                                        if heartbeats_received % 5 == 0:
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

                                        # Verify max queue size matches expected
                                        server_max_queue = event_data.get("max_queue_size")
                                        if server_max_queue != max_queue_size:
                                            print(
                                                f"⚠️  Server max queue size ({server_max_queue}) differs from expected ({max_queue_size})"
                                            )

                                    # Simulate slow consumer by adding delay
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
        print("⚠️  No queue overflow events detected (expected with slow consumer)")

    if disconnect_events > 0:
        print("✅ Disconnect on queue overflow working correctly")
    else:
        print("⚠️  No disconnect events detected (expected if queue overflow threshold not reached)")

    return 0


if __name__ == "__main__":
    # Parse command line arguments
    import argparse

    parser = argparse.ArgumentParser(
        description="SSE Slow Consumer Test for Backpressure Buffering"
    )
    parser.add_argument("--max-queue", type=int, default=100, help="Expected max queue size")
    parser.add_argument(
        "--delay", type=float, default=0.5, help="Message processing delay in seconds"
    )
    parser.add_argument("--duration", type=int, default=60, help="Test duration in seconds")

    args = parser.parse_args()

    # Run the test
    exit_code = asyncio.run(
        slow_consumer_test(
            max_queue_size=args.max_queue, delay=args.delay, test_duration=args.duration
        )
    )

    sys.exit(exit_code)
