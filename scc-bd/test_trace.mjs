import { createJobExecutor } from './L6_execution_layer/executors/opencodecli_executor.mjs'

// 拦截并打印AI的原始响应
const originalExecuteMultiRound = async (params) => {
  const { executeMultiRound } = await import('./L6_execution_layer/executors/opencodecli_executor.mjs')
  return executeMultiRound(params)
}

const executor = createJobExecutor({ maxRounds: 5 })

console.log('=== 测试并追踪工具调用 ===\n')

// 修改执行器以打印原始响应
const result = await executor.execute({
  id: 'trace_test_' + Date.now(),
  prompt: `请完成以下任务：
1. 使用 list_dir 工具查看 C:\scc\scc-bd\L1_code_layer 目录
2. 使用 read_file 工具读取 README.md 文件的前10行
3. 告诉我你发现了什么

注意：必须使用工具调用格式！`,
  systemPrompt: '你是一个 helpful 的助手，必须使用工具来完成任务。'
})

console.log('\n=== 执行结果 ===')
console.log('成功:', result.ok)
console.log('轮数:', result.rounds)
console.log('耗时:', result.elapsed, 'ms')

console.log('\n=== 完整对话记录 ===')
result.result.conversation.forEach((item, i) => {
  console.log(`\n[${i+1}] ${item.role} (轮${item.round}):`)
  console.log('='.repeat(50))
  console.log(item.content || '(空)')
  console.log('='.repeat(50))
})
