#!/usr/bin/env python3
"""
Trace ID End-to-End Test Script

Tests the Trace ID functionality across the exchange server ecosystem.
"""

import asyncio
import json
import subprocess
import time
import uuid

from aiohttp import ClientSession

# Project root directory
PROJECT_ROOT = "d:/quantsys"


async def run_server():
    """Start the exchange server in the background"""
    server_cmd = "python -m tools.exchange_server.main"
    return subprocess.Popen(
        server_cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=PROJECT_ROOT
    )


async def test_jsonrpc_with_trace_id():
    """Test JSON-RPC with Trace ID"""
    url = "http://localhost:18788/mcp"
    custom_trace_id = str(uuid.uuid4())

    payload = {
        "jsonrpc": "2.0",
        "id": "1",
        "method": "tools/call",
        "params": {"tool_call": {"name": "ata.search", "params": {"query": "ATA"}}},
    }
    headers = {"Authorization": "Bearer default_secret_token", "X-Trace-ID": custom_trace_id}

    async with ClientSession() as session:
        async with session.post(url, json=payload, headers=headers) as response:
            status = response.status
            body = await response.json()

            print(f"JSON-RPC Response Status: {status}")
            print(f"JSON-RPC Response Headers: {dict(response.headers)}")
            print(f"JSON-RPC Response Body: {json.dumps(body, indent=2)}")

            # Verify Trace ID is returned in response
            if (
                "X-Trace-ID" in response.headers
                and response.headers["X-Trace-ID"] == custom_trace_id
            ):
                print(f"✓ Trace ID correctly returned in response headers: {custom_trace_id}")
            else:
                print("✗ Trace ID mismatch in response headers")

            # Verify Trace ID is in the response body
            if (
                "result" in body
                and "tool_result" in body["result"]
                and "trace_id" in body["result"]["tool_result"]
            ):
                if body["result"]["tool_result"]["trace_id"] == custom_trace_id:
                    print(f"✓ Trace ID correctly returned in response body: {custom_trace_id}")
                else:
                    print("✗ Trace ID mismatch in response body")
            else:
                print("✗ Trace ID not found in response body")

            return status == 200


async def test_sse_with_trace_id():
    """Test SSE with Trace ID"""
    url = "http://localhost:18788/sse"
    custom_trace_id = str(uuid.uuid4())

    headers = {"X-Trace-ID": custom_trace_id}

    async with ClientSession() as session, session.get(url, headers=headers) as response:
        status = response.status

        print(f"SSE Response Status: {status}")
        print(f"SSE Response Headers: {dict(response.headers)}")

        # Verify Trace ID is returned in response headers
        if "X-Trace-ID" in response.headers and response.headers["X-Trace-ID"] == custom_trace_id:
            print(f"✓ Trace ID correctly returned in SSE response headers: {custom_trace_id}")
        else:
            print("✗ Trace ID mismatch in SSE response headers")

        # Read first few lines of SSE response
        data = b""
        event_count = 0
        async for line in response.content:
            data += line
            if line == b"\n" and b"data:" in data:
                event_count += 1
                if event_count >= 1:
                    break

        # Parse SSE data
        sse_data = data.decode()
        print(f"SSE Initial Response: {sse_data}")

        # Check if trace_id is in the SSE response
        if custom_trace_id in sse_data:
            print(f"✓ Trace ID found in SSE data: {custom_trace_id}")
        else:
            print("✗ Trace ID not found in SSE data")

        return status == 200


async def test_ata_fetch_with_trace_id():
    """Test ata.fetch with Trace ID"""
    url = "http://localhost:18788/mcp"
    custom_trace_id = str(uuid.uuid4())

    # Use a valid task code from the ATA ledger
    # Note: This assumes there's a valid task code in the ledger
    test_task_code = "EXCHANGE-A2A-BRIDGE-v0.1__20260115"

    payload = {
        "jsonrpc": "2.0",
        "id": "2",
        "method": "tools/call",
        "params": {"tool_call": {"name": "ata.fetch", "params": {"task_code": test_task_code}}},
    }
    headers = {"Authorization": "Bearer default_secret_token", "X-Trace-ID": custom_trace_id}

    async with ClientSession() as session:
        async with session.post(url, json=payload, headers=headers) as response:
            status = response.status
            body = await response.json()

            print(f"ata.fetch Response Status: {status}")
            print(f"ata.fetch Response Headers: {dict(response.headers)}")

            # Verify Trace ID is returned in response
            if (
                "X-Trace-ID" in response.headers
                and response.headers["X-Trace-ID"] == custom_trace_id
            ):
                print(
                    f"✓ Trace ID correctly returned in ata.fetch response headers: {custom_trace_id}"
                )
            else:
                print("✗ Trace ID mismatch in ata.fetch response headers")

            return status == 200


async def main():
    """Main test function"""
    print("# Trace ID End-to-End Test")
    print(f"TIMESTAMP={time.strftime('%Y-%m-%dT%H:%M:%S')}")
    print()

    # Start the server
    print("## Starting Exchange Server...")
    server_process = await run_server()
    time.sleep(2)  # Wait for server to start

    try:
        # Run tests
        print("\n## Testing JSON-RPC with Trace ID")
        await test_jsonrpc_with_trace_id()

        print("\n## Testing SSE with Trace ID")
        await test_sse_with_trace_id()

        print("\n## Testing ata.fetch with Trace ID")
        await test_ata_fetch_with_trace_id()

        print("\n## All Tests Completed!")

    finally:
        # Stop the server
        print("\n## Stopping Exchange Server...")
        server_process.terminate()
        try:
            server_process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            server_process.kill()

        print("Exchange Server stopped.")


if __name__ == "__main__":
    asyncio.run(main())
