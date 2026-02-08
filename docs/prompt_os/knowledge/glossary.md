# SCC Glossary

This glossary defines core terms used across the SCC / Prompt OS system.
Each entry includes a definition, typical usage context, and related terms.

| Term | Definition | Context | Related |
| --- | --- | --- | --- |
| Agent | An AI execution unit that receives tasks and produces results. | Used when describing who/what performs work in the system. | Role, Executor |
| Artifact | A generated deliverable produced during execution (e.g., report, patch, logs). | Referenced by verifiers/judges as proof of completion. | Evidence, Submit |
| Backlog | A state where tasks are captured but not yet eligible for execution. | First stage in the task lifecycle. | Ready, Board |
| Board | The task board that manages task lifecycle state and transitions. | Used to track tasks from backlog to done/failed/blocked. | Task Lifecycle, Lane |
| Circuit Breaker | A safety mechanism that pauses task dispatch after repeated failures. | Prevents cascading failures when an executor/model is unhealthy. | Degradation Matrix, Escalation |
| Constitution | The highest-authority document defining Prompt OS rules and priorities. | Used to resolve conflicts between policies and behaviors. | Factory Policy, Contract |
| Contract | The explicit agreement between a task and the system (inputs, outputs, constraints). | Defines acceptance criteria, pins, tests, and required artifacts. | Scope, Submit |
| Degradation Matrix | A defined set of fallback strategies when a model/tool is unavailable. | Applied when quality or availability drops below thresholds. | Circuit Breaker, Escalation |
| DLQ | Dead Letter Queue; a holding area for tasks that can no longer be processed normally. | Used after repeated failures or unresolved blocks. | Quarantine, Escalation |
| Escalation | The process for handling tasks that cannot be completed within constraints. | Triggered by missing scope, unclear requirements, or persistent failures. | DLQ, Verdict |
| Evidence | Proof that a task was executed correctly (logs, diffs, screenshots, outputs). | Collected to support verification and judging. | Artifact, Hygiene Check |
| Executor | The component that runs task steps and produces artifacts (e.g., opencodecli, codex). | Executes changes, runs checks, and generates outputs. | Agent, Verifier |
| Factory Policy | Global behavior configuration applied to all tasks and roles. | Controls defaults like formatting, safety rules, and retries. | Constitution, Role |
| Gate | A checkpoint before or after execution (e.g., preflight gate, hygiene gate). | Ensures constraints are met at defined boundaries. | Preflight, Hygiene Check |
| Gateway | The HTTP API server responsible for orchestration and core scheduling. | Routes requests and coordinates Board, Executor, and Verifier. | Board, Event System |
| Goal | A natural-language statement describing what the task should accomplish. | Drives task planning, decomposition, and acceptance criteria. | Prompt, Contract |
| Hygiene Check | A post-completion formatting and consistency validation step. | Ensures outputs match required schema and conventions. | Evidence, Submit |
| Instinct | A clustered pattern of similar tasks used for recognition and reuse. | Helps standardize approaches for repeated task types. | Playbook, Map |
| Judge | The component that issues the final decision (DONE/RETRY/ESCALATE). | Consumes evidence, verifier output, and policies. | Verifier, Verdict |
| Lane | A scheduling channel used to route tasks with different priorities or constraints. | Used to limit concurrency and separate workloads. | WIP Limit, Board |
| Map | A symbolic index of repository structure (a “code map”). | Helps agents quickly locate relevant modules and boundaries. | Scope, SSOT |
| Pins | File-level access control declarations that constrain reads/writes. | Defines what paths a task is allowed to touch. | Scope, Gate |
| Playbook | A predefined sequence of steps for a known task pattern. | Used for repeatable, high-confidence execution workflows. | Instinct, Best Practices |
| Preflight | A qualification check performed before execution starts. | Verifies environment, pins, and required inputs. | Gate, Contract |
| Prompt | The instruction payload (often Markdown) given to an agent/executor. | Encodes goal, requirements, constraints, and acceptance checks. | Goal, Best Practices |
| Quarantine | An isolation state/area for problematic tasks awaiting review. | Used when tasks are unsafe to retry automatically. | DLQ, Escalation |
| Ready | A state where tasks are eligible to be picked up for execution. | Typically follows backlog once prerequisites are met. | Backlog, In Progress |
| Retry | A controlled re-attempt of execution after failure. | Used when failures are transient or fixable. | Verdict, Circuit Breaker |
| Role | A named capability and permission set for an agent. | Determines what actions an agent may perform. | Permission Matrix, Scope |
| Scope | The allowed set of files/resources a task may modify. | Enforced via pins and gates to prevent overreach. | Pins, Contract |
| Selftest | A lightweight, local verification run before submission. | Confirms generated artifacts meet basic acceptance rules. | Hygiene Check, Verifier |
| SSOT | Single Source of Truth; the uniquely trusted reference for a fact or rule. | Prevents conflicting guidance across documents/config. | Constitution, Map |
| Submit | The standardized completion output containing artifacts and metadata. | Passed to verifier and judge for evaluation. | Evidence, Verdict |
| Task | A unit of work with goal, constraints, and acceptance criteria. | The primary object tracked on the Board. | Board, Contract |
| Verifier | The component that checks outputs against constraints and tests. | Validates artifacts, scope compliance, and formatting. | Hygiene Check, Judge |
| Verdict | The final decision outcome for a submission (e.g., DONE/RETRY/ESCALATE). | Emitted by the judge based on evidence and policy. | Judge, Retry |
| WIP Limit | Work-in-progress limit: the maximum number of concurrent tasks. | Prevents overload and improves throughput predictability. | Lane, Board |

