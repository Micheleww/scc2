# Best Practices

## 1. Task Decomposition
- Each atomic task should change < 500 lines of code
- Prefer vertical slicing (by feature) over horizontal (by layer)
- Parent tasks plan only — never modify code directly
- Each atomic task should touch 1-3 files, not 10+

## 2. Prompt Writing
- Goal MUST include: **background** (why), **requirements** (what), **acceptance criteria** (how to verify)
- Use markdown formatting for structure — models parse it better than plain text
- Provide before/after examples when asking for transformations
- Be explicit about output format expectations

## 3. Pins Configuration
- Use the narrowest possible pins — pin specific files, not directories
- Use `line_windows` to pin specific line ranges for large files
- For doc tasks: pin only the target output path + 1-2 reference files
- Never pin `**/*` or `src/**` — this wastes tokens massively

## 4. Testing
- Priority: existence tests (`test -s file`) > content tests (`grep -q pattern file`) > integration tests
- Every task needs at least one non-selftest test command
- Test the output, not the process
- Include negative tests for critical constraints (e.g., verify secrets aren't leaked)

## 5. Error Recovery
- `CI_FAILED`: Read selftest.log first, understand the failure, fix the root cause
- `SCOPE_CONFLICT`: Check pins.allowed_paths, remove out-of-scope changes
- `TIMEOUT_EXCEEDED`: Split into smaller subtasks
- `PINS_INSUFFICIENT`: Set NEED_INPUT, list exactly which files are needed

## 6. Documentation
- `report.md` is mandatory — explain what you did and why
- Include patch.diff for all code changes
- List all tests run in selftest.log, even if they passed
