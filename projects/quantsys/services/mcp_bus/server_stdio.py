#!/usr/bin/env python3
"""
MCP Server stdio wrapper for Cursor integration.

This wrapper allows Cursor to connect to the MCP server via stdio transport,
which is the recommended approach for Cursor MCP integration.

Usage:
    python server_stdio.py

The server will communicate via stdin/stdout using JSON-RPC 2.0 protocol.
"""

import asyncio
import json
import os
import sys
from pathlib import Path

# Add the server directory to the path
server_dir = Path(__file__).parent
sys.path.insert(0, str(server_dir.parent.parent.parent))

# Set up environment variables if not already set
if "REPO_ROOT" not in os.environ:
    os.environ["REPO_ROOT"] = str(Path(__file__).parent.parent.parent.parent.resolve())
if "MCP_BUS_HOST" not in os.environ:
    os.environ["MCP_BUS_HOST"] = "127.0.0.1"
if "MCP_BUS_PORT" not in os.environ:
    os.environ["MCP_BUS_PORT"] = "8000"
if "AUTH_MODE" not in os.environ:
    os.environ["AUTH_MODE"] = "none"

# Import the MCP server components
try:
    from tools.mcp_bus.server.audit import AuditLogger
    from tools.mcp_bus.server.main import app
    from tools.mcp_bus.server.security import PathSecurity, load_security_config
    from tools.mcp_bus.server.tools import ToolExecutor
except ImportError as e:
    print(
        json.dumps(
            {
                "jsonrpc": "2.0",
                "id": None,
                "error": {"code": -32603, "message": f"Failed to import server modules: {str(e)}"},
            }
        ),
        file=sys.stderr,
    )
    sys.exit(1)


class StdioMCPServer:
    """MCP Server that communicates via stdin/stdout"""

    def __init__(self):
        self.tool_executor = None
        self.audit_logger = None
        self.initialized = False

    async def initialize(self):
        """Initialize server components"""
        if self.initialized:
            return

        repo_root = os.environ.get("REPO_ROOT", ".")
        repo_root = Path(repo_root).resolve()
        config_path = repo_root / "tools" / "mcp_bus" / "config" / "config.example.json"

        # Load config file
        import json

        with open(config_path) as f:
            config = json.load(f)

        paths_config = config.get("paths", {})

        # Load security config
        security_config = load_security_config(str(config_path), str(repo_root))
        security = PathSecurity(security_config, str(repo_root))

        # Initialize audit logger
        log_dir = paths_config.get("log_dir", "docs/LOG/mcp_bus")
        self.audit_logger = AuditLogger(log_dir, str(repo_root))

        # Initialize tool executor with correct parameters
        self.tool_executor = ToolExecutor(
            repo_root=str(repo_root),
            inbox_dir=paths_config.get("inbox_dir", "docs/REPORT/inbox"),
            board_file=paths_config.get("board_file", "docs/REPORT/QCC-PROGRAM-BOARD-v0.1.md"),
            security=security,
            audit_logger=self.audit_logger,
        )

        self.initialized = True

    async def handle_request(self, request: dict) -> dict:
        """Handle a JSON-RPC request"""
        try:
            await self.initialize()
        except Exception as e:
            return {
                "jsonrpc": "2.0",
                "id": request.get("id"),
                "error": {"code": -32603, "message": f"Initialization error: {str(e)}"},
            }

        method = request.get("method")
        params = request.get("params", {})
        request_id = request.get("id")

        if method == "initialize":
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "qcc-bus-local", "version": "0.1.0"},
                },
            }

        elif method == "tools/list":
            # Import tools_list function from main
            from tools.mcp_bus.server.main import tools_list

            tools_result = await tools_list()
            # tools_list returns a full JSON-RPC response, extract the result
            if isinstance(tools_result, dict) and "result" in tools_result:
                return {"jsonrpc": "2.0", "id": request_id, "result": tools_result["result"]}
            else:
                # Fallback: return as-is but update id
                if isinstance(tools_result, dict):
                    tools_result["id"] = request_id
                return tools_result

        elif method == "tools/call":
            # Import tools_call function and necessary components
            from starlette.datastructures import Headers

            import tools.mcp_bus.server.main as main_module
            from tools.mcp_bus.server.main import tools_call

            tool_name = params.get("name") or params.get("toolName")
            arguments = params.get("arguments", {}) or params.get("params", {})

            if not tool_name:
                return {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "error": {"code": -32602, "message": "Missing tool name"},
                }

            try:
                # Set global tool_executor for tools_call to use
                # This is needed because tools_call uses global tool_executor
                main_module.tool_executor = self.tool_executor

                # Create a mock request object for stdio mode
                # Since we're in stdio mode, we don't have a real HTTP request
                # Create minimal mock request with necessary attributes
                class MockRequest:
                    def __init__(self):
                        self.headers = Headers(
                            {
                                "user-agent": "Cursor/stdio",
                                "x-trace-id": str(request_id) if request_id else "stdio-unknown",
                            }
                        )

                mock_request = MockRequest()

                # Call tools_call with params dict
                call_params = {"name": tool_name, "arguments": arguments}
                result = await tools_call(call_params, "Cursor", mock_request)

                # Set the request ID
                result["id"] = request_id

                return result
            except Exception as e:
                import traceback

                traceback.print_exc()
                return {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "error": {"code": -32000, "message": f"Tool execution error: {str(e)}"},
                }

        else:
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "error": {"code": -32601, "message": f"Unknown method: {method}"},
            }

    async def run(self):
        """Run the stdio server"""
        # Note: MCP stdio protocol - client sends initialize request first
        # We don't send initialized notification automatically

        # Read requests from stdin using async executor (works on Windows)
        loop = asyncio.get_event_loop()

        # Read requests from stdin
        while True:
            try:
                # Read a line from stdin using executor (non-blocking)
                line = await loop.run_in_executor(None, sys.stdin.readline)
                if not line:
                    # EOF reached
                    break

                line = line.strip()
                if not line:
                    continue

                try:
                    request = json.loads(line)
                except json.JSONDecodeError as e:
                    error_response = {
                        "jsonrpc": "2.0",
                        "id": None,
                        "error": {"code": -32700, "message": f"Parse error: {str(e)}"},
                    }
                    print(json.dumps(error_response), flush=True)
                    continue

                # Handle request
                response = await self.handle_request(request)
                print(json.dumps(response), flush=True)

            except EOFError:
                # End of input
                break
            except KeyboardInterrupt:
                # User interrupt
                break
            except Exception as e:
                import traceback

                traceback.print_exc(file=sys.stderr)
                error_response = {
                    "jsonrpc": "2.0",
                    "id": None,
                    "error": {"code": -32603, "message": f"Internal error: {str(e)}"},
                }
                print(json.dumps(error_response), flush=True)


def main():
    """Main entry point"""
    server = StdioMCPServer()
    try:
        asyncio.run(server.run())
    except KeyboardInterrupt:
        pass
    except Exception as e:
        error_response = {
            "jsonrpc": "2.0",
            "id": None,
            "error": {"code": -32603, "message": f"Server error: {str(e)}"},
        }
        print(json.dumps(error_response), file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
