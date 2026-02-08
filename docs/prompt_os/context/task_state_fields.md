# Task State Fields

This document enumerates common task object fields used by PromptOS/SCC, their meaning, and mutability expectations.

## Field Table

| Field | Type | Description | Mutable |
|------|------|-------------|---------|
| `id` | `uuid` | Task unique identifier. | No |
| `parent_id` | `uuid \| null` | Parent task id if this is a child task. | No |
| `status` | `enum` | `backlog/ready/in_progress/done/failed`. | Yes |
| `kind` | `enum` | Task kind: `parent/atomic`. | No |
| `role` | `string` | Execution role (e.g., executor, curator). | No |
| `lane` | `enum` | `fastlane/mainlane/batchlane/quarantine/dlq`. | Yes |
| `priority` | `number` | Scheduling priority (higher runs sooner). | Yes |
| `title` | `string` | Human-friendly task title. | No |
| `goal` | `string` | Task goal/instructions. | No |
| `created_at` | `datetime` | Creation timestamp. | No |
| `updated_at` | `datetime` | Last update timestamp. | Yes |
| `started_at` | `datetime \| null` | When execution started. | Yes |
| `finished_at` | `datetime \| null` | When execution finished. | Yes |
| `attempt` | `number` | Current attempt index. | Yes |
| `max_attempts` | `number` | Maximum attempts before terminal failure. | No |
| `inputs` | `object` | Structured inputs (pins, constraints, pointers). | No |
| `pins` | `object` | Pins declaration (`allowed_paths`, `forbidden_paths`). | No |
| `constraints` | `object` | Execution constraints (must/forbid/unknown_policy). | No |
| `acceptance` | `array<string>` | Acceptance criteria for completion. | No |
| `execution_plan` | `object` | Stop conditions, fallback policies, retries. | No |
| `required_artifacts` | `object` | Artifact paths required by the runner. | No |
| `submit_contract` | `object` | Schema expectations for final submission. | No |
| `error_snippets` | `array<object>` | Recent error snippets and metadata. | Yes |
| `assigned_to` | `string \| null` | Assigned worker/agent identifier. | Yes |
| `tags` | `array<string>` | Labels (area/type). | Yes |
| `notes` | `string \| null` | Free-form notes / rationale. | Yes |
| `progress` | `number` | Normalized progress (`0.0`–`1.0`). | Yes |
| `result` | `object \| null` | Structured final result metadata. | Yes |
| `timeout_ms` | `number \| null` | Optional task timeout budget. | Yes |

## Example Task Object (Simplified)

```json
{
  "id": "254587b3-c219-4af2-b8f1-3cebe2a9771e",
  "parent_id": "d7baa8d0-5124-403a-a16a-0e2770698a76",
  "title": "PromptOS T05: Context Layer — Pins, Budget, Memory, State",
  "kind": "atomic",
  "role": "executor",
  "lane": "batchlane",
  "priority": 5,
  "status": "in_progress",
  "attempt": 1,
  "max_attempts": 2,
  "created_at": "2026-02-08T00:00:00Z",
  "updated_at": "2026-02-08T00:10:00Z",
  "started_at": "2026-02-08T00:10:00Z",
  "finished_at": null,
  "pins": {
    "allowed_paths": ["docs/prompt_os/context/**"],
    "forbidden_paths": ["**/secrets/**"]
  },
  "constraints": {
    "must": ["patch-only", "minimal-diff"],
    "forbid": ["reading outside pins allowlist"],
    "unknown_policy": "NEED_INPUT"
  },
  "tags": ["docs", "prompt_os"],
  "progress": 0.5,
  "notes": "Drafting context layer documentation"
}
```
