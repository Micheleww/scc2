# API Rules

## Table of Contents

- [Overview](#overview)
- [1. Rate Limiting](#1-rate-limiting)
- [2. Retry Policy](#2-retry-policy)
- [3. Fallback Chain](#3-fallback-chain)
- [4. Token Accounting](#4-token-accounting)
- [5. Response Validation](#5-response-validation)

## Overview

These rules define how agents should call model and service APIs safely and reliably.

## 1. Rate Limiting

- Enforce per-key and per-role limits (requests/minute and tokens/minute).
- Apply adaptive throttling on 429/503 responses.
- Use a shared limiter to prevent “thundering herd” across workers.

## 2. Retry Policy

- Retry only on transient failures (e.g., timeouts, 429, 502, 503, 504).
- Use exponential backoff with jitter.
- Cap retries to a small bounded number (e.g., 2–5 attempts) to avoid runaway costs.
- Never retry non-idempotent operations unless the API explicitly supports it.

## 3. Fallback Chain

- Define a primary model/service and an ordered fallback list.
- Fallback only when:
  - The primary is unavailable (timeouts/5xx), or
  - The primary is rate-limited beyond a threshold, or
  - The response fails validation.
- Preserve safety and policy constraints during fallback (do not “fallback into” a less safe configuration).

## 4. Token Accounting

- Track:
  - Prompt tokens, completion tokens, and total tokens per call
  - Per-run and per-user budget consumption
- Emit budget telemetry to evidence/audit logs (numbers only; no PII).
- When budgets are exceeded, degrade features or refuse with a clear error.

## 5. Response Validation

- Validate responses against the expected schema (JSON Schema / regex / structural checks).
- Reject responses that:
  - Are not parseable
  - Exceed size/token limits
  - Contain forbidden content per policy
- On validation failure, either:
  - Request a corrected response with a constrained prompt, or
  - Trigger fallback.
