import { createJobExecutor } from './L6_execution_layer/executors/opencodecli_executor.mjs'

const executor = createJobExecutor({ maxRounds: 3 })

console.log('=== 开始详细调试测试 ===\n')

const result = await executor.execute({
  id: 'debug_test_001',
  prompt: `请使用 list_dir 工具查看 C:\scc\scc-bd\L1_code_layer 目录，然后告诉我里面有什么文件。`,
  systemPrompt: '你是一个 helpful 的助手，可以使用工具来完成任务。'
})

console.log('\n=== 执行完成 ===')
console.log('成功:', result.ok)
console.log('轮数:', result.rounds)
console.log('耗时:', result.elapsed, 'ms')
console.log('上下文ID:', result.context)

console.log('\n=== 完整对话记录 ===')
if (result.result.conversation && result.result.conversation.length > 0) {
  result.result.conversation.forEach((item, index) => {
    console.log(`\n--- 记录 ${index + 1} ---`)
    console.log(`角色: ${item.role}`)
    console.log(`轮数: ${item.round || 'N/A'}`)
    console.log(`内容:\n${item.content || '(空)'}`)
  })
} else {
  console.log('没有对话记录')
}

console.log('\n=== AI 最终回复 ===')
console.log(result.result.text || '(无内容)')
