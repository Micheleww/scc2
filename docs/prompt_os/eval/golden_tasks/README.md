# Golden Tasks

Golden tasks are standardized test cases for evaluating Prompt OS quality.

## Task Format
Each golden task is a JSON file with:
- `task`: the task definition (goal, role, files, pins)
- `expected_outcome`: expected status, changed files, test results
- `difficulty`: `easy` / `medium` / `hard`

## Example Tasks

### Golden Task 1: Simple Doc Creation (Easy)
```json
{
  "id": "golden-001",
  "name": "Create a README.md",
  "difficulty": "easy",
  "task": {
    "goal": "Create a README.md file with project name, description, and usage instructions",
    "role": "doc",
    "files": ["README.md"],
    "pins": { "allowed_paths": ["README.md", "docs/**"] }
  },
  "expected_outcome": {
    "status": "DONE",
    "changed_files": ["README.md"],
    "tests_passed": true
  },
  "evaluation_criteria": [
    "File exists and is non-empty",
    "Contains project name",
    "Contains usage section"
  ]
}
```

### Golden Task 2: Bug Fix (Medium)
Fix a small, well-scoped bug with a minimal patch and tests.

```json
{
  "id": "golden-002",
  "name": "Fix off-by-one in pagination",
  "difficulty": "medium",
  "task": {
    "goal": "Fix an off-by-one bug in paginate(items, page, page_size) where the last item of a page is dropped; add/adjust a unit test",
    "role": "code",
    "files": ["src/pagination.py", "tests/test_pagination.py"],
    "pins": { "allowed_paths": ["src/**", "tests/**", "docs/**"] }
  },
  "expected_outcome": {
    "status": "DONE",
    "changed_files": ["src/pagination.py", "tests/test_pagination.py"],
    "tests_passed": true
  },
  "evaluation_criteria": [
    "Bug reproduction test added or fixed",
    "Patch is minimal and targets root cause",
    "All tests pass"
  ]
}
```

### Golden Task 3: Multi-file Refactor (Hard)
Refactor across multiple files while keeping behavior identical and tests green.

```json
{
  "id": "golden-003",
  "name": "Refactor config loading into a module",
  "difficulty": "hard",
  "task": {
    "goal": "Refactor configuration loading so it lives in a dedicated module; update imports/usages across the codebase; keep public behavior unchanged; ensure tests still pass",
    "role": "code",
    "files": [
      "src/app.py",
      "src/config/__init__.py",
      "src/config/loader.py",
      "tests/test_app_config.py"
    ],
    "pins": { "allowed_paths": ["src/**", "tests/**", "docs/**"] }
  },
  "expected_outcome": {
    "status": "DONE",
    "changed_files": [
      "src/app.py",
      "src/config/__init__.py",
      "src/config/loader.py",
      "tests/test_app_config.py"
    ],
    "tests_passed": true
  },
  "evaluation_criteria": [
    "Refactor preserves behavior (no functional changes)",
    "Imports/usages updated consistently",
    "Tests updated as needed and pass"
  ]
}
```
