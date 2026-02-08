Title: ADR-20260206-doclink-fail-missing-owner-v4
Date: 2026-02-06
Status: Proposed
Deciders: SCC
Owner: SCC
Tags: ci, doclink, adr
Context: CI doclink gate expects ADRs to begin with a required 6-line prefix header.
Decision: Add the missing prefix lines so the doclink gate passes.
Alternatives: Keep the file minimal and allow the gate to fail (rejected).
Consequences: CI will no longer fail for this ADR on missing template prefix lines.
Migration: None.
