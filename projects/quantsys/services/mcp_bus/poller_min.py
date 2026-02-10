#!/usr/bin/env python3

import asyncio
import hashlib
import json
import os
from datetime import datetime

import httpx

# Configuration
POLL_INTERVAL = 60  # seconds
CONTROL_PANEL_DOC_ID = "docs/REPORT/_control/CONTROL_PANEL.md"
MCP_SERVER = "http://localhost:18788/mcp"
LOCK_TIMEOUT = 3600  # seconds


class Poller:
    def __init__(self):
        self.mcp_client = httpx.AsyncClient()
        self.executed_requests = set()

    async def get_control_panel(self):
        """Get CONTROL_PANEL.md content via doc_get"""
        try:
            response = await self.mcp_client.post(
                MCP_SERVER,
                json={
                    "jsonrpc": "2.0",
                    "id": "poller_get_panel",
                    "method": "tools/call",
                    "params": {"name": "doc_get", "arguments": {"doc_id": CONTROL_PANEL_DOC_ID}},
                },
                headers={"Authorization": "Bearer test_token", "User-Agent": "poller_min"},
            )
            response.raise_for_status()
            result = response.json()
            return result.get("result", {})
        except Exception as e:
            print(f"Error getting control panel: {e}")
            return None

    async def update_control_panel(self, content, base_rev):
        """Update CONTROL_PANEL.md via doc_patch"""
        try:
            response = await self.mcp_client.post(
                MCP_SERVER,
                json={
                    "jsonrpc": "2.0",
                    "id": "poller_update_panel",
                    "method": "tools/call",
                    "params": {
                        "name": "doc_patch",
                        "arguments": {
                            "doc_id": CONTROL_PANEL_DOC_ID,
                            "base_rev": base_rev,
                            "ops": [{"type": "replace", "value": content}],
                        },
                    },
                },
                headers={"Authorization": "Bearer test_token", "User-Agent": "poller_min"},
            )
            response.raise_for_status()
            result = response.json()
            return result.get("result", {})
        except Exception as e:
            print(f"Error updating control panel: {e}")
            return None

    def parse_control_panel(self, content):
        """Parse CONTROL_PANEL.md content into structured data"""
        sections = {}
        current_section = None
        current_content = []

        for line in content.split("\n"):
            if line.startswith("## "):
                if current_section:
                    sections[current_section] = "\n".join(current_content)
                current_section = line[3:]
                current_content = []
            elif current_section:
                current_content.append(line)

        if current_section:
            sections[current_section] = "\n".join(current_content)

        return sections

    def extract_json(self, markdown_content):
        """Extract JSON from markdown code block"""
        if "```json" in markdown_content:
            start = markdown_content.find("```json") + 7
            end = markdown_content.find("```", start)
            if end > start:
                return json.loads(markdown_content[start:end].strip())
        return None

    def generate_lock_content(self, running_run_id, lock_owner):
        """Generate lock JSON content"""
        lock = {
            "running_run_id": running_run_id,
            "lock_owner": lock_owner,
            "lock_ts": datetime.now().isoformat(),
        }
        return f"```json\n{json.dumps(lock, indent=2)}\n```"

    def generate_nexttask_content(self, nexttask):
        """Generate NextTask JSON content"""
        return f"```json\n{json.dumps(nexttask, indent=2)}\n```"

    async def execute_skill(self, skill_id, inputs):
        """Execute skill via trae_run or exec"""
        try:
            # For dummy test, just create the expected artifact
            if skill_id == "skill.dummy_smoke":
                # Create the expected artifact
                artifact_path = inputs.get("expected_artifacts", [""])[0]
                if artifact_path:
                    # Use repo root as base directory
                    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
                    full_artifact_path = os.path.join(repo_root, artifact_path)
                    os.makedirs(os.path.dirname(full_artifact_path), exist_ok=True)
                    with open(full_artifact_path, "w") as f:
                        f.write(inputs.get("message", "Dummy output") + "\n")
                return {
                    "success": True,
                    "exit_code": 0,
                    "stdout": "Dummy skill executed successfully",
                    "stderr": "",
                }

            # For other skills, use exec tool
            response = await self.mcp_client.post(
                MCP_SERVER,
                json={
                    "jsonrpc": "2.0",
                    "id": "poller_exec_skill",
                    "method": "tools/call",
                    "params": {
                        "name": "exec",
                        "arguments": {"cmd": f"echo 'Executing {skill_id}'", "cwd": "."},
                    },
                },
            )
            response.raise_for_status()
            result = response.json()
            return result.get("result", {})
        except Exception as e:
            print(f"Error executing skill: {e}")
            return {"success": False, "exit_code": 1, "stdout": "", "stderr": str(e)}

    def update_runs_section(
        self, runs_section, request_id, skill_id, status, start_ts, end_ts, artifacts
    ):
        """Update Runs section"""
        # Remove existing table header if present
        runs_lines = runs_section.strip().split("\n")
        table_lines = [line for line in runs_lines if line.strip()]

        # Check if header exists
        if not table_lines or not table_lines[0].startswith("| request_id |"):
            table_lines = [
                "| request_id | skill_id | status | start_ts | end_ts | artifacts |",
                "|------------|----------|--------|----------|--------|-----------|",
            ]

        # Add new run entry
        artifacts_str = ", ".join(artifacts)
        new_run_line = (
            f"| {request_id} | {skill_id} | {status} | {start_ts} | {end_ts} | {artifacts_str} |"
        )
        table_lines.append(new_run_line)

        return "\n".join(table_lines)

    def update_artifacts_section(self, artifacts_section, artifacts, request_id, skill_id):
        """Update Artifacts section"""
        # Remove existing table header if present
        artifacts_lines = artifacts_section.strip().split("\n")
        table_lines = [line for line in artifacts_lines if line.strip()]

        # Check if header exists
        if not table_lines or not table_lines[0].startswith("| artifact_path |"):
            table_lines = [
                "| artifact_path | request_id | skill_id | create_ts |",
                "|---------------|------------|----------|-----------|",
            ]

        # Add new artifact entries
        create_ts = datetime.now().isoformat()
        for artifact_path in artifacts:
            new_artifact_line = f"| {artifact_path} | {request_id} | {skill_id} | {create_ts} |"
            table_lines.append(new_artifact_line)

        return "\n".join(table_lines)

    def update_audit_section(self, audit_section, actor, action, details):
        """Update Audit section"""
        # Remove existing table header if present
        audit_lines = audit_section.strip().split("\n")
        table_lines = [line for line in audit_lines if line.strip()]

        # Check if header exists
        if not table_lines or not table_lines[0].startswith("| ts |"):
            table_lines = ["| ts | actor | action | details |", "|----|-------|--------|---------|"]

        # Add new audit entry
        ts = datetime.now().isoformat()
        new_audit_line = f"| {ts} | {actor} | {action} | {details} |"
        table_lines.append(new_audit_line)

        return "\n".join(table_lines)

    async def run(self):
        """Main poller loop"""
        print(f"Poller started with interval {POLL_INTERVAL}s")

        while True:
            try:
                # Get control panel
                result = await self.get_control_panel()
                if not result or "success" not in result or not result["success"]:
                    print("Failed to get control panel, retrying...")
                    await asyncio.sleep(POLL_INTERVAL)
                    continue

                content = result.get("content", "")
                base_rev = result.get("rev", "")

                if not content:
                    print("Empty control panel content, retrying...")
                    await asyncio.sleep(POLL_INTERVAL)
                    continue

                # Parse control panel
                sections = self.parse_control_panel(content)
                nexttask = self.extract_json(sections.get("NextTask", ""))
                lock = self.extract_json(sections.get("Lock", ""))
                runs_section = sections.get("Runs", "")
                artifacts_section = sections.get("Artifacts", "")
                audit_section = sections.get("Audit", "")

                # Check if there's a task to execute
                if not nexttask:
                    print("No NextTask found, waiting...")
                    await asyncio.sleep(POLL_INTERVAL)
                    continue

                # Check if task already executed
                request_id = nexttask.get("request_id")
                if request_id in self.executed_requests:
                    print(f"Request {request_id} already executed, skipping...")
                    await asyncio.sleep(POLL_INTERVAL)
                    continue

                # Check lock
                lock_owner = "poller_min"
                running_run_id = hashlib.sha256(
                    f"{request_id}:{datetime.now().isoformat()}".encode()
                ).hexdigest()[:16]

                if lock and lock.get("running_run_id"):
                    # Check if lock is expired
                    lock_ts = lock.get("lock_ts")
                    if lock_ts:
                        lock_dt = datetime.fromisoformat(lock_ts)
                        if (datetime.now() - lock_dt).total_seconds() > LOCK_TIMEOUT:
                            print("Lock is expired, taking over...")
                        else:
                            print(f"Task already locked by {lock.get('lock_owner')}, waiting...")
                            await asyncio.sleep(POLL_INTERVAL)
                            continue

                # Acquire lock
                print(f"Acquiring lock for request {request_id}...")
                lock_content = self.generate_lock_content(running_run_id, lock_owner)

                # Update control panel with lock
                updated_content = content.replace(sections.get("Lock", ""), lock_content)

                update_result = await self.update_control_panel(updated_content, base_rev)
                if (
                    not update_result
                    or "success" not in update_result
                    or not update_result["success"]
                ):
                    print("Failed to acquire lock, rev conflict or error")
                    await asyncio.sleep(POLL_INTERVAL)
                    continue

                new_rev = update_result.get("new_rev", base_rev)

                # Execute skill
                print(f"Executing skill {nexttask.get('skill_id')} for request {request_id}...")
                skill_id = nexttask.get("skill_id")
                inputs = nexttask.get("inputs", {})
                start_ts = datetime.now().isoformat()

                # Add expected_artifacts to inputs for dummy execution
                inputs["expected_artifacts"] = nexttask.get("expected_artifacts", [])

                execution_result = await self.execute_skill(skill_id, inputs)
                end_ts = datetime.now().isoformat()

                status = "success" if execution_result.get("success") else "failed"
                artifacts = nexttask.get("expected_artifacts", [])

                # Update runs, artifacts, audit sections
                updated_runs = self.update_runs_section(
                    runs_section, request_id, skill_id, status, start_ts, end_ts, artifacts
                )
                updated_artifacts = self.update_artifacts_section(
                    artifacts_section, artifacts, request_id, skill_id
                )
                updated_audit = self.update_audit_section(
                    audit_section,
                    lock_owner,
                    f"executed_{skill_id}",
                    f"Request {request_id} executed with status {status}",
                )

                # Clear NextTask and Lock
                updated_nexttask = self.generate_nexttask_content({})
                updated_lock = self.generate_lock_content(None, None)

                # Get fresh content to avoid rev conflict
                fresh_result = await self.get_control_panel()
                if not fresh_result or "success" not in fresh_result or not fresh_result["success"]:
                    print("Failed to get fresh control panel, skipping update...")
                    await asyncio.sleep(POLL_INTERVAL)
                    continue

                fresh_content = fresh_result.get("content", "")
                fresh_rev = fresh_result.get("rev", "")
                fresh_sections = self.parse_control_panel(fresh_content)

                # Update all sections
                final_content = (
                    fresh_content.replace(fresh_sections.get("NextTask", ""), updated_nexttask)
                    .replace(fresh_sections.get("Lock", ""), updated_lock)
                    .replace(fresh_sections.get("Runs", ""), updated_runs)
                    .replace(fresh_sections.get("Artifacts", ""), updated_artifacts)
                    .replace(fresh_sections.get("Audit", ""), updated_audit)
                )

                # Update control panel
                final_update = await self.update_control_panel(final_content, fresh_rev)
                if final_update and "success" in final_update and final_update["success"]:
                    print(f"Request {request_id} completed successfully")
                    self.executed_requests.add(request_id)
                else:
                    print("Failed to update control panel after execution")

            except Exception as e:
                print(f"Poller error: {e}")

            # Sleep until next poll
            await asyncio.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    import asyncio

    poller = Poller()
    asyncio.run(poller.run())
