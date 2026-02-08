# Task State Fields

| # | Field | Type | Description | Mutable |
|---|-------|------|-------------|---------|
| 1 | `id` | uuid | Unique task identifier | No |
| 2 | `kind` | enum | `parent` or `atomic` | No |
| 3 | `title` | string | Short descriptive title | No |
| 4 | `goal` | string | Full task description (the prompt) | No |
| 5 | `parentId` | uuid\|null | Link to parent task | No |
| 6 | `status` | enum | `backlog\|needs_split\|ready\|in_progress\|blocked\|done\|failed` | Yes |
| 7 | `role` | string | Execution role (e.g., engineer, doc) | No |
| 8 | `lane` | enum | `fastlane\|mainlane\|batchlane\|quarantine\|dlq` | Yes |
| 9 | `priority` | number | Numeric priority (lower = higher priority) | Yes |
| 10 | `files` | string[] | Target file paths (required for atomic) | No |
| 11 | `skills` | string[] | Custom skills (defaults to role skills) | No |
| 12 | `pins` | object | `{ allowed_paths, forbidden_paths }` | No |
| 13 | `pins_instance` | object | Pre-resolved pins content | Yes |
| 14 | `pins_pending` | boolean | Whether pins are still being resolved | Yes |
| 15 | `pins_target_id` | string | Target pins resolution ID | Yes |
| 16 | `allowedExecutors` | string[] | Permitted executors | No |
| 17 | `allowedModels` | string[] | Permitted model IDs (max 8) | No |
| 18 | `allowedTests` | string[] | Test commands (max 24) | No |
| 19 | `assumptions` | string[] | Context constraints (max 16) | No |
| 20 | `contract` | object | Acceptance contract | No |
| 21 | `toolingRules` | object | Custom tool rules | No |
| 22 | `pointers` | object | Reference pointers | No |
| 23 | `area` | string | Area name (affects lane inference) | No |
| 24 | `runner` | enum | `external\|internal` | No |
| 25 | `timeoutMs` | number | Execution timeout in ms | No |
| 26 | `task_class_id` | string | Task classification ID | No |
| 27 | `task_class_candidate` | string | Candidate classification | Yes |
| 28 | `task_class_params` | object | Classification parameters | Yes |
| 29 | `prompt_ref` | object | Prompt template reference | Yes |
| 30 | `createdAt` | number | Creation timestamp (ms) | No |
| 31 | `updatedAt` | number | Last update timestamp (ms) | Yes |
| 32 | `lastJobId` | string\|null | Most recent job ID | Yes |
