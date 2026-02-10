import { createJobExecutor } from './L6_execution_layer/executors/opencodecli_executor.mjs'

const executor = createJobExecutor({ maxRounds: 5 })

const result = await executor.execute({
  id: 'test_001',
  prompt: \请完成以下任务：
1. 使用 list_dir 工具查看 C:\\\\scc\\\\scc-bd\\\\L1_code_layer 目录
2. 告诉我你看到了什么文件

记住使用工具调用格式：<tool_call>{"tool": "list_dir", "args": {"path": "C:\\\\scc\\\\scc-bd\\\\L1_code_layer"}}</tool_call>\,
  systemPrompt: '你是一个 helpful 的助手，可以使用工具来完成任务。'
})

console.log('=== 执行结果 ===')
console.log('成功:', result.ok)
console.log('轮数:', result.rounds)
console.log('耗时:', result.elapsed, 'ms')
console.log('对话记录:', JSON.stringify(result.result.conversation, null, 2))
