# Eval / Replay (MVP)

目标：把验证分层固化为 **smoke** / **regression** 两档，默认只跑 smoke；回归进入 batchlane 或按风险触发。

入口：
- `eval/eval_manifest.json`（权威配置）
- `contracts/eval/eval_manifest.schema.json`（schema）

