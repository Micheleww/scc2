import { executeWithTools } from './L6_execution_layer/executors/trae_level_executor.mjs'

console.log('=== 测试 Trae 级别执行器 ===\n')

try {
  const result = await executeWithTools(
    '请查看 C:\\scc\\scc-bd\\L1_code_layer 目录的内容，然后读取 README.md 文件的前10行，总结这个项目。',
    { maxRounds: 5 }
  )
  
  console.log('\n=== 执行结果 ===')
  console.log('成功:', result.ok)
  console.log('轮数:', result.rounds)
  console.log('\n=== 对话记录 ===')
  result.conversation.forEach((item, i) => {
    console.log(`\n[${i+1}] ${item.role} (轮${item.round}):`)
    console.log(item.content?.substring(0, 200) + '...')
  })
  
  console.log('\n=== 最终回复 ===')
  console.log(result.result.text)
} catch (error) {
  console.error('错误:', error)
}
