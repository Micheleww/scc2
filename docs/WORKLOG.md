# WORKLOG

仅保留最近一次快照，历史已降级为日志文件。
更新入口：`C:\scc\update_worklog.ps1`

## Last Snapshot (2026-02-04)
- gateway: 18788
- scc upstream: http://127.0.0.1:18789
- opencode upstream: http://127.0.0.1:18790

## Factory Runthrough Reset (2026-02-06)
- Gateway stabilized to a single instance on port 18788
- EXEC_ROOT set to C:/scc so tasks operate on control-plane assets
- Next: run a happy-path doc task + exercise policy gate and DLQ
(v4) worker-codex ran
2026-02-06: smoke2 placeholder line for L4 auto-pins fix path.

2026-02-06: factory run-through started (codex external worker ok).
2026-02-06: codex external worker happy-path confirmed.
2026-02-06: smoke: contracts_gate + replay_bundle (codex) task 3c741d4a-76de-4fbb-ab60-97e9d0a7048c (gates PASS).
2026-02-06: smoke: L2+L3 after worker watchdog (gates PASS).
2026-02-06: smoke: gateway-owned gates (no executor tests) task 34de3715-0857-47f0-b7ad-bcb2d1e65ded (worklog appended).
2026-02-06: smoke: L2+L3 stable after gateway overwrite.
2026-02-06: smoke: L2+L3 stable after gateway overwrite (gateway overwrites executor artifacts) task daca6a3f-65eb-4bb8-b161-324dd328842e.
2026-02-06: smoke3 dummy line for pins fix + tooling fallback.
2026-02-06: dummy line for L4 pins reason smoke.
2026-02-06: policy smoke executor appended single-line doc update.
2026-02-06: stop-bleeding allow smoke doc-only update.
invalid-worklog-entry: deliberately breaking schema for rollback smoke test.
2026-02-06: AllowedTests runner smoke doc append.
2026-02-07 06:41:07: executor appended timestamp line (task 9a3e9968-e664-434f-a9fa-46b4146e6e7d).
2026-02-07 06:51:21: executor appended timestamp line (task d8cfdbf5-88f0-4ba5-96a9-e824605e79e9).
