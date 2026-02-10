#!/usr/bin/env python3
import argparse
import asyncio
import json
import logging
import time

import aiohttp

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


class SSEClient:
    def __init__(
        self,
        url: str,
        timeout: float = 30.0,
        initial_backoff: float = 1.0,
        max_backoff: float = 32.0,
        max_retries: int = 5,
        heartbeat_timeout: float = 60.0,
    ):
        self.url = url
        self.timeout = timeout
        self.initial_backoff = initial_backoff
        self.max_backoff = max_backoff
        self.max_retries = max_retries
        self.heartbeat_timeout = heartbeat_timeout

        self.session: aiohttp.ClientSession | None = None
        self.retry_count = 0
        self.connected = False
        self.last_heartbeat = time.time()
        self.total_connections = 0
        self.total_disconnections = 0
        self.total_reconnection_attempts = 0
        self.total_successful_reconnections = 0

    async def connect(self) -> None:
        self.retry_count = 0
        while self.retry_count <= self.max_retries:
            try:
                await self._attempt_connection()
            except (TimeoutError, aiohttp.ClientError, Exception) as e:
                self.connected = False
                self.total_disconnections += 1

                # Log disconnect event
                event = {
                    "event_type": "disconnect",
                    "timestamp": time.time(),
                    "reason": str(e),
                    "connection_count": self.total_connections,
                    "disconnection_count": self.total_disconnections,
                    "reconnection_attempt_count": self.total_reconnection_attempts,
                    "successful_reconnection_count": self.total_successful_reconnections,
                }
                logger.info(json.dumps(event))

                if self.retry_count >= self.max_retries:
                    logger.error(f"Max retries reached ({self.max_retries}), stopping...")
                    break

                # Calculate exponential backoff with cap
                backoff = min(self.initial_backoff * (2**self.retry_count), self.max_backoff)
                self.retry_count += 1
                self.total_reconnection_attempts += 1

                # Log reconnect attempt event
                event = {
                    "event_type": "reconnect_attempt",
                    "timestamp": time.time(),
                    "attempt": self.retry_count,
                    "backoff": backoff,
                    "max_retries": self.max_retries,
                    "max_backoff": self.max_backoff,
                }
                logger.info(json.dumps(event))

                await asyncio.sleep(backoff)
            else:
                # Connection closed normally
                break

    async def _attempt_connection(self) -> None:
        if self.session and not self.session.closed:
            await self.session.close()

        self.session = aiohttp.ClientSession()
        self.total_connections += 1

        # Log connect event
        event = {
            "event_type": "connect",
            "timestamp": time.time(),
            "url": self.url,
            "connection_count": self.total_connections,
            "reconnection_attempt_count": self.total_reconnection_attempts,
            "successful_reconnection_count": self.total_successful_reconnections,
        }
        logger.info(json.dumps(event))

        async with self.session.get(
            self.url, timeout=self.timeout, headers={"Accept": "text/event-stream"}
        ) as response:
            self.connected = True
            self.last_heartbeat = time.time()

            # Log reconnect success if this is a reconnection
            if self.retry_count > 0:
                self.total_successful_reconnections += 1
                event = {
                    "event_type": "reconnect_success",
                    "timestamp": time.time(),
                    "attempt": self.retry_count,
                    "connection_count": self.total_connections,
                    "reconnection_attempt_count": self.total_reconnection_attempts,
                    "successful_reconnection_count": self.total_successful_reconnections,
                }
                logger.info(json.dumps(event))
                # Reset retry count after successful reconnection
                self.retry_count = 0

            async for line in response.content:
                line = line.decode("utf-8").strip()
                if not line:
                    continue

                if line.startswith("data:"):
                    try:
                        data = json.loads(line[5:])
                        if data.get("event") == "heartbeat":
                            current_time = time.time()
                            heartbeat_lag = current_time - self.last_heartbeat
                            self.last_heartbeat = current_time

                            # Log heartbeat lag event
                            event = {
                                "event_type": "heartbeat_lag_ms",
                                "timestamp": current_time,
                                "lag_ms": round(heartbeat_lag * 1000, 2),
                                "connection_count": self.total_connections,
                            }
                            logger.info(json.dumps(event))
                    except json.JSONDecodeError:
                        pass

                # Check heartbeat timeout
                if time.time() - self.last_heartbeat > self.heartbeat_timeout:
                    raise TimeoutError(f"Heartbeat timeout after {self.heartbeat_timeout} seconds")

    async def close(self) -> None:
        if self.session and not self.session.closed:
            await self.session.close()


def main():
    parser = argparse.ArgumentParser(description="SSE Client with Auto-Reconnect")
    parser.add_argument("--url", type=str, required=True, help="SSE server URL")
    parser.add_argument("--timeout", type=float, default=30.0, help="Connection timeout in seconds")
    parser.add_argument("--backoff", type=float, default=1.0, help="Initial backoff in seconds")
    parser.add_argument(
        "--max-retries", type=int, default=5, help="Maximum number of reconnection attempts"
    )
    parser.add_argument(
        "--heartbeat-timeout", type=float, default=60.0, help="Heartbeat timeout in seconds"
    )

    args = parser.parse_args()

    client = SSEClient(
        url=args.url,
        timeout=args.timeout,
        initial_backoff=args.backoff,
        max_backoff=32.0,  # Fixed max backoff
        max_retries=args.max_retries,
        heartbeat_timeout=args.heartbeat_timeout,
    )

    try:
        asyncio.run(client.connect())
    except KeyboardInterrupt:
        logger.info("Client stopped by user")
    finally:
        asyncio.run(client.close())


if __name__ == "__main__":
    main()
