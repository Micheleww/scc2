import { createJobExecutor } from './L6_execution_layer/executors/opencodecli_executor.mjs'

const executor = createJobExecutor({ maxRounds: 5 })

console.log('=== 测试多轮交互 ===\n')

const result = await executor.execute({
  id: 'multi_round_test',
  prompt: `请完成以下多步骤任务：

步骤1：使用 list_dir 工具查看 C:\scc\scc-bd\L1_code_layer 目录
步骤2：使用 read_file 工具读取该目录下的 README.md 文件的前20行
步骤3：总结你发现了什么

注意：每个步骤都要使用工具调用格式：<tool_call>{"tool": "工具名", "args": {}}</tool_call>`,
  systemPrompt: '你是一个 helpful 的助手，必须使用工具来完成每个步骤。'
})

console.log('\n=== 执行结果 ===')
console.log('成功:', result.ok)
console.log('轮数:', result.rounds)
console.log('耗时:', result.elapsed, 'ms')

console.log('\n=== 对话记录 ===')
result.result.conversation.forEach((item, index) => {
  console.log(`\n[${index + 1}] ${item.role} (轮${item.round}):`)
  console.log(item.content?.substring(0, 300) + (item.content?.length > 300 ? '...' : ''))
})

console.log('\n=== 最终回复 ===')
console.log(result.result.text)
