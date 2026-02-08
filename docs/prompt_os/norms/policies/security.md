# Security Policies

> Security policies protect the system, its users, and their data.

## 1. Secret Protection
- **Rule**: Paths matching `**/secrets/**` are NEVER accessible — no read, write, copy, or reference
- **Enforcement**: Preflight gate blocks any task with secrets in pins; verifier rejects any submit touching secrets
- **Violation**: `POLICY_VIOLATION` → immediate escalation to human (Level 3)

## 2. No Network Access
- **Rule**: Network access (HTTP, DNS, sockets) is forbidden unless `"network"` is in `role.tools.allow`
- **Enforcement**: Tool policy check before execution
- **Violation**: `POLICY_VIOLATION` → task failure

## 3. Input Validation
- **Rule**: Any external input (user-provided strings, API responses, file contents) must be validated before use in commands or code generation
- **Enforcement**: Code review gate
- **Violation**: Warning + mandatory review

## 4. No Eval/Exec with Untrusted Input
- **Rule**: `eval()`, `exec()`, `child_process.exec(userInput)`, `Function(userInput)` are prohibited with any untrusted or user-supplied data
- **Enforcement**: Static analysis in hygiene check
- **Violation**: `POLICY_VIOLATION` → task failure

## 5. Dependency Safety
- **Rule**: No new dependencies may be added without explicit mention in the task goal. Version pinning is required.
- **Enforcement**: Diff analysis of package.json changes
- **Violation**: Warning + review required

## 6. Credential Hygiene
- **Rule**: No API keys, tokens, passwords, or credentials may appear in logs, reports, commit messages, or any output artifact
- **Enforcement**: Post-processing scan of all artifacts
- **Violation**: `POLICY_VIOLATION` → task failure + immediate credential rotation recommended
