# Soft Policies

> Violation of soft policies produces a **warning** but does not fail the task.

## 1. Code Style
- **Suggestion**: Follow the existing code style in the repository (indentation, naming conventions, bracket placement)
- **Consequence**: Warning logged in report.md
- **Exception**: When the task goal explicitly specifies a different style

## 2. Documentation
- **Suggestion**: Add JSDoc/docstring comments to new public functions
- **Consequence**: Warning from hygiene check
- **Exception**: Trivial one-line helpers, internal functions with self-explanatory names

## 3. Commit Messages
- **Suggestion**: Use conventional commit format (`feat:`, `fix:`, `docs:`, `refactor:`)
- **Consequence**: Warning logged
- **Exception**: When the project uses a different commit convention

## 4. Error Handling
- **Suggestion**: Use explicit try-catch with meaningful error messages instead of empty catch blocks
- **Consequence**: Warning in code review
- **Exception**: Best-effort operations where failure is acceptable (e.g., optional cleanup)

## 5. Logging
- **Suggestion**: Use structured logging with context (task_id, role, operation)
- **Consequence**: Warning logged
- **Exception**: Debug-only log statements that will be removed
