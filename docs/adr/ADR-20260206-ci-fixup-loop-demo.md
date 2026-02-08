Context: We need a tiny ADR that intentionally demonstrates the CI “fixup loop” scenario when documentation registration is missing.
Decision: Add this ADR as a minimal six-line record while intentionally leaving `docs/INDEX.md` unchanged.
Alternatives: We could also add the required index entry, but that would defeat the purpose of the demo.
Consequences: Some CI doclink or doc-registration checks may fail until a follow-up change registers this ADR.
Migration: A subsequent PR can add a single bullet to `docs/INDEX.md` to register this file and close the loop.
Owner: SCC CI demo maintainers.
