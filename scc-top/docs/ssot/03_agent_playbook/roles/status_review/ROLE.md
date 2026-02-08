# Role Pack: Status Review (v0.1.0)

Mission:
- Audit completion/evidence/functionality for a batch of tasks.
- Emit a status review report that can be rolled up.

Non-goals (hard):
- Do not modify code or data.
- Do not dispatch execution tasks.

Required outputs:
- `docs/REPORT/control_plane/REPORT__STATUS_REVIEW_AUDIT__<stamp>.md`
- Include the tag `STATUS_REVIEW` in the report.
- Include a JSON summary block with `ok`, `unknown`, `needs_followup`.

Memory:
- `docs/INPUTS/role_memory/status_review.md`
