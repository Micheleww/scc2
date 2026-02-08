# SCC Glossary

| Term | Definition | Context | Related |
|------|-----------|---------|---------|
| **Agent** | An AI execution unit that receives a task and produces results | The primary actor in the SCC system | Role, Executor |
| **Atomic Task** | An executable unit of work with `kind: "atomic"` | Must have `files[]`, can be dispatched to executor | Parent Task, Board |
| **Board** | The task management system that tracks all task lifecycles | Central state store in gateway | Lane, Status |
| **Circuit Breaker** | Pattern that stops dispatching after consecutive failures | Prevents wasting resources on broken executor/model | Degradation Matrix |
| **Constitution** | The highest-authority document governing all agent behavior | Overrides all other policies and contracts | Conflict Order |
| **Context Pack** | Pre-assembled markdown document injected into agent prompt | Contains pinned file contents, map summary | Pins, Token Budget |
| **Contract** | Bilateral agreement between agent and system for a task | Defines obligations, scope, and breach handling | Task, Pins |
| **Degradation Matrix** | Strategy for falling back when models/features are unavailable | Tier 1→2→3 model fallback chain | Circuit Breaker |
| **DLQ** | Dead Letter Queue — where abandoned tasks go | Terminal state, requires manual intervention | Lane, Escalation |
| **Escalation** | Process of upgrading task handling when current approach fails | Level 0→4: retry → model → role → human → abort | Verdict |
| **Evidence** | Artifacts proving task execution results | report.md, selftest.log, patch.diff, submit.json | Submit, Artifact |
| **Factory Policy** | Global configuration controlling system behavior | WIP limits, lane budgets, circuit breaker settings | Hard Policy |
| **Gate** | Checkpoint validating task before or after execution | Preflight (before), Hygiene (after) | Preflight, Hygiene |
| **Goal** | Natural language description of what a task should accomplish | The primary prompt given to the agent | Task, Contract |
| **Hygiene Check** | Post-execution validation of output format and completeness | Checks submit.json schema, artifact presence | Gate, Submit |
| **Instinct** | Pattern recognition clustering for similar tasks | Groups tasks by similarity for optimization | Token CFO |
| **Lane** | Scheduling channel determining dispatch priority | fastlane > mainlane > batchlane | Board, Priority |
| **Map** | Code structure index with symbols, entry points, dependencies | Built by map_v1.mjs, injected into context | Context Pack |
| **Parent Task** | Container task with `kind: "parent"` that holds children | Cannot be executed directly, only planned/split | Atomic Task |
| **Pins** | Task-level file access control declarations | `allowed_paths` and `forbidden_paths` with glob patterns | Scope, Context Pack |
| **Playbook** | Predefined sequence of tasks for common operations | Automates multi-step workflows | Planner |
| **Preflight** | Pre-execution check validating role, pins, and test config | Must pass before agent begins work | Gate, Role |
| **Prompt Registry** | System managing prompt templates and blocks | `registry.json` + `blocks/*.txt` with `{{placeholder}}` | Context Pack |
| **Role** | Permission and capability set assigned to an agent | Defined in `roles/*.json`, controls tools/paths/actions | Agent, Policy |
| **Scope** | The set of files an agent is authorized to modify | Intersection of pins and role write permissions | Pins, Role |
| **Skill** | Specialized capability available to a role | Defined in `skills/` directory, attached to roles | Role |
| **SSOT** | Single Source of Truth — authoritative system state | Managed exclusively by ssot_curator role | Designer |
| **Submit** | Standardized output format when agent completes a task | `submit.json` following `scc.submit.v1` schema | Evidence, Verdict |
| **Token CFO** | Automated system analyzing and reducing token waste | Runs every 120s, detects unused context files | Context Budget |
| **Verdict** | System's judgment on a task submission | DONE / RETRY / ESCALATE / REJECT | Judge, Submit |
| **WIP Limit** | Maximum number of simultaneously in-progress tasks | Enforced per-system and per-lane | Factory Policy |
