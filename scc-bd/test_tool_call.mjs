import { execSync } from 'child_process'
import fs from 'fs'
import path from 'path'

const prompt = `你是一个智能助手，可以使用以下工具来完成任务：

- list_dir: 列出目录
  参数:
    - path: 目录路径

重要：当你需要使用工具时，必须严格按照以下格式输出：
<tool_call>
{
  "tool": "工具名称",
  "args": {
    "参数名": "参数值"
  }
}
</tool_call>

当前任务:
请使用 list_dir 工具查看 C:\\scc\\scc-bd\\L1_code_layer 目录。

你必须使用工具调用格式！`

const promptBase64 = Buffer.from(prompt).toString('base64')

const psScript = `[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$prompt = [System.Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('${promptBase64}'))
& 'C:\\scc\\plugin\\OpenCode\\opencode-cli.exe' run $prompt --model "opencode/kimi-k2.5-free" --format json`

const tempScriptPath = `.opencode_test_${Date.now()}.ps1`
fs.writeFileSync(tempScriptPath, psScript, 'utf-8')

console.log('=== 测试 AI 工具调用 ===\n')

try {
  const stdout = execSync(`powershell.exe -NoProfile -ExecutionPolicy Bypass -File "${tempScriptPath}"`, {
    timeout: 60000,
    encoding: 'utf-8',
    maxBuffer: 10 * 1024 * 1024
  })
  
  fs.unlinkSync(tempScriptPath)
  
  console.log('=== 原始输出 ===')
  console.log(stdout.substring(0, 2000))
  
  console.log('\n=== 解析 AI 响应 ===')
  const lines = stdout.split('\n').filter(line => line.trim())
  for (const line of lines) {
    try {
      const parsed = JSON.parse(line)
      if (parsed.type === 'text' && parsed.part?.text) {
        console.log('\nAI 响应:')
        console.log(parsed.part.text)
        
        // 检查 tool_call
        const hasToolCall = parsed.part.text.includes('<tool_call>')
        console.log('\n是否包含 <tool_call>:', hasToolCall)
        
        if (hasToolCall) {
          const matches = Array.from(parsed.part.text.matchAll(/<tool_call>\s*({[\s\S]*?})\s*<\/tool_call>/g))
          console.log('找到工具调用数量:', matches.length)
          matches.forEach((match, i) => {
            console.log(`\n工具调用 ${i+1}:`)
            console.log(match[1])
            try {
              const toolCall = JSON.parse(match[1].trim())
              console.log('解析成功:', toolCall)
            } catch (e) {
              console.log('解析失败:', e.message)
            }
          })
        }
      }
    } catch (e) {
      // 不是 JSON 行，忽略
    }
  }
} catch (error) {
  console.error('错误:', error.message)
  try { fs.unlinkSync(tempScriptPath) } catch {}
}
