import json
import os
from datetime import datetime

import requests

# Configuration
MCP_URL = "http://localhost:18788/mcp"
DOC_ID = "docs/REPORT/_control/CONTROL_PANEL.md"
TOKEN = os.getenv("MCP_BUS_TOKEN", "test-token")

# Output directory
OUTPUT_DIR = "d:/quantsys/docs/REPORT/MCP/artifacts/DOC_RW_MIN/"
os.makedirs(OUTPUT_DIR, exist_ok=True)

# Headers
headers = {"Content-Type": "application/json", "X-API-Key": TOKEN}


def call_mcp(method, params):
    """Call MCP API"""
    payload = {"jsonrpc": "2.0", "id": "test", "method": method, "params": params}
    response = requests.post(MCP_URL, json=payload, headers=headers)
    return response.json()


def main():
    print("Starting smoke test for doc_get/doc_patch...")

    # Reset test document content first
    print("Resetting test document content...")
    reset_resp = call_mcp(
        "tools/call",
        {
            "name": "doc_patch",
            "arguments": {
                "doc_id": DOC_ID,
                "base_rev": None,
                "ops": [
                    {
                        "type": "replace",
                        "value": "# Control Panel\n\nThis is a test document for the MCP doc_get/doc_patch functionality.\n\n## Initial Content\n- Document ID: docs/REPORT/_control/CONTROL_PANEL.md\n- Test case: Basic read-write operations\n- Version: 1.0",
                    }
                ],
            },
        },
    )

    # Step 1: Initial doc_get
    print("Step 1: Initial doc_get")
    get_before = call_mcp("tools/call", {"name": "doc_get", "arguments": {"doc_id": DOC_ID}})
    print(f"Initial get result: {json.dumps(get_before, indent=2)}")

    # Save initial get response
    with open(os.path.join(OUTPUT_DIR, "smoke_get_before.json"), "w") as f:
        json.dump(get_before, f, indent=2)

    # Check if initial get was successful
    if "error" in get_before:
        print(f"ERROR: Initial doc_get failed: {get_before['error']['message']}")
        return 1

    # Parse the response correctly
    content_text = get_before["result"]["content"][0]["text"]
    content_json = json.loads(content_text)
    if not content_json.get("success"):
        print(f"ERROR: doc_get returned error: {content_json.get('error')}")
        return 1

    base_rev_value = content_json["rev"]
    print(f"Initial rev: {base_rev_value}")

    # Step 2: doc_patch
    print(f"Step 2: doc_patch with base_rev={base_rev_value}")
    patch_resp = call_mcp(
        "tools/call",
        {
            "name": "doc_patch",
            "arguments": {
                "doc_id": DOC_ID,
                "base_rev": base_rev_value,
                "ops": [
                    {
                        "type": "replace",
                        "value": "# Control Panel\n\nThis is an updated test document.\n\n## Modified Content\n- Document ID: docs/REPORT/_control/CONTROL_PANEL.md\n- Test case: Patch operation successful\n- Version: 1.1",
                    }
                ],
            },
        },
    )
    print(f"Patch response: {json.dumps(patch_resp, indent=2)}")

    # Save patch response
    with open(os.path.join(OUTPUT_DIR, "smoke_patch_resp.json"), "w") as f:
        json.dump(patch_resp, f, indent=2)

    # Check if patch was successful
    if "error" in patch_resp:
        print(f"ERROR: doc_patch failed: {patch_resp['error']['message']}")
        return 1

    # Parse patch response
    patch_content = patch_resp["result"]["content"][0]["text"]
    patch_json = json.loads(patch_content)
    if not patch_json.get("success"):
        print(f"ERROR: doc_patch returned error: {patch_json.get('error')}")
        return 1

    new_rev_value = patch_json["new_rev"]
    change_id = patch_json["change_id"]

    # Verify rev incremented
    if new_rev_value == base_rev_value:
        print(f"ERROR: Revision did not increment: {base_rev_value} -> {new_rev_value}")
        return 1
    print(f"✓ Revision incremented: {base_rev_value} -> {new_rev_value}")

    # Verify change_id exists
    if not change_id:
        print("ERROR: change_id not found in patch response")
        return 1
    print(f"✓ change_id found: {change_id}")

    # Step 3: Final doc_get
    print("Step 3: Final doc_get")
    get_after = call_mcp("tools/call", {"name": "doc_get", "arguments": {"doc_id": DOC_ID}})
    print(f"Final get result: {json.dumps(get_after, indent=2)}")

    # Save final get response
    with open(os.path.join(OUTPUT_DIR, "smoke_get_after.json"), "w") as f:
        json.dump(get_after, f, indent=2)

    # Check if final get was successful
    if "error" in get_after:
        print(f"ERROR: Final doc_get failed: {get_after['error']['message']}")
        return 1

    # Parse final get response
    final_content = get_after["result"]["content"][0]["text"]
    final_json = json.loads(final_content)
    if not final_json.get("success"):
        print(f"ERROR: Final doc_get returned error: {final_json.get('error')}")
        return 1

    final_rev_value = final_json["rev"]

    # Verify final rev matches patch new_rev
    if final_rev_value != new_rev_value:
        print(f"ERROR: Final rev doesn't match patch new_rev: {final_rev_value} != {new_rev_value}")
        return 1
    print(f"✓ Final rev matches patch new_rev: {final_rev_value}")

    # Step 4: Test rev conflict
    print("Step 4: Testing rev conflict")
    conflict_resp = call_mcp(
        "tools/call",
        {
            "name": "doc_patch",
            "arguments": {
                "doc_id": DOC_ID,
                "base_rev": base_rev_value,  # Use old rev to cause conflict
                "ops": [
                    {
                        "type": "replace",
                        "value": "# Control Panel\n\nThis should fail due to rev conflict.\n",
                    }
                ],
            },
        },
    )
    print(f"Conflict test response: {json.dumps(conflict_resp, indent=2)}")

    # Save conflict case
    with open(os.path.join(OUTPUT_DIR, "conflict_case.json"), "w") as f:
        json.dump(conflict_resp, f, indent=2)

    # Check if conflict was handled correctly
    # Check if there's an error at the top level
    if "error" in conflict_resp:
        error_msg = conflict_resp["error"]["message"]
        if "Revision mismatch" in error_msg:
            print(f"✓ Rev conflict handled correctly: {error_msg}")
        else:
            print(f"ERROR: Expected 'Revision mismatch' error, got: {error_msg}")
            return 1
    elif "result" in conflict_resp:
        # Check if there's an error inside the result
        result = conflict_resp["result"]
        if "error" in result:
            error_msg = result["error"]["message"]
            if "Revision mismatch" in error_msg:
                print(f"✓ Rev conflict handled correctly: {error_msg}")
            else:
                print(f"ERROR: Expected 'Revision mismatch' error, got: {error_msg}")
                return 1
        # Check if there's content inside the result
        elif "content" in result:
            try:
                conflict_content = result["content"][0]["text"]
                conflict_json = json.loads(conflict_content)
                if conflict_json.get("success"):
                    print("ERROR: Expected rev conflict error, but got success")
                    return 1
                else:
                    error_msg = conflict_json.get("error", "Unknown error")
                    if "Revision mismatch" in error_msg:
                        print(f"✓ Rev conflict handled correctly: {error_msg}")
                    else:
                        print(f"ERROR: Expected 'Revision mismatch' error, got: {error_msg}")
                        return 1
            except (KeyError, IndexError, json.JSONDecodeError):
                print("ERROR: Unexpected response structure for conflict test")
                return 1
        else:
            print("ERROR: Unexpected response structure for conflict test")
            return 1
    else:
        print("ERROR: Unexpected response structure for conflict test")
        return 1

    # Generate API contract
    api_contract = {
        "version": "1.0",
        "date": datetime.now().isoformat(),
        "endpoints": {
            "doc_get": {
                "method": "tools/call",
                "arguments": {
                    "doc_id": {
                        "type": "string",
                        "description": "Document ID (path relative to repo root)",
                    }
                },
                "response": {"result": {"content": "string", "rev": "string"}},
            },
            "doc_patch": {
                "method": "tools/call",
                "arguments": {
                    "doc_id": {
                        "type": "string",
                        "description": "Document ID (path relative to repo root)",
                    },
                    "base_rev": {
                        "type": "string",
                        "description": "Expected current revision of the document (required for CAS)",
                    },
                    "ops": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "type": {
                                    "type": "string",
                                    "description": "Operation type (e.g., 'replace')",
                                },
                                "value": {
                                    "type": "string",
                                    "description": "New content for replace operation",
                                },
                            },
                        },
                    },
                },
                "response": {"result": {"new_rev": "string", "change_id": "string"}},
            },
        },
        "error_codes": {
            "404": "Document not found",
            "409": {
                "Revision mismatch": "Base revision does not match current revision",
                "Another operation is in progress": "Concurrency lock violation",
            },
            "403": "Access denied",
            "500": "Internal server error",
        },
    }

    # Save API contract
    with open(os.path.join(OUTPUT_DIR, "api_contract.md"), "w") as f:
        f.write("# API Contract for doc_get/doc_patch\n\n")
        f.write("## Overview\n")
        f.write(
            "This document defines the API contract for the doc_get and doc_patch methods implemented in MCP.\n\n"
        )

        f.write("## Endpoints\n\n")
        f.write("### doc_get\n")
        f.write("- **Method**: tools/call\n")
        f.write("- **Tool Name**: doc_get\n")
        f.write("- **Description**: Get a document by its ID\n\n")
        f.write("**Arguments**:\n")
        f.write("| Parameter | Type | Required | Description |\n")
        f.write("|-----------|------|----------|-------------|\n")
        f.write("| doc_id | string | Yes | Document ID (path relative to repo root) |\n\n")

        f.write("**Response**:\n")
        f.write("```json\n")
        f.write(
            json.dumps(
                {"result": {"content": "document content", "rev": "revision_hash"}}, indent=2
            )
        )
        f.write("\n```\n\n")

        f.write("### doc_patch\n")
        f.write("- **Method**: tools/call\n")
        f.write("- **Tool Name**: doc_patch\n")
        f.write("- **Description**: Patch a document by its ID\n\n")

        f.write("**Arguments**:\n")
        f.write("| Parameter | Type | Required | Description |\n")
        f.write("|-----------|------|----------|-------------|\n")
        f.write("| doc_id | string | Yes | Document ID (path relative to repo root) |\n")
        f.write(
            "| base_rev | string | Yes | Expected current revision of the document (for CAS) |\n"
        )
        f.write("| ops | array | Yes | List of patch operations |\n\n")

        f.write("**Patch Operation Format**:\n")
        f.write("```json\n")
        f.write(json.dumps([{"type": "replace", "value": "new content"}], indent=2))
        f.write("\n```\n\n")

        f.write("**Response**:\n")
        f.write("```json\n")
        f.write(
            json.dumps(
                {"result": {"new_rev": "new_revision_hash", "change_id": "change_identifier"}},
                indent=2,
            )
        )
        f.write("\n```\n\n")

        f.write("## Error Codes\n\n")
        f.write("| Status Code | Error Type | Description |\n")
        f.write("|-------------|------------|-------------|\n")
        f.write("| 404 | Document not found | The requested document does not exist |\n")
        f.write("| 409 | Revision mismatch | Base revision does not match current revision |\n")
        f.write("| 409 | Another operation is in progress | Concurrency lock violation |\n")
        f.write("| 403 | Access denied | Insufficient permissions to access the document |\n")
        f.write("| 500 | Internal server error | An unexpected error occurred on the server |\n\n")

        f.write("## Usage Examples\n\n")
        f.write("### Example 1: Get a document\n")
        f.write("```json\n")
        f.write(
            json.dumps(
                {
                    "jsonrpc": "2.0",
                    "id": "test",
                    "method": "tools/call",
                    "params": {
                        "name": "doc_get",
                        "arguments": {"doc_id": "docs/REPORT/_control/CONTROL_PANEL.md"},
                    },
                },
                indent=2,
            )
        )
        f.write("\n```\n\n")

        f.write("### Example 2: Patch a document\n")
        f.write("```json\n")
        f.write(
            json.dumps(
                {
                    "jsonrpc": "2.0",
                    "id": "test",
                    "method": "tools/call",
                    "params": {
                        "name": "doc_patch",
                        "arguments": {
                            "doc_id": "docs/REPORT/_control/CONTROL_PANEL.md",
                            "base_rev": "old_revision_hash",
                            "ops": [{"type": "replace", "value": "new content"}],
                        },
                    },
                },
                indent=2,
            )
        )
        f.write("\n```\n")

    print("\nAll tests passed!")
    return 0


if __name__ == "__main__":
    exit_code = main()

    # Write selftest.log with EXIT_CODE
    with open(os.path.join(OUTPUT_DIR, "selftest.log"), "w") as f:
        f.write(f"SMOKE_TEST_RUN_AT: {datetime.now().isoformat()}\n")
        f.write(f"EXIT_CODE: {exit_code}\n")
        if exit_code == 0:
            f.write("STATUS: SUCCESS\n")
        else:
            f.write("STATUS: FAILURE\n")

    exit(exit_code)
