import { execSync } from 'child_process'

const prompt = `你是一个 helpful 的助手，可以使用工具来完成任务。

你有以下工具可用：
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

系统会执行工具并返回结果。你可以根据结果决定下一步操作。
当你认为任务已经完成时，请输出：<task_complete>

请开始执行任务。

当前任务:
请使用 list_dir 工具查看 C:\scc\scc-bd\L1_code_layer 目录，然后告诉我里面有什么文件。`

const promptBase64 = Buffer.from(prompt).toString('base64')

const psScript = `[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$prompt = [System.Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('${promptBase64}'))
& 'C:\\scc\\plugin\\OpenCode\\opencode-cli.exe' run $prompt --model "opencode/kimi-k2.5-free" --format json`

console.log('=== 执行命令 ===')
const stdout = execSync(`powershell.exe -NoProfile -Command "${psScript}"`, {
  timeout: 60000,
  encoding: 'utf-8',
  maxBuffer: 10 * 1024 * 1024
})

console.log('\n=== 原始输出 ===')
console.log(stdout)

console.log('\n=== 解析结果 ===')
const lines = stdout.split('\n').filter(line => line.trim())
console.log('行数:', lines.length)

for (const line of lines) {
  try {
    const parsed = JSON.parse(line)
    console.log('解析成功:', parsed.type)
    if (parsed.type === 'text' && parsed.part?.text) {
      console.log('\nAI 响应文本:')
      console.log(parsed.part.text)
    }
  } catch (e) {
    console.log('解析失败:', line.substring(0, 50))
  }
}
