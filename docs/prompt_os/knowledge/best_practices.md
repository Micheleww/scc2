# SCC / Prompt OS Best Practices

This document describes execution and documentation best practices for SCC tasks.

## 1. Task Decomposition (Breaking Work Down)

**Principles**

1. Keep each **atomic task** small: target **< 500 lines** of code/content changes.
2. Prefer **vertical slicing (by feature/outcome)** rather than horizontal slicing (by layer).
3. A **parent task** should focus on **planning and coordination**, not implementation.

**Example**

- ✅ Vertical slice: “Add glossary + best practices + domain KB docs for Prompt OS.”
- ❌ Horizontal slice: “Update all docs headings everywhere” (too broad, unclear acceptance).

**Before (too big / vague)**

```markdown
Goal: Improve Prompt OS documentation.
```

**After (small / testable)**

```markdown
Goal: Create knowledge-layer docs.

Requirements:
- Add glossary with >= 30 terms.
- Add best practices with numbered sections + examples.
- Add domain KB with architecture + lifecycle + roles + events.

Acceptance:
- Files exist and exceed minimum size.
- Glossary is alphabetically sorted.
```

## 2. Prompt Writing (Writing Clear Goals)

**Goal must include**

1. **Background**: why the change is needed.
2. **Concrete requirements**: what must be created/modified.
3. **Acceptance criteria**: how it will be judged.

**Formatting guidance**

- Prefer **Markdown** with headings, lists, and code blocks.
- Include **before/after** examples for ambiguous requirements.
- Use consistent terminology (see `glossary.md`).

**Before (missing acceptance)**

```markdown
Add a glossary.
```

**After (complete)**

```markdown
Add `docs/prompt_os/knowledge/glossary.md`.

Acceptance:
- Table format with columns: Term, Definition, Context, Related
- Alphabetically sorted
- At least 30 terms
```

## 3. Testing (What to Test, and in What Order)

**Recommended sequence**

1. **Existence tests**: confirm files are generated/updated.
2. **Content tests**: confirm key strings/sections exist.
3. **Integration tests**: confirm multiple files work together (links, references, shared vocabulary).

**Examples**

Existence test:

```bash
python -c "import pathlib; p=pathlib.Path('docs/prompt_os/knowledge/glossary.md'); print(p.exists())"
```

Content test:

```bash
python -c "import pathlib; t=pathlib.Path('docs/prompt_os/knowledge/glossary.md').read_text('utf-8'); print('Circuit Breaker' in t)"
```

Integration test (cross-doc vocabulary):

```bash
python -c "import pathlib; g=pathlib.Path('docs/prompt_os/knowledge/glossary.md').read_text('utf-8'); d=pathlib.Path('docs/prompt_os/knowledge/domain_kb.md').read_text('utf-8'); print('Gateway' in g and 'Gateway' in d)"
```

## 4. Error Recovery (How to Respond to Failures)

**If CI_FAILED**

1. Read `selftest.log` first.
2. Fix the root cause.
3. Re-run the smallest relevant check.

**If SCOPE_CONFLICT**

1. Re-check **pins** allowlist.
2. Ensure no files outside scope were changed.
3. If additional files are required, trigger escalation with a clear list of missing paths.

**If TIMEOUT**

1. Split the work into smaller atomic tasks.
2. Reduce search surface area (use a map / targeted file reads).
3. Prefer deterministic steps over exploration.

## 5. Documentation (What to Produce)

**Minimum documentation set**

1. `report.md` must explain **what changed** and **why**.
2. Code/content changes must be represented in `patch.diff`.
3. New files must be listed in `new_files` in submission metadata.

**Example report snippet**

```markdown
Changes:
- Added SCC glossary for consistent terminology.
- Added best practices to standardize decomposition, prompting, and testing.
- Added domain knowledge base describing architecture and lifecycle.

Rationale:
- Reduces ambiguity and improves repeatability across agents and roles.
```

