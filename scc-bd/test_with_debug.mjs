import { createJobExecutor } from './L6_execution_layer/executors/opencodecli_executor.mjs'

const executor = createJobExecutor({ maxRounds: 3 })

console.log('=== 测试带调试信息 ===\n')

const result = await executor.execute({
  id: 'debug_test_' + Date.now(),
  prompt: `请使用 list_dir 工具查看 C:\scc\scc-bd\L1_code_layer 目录。`,
  systemPrompt: '你是一个 helpful 的助手。'
})

console.log('\n=== 结果 ===')
console.log('成功:', result.ok)
console.log('错误:', result.error || '无')
console.log('轮数:', result.rounds)
console.log('耗时:', result.elapsed, 'ms')

console.log('\n=== 对话记录 ===')
result.result.conversation.forEach((item, i) => {
  console.log(`\n[${i+1}] ${item.role} (轮${item.round}):`)
  const content = item.content || '(空)'
  console.log(content.substring(0, 500))
  if (content.length > 500) console.log('... (截断)')
})
