import { execSync } from 'child_process'
import fs from 'fs'

const prompt = `请完成以下任务：
1. 查看 C:\scc\scc-bd\L1_code_layer 目录的内容
2. 读取该目录下的 README.md 文件的前15行
3. 总结你发现了什么

你可以使用 bash 工具来执行命令。`

const promptBase64 = Buffer.from(prompt).toString('base64')

// 使用双反斜杠
const psScript = `[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$prompt = [System.Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('${promptBase64}'))
& "C:\\scc\\plugin\\OpenCode\\opencode-cli.exe" run $prompt --model "opencode/kimi-k2.5-free" --format json`

const tempScriptPath = `.opencode_debug2_${Date.now()}.ps1`
fs.writeFileSync(tempScriptPath, psScript, 'utf-8')

console.log('=== 调试 AI 原始响应 ===\n')

try {
  const stdout = execSync(`powershell.exe -NoProfile -ExecutionPolicy Bypass -File "${tempScriptPath}"`, {
    timeout: 60000,
    encoding: 'utf-8',
    maxBuffer: 10 * 1024 * 1024
  })
  
  fs.unlinkSync(tempScriptPath)
  
  console.log('=== 完整原始输出 ===')
  console.log(stdout)
  
  console.log('\n=== 解析 ===')
  const lines = stdout.split('\n').filter(line => line.trim())
  for (const line of lines) {
    try {
      const parsed = JSON.parse(line)
      if (parsed.type === 'text' && parsed.part?.text) {
        console.log('\nAI 文本响应:')
        console.log(parsed.part.text)
        
        // 检查是否包含工具调用
        const hasInvoke = parsed.part.text.includes('<invoke')
        const hasToolCall = parsed.part.text.includes('<tool_call')
        console.log('\n包含 <invoke>:', hasInvoke)
        console.log('包含 <tool_call>:', hasToolCall)
        
        if (hasInvoke) {
          const matches = Array.from(parsed.part.text.matchAll(/<invoke\s+name="([^"]+)">/g))
          console.log('工具调用:', matches.map(m => m[1]))
        }
      }
    } catch {}
  }
} catch (error) {
  console.error('错误:', error.message)
  try { fs.unlinkSync(tempScriptPath) } catch {}
}
