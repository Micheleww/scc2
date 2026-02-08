# Evaluation Metrics

This document defines the core metrics used to continuously evaluate Prompt OS quality.

## 1) Task Success Rate
- **Name:** Task Success Rate
- **Definition (formula):** `done_count / total_count`
- **Target:** `> 85%`
- **Calculation method:** Aggregate all evaluated tasks over the selected period and count tasks with submit status `DONE`.
- **Cadence:** Daily / Weekly
- **Alert threshold:** Warn if `< 80%` daily, critical if `< 75%` weekly.

## 2) First-Attempt Pass Rate
- **Name:** First-Attempt Pass Rate
- **Definition (formula):** `first_attempt_done / total_count`
- **Target:** `> 60%`
- **Calculation method:** Count tasks that reached `DONE` on attempt #1, divided by total tasks.
- **Cadence:** Daily / Weekly
- **Alert threshold:** Warn if `< 55%`, critical if `< 45%`.

## 3) Escalation Rate
- **Name:** Escalation Rate
- **Definition (formula):** `escalated_count / total_count`
- **Target:** `< 10%`
- **Calculation method:** Count tasks that required escalation (e.g., model/role upgrade, human handoff), divided by total tasks.
- **Cadence:** Daily / Weekly
- **Alert threshold:** Warn if `> 12%`, critical if `> 20%`.

## 4) Average Attempts
- **Name:** Average Attempts
- **Definition (formula):** `sum(attempts) / total_count`
- **Target:** `< 1.5`
- **Calculation method:** For each task, record the number of attempts until terminal state, then compute the mean.
- **Cadence:** Daily / Weekly
- **Alert threshold:** Warn if `> 1.6`, critical if `> 2.0`.

## 5) Policy Violation Rate
- **Name:** Policy Violation Rate
- **Definition (formula):** `violation_count / total_count`
- **Target:** `< 2%`
- **Calculation method:** Count tasks flagged as policy violations (safety, privacy, licensing, pinned-scope violations), divided by total tasks.
- **Cadence:** Daily / Weekly
- **Alert threshold:** Warn if `> 2%`, critical if `> 5%`.

## 6) Token Efficiency
- **Name:** Token Efficiency
- **Definition (formula):** `tokens_used / task_complexity_score`
- **Target:** Continually decreasing (trend-based)
- **Calculation method:** Normalize total tokens used per task by a task complexity score (e.g., 1=easy, 2=medium, 3=hard) and track median + p95.
- **Cadence:** Weekly
- **Alert threshold:** Warn if 2-week moving average increases by `> 10%`.

## 7) Test Coverage
- **Name:** Test Coverage
- **Definition (formula):** `tasks_with_tests / total_tasks`
- **Target:** `100%`
- **Calculation method:** Count tasks with at least one runnable test or verifiable check (unit/integration/gateway checks), divided by total tasks.
- **Cadence:** Weekly
- **Alert threshold:** Warn if `< 95%`, critical if `< 90%`.

## 8) Evidence Completeness
- **Name:** Evidence Completeness
- **Definition (formula):** `tasks_with_full_evidence / total_tasks`
- **Target:** `> 95%`
- **Calculation method:** A task has full evidence if it includes the required artifacts (e.g., patch diff, self-test log, report, submit JSON) and they are internally consistent.
- **Cadence:** Daily / Weekly
- **Alert threshold:** Warn if `< 95%`, critical if `< 90%`.

---

### Notes on metric computation
- Use the same task population (same `total_count`) across metrics for a given window.
- Prefer reporting both mean and distribution percentiles (p50/p95) for attempt- and token-based metrics.
- Alerts should be evaluated on both short windows (daily) and rolling windows (weekly) to reduce noise.
