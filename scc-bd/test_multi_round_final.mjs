import { createJobExecutor } from './L6_execution_layer/executors/opencodecli_executor.mjs'

const executor = createJobExecutor({ maxRounds: 5 })

console.log('=== 测试多轮交互（最终版）===\n')

const result = await executor.execute({
  id: 'final_test_' + Date.now(),
  prompt: `请完成以下任务：
1. 查看 C:\scc\scc-bd\L1_code_layer 目录的内容
2. 读取该目录下的 README.md 文件的前15行
3. 总结你发现了什么`,
  systemPrompt: '你是一个 helpful 的助手，可以使用工具来完成任务。'
})

console.log('\n=== 执行结果 ===')
console.log('成功:', result.ok)
console.log('错误:', result.error || '无')
console.log('轮数:', result.rounds)
console.log('耗时:', result.elapsed, 'ms')

console.log('\n=== 对话记录 ===')
result.result.conversation.forEach((item, i) => {
  console.log(`\n[${i+1}] ${item.role} (轮${item.round}):`)
  console.log('-'.repeat(50))
  console.log(item.content || '(空)')
})

console.log('\n=== 最终回复 ===')
console.log(result.result.text)
