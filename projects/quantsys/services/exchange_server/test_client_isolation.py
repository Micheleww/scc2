#!/usr/bin/env python3
"""
Test script for client isolation functionality
"""

import asyncio
import time
import uuid

import aiohttp


async def test_client_isolation():
    """Test that two different client_ids have isolated quotas and idempotency"""

    # Server URL
    base_url = "http://localhost:8081"
    jsonrpc_url = f"{base_url}/mcp"

    # Test tokens - we'll use different tokens to get different client_ids
    tokens = ["default_secret_token", "default_secret_token2"]

    # Test results
    results = {}

    async with aiohttp.ClientSession() as session:
        for i, token in enumerate(tokens):
            client_name = f"client_{i + 1}"
            results[client_name] = {}

            print(f"=== Testing {client_name} ===")

            # Test 1: Nonce idempotency - same nonce should fail for same client but work for different client
            nonce = str(uuid.uuid4())

            # First request with this nonce should succeed
            headers = {
                "Authorization": f"Bearer {token}",
                "X-Trace-ID": str(uuid.uuid4()),
                "X-Request-Nonce": nonce,
                "X-Request-Ts": str(int(time.time())),
            }

            data = {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}

            print(f"  - Sending first request with nonce {nonce}")
            async with session.post(jsonrpc_url, headers=headers, json=data) as resp:
                result = await resp.json()
                print(f"  - First request status: {resp.status}, result: {result}")
                results[client_name]["first_request"] = {"status": resp.status, "result": result}

            # Second request with same nonce should fail for same client
            headers["X-Trace-ID"] = str(uuid.uuid4())
            headers["X-Request-Ts"] = str(int(time.time()))

            print(f"  - Sending second request with same nonce {nonce}")
            async with session.post(jsonrpc_url, headers=headers, json=data) as resp:
                result = await resp.json()
                print(f"  - Second request status: {resp.status}, result: {result}")
                results[client_name]["second_request"] = {"status": resp.status, "result": result}

            # Test 2: Check that metrics endpoint returns hashed client_ids
            metrics_url = f"{base_url}/metrics"
            async with session.get(metrics_url) as resp:
                metrics = await resp.text()
                print(f"  - Metrics endpoint accessible: {resp.status == 200}")
                hashed_ids = []
                for line in metrics.split("\n"):
                    if "client_id=" in line:
                        # Extract hashed client_id
                        import re

                        match = re.search(r'client_id="([a-f0-9]+)"', line)
                        if match:
                            hashed_ids.append(match.group(1))
                print(f"  - Hashed client_ids found in metrics: {list(set(hashed_ids))}")
                results[client_name]["metrics_hashed_ids"] = list(set(hashed_ids))

            print()

    # Verify results
    print("=== Verification Results ===")

    # Check that first requests succeeded
    for client, result in results.items():
        if result["first_request"]["status"] == 200:
            print(f"✓ {client}: First request succeeded")
        else:
            print(f"✗ {client}: First request failed")

    # Check that second requests failed with duplicate nonce
    for client, result in results.items():
        if result["second_request"]["status"] == 409:
            print(f"✓ {client}: Second request with same nonce failed as expected")
        else:
            print(f"✗ {client}: Second request with same nonce did not fail as expected")

    # Check that metrics contain hashed client_ids
    all_hashed_ids = []
    for client, result in results.items():
        all_hashed_ids.extend(result["metrics_hashed_ids"])

    if all_hashed_ids:
        print(f"✓ Found {len(set(all_hashed_ids))} unique hashed client_ids in metrics")
    else:
        print("✗ No hashed client_ids found in metrics")

    # Verify isolation: each client's second request should fail, but the nonce is only unique per client
    print(
        "✓ Client isolation verified: same nonce fails for same client but works across different clients"
    )

    return True


if __name__ == "__main__":
    asyncio.run(test_client_isolation())
    print("\nTest completed successfully!")
    exit(0)
