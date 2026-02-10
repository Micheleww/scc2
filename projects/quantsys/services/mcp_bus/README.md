# QCC Bus - Remote MCP Server

## Purpose

QCC Bus is a remote MCP (Model Context Protocol) server that enables communication between ChatGPT web interface and TRAE desktop IDE. It provides a minimal toolset for agents to read and write to a shared fact source (`docs/REPORT/inbox` and `Program Board`), accelerating development progress and reducing manual data transfer.

## Features

- **Streamable HTTP Transport**: Compatible with OpenAI's remote server_url specification
- **Bearer Token Authentication**: Fail-closed security model
- **Path Whitelisting**: Strict access control to approved directories only
- **Audit Logging**: All tool calls are logged with timestamps and details
- **Minimal Toolset**: 4 core tools for inbox and program board operations

## Tools

### 1. `inbox_append`
Append a new block to the daily inbox file.

**Parameters:**
- `date` (string, required): Date in YYYY-MM-DD format
- `task_code` (string, required): Task identifier (e.g., TC-MCP-BRIDGE-0002)
- `source` (string, required): Source identifier (e.g., "ChatGPT", "TRAE")
- `text` (string, required): Content to append

**Returns:** Success confirmation with file path

### 2. `inbox_tail`
Read the last n lines or last block from the inbox.

**Parameters:**
- `date` (string, required): Date in YYYY-MM-DD format
- `n` (integer, optional): Number of lines to return (default: 50)

**Returns:** Content from the end of the file

### 3. `board_get`
Read the Program Board content.

**Parameters:** None

**Returns:** Full content of `docs/REPORT/QCC-PROGRAM-BOARD-v0.1.md`

### 4. `board_set_status`
Update task status and artifacts in the Program Board.

**Parameters:**
- `task_code` (string, required): Task identifier
- `status` (string, required): New status value
- `artifacts` (string, optional): Artifacts/deliverables path

**Returns:** Success confirmation

## Security

### Authentication
- Bearer Token required for all requests
- Token read from `MCP_BUS_TOKEN` environment variable
- Requests without valid token are rejected (fail-closed)

### Path Whitelist
Only the following paths are allowed:
- **Read/Write**: `docs/REPORT/inbox/`
- **Read/Write**: `docs/REPORT/QCC-PROGRAM-BOARD-v0.1.md`
- **Write**: `docs/LOG/mcp_bus/` (audit logs)

**Blocked:**
- All access to `law/` directory is strictly prohibited
- Any path outside the whitelist is rejected

### Audit Logging
All tool calls are logged to `docs/LOG/mcp_bus/YYYY-MM-DD.log` with:
- Timestamp
- Tool name
- Caller (source)
- Parameter summary (truncated if needed)
- Result summary
- Whether the request was denied

## Installation

### Prerequisites
- Python 3.8+
- pip

### Setup
```bash
cd tools/mcp_bus
pip install -r requirements.txt
```

## Configuration

### Environment Variables

**SECURITY REQUIREMENT:**
- Production environments MUST NOT use `.env` files committed to repository
- Use system environment variables or external secret management instead
- NEVER commit real secrets (tokens, API keys, etc.) to the repository

**For Local Development:**
Create a `.env` file from the example:
```bash
cp .env.example .env
# Edit .env with your values
```

**For Production:**
Set environment variables directly or use secret management:
```bash
# Required: Bearer token for authentication
export MCP_BUS_TOKEN=your-secure-token-here

# Optional: Repository root (defaults to script directory)
export REPO_ROOT=/path/to/quantsys

# Optional: Server host and port
export MCP_BUS_HOST=127.0.0.1
export MCP_BUS_PORT=8000
```

**Template File:**
A `.env.template` file is provided as a placeholder. To use:
```bash
cp .env.template .env
# Edit .env and replace TOKEN=CHANGEME with actual token
```

**Important:** The `.env.template` file contains only variable names and comments, NO real secrets.

# Optional: Repository root (defaults to script directory)
REPO_ROOT=/path/to/quantsys

# Optional: Server host and port
MCP_BUS_HOST=0.0.0.0
MCP_BUS_PORT=8000
```

### Example Config File
See `config/config.example.json` for a full configuration example.

## Running the Server

### Local Development
```bash
cd tools/mcp_bus
python server/main.py
```

### Using uvicorn (recommended for production)
```bash
cd tools/mcp_bus
uvicorn server.main:app --host 0.0.0.0 --port 8000
```

### With Docker
```bash
docker build -t qcc-bus .
docker run -p 8000:8000 --env-file .env qcc-bus
```

## Testing

Run the self-test script:
```bash
python test/test_client.py
```

Or use curl commands (see `test/curl_examples.sh`).

## Integration

### TRAE Configuration
Add to `.trae/mcp.json`:
```json
{
  "mcpServers": {
    "qcc-bus": {
      "transport": {
        "type": "http",
        "url": "http://localhost:18788/mcp"
      },
      "auth": {
        "type": "bearer",
        "token": "your-secure-token-here"
      }
    }
  }
}
```

### ChatGPT Web Interface
1. Go to Settings → Connectors
2. Add a new MCP server
3. Enter server URL: `https://your-server.com/mcp`
4. Configure Bearer token authentication
5. Enable the connector

**Note:** ChatGPT cannot access localhost. Deploy to a VPS or use a tunnel service (ngrok, localtunnel, etc.) for remote access.

## MCP Protocol

This server implements the Model Context Protocol with Streamable HTTP transport. For protocol details, see:
- [OpenAI MCP Documentation](https://platform.openai.com/docs/guides/mcp)
- [MCP Specification](https://modelcontextprotocol.io/)

## Troubleshooting

### Server won't start
- Check if port 8000 is already in use
- Verify `MCP_BUS_TOKEN` is set
- Check Python dependencies are installed

### Authentication failures
- Verify token matches between client and server
- Check Authorization header format: `Bearer <token>`

### Path access denied
- Verify the path is in the whitelist
- Check for typos in path strings
- Ensure `law/` directory is not being accessed

## License

Part of the QuantSys project. See project license for details.
