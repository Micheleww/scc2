#!/usr/bin/env python3
"""
Simple SSE Heartbeat Test

This is a simplified test that directly prints to console for debugging.
"""

import time

import requests

# Test configuration
SERVER_URL = "http://localhost:8083"
SSE_ENDPOINT = f"{SERVER_URL}/mcp/messages"

print(f"Testing SSE endpoint: {SSE_ENDPOINT}")
print("Press Ctrl+C to stop...")
print()

# Make a direct HTTP request to check if the server is running
try:
    response = requests.get(f"{SERVER_URL}/version")
    print(f"Server version check: {response.status_code}")
    if response.status_code == 200:
        print(f"Server info: {response.json()}")
except Exception as e:
    print(f"Server check failed: {e}")

print()
print("=== Starting SSE Connection Test ===")

# Use requests to connect to SSE endpoint
try:
    with requests.get(
        SSE_ENDPOINT,
        stream=True,
        headers={"Accept": "text/event-stream", "Cache-Control": "no-cache"},
    ) as response:
        print(f"SSE Connection Status: {response.status_code}")
        print(f"Response headers: {dict(response.headers)}")
        print()

        event_count = 0
        start_time = time.time()

        # Read the response line by line
        for line in response.iter_lines():
            if line:
                line = line.decode("utf-8")
                print(f"[{time.time() - start_time:.2f}s] {line}")
                event_count += 1

            # Stop after 20 events or 30 seconds
            if event_count >= 20 or time.time() - start_time > 30:
                print(f"\nTest completed: {event_count} events in {time.time() - start_time:.2f}s")
                break

        print("\nEXIT_CODE=0")
        exit(0)

except Exception as e:
    print(f"\nError: {e}")
    print("EXIT_CODE=1")
    exit(1)
