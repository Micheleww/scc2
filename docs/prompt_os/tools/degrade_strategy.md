# Degradation Strategy

## Table of Contents

- [Overview](#overview)
- [1. Model Degradation](#1-model-degradation)
- [2. Feature Degradation](#2-feature-degradation)
- [3. Circuit Breaker Rules](#3-circuit-breaker-rules)
- [Operational Guidance](#operational-guidance)

## Overview

This document defines how the system degrades gracefully when models or features are unavailable.

## 1. Model Degradation

Degrade by tiers, from higher capability/cost to lower capability/cost.

```
Tier 1 (Premium): claude-opus, gpt-4o
Tier 2 (Standard): claude-sonnet, gpt-4o-mini
Tier 3 (Free): glm-4.7, kimi-k2.5, deepseek
```

Rules:

- Start with the configured primary model in its tier.
- On failure, try the next model in the same tier (if any).
- If the tier is exhausted, drop to the next tier.
- Preserve safety policy: do not switch to a model/provider that lacks required guardrails.

## 2. Feature Degradation

- Map unavailable → fall back to file list navigation.
- Instinct unavailable → skip clustering and run deterministic steps.
- Playbook unavailable → execute single-step mode.

Additional guidance:

- Prefer correctness over completeness when degrading.
- Emit a user-visible note describing what was degraded and why.

## 3. Circuit Breaker Rules

- Continuous failures threshold: after **N** consecutive failures, trip the breaker for that model/executor.
- When tripped:
  - Stop routing requests to that target.
  - Enter cooldown for a fixed duration.
- After cooldown:
  - Half-open: allow a small number of trial requests.
  - If trials succeed, close the breaker; otherwise, trip again.

## Operational Guidance

- Prefer predictable degradation over repeated retries.
- Record breaker state transitions to evidence logs (no PII).
- If degradation changes output guarantees, tighten response validation.
