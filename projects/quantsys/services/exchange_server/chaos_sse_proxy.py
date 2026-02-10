#!/usr/bin/env python3
"""
Chaos test script to simulate proxy buffering causing SSE heartbeat delays
"""

import asyncio
import json
import os
import time
import uuid

import requests
from aiohttp import web

# Configuration
EXCHANGE_SERVER_HOST = "localhost"
EXCHANGE_SERVER_PORT = 8080
PROXY_PORT = 8083
BUFFER_DELAY = 15  # Seconds to delay buffer flushing
TEST_DURATION = 60  # Seconds to run the test
ARTIFACTS_DIR = os.path.join(os.path.dirname(__file__), "docs", "REPORT", "ci", "artifacts")
REPORT_NAME = "chaos_sse_proxy_report.json"


class SSEProxyBuffer:
    """Simulates a proxy with buffering that delays SSE messages"""

    def __init__(self):
        self.buffer = []
        self.flush_event = asyncio.Event()
        self.is_running = True
        self.last_flush = time.time()

    async def flush_buffer(self, response):
        """Flush the buffer to the client"""
        if self.buffer:
            # Send all buffered messages
            for msg in self.buffer:
                await response.write(msg)
            # Clear buffer
            self.buffer = []
            self.last_flush = time.time()

    async def proxy_handler(self, request):
        """Handle incoming SSE requests and proxy them with buffering"""
        # Create SSE response
        sse_response = web.StreamResponse(
            status=200,
            headers={
                "Content-Type": "text/event-stream",
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Proxy-Buffering": "simulated",
                "X-Trace-ID": request.headers.get("X-Trace-ID", str(uuid.uuid4())),
            },
        )
        await sse_response.prepare(request)

        # Forward request to exchange server
        exchange_url = f"http://{EXCHANGE_SERVER_HOST}:{EXCHANGE_SERVER_PORT}{request.path}"
        async with requests.Session() as session:
            try:
                # Stream response from exchange server
                with session.get(exchange_url, stream=True, headers=request.headers) as resp:
                    # Read and buffer SSE messages
                    buffer_task = asyncio.create_task(self.buffer_messages(resp, sse_response))
                    flush_task = asyncio.create_task(self.periodic_flush(sse_response))

                    # Wait for either task to complete
                    done, pending = await asyncio.wait(
                        [buffer_task, flush_task], return_when=asyncio.FIRST_COMPLETED
                    )

                    # Cancel remaining tasks
                    for task in pending:
                        task.cancel()
                        try:
                            await task
                        except asyncio.CancelledError:
                            pass
            except Exception as e:
                print(f"Proxy error: {e}")
            finally:
                await sse_response.write_eof()

        return sse_response

    async def buffer_messages(self, resp, response):
        """Buffer SSE messages from exchange server"""
        for line in resp.iter_lines():
            if line:
                # Add newline back if it was stripped
                if not line.endswith(b"\n"):
                    line += b"\n"
                self.buffer.append(line)

    async def periodic_flush(self, response):
        """Periodically flush the buffer"""
        while self.is_running:
            await asyncio.sleep(BUFFER_DELAY)
            await self.flush_buffer(response)


async def run_proxy():
    """Run the simulated proxy server"""
    buffer = SSEProxyBuffer()
    app = web.Application()
    app.router.add_get("/sse", buffer.proxy_handler)
    app.router.add_get("/mcp/messages", buffer.proxy_handler)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PROXY_PORT)
    await site.start()

    print(f"Simulated SSE proxy running on port {PROXY_PORT} with {BUFFER_DELAY}s buffer delay")

    return runner, buffer


async def test_sse_through_proxy():
    """Test SSE through the simulated proxy"""
    # Start proxy
    runner, buffer = await run_proxy()

    try:
        # Connect to proxy SSE endpoint
        proxy_url = f"http://localhost:{PROXY_PORT}/sse"
        headers = {
            "X-Trace-ID": str(uuid.uuid4()),
            "Authorization": "Bearer default_secret_token",  # Use default token for testing
        }

        print(f"Connecting to SSE proxy at {proxy_url}")

        # Track events and anomalies
        events = []
        anomalies = []
        start_time = time.time()

        with requests.Session() as session:
            with session.get(proxy_url, stream=True, headers=headers) as resp:
                event_type = "message"
                data_buffer = []

                # Read SSE events
                while time.time() - start_time < TEST_DURATION:
                    line = resp.raw.readline()
                    if not line:
                        break

                    line = line.decode("utf-8").rstrip()

                    if not line:
                        # End of event
                        if data_buffer:
                            data = "\n".join(data_buffer)
                            try:
                                event_data = json.loads(data)
                            except json.JSONDecodeError:
                                event_data = data

                            event = {
                                "type": event_type,
                                "data": event_data,
                                "timestamp": time.time(),
                            }
                            events.append(event)

                            # Check for anomalies
                            if event_type == "heartbeat":
                                if isinstance(event_data, dict):
                                    if event_data.get("heartbeat_delay_anomaly"):
                                        anomalies.append(
                                            {
                                                "type": "heartbeat_delay",
                                                "data": event_data,
                                                "timestamp": time.time(),
                                            }
                                        )
                                    if event_data.get("proxy_buffering_risk"):
                                        anomalies.append(
                                            {
                                                "type": "proxy_buffering",
                                                "data": event_data,
                                                "timestamp": time.time(),
                                            }
                                        )

                        # Reset for next event
                        event_type = "message"
                        data_buffer = []
                    elif line.startswith("event:"):
                        event_type = line[6:].strip()
                    elif line.startswith("data:"):
                        data_buffer.append(line[5:].strip())
    finally:
        # Stop proxy
        await runner.cleanup()

    return events, anomalies


def generate_report(events, anomalies):
    """Generate chaos test report"""
    report = {
        "test_name": "CHAOS-SSE-PROXY-BUFFER",
        "test_version": "v0.1",
        "test_date": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "configuration": {
            "proxy_buffer_delay": BUFFER_DELAY,
            "test_duration": TEST_DURATION,
            "exchange_server": f"http://{EXCHANGE_SERVER_HOST}:{EXCHANGE_SERVER_PORT}",
            "proxy_server": f"http://localhost:{PROXY_PORT}",
        },
        "results": {
            "total_events": len(events),
            "anomalies": len(anomalies),
            "heartbeat_events": len([e for e in events if e["type"] == "heartbeat"]),
            "proxy_buffering_anomalies": len(
                [a for a in anomalies if a["type"] == "proxy_buffering"]
            ),
            "heartbeat_delay_anomalies": len(
                [a for a in anomalies if a["type"] == "heartbeat_delay"]
            ),
        },
        "anomalies": anomalies,
        "events": events[:10],  # Include first 10 events as sample
    }

    # Create artifacts directory if it doesn't exist
    os.makedirs(ARTIFACTS_DIR, exist_ok=True)

    # Write report to file
    report_path = os.path.join(ARTIFACTS_DIR, REPORT_NAME)
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    print(f"Report generated: {report_path}")
    return report


def write_spec():
    """Write specification document"""
    spec_content = f"""# CHAOS-SSE-PROXY-BUFFER Specification

## Overview
This specification defines a chaos test to simulate proxy buffering causing SSE heartbeat delays in the exchange server.

## Test Objective
- Simulate a reverse proxy with buffering that delays SSE messages
- Verify that the exchange server detects heartbeat delay anomalies
- Verify that the exchange server detects proxy buffering risks
- Generate a report with test results and anomalies

## Test Configuration
- **Proxy Buffer Delay**: {BUFFER_DELAY} seconds
- **Test Duration**: {TEST_DURATION} seconds
- **Exchange Server**: http://{EXCHANGE_SERVER_HOST}:{EXCHANGE_SERVER_PORT}
- **Proxy Server**: http://localhost:{PROXY_PORT}

## Test Steps
1. Start the simulated SSE proxy with configured buffer delay
2. Connect to the proxy's SSE endpoint
3. Monitor SSE events for anomalies
4. Check for:
   - Heartbeat delay anomalies (delay > 2x expected interval)
   - Proxy buffering risks (no buffer flush for >60 seconds with pending messages)
5. Generate a report with test results

## Expected Results
- The exchange server should detect heartbeat delay anomalies
- The exchange server should detect proxy buffering risks
- The test should generate a comprehensive report with all detected anomalies

## Report Format
The test generates a JSON report at `{ARTIFACTS_DIR}/{REPORT_NAME}` with the following structure:
- Test configuration
- Results summary
- Detailed anomalies list
- Sample events

## Exit Code
- `0`: Test passed (anomalies detected as expected)
- `1`: Test failed (no anomalies detected or unexpected errors)
"""

    spec_dir = os.path.join(os.path.dirname(__file__), "docs", "SPEC", "ci")
    os.makedirs(spec_dir, exist_ok=True)
    spec_path = os.path.join(spec_dir, "chaos_sse_proxy__v0.1__20260116.md")

    with open(spec_path, "w") as f:
        f.write(spec_content)

    print(f"Specification written: {spec_path}")
    return spec_path


async def main():
    """Main test function"""
    print("Starting CHAOS-SSE-PROXY-BUFFER test...")

    # Run test
    events, anomalies = await test_sse_through_proxy()

    # Generate report
    report = generate_report(events, anomalies)

    # Write specification
    write_spec()

    # Verify test results
    if report["results"]["anomalies"] > 0:
        print(f"✓ Test passed: {report['results']['anomalies']} anomalies detected")
        print(f"  - Heartbeat delay anomalies: {report['results']['heartbeat_delay_anomalies']}")
        print(f"  - Proxy buffering anomalies: {report['results']['proxy_buffering_anomalies']}")
        exit(0)
    else:
        print("✗ Test failed: No anomalies detected")
        exit(1)


if __name__ == "__main__":
    asyncio.run(main())
