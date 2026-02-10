#!/usr/bin/env python3
"""
SSE Client Reconnect Engine Selftest

This script tests the SSE client reconnect engine using toxiproxy to simulate network failures.
"""

import asyncio
import json
import logging
import os
import sys
import time
from pathlib import Path

# Add the current directory to the path
sys.path.insert(0, os.path.dirname(__file__))

from sse_client_autoreconnect import SSEClient

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

# Constants
TEST_NAME = "SSE-CLIENT-RECONNECT-ENGINE-v0.1__20260116"
ARTIFACTS_DIR = (
    Path(__file__).parent.parent.parent
    / "docs"
    / "REPORT"
    / "ci"
    / "exchange"
    / "artifacts"
    / TEST_NAME
)
LOG_FILE = Path("selftest.log")
TOXIPROXY_API = "http://localhost:8474"
PROXY_NAME = "exchange_sse_proxy"
PROXY_LISTEN = "0.0.0.0:18081"
UPSTREAM = "localhost:8081"
SSE_URL = "http://localhost:18081/sse"


class ToxiproxyManager:
    """Manages Toxiproxy configuration"""

    def __init__(self, api_url):
        self.api_url = api_url
        self.session = None

    async def __aenter__(self):
        import aiohttp

        self.session = aiohttp.ClientSession()
        await self._create_proxy()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()

    async def _make_request(self, method, path, json=None):
        """Make HTTP request to Toxiproxy API"""
        url = f"{self.api_url}{path}"
        try:
            async with self.session.request(method, url, json=json) as resp:
                return await resp.text()
        except Exception as e:
            logger.error(f"Toxiproxy API request failed: {e}")
            return None

    async def _create_proxy(self):
        """Create or update proxy"""
        proxy_data = {"name": PROXY_NAME, "listen": PROXY_LISTEN, "upstream": UPSTREAM}
        await self._make_request("POST", "/proxies", json=proxy_data)
        await self._make_request("POST", f"/proxies/{PROXY_NAME}/reset")

    async def inject_disconnect(self):
        """Inject disconnect chaos"""
        toxic_data = {
            "name": "disconnect",
            "type": "close_connection",
            "stream": "upstream",
            "toxicity": 1.0,
            "attributes": {"close_delay": 0},
        }
        await self._make_request("POST", f"/proxies/{PROXY_NAME}/toxics", json=toxic_data)

    async def remove_disconnect(self):
        """Remove disconnect chaos"""
        await self._make_request("DELETE", f"/proxies/{PROXY_NAME}/toxics/disconnect")


class SelftestRunner:
    """Runs the selftest"""

    def __init__(self):
        self.events = []
        self.test_start_time = None
        self.test_end_time = None
        self.test_passed = False

    def log_event(self, event_type, message):
        """Log test event"""
        event = {"event_type": event_type, "timestamp": time.time(), "message": message}
        self.events.append(event)
        logger.info(f"[{event_type}] {message}")

        # Write to selftest.log
        with open(LOG_FILE, "a") as f:
            f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} [{event_type}] {message}\n")

    async def run(self):
        """Run the selftest"""
        # Clear previous log
        with open(LOG_FILE, "w") as f:
            f.write(f"# {TEST_NAME} Selftest Log\n")
            f.write(f"Test started: {time.strftime('%Y-%m-%d %H:%M:%S')}\n\n")

        self.test_start_time = time.time()
        self.log_event("INFO", "Starting SSE Client Reconnect Engine Selftest")

        try:
            # 1. Create SSE client
            client = SSEClient(
                url=SSE_URL,
                timeout=10.0,
                initial_backoff=1.0,
                max_backoff=10.0,
                max_retries=5,
                heartbeat_timeout=15.0,
            )

            # 2. Start client in background
            client_task = asyncio.create_task(client.connect())

            # 3. Wait for initial connection
            self.log_event("INFO", "Waiting for initial connection...")
            await asyncio.sleep(5)

            if not client.connected:
                self.log_event("ERROR", "Initial connection failed")
                return False

            # 4. Inject disconnect chaos using toxiproxy
            self.log_event("INFO", "Injecting disconnect chaos...")
            async with ToxiproxyManager(TOXIPROXY_API) as toxiproxy:
                await toxiproxy.inject_disconnect()

                # 5. Wait for client to detect disconnect
                self.log_event("INFO", "Waiting for client to detect disconnect...")
                await asyncio.sleep(10)

                # 6. Remove disconnect chaos
                self.log_event("INFO", "Removing disconnect chaos...")
                await toxiproxy.remove_disconnect()

            # 7. Wait for reconnection
            self.log_event("INFO", "Waiting for client to reconnect...")
            await asyncio.sleep(15)

            # 8. Verify client is connected
            if client.connected:
                self.log_event("INFO", "Client reconnected successfully")
                self.test_passed = True
            else:
                self.log_event("ERROR", "Client failed to reconnect")

            # 9. Stop client
            client_task.cancel()
            await client.close()

            # 10. Check logs for expected events
            self.log_event("INFO", "Checking logs for expected events...")
            await self._verify_log_events()

        except Exception as e:
            self.log_event("ERROR", f"Test failed with exception: {e}")
            import traceback

            self.log_event("ERROR", f"Traceback: {traceback.format_exc()}")
            return False

        finally:
            self.test_end_time = time.time()
            self._generate_artifacts()

        return self.test_passed

    async def _verify_log_events(self):
        """Verify expected events in logs"""
        log_content = open(LOG_FILE).read()
        expected_events = [
            "connect",
            "disconnect",
            "reconnect_attempt",
            "reconnect_success",
            "heartbeat_lag_ms",
        ]

        for event in expected_events:
            if f'event_type": "{event}"' in log_content:
                self.log_event("INFO", f"✓ Found expected event: {event}")
            else:
                self.log_event("WARNING", f"✗ Missing expected event: {event}")

    def _generate_artifacts(self):
        """Generate test artifacts"""
        try:
            # Create artifacts directory structure
            (ARTIFACTS_DIR / "ata").mkdir(parents=True, exist_ok=True)

            # Copy selftest.log to artifacts
            artifact_log = ARTIFACTS_DIR / "selftest.log"
            import shutil

            shutil.copy2(LOG_FILE, artifact_log)

            # Create context.json
            context = {
                "test_name": TEST_NAME,
                "test_version": "v0.1",
                "test_date": time.strftime("%Y-%m-%dT%H:%M:%S"),
                "result": "PASS" if self.test_passed else "FAIL",
                "exit_code": 0 if self.test_passed else 1,
                "duration_seconds": round(self.test_end_time - self.test_start_time, 2),
                "events": self.events,
                "config": {
                    "sse_url": SSE_URL,
                    "toxiproxy_api": TOXIPROXY_API,
                    "proxy_name": PROXY_NAME,
                    "proxy_listen": PROXY_LISTEN,
                    "upstream": UPSTREAM,
                },
            }

            context_path = ARTIFACTS_DIR / "ata" / "context.json"
            with open(context_path, "w") as f:
                json.dump(context, f, indent=2)

            # Create SUBMIT.txt
            submit_content = f"""
TEST_NAME: {TEST_NAME}
TEST_DATE: {time.strftime("%Y-%m-%d")}
RESULT: {"PASS" if self.test_passed else "FAIL"}
EXIT_CODE: {"0" if self.test_passed else "1"}
"""

            submit_path = ARTIFACTS_DIR / "SUBMIT.txt"
            with open(submit_path, "w") as f:
                f.write(submit_content.strip())

            # Write exit code to selftest.log
            with open(LOG_FILE, "a") as f:
                f.write(f"\nEXIT_CODE={'0' if self.test_passed else '1'}\n")

        except Exception as e:
            self.log_event("ERROR", f"Failed to generate artifacts: {e}")
            import traceback

            self.log_event("ERROR", f"Artifacts generation traceback: {traceback.format_exc()}")


async def main():
    """Main function"""
    runner = SelftestRunner()
    success = await runner.run()

    if success:
        logger.info("✓ Selftest passed!")
        sys.exit(0)
    else:
        logger.error("✗ Selftest failed!")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
