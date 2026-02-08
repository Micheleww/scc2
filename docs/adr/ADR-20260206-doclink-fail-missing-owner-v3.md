Context: CI doclink gate fails when ADR frontmatter is incomplete (missing owner).
Decision: Intentionally ship an ADR without an Owner line to validate gate behavior (v3).
Alternatives: Add Owner now; or disable/relax the doclink gate.
Consequences: Expect CI failure until gate is updated or content is corrected.
Migration: Follow up by adding the missing Owner field or updating the gate rules.
