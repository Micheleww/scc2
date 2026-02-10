#!/usr/bin/env python3
"""
Simple test for server_stdio.py - just check if it can be imported and initialized
"""

import os
import sys
from pathlib import Path

# Add repo root to path
repo_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(repo_root))

# Set environment variables
os.environ["REPO_ROOT"] = str(repo_root)
os.environ["MCP_BUS_HOST"] = "127.0.0.1"
os.environ["MCP_BUS_PORT"] = "8000"
os.environ["AUTH_MODE"] = "none"

try:
    print("Testing server_stdio.py import and initialization...")

    # Test import
    from tools.mcp_bus.server_stdio import StdioMCPServer

    print("[OK] Import successful")

    # Test initialization
    server = StdioMCPServer()
    print("[OK] Server instance created")

    # Test async initialization (without actually running)
    import asyncio

    async def test_init():
        try:
            await server.initialize()
            print("[OK] Async initialization successful")
            return True
        except Exception as e:
            print(f"[FAIL] Initialization failed: {e}")
            import traceback

            traceback.print_exc()
            return False

    result = asyncio.run(test_init())

    if result:
        print("\n[SUCCESS] All basic tests passed!")
        sys.exit(0)
    else:
        print("\n[FAIL] Tests failed")
        sys.exit(1)

except Exception as e:
    print(f"[FAIL] Test failed: {e}")
    import traceback

    traceback.print_exc()
    sys.exit(1)
