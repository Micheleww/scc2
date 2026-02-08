# Degradation Strategy

> Prompt OS — Tools Layer / Degradation Strategy

## Overview

When tools or resources become unavailable, SCC follows a graceful degradation strategy rather than hard-failing. This ensures maximum task completion even under constrained conditions.

## Degradation Levels

```
Level 0: Full Capability     — All tools available, normal operation
Level 1: Reduced Tools       — Some tools unavailable, alternatives used
Level 2: Read-Only Mode      — Write tools failed, read/analyze only
Level 3: Offline Mode        — No external tools, prompt-only reasoning
Level 4: Emergency Stop      — Critical failure, all tasks halted
```

## Tool Degradation Matrix

| Tool | Fallback | Degradation Level | Action |
|------|----------|-------------------|--------|
| `git` | None | L4 (Emergency) | Halt — VCS is critical |
| `rg` | `grep` | L1 | Use grep with reduced performance |
| `node` | None | L4 (Emergency) | Halt — runtime is critical |
| `python` | `node` | L1 | Rewrite test in JS if possible |
| `pytest` | manual check | L2 | Skip automated tests, note in evidence |
| `npm` | cached modules | L1 | Use existing node_modules |
| `curl` | None | L1 | Skip network calls, use cached data |
| `jq` | `node -e` | L1 | Parse JSON via Node.js |

## Budget Degradation

When token budget is constrained:

| Budget Remaining | Strategy |
|------------------|----------|
| > 70% | Normal operation |
| 50-70% | Reduce context pack size (drop L2 pins) |
| 30-50% | Summarize rather than include full files |
| 10-30% | Minimal context (goal + critical pins only) |
| < 10% | Emergency: complete current task, halt queue |

## Circuit Breaker

The gateway implements circuit breakers for executor failures:

```
Closed → Half-Open → Open
  ↑         │         │
  └─────────┘         │ (consecutive failures > threshold)
  (success)           ↓
                  Block dispatch to executor
                  Wait cooldown period
                  Try single probe task
                  Success → Close circuit
                  Fail → Reopen
```

**Thresholds:**
- Open after: 3 consecutive failures
- Cooldown: 120 seconds
- Probe: 1 minimal task
- Max open duration: 600 seconds → escalate

## Recovery Procedures

### Tool Recovery
1. Detect tool failure via non-zero exit code or timeout
2. Check degradation matrix for fallback
3. If fallback exists → use it, log degradation event
4. If no fallback → emit appropriate fail code
5. After task completion → attempt tool recovery check

### Budget Recovery
1. Token CFO detects waste pattern (>60% unused context)
2. Auto-correction: tighten pins via `pinsExclusionMap`
3. Next task gets reduced context pack
4. Monitor: if waste drops below 30%, restore original pins

### Circuit Recovery
1. Circuit opens → log `CIRCUIT_OPEN` event
2. Queue tasks for that executor are paused
3. After cooldown → send probe task
4. Probe succeeds → close circuit, resume queue
5. Probe fails → extend cooldown, alert human after 3rd failure
