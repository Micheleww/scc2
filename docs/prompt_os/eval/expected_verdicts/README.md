# Expected Verdicts

Maps golden task outcomes to expected system verdicts.

## Verdict Types
- **DONE:** Task completed successfully.
- **RETRY:** Task needs another attempt (e.g., incomplete output, failing tests, wrong files).
- **ESCALATE:** Task needs a model/role upgrade or additional capabilities (e.g., missing context, blocked by constraints, needs human decision).
- **REJECT:** Task output violates policies (e.g., unsafe content, privacy violations, license issues, out-of-scope file access).

## Verdict Logic (How to Decide)
- If **submit status is `DONE`** and **tests pass**, expected verdict is **DONE**.
- If **submit status is `DONE`** but **tests fail**, expected verdict is **RETRY** (the work is not validated).
- If **submit status is `FAILED`**, expected verdict is **RETRY** (keep iterating unless policy/blocked).
- If **submit status is `NEED_INPUT`** (blocked or missing required information), expected verdict is **ESCALATE**.
- If output is **policy-violating** (regardless of test status), expected verdict is **REJECT**.

## Verdict Matrix

The matrix below enumerates the expected verdict for common combinations of submit status and test outcomes.

| Golden Task | Submit Status | Tests | Expected Verdict |
|------------|--------------|-------|-----------------|
| golden-001 | DONE | passed | DONE |
| golden-001 | DONE | failed | RETRY |
| golden-001 | FAILED | - | RETRY |
| golden-001 | NEED_INPUT | - | ESCALATE |
| golden-001 | REJECTED | - | REJECT |
| golden-002 | DONE | passed | DONE |
| golden-002 | DONE | failed | RETRY |
| golden-002 | FAILED | - | RETRY |
| golden-002 | NEED_INPUT | - | ESCALATE |
| golden-002 | REJECTED | - | REJECT |
| golden-003 | DONE | passed | DONE |
| golden-003 | DONE | failed | RETRY |
| golden-003 | FAILED | - | RETRY |
| golden-003 | NEED_INPUT | - | ESCALATE |
| golden-003 | REJECTED | - | REJECT |

### Notes
- `Tests = -` means tests are not available or not executed for that status.
- The `REJECTED` submit status is a convenient label for cases where the system blocks output due to policy violations; if your system uses a different status name, map it equivalently.
