#!/usr/bin/env python3
"""
Test script for A2A Agent Registry functionality
"""

import requests

# A2A Hub base URL
BASE_URL = "http://localhost:18788/api"

# Test configuration
test_agent = {
    "agent_id": "test-agent-001",
    "name": "Test Agent",
    "owner_role": "Backend Engineer",
    "abilities": ["code_generation", "testing"],
    "allowed_tools": ["ata.search", "ata.fetch"],
}

test_task = {
    "TaskCode": "TEST-AGENT-TASK-001__20260115",
    "instructions": "Use ata.search to find relevant tasks",
    "owner_role": "Backend Engineer",
}

test_task_no_match = {
    "TaskCode": "TEST-AGENT-TASK-002__20260115",
    "instructions": "Use non_existent_tool to do something",
    "owner_role": "NonExistentRole",
}


def test_agent_registry():
    """Test the agent registry functionality"""
    print("=== A2A Agent Registry Test ===")
    print("\n1. Testing Agent Registration:")

    # Register agent
    register_url = f"{BASE_URL}/api/agent/register"
    response = requests.post(register_url, json=test_agent)
    print(f"   Status: {response.status_code}")
    print(f"   Response: {response.text}")
    assert response.status_code == 200, (
        f"Agent registration failed with status {response.status_code}"
    )
    print("   PASS: Agent registration successful")

    print("\n2. Testing List Agents:")
    list_url = f"{BASE_URL}/api/agent/list"
    response = requests.get(list_url)
    print(f"   Status: {response.status_code}")
    agents = response.json()
    print(f"   Agents found: {len(agents['agents'])}")
    assert response.status_code == 200, f"List agents failed with status {response.status_code}"
    assert len(agents["agents"]) >= 1, "No agents found after registration"
    print("   PASS: List agents successful")

    print("\n3. Testing Get Agent Details:")
    get_url = f"{BASE_URL}/api/agent/{test_agent['agent_id']}"
    response = requests.get(get_url)
    print(f"   Status: {response.status_code}")
    agent_details = response.json()
    print(f"   Agent name: {agent_details['agent']['name']}")
    assert response.status_code == 200, (
        f"Get agent details failed with status {response.status_code}"
    )
    print("   PASS: Get agent details successful")

    print("\n4. Testing Task Creation with Agent Matching:")
    create_url = f"{BASE_URL}/api/task/create"
    response = requests.post(create_url, json=test_task)
    print(f"   Status: {response.status_code}")
    print(f"   Response: {response.text}")
    assert response.status_code == 200, f"Task creation failed with status {response.status_code}"
    task_response = response.json()
    assert "agent_id" in task_response, "Task creation did not return agent_id"
    assert task_response["agent_id"] == test_agent["agent_id"], (
        "Task was not assigned to correct agent"
    )
    print("   PASS: Task creation with agent matching successful")

    print("\n5. Testing Task Creation with No Matching Agent:")
    response = requests.post(create_url, json=test_task_no_match)
    print(f"   Status: {response.status_code}")
    print(f"   Response: {response.text}")
    assert response.status_code == 400, (
        f"Task creation should have failed with status 400, got {response.status_code}"
    )
    print("   PASS: Task creation with no matching agent correctly failed")

    print("\n6. Testing Agent Update:")
    update_url = f"{BASE_URL}/api/agent/{test_agent['agent_id']}"
    update_data = {"name": "Updated Test Agent", "status": "inactive"}
    response = requests.put(update_url, json=update_data)
    print(f"   Status: {response.status_code}")
    print(f"   Response: {response.text}")
    assert response.status_code == 200, f"Agent update failed with status {response.status_code}"
    print("   PASS: Agent update successful")

    print("\n7. Testing Agent Deregistration:")
    delete_url = f"{BASE_URL}/api/agent/{test_agent['agent_id']}"
    response = requests.delete(delete_url)
    print(f"   Status: {response.status_code}")
    print(f"   Response: {response.text}")
    assert response.status_code == 200, (
        f"Agent deregistration failed with status {response.status_code}"
    )
    print("   PASS: Agent deregistration successful")

    print("\n=== Test Summary ===")
    print("Agent Registration: PASSED")
    print("List Agents: PASSED")
    print("Get Agent Details: PASSED")
    print("Task Creation with Agent Matching: PASSED")
    print("Task Creation with No Matching Agent: PASSED")
    print("Agent Update: PASSED")
    print("Agent Deregistration: PASSED")
    print("\nAll tests completed successfully!")


if __name__ == "__main__":
    try:
        test_agent_registry()
    except Exception as e:
        print(f"\nTest failed with error: {e}")
        import traceback

        traceback.print_exc()
