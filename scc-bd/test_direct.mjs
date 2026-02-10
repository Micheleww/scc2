import { createJobExecutor } from './L6_execution_layer/executors/opencodecli_executor.mjs'

const executor = createJobExecutor({ maxRounds: 3 })

console.log('=== 开始测试执行器 ===')

const result = await executor.execute({
  id: 'test_001',
  prompt: `请使用 list_dir 工具查看 C:\scc\scc-bd\L1_code_layer 目录，然后告诉我里面有什么文件。

你必须使用以下格式调用工具：
<tool_call>
{"tool": "list_dir", "args": {"path": "C:\\scc\\scc-bd\\L1_code_layer"}}
</tool_call>`,
  systemPrompt: '你是一个 helpful 的助手，可以使用工具来完成任务。'
})

console.log('\n=== 执行结果 ===')
console.log('成功:', result.ok)
console.log('轮数:', result.rounds)
console.log('耗时:', result.elapsed, 'ms')
console.log('\nAI 响应:')
console.log(result.result.text || '(无内容)')
console.log('\n对话记录:')
result.result.conversation.forEach((c, i) => {
  console.log(`${i + 1}. [${c.role}] ${c.content?.substring(0, 200)}...`)
})
