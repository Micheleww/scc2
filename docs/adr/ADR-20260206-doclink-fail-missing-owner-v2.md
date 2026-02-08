Context: CI doclink gate needs a reproducible failure case for missing required ADR metadata.
Decision: Add an ADR entry that intentionally omits the required owner line to exercise the gate.
Alternatives: Add the owner line; weaken/disable the gate; avoid testing the negative path.
Consequences: The gate should detect and report the missing owner metadata during CI.
Migration: After the gate behavior is validated, update the template and create compliant ADRs going forward.
