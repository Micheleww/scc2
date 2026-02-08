# Flow: CI Fixup v1

适用：任务执行完成但 CI gate 失败/跳过，需要补齐证据或修复测试/实现。

## 触发条件

- `ci_gate_result.ok=false`
- 或 `ci_gate_skipped.required=true`

## 约束

- 最多补救 2 次（超过则保持 failed，交给上游决定升级/拆分）。
- 修复任务必须把“失败根因 → 修复动作 → 可复现命令 → 证据路径”写清楚。

## 最小闭环步骤

1. 系统自动创建 `ci_fixup_v1`（角色默认 `qa`）
2. Fixup 执行后：CI gate 再次运行
3. 通过：源任务可重新进入 ready 并重跑；不通过：继续失败（最多 2 次）

