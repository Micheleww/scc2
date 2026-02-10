import { execSync } from 'child_process'
import fs from 'fs'

const prompt = `你是一个智能助手，可以使用以下工具来完成任务：

可用工具列表（只能使用这些工具）：
1. list_dir - 列出目录内容
   参数: { "path": "目录路径" }

2. read_file - 读取文件
   参数: { "file_path": "文件路径", "limit": 行数 }

重要规则：
- 只能使用上面列出的工具名称
- 必须使用以下格式调用工具：
<tool_call>
{
  "tool": "list_dir",
  "args": {
    "path": "C:\\\\scc\\\\scc-bd\\\\L1_code_layer"
  }
}
</tool_call>

当前任务:
请使用 list_dir 工具查看 C:\\scc\\scc-bd\\L1_code_layer 目录的内容。

注意：只能使用 "list_dir" 工具，不能使用其他工具如 "bash" 或 "ls"。`

const promptBase64 = Buffer.from(prompt).toString('base64')

const psScript = `[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$prompt = [System.Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('${promptBase64}'))
& 'C:\\scc\\plugin\\OpenCode\\opencode-cli.exe' run $prompt --model "opencode/kimi-k2.5-free" --format json`

const tempScriptPath = `.opencode_correct_${Date.now()}.ps1`
fs.writeFileSync(tempScriptPath, psScript, 'utf-8')

console.log('=== 测试正确的工具调用 ===\n')

try {
  const stdout = execSync(`powershell.exe -NoProfile -ExecutionPolicy Bypass -File "${tempScriptPath}"`, {
    timeout: 60000,
    encoding: 'utf-8',
    maxBuffer: 10 * 1024 * 1024
  })
  
  fs.unlinkSync(tempScriptPath)
  
  const lines = stdout.split('\n').filter(line => line.trim())
  for (const line of lines) {
    try {
      const parsed = JSON.parse(line)
      if (parsed.type === 'text' && parsed.part?.text) {
        console.log('AI 响应:')
        console.log(parsed.part.text)
        
        // 检查 tool_call
        const matches = Array.from(parsed.part.text.matchAll(/<tool_call>\s*({[\s\S]*?})\s*<\/tool_call>/g))
        if (matches.length > 0) {
          console.log('\n✅ 找到工具调用!')
          matches.forEach((match, i) => {
            const toolCall = JSON.parse(match[1].trim())
            console.log(`工具: ${toolCall.tool}`)
            console.log(`参数:`, toolCall.args)
          })
        }
      }
    } catch {}
  }
} catch (error) {
  console.error('错误:', error.message)
  try { fs.unlinkSync(tempScriptPath) } catch {}
}
