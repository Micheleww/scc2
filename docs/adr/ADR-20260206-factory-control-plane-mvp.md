# ADR-20260206-factory-control-plane-mvp

Context: The SSOT tree is drifting and SCC lacks mechanisms to operate as a self-running factory.
Decision: Define the MVP control-plane as roles/skills/contracts registries plus a `factory_policy` for budgets and lanes, enforce CI gates (SSOT/DocLink/Schema/Hygiene), and orchestrate retries via a DLQ.
Alternatives: Rely on human discipline and manual review without automated gates.
Consequences: This adds stricter gating but clarifies ownership and reduces task explosions by making failure handling explicit.
Migration: Phase in by documenting `docs/contracts` first, then adding module manifests and the Map.
Owner: `ssot_curator` and `doc_adr_scribe`.

- Status: Accepted.
- Date: 2026-02-06.
- Owner: `ssot_curator` and `doc_adr_scribe`.

## Context
The SSOT tree is drifting and SCC lacks mechanisms to operate as a self-running factory.

## Decision
Define the MVP control-plane as roles/skills/contracts registries plus a `factory_policy` for budgets and lanes, enforce CI gates (SSOT/DocLink/Schema/Hygiene), and orchestrate retries via a DLQ.

## Alternatives
Rely on human discipline and manual review without automated gates.

## Consequences
This adds stricter gating but clarifies ownership and reduces task explosions by making failure handling explicit.

## Migration
Phase in by documenting `docs/contracts` first, then adding module manifests and the Map.
