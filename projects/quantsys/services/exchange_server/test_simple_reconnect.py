#!/usr/bin/env python3
"""
Simple test for SSE client reconnect functionality
"""

import asyncio
import sys

from sse_client_autoreconnect import SSEClient


async def main():
    """Test the SSE client with the existing server"""
    print("Starting simple SSE client reconnect test...")

    # Use the existing SSE server on port 8081
    client = SSEClient(
        url="http://localhost:8081/sse",
        timeout=10.0,
        initial_backoff=1.0,
        max_backoff=5.0,
        max_retries=3,
        heartbeat_timeout=15.0,
    )

    print(f"Connecting to: {client.url}")
    print(f"Heartbeat timeout: {client.heartbeat_timeout}s")
    print(f"Max retries: {client.max_retries}")
    print(f"Initial backoff: {client.initial_backoff}s")
    print(f"Max backoff: {client.max_backoff}s")
    print("=" * 60)

    # Start client in background
    client_task = asyncio.create_task(client.connect())

    try:
        # Wait for initial connection
        await asyncio.sleep(5)
        print(f"Initial connection status: {'Connected' if client.connected else 'Failed'}")

        if client.connected:
            print("✓ Initial connection successful")
        else:
            print("✗ Initial connection failed")
            return False

        # Let it run for a bit to get heartbeats
        print("\nWaiting for heartbeats...")
        await asyncio.sleep(10)

        print("\nTest completed successfully!")
        print(f"Final connection status: {'Connected' if client.connected else 'Disconnected'}")
        print(f"Total connections: {client.total_connections}")
        print(f"Total disconnections: {client.total_disconnections}")
        print(f"Total reconnection attempts: {client.total_reconnection_attempts}")
        print(f"Total successful reconnections: {client.total_successful_reconnections}")

        return True

    except KeyboardInterrupt:
        print("\nTest interrupted by user")
        return False
    finally:
        # Cancel the client task
        client_task.cancel()
        await client.close()
        print("\nClient closed")


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
