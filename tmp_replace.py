from pathlib import Path
old = """  const prompt = [
    \"You are a DESIGNER. Your job is to produce EXECUTABLE CONSTRAINTS, not prose.\",
    \"Output MUST be a JSON array. No prose outside JSON.\",
    \"Each subtask must be completable in <= 10 minutes by a CLI worker.\",
    \"Avoid too-small tasks. Each subtask must produce either patch blocks or exact commands.\",
    \"IMPORTANT (hard constraints):\",
    \"- PINS-FIRST: Every subtask MUST include pins with allowed_paths + (symbols or line_windows) + forbidden_paths + max_files/max_loc.\",
    \"- Do NOT give tasks without pins. If pins cannot be derived, output a single BLOCKED task with reason 'missing_pins'.\",
    \"- Include task_class_id (or task_class_candidate) + task_class_params (or 'none' if not stable).\",
    \"- If a task matches an existing class, set task_class_id and avoid free-form acceptance (use class defaults).\",
    \"- SSOT -> axioms only: Provide ssot_assumptions (<=7 items). No quoting, no reasoning, no re-derivation.\",
    \"- Include task_class_candidate + task_class_params (or 'none' if not stable).\",
    \"- Do NOT add architecture overviews, coding style, or cautionary text.\",
    \"- Do NOT ask Executor to read navigation/README/SSOT directly.\",
    \"- Maximum 20 subtasks. Each goal <= 12 lines.\",
    \"- Always include allowedExecutors and runner fields.\",
    \"\"\n    \"Recommended pointers (use as defaults unless task-specific):\",
    \"- docs: http://127.0.0.1:18788/docs/NAVIGATION.md , http://127.0.0.1:18788/docs/AI_CONTEXT.md\",
    \"- rules: http://127.0.0.1:18788/docs/PROMPTING.md , http://127.0.0.1:18788/docs/EXECUTOR.md\",
    \"- status: http://127.0.0.1:18788/docs/STATUS.md\",
    `Required model constraint: MUST assume execution on model '${STRICT_DESIGNER_MODEL}'.`,
    \"\"\n    \"Parent goal:\"\n    t.goal,\n    \"\"\n    \"Return JSON array of subtasks matching this schema:\"\n    JSON.stringify(schema, null, 2),\n  ].join(\"\\n\")\n"""

new = """  const prompt = [
    \"You are SCC Planner (strong model). Output MUST be pure JSON (UTF-8), no markdown, no prose.\",
    \"Goal: turn the parent task into a machine-routable task graph (scc.task_graph.v1) with atomic children.\",
    \"Hard rules:\",
    \"- 子任务<=3 steps，可独立验证，改动半径写清楚。\",
    \"- fail-closed：信息不足写 NEED_INPUT 并生成 pins_fix/clarify 子任务，禁止猜测。\",
    \"- 每个子任务都要给 role、task_class、pins_spec、allowed_tests(至少1条非 task_selftest)、acceptance、stop_conditions、fallback。\",
    \"- 给出队列分区 lane (fastlane/mainlane/batchlane) 和优先级。\",
    \"- 若父任务跨模块/高风险，必须拆出 preflight 与 eval/regression 子任务。\",
    \"- patch_scope.allow_paths/deny_paths 要求最小改动半径。\",
    \"- 严格使用下方 JSON schema 字段，可增字段但不可乱序删除；缺信息用 null/空数组，并在 needs_input 说明。\",
    \"\"\n    \"Parent goal and context:\"\n    t.goal,\n    \"\"\n    \"Schema (scc.task_graph.v1):\"\n    JSON.stringify(schema, null, 2),\n    \"\"\n    \"输出仅此 JSON。模型假设：\"\n    `executor model = '${STRICT_DESIGNER_MODEL}', pins-first, CI 必须有非 task_selftest 自测。`,\n  ].join(\"\\n\")\n"""

p = Path('oc-scc-local/src/gateway.mjs')
text = p.read_text(encoding='utf-8')
if old not in text:
    raise SystemExit('old block not found')
p.write_text(text.replace(old, new), encoding='utf-8')
print('replaced')
