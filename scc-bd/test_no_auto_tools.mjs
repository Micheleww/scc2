import { execSync } from 'child_process'
import fs from 'fs'

const prompt = `请完成以下任务：
1. 查看 C:\scc\scc-bd\L1_code_layer 目录的内容
2. 读取该目录下的 README.md 文件的前15行
3. 总结你发现了什么

你可以使用以下工具：
- bash: 执行命令，参数: command
- read: 读取文件，参数: filePath, limit

必须使用工具调用格式：
<invoke name="工具名">
<parameter name="参数名">参数值</parameter>
</invoke>`

const promptBase64 = Buffer.from(prompt).toString('base64')

// 使用 general agent 来禁用自动工具执行
const psScript = `[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$prompt = [System.Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('${promptBase64}'))
& 'C:\\scc\\plugin\\OpenCode\\opencode-cli.exe' run $prompt --model "opencode/kimi-k2.5-free" --agent general --format json`

const tempScriptPath = `.opencode_no_tools_${Date.now()}.ps1`
fs.writeFileSync(tempScriptPath, psScript, 'utf-8')

console.log('=== 测试禁用自动工具执行 ===\n')

try {
  const stdout = execSync(`powershell.exe -NoProfile -ExecutionPolicy Bypass -File "${tempScriptPath}"`, {
    timeout: 60000,
    encoding: 'utf-8',
    maxBuffer: 10 * 1024 * 1024
  })
  
  fs.unlinkSync(tempScriptPath)
  
  console.log('=== 完整输出 ===')
  console.log(stdout)
  
  console.log('\n=== 解析 ===')
  const lines = stdout.split('\n').filter(line => line.trim())
  for (const line of lines) {
    try {
      const parsed = JSON.parse(line)
      console.log('类型:', parsed.type)
      
      if (parsed.type === 'text' && parsed.part?.text) {
        console.log('\nAI 文本响应:')
        console.log(parsed.part.text)
        
        // 检查是否包含工具调用
        const hasInvoke = parsed.part.text.includes('<invoke')
        console.log('\n包含 <invoke>:', hasInvoke)
      }
      
      if (parsed.type === 'tool_use') {
        console.log('\n⚠️ 发现工具被自动执行:', parsed.part?.tool)
      }
    } catch (e) {
      // 不是 JSON 行
    }
  }
} catch (error) {
  console.error('错误:', error.message)
  try { fs.unlinkSync(tempScriptPath) } catch {}
}
