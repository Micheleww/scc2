import { execSync } from 'child_process'

const prompt = '你好，请回复"测试成功"'
const promptBase64 = Buffer.from(prompt).toString('base64')

console.log('Prompt:', prompt)
console.log('Base64:', promptBase64.substring(0, 50) + '...')

const psScript = `$prompt = [System.Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('${promptBase64}'))
& 'C:\\scc\\plugin\\OpenCode\\opencode-cli.exe' run $prompt --model "opencode/kimi-k2.5-free" --format json`

console.log('\n执行命令...')

try {
  const stdout = execSync(`powershell.exe -NoProfile -Command "${psScript}"`, {
    encoding: 'utf-8',
    timeout: 60000,
    maxBuffer: 10 * 1024 * 1024
  })
  
  console.log('\n=== 输出 ===')
  console.log(stdout)
  console.log('长度:', stdout.length)
} catch (e) {
  console.error('错误:', e.message)
  console.error('stderr:', e.stderr?.toString())
}
