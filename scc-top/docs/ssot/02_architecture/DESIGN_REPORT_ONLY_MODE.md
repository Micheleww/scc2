---
oid: 01KGEJFSZQCP8ZE0CVY28ZQBY0
layer: ARCH
primary_unit: A.PLANNER
tags: [S.ADR]
status: active
---

# Report-Only Mode Design Document

## Objective
Implement a report-only mode that allows the ATA system to report what actions would be taken without actually executing them. This is especially useful for high-risk changes where we want to preview the impact before actually making changes.

## Design

### Configuration Changes
1. Add a `report_only` boolean flag to the `ata.yaml` configuration file
2. Add a command-line argument `--report-only` to the runner to override the config

### Execution Flow Changes
1. When in report-only mode, all executors will log what they would do instead of executing actions
2. MockExecutor: Report what would be executed with delay
3. ShellExecutor: Report the command that would be run without running it
4. TraeExecutor: Report what would be executed without running it
5. CursorCodexExecutor: Report what would be executed without running it
6. IfcliExecutor: Report what would be executed without running it

### Expected Behavior
- In report-only mode, no actual changes are made to the system
- All actions that would be taken are logged in detail
- The result status should be 'done' but with a 'report_only' flag
- Artifacts should contain the report of what would have been done

### Implementation
1. Add a `report_only` flag to the Config class
2. Add a `report_only` parameter to each Executor's execute method
3. Modify each executor to report actions instead of executing when in report-only mode
4. Update the main runner loop to pass the report_only flag to executors
