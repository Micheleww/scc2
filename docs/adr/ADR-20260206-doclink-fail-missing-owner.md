Context: We need a failing ADR sample to verify doclink/ADR lint catches missing metadata.
Decision: Add an ADR that intentionally omits the required Owner line.
Alternatives: Add a dummy Owner value; disable the lint; or exclude this file from checks.
Consequences: CI/doc gates should flag this ADR as invalid until corrected.
Migration: Add an Owner line to this ADR once the failure scenario is no longer needed.
