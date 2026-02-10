import { execSync } from 'child_process'

const prompt = '你好'
const promptBase64 = Buffer.from(prompt).toString('base64')

const psScript = `$prompt = [System.Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('${promptBase64}'))
Write-Host "Prompt: $prompt"
& 'C:\\scc\\plugin\\OpenCode\\opencode-cli.exe' run $prompt --model "opencode/kimi-k2.5-free" --format json`

console.log('PS Script:')
console.log(psScript)
console.log('\n--- 执行 ---\n')

try {
  const stdout = execSync(`powershell.exe -NoProfile -Command "${psScript}"`, {
    encoding: 'utf-8',
    timeout: 60000,
    maxBuffer: 10 * 1024 * 1024
  })
  
  console.log('stdout:', stdout)
} catch (e) {
  console.error('错误:', e.message)
  console.error('stdout:', e.stdout)
  console.error('stderr:', e.stderr)
  console.error('exit code:', e.status)
}
