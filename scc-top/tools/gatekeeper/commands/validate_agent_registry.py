
#!/usr/bin/env python3
"""
Agent Registry validator (CI hard-gate)

Validates `.cursor/agent_registry.json` invariants so CI can enforce the same hard rules
as the MCP server (e.g., numeric_code uniqueness / range, send_enabled type).
"""

import json
import os

# Repo root
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))


def validate_agent_registry_invariants():
    registry_path = os.path.join(PROJECT_ROOT, ".cursor", "agent_registry.json")
    if not os.path.exists(registry_path):
        print("WARNING: agent_registry.json not found; skip")
        return True, "AGENT_REGISTRY_NOT_FOUND"
    try:
        with open(registry_path, encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        print(f"ERROR: Failed to load agent_registry.json: {e}")
        return False, "AGENT_REGISTRY_INVALID_JSON"

    agents = data.get("agents", {})
    if not isinstance(agents, dict):
        print("ERROR: agent_registry.json: agents must be an object")
        return False, "AGENT_REGISTRY_INVALID_FORMAT"

    used = {}
    for agent_id, agent_data in agents.items():
        if not isinstance(agent_id, str) or not agent_id.strip():
            print("ERROR: agent_registry.json: agent_id must be non-empty string")
            return False, "AGENT_REGISTRY_INVALID_AGENT_ID"
        if not isinstance(agent_data, dict):
            print(f"ERROR: agent_registry.json: agent entry must be object: {agent_id}")
            return False, "AGENT_REGISTRY_INVALID_AGENT_ENTRY"

        if "send_enabled" in agent_data and not isinstance(agent_data["send_enabled"], bool):
            print(f"ERROR: send_enabled must be boolean: {agent_id}")
            return False, "AGENT_REGISTRY_SEND_ENABLED_INVALID"

        code = agent_data.get("numeric_code", None)
        if code is None:
            continue
        if not isinstance(code, int):
            print(f"ERROR: numeric_code must be integer: {agent_id} -> {code}")
            return False, "AGENT_REGISTRY_NUMERIC_CODE_TYPE"
        if not (1 <= code <= 100):
            print(f"ERROR: numeric_code out of range: {agent_id} -> {code}")
            return False, "AGENT_REGISTRY_NUMERIC_CODE_RANGE"
        if code in used and used[code] != agent_id:
            print(f"ERROR: numeric_code duplicate: {code} used by {used[code]} and {agent_id}")
            return False, "AGENT_REGISTRY_NUMERIC_CODE_DUPLICATE"
        used[code] = agent_id

    print("SUCCESS: agent_registry.json invariants check passed")
    return True, "SUCCESS"


def main():
    ok, _ = validate_agent_registry_invariants()
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
