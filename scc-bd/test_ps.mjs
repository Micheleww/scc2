import { execSync } from 'child_process'

// 测试 1: 简单 echo
console.log('=== 测试 1: 简单 echo ===')
try {
  const r1 = execSync('powershell.exe -Command "Write-Host hello"', { encoding: 'utf-8' })
  console.log('结果:', JSON.stringify(r1))
} catch (e) {
  console.error('错误:', e.message)
}

// 测试 2: 带引号
console.log('\n=== 测试 2: 带引号 ===')
try {
  const r2 = execSync('powershell.exe -Command "Write-Host \\"hello world\\""', { encoding: 'utf-8' })
  console.log('结果:', JSON.stringify(r2))
} catch (e) {
  console.error('错误:', e.message)
}

// 测试 3: 多行
console.log('\n=== 测试 3: 多行命令 ===')
const multiLine = `$a = "test"
Write-Host "Value: $a"`
try {
  const r3 = execSync(`powershell.exe -Command "${multiLine}"`, { encoding: 'utf-8' })
  console.log('结果:', JSON.stringify(r3))
} catch (e) {
  console.error('错误:', e.message)
}

// 测试 4: 使用文件
console.log('\n=== 测试 4: 使用文件 ===')
import fs from 'fs'
fs.writeFileSync('test.ps1', 'Write-Host "from file"')
try {
  const r4 = execSync('powershell.exe -File test.ps1', { encoding: 'utf-8' })
  console.log('结果:', JSON.stringify(r4))
} catch (e) {
  console.error('错误:', e.message)
}
