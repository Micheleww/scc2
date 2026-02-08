# 测试所有免费模型
$models = @(
    "openrouter/arcee-ai/trinity-mini:free",
    "openrouter/google/gemma-3-27b-it:free",
    "openrouter/nvidia/nemotron-nano-9b-v2:free",
    "openrouter/openai/gpt-oss-20b:free",
    "openrouter/qwen/qwen3-4b:free",
    "openrouter/qwen/qwen3-coder:free",
    "openrouter/stepfun/step-3.5-flash:free",
    "openrouter/tngtech/tng-r1t-chimera:free",
    "openrouter/upstage/solar-pro-3:free",
    "openrouter/z-ai/glm-4.5-air:free"
)

$results = @()

foreach ($model in $models) {
    Write-Host "`n========================================" -ForegroundColor Cyan
    Write-Host "测试模型: $model" -ForegroundColor Yellow
    Write-Host "========================================" -ForegroundColor Cyan
    
    # 设置模型
    openclaw --profile kimi config set agents.defaults.model.primary $model 2>&1 | Out-Null
    
    # 等待1秒
    Start-Sleep -Seconds 1
    
    # 测试API调用
    $testResult = openclaw --profile kimi agent --local --message "你好，请回复'测试成功'" --to "+1234567890" 2>&1
    
    # 分析结果
    if ($testResult -match "rate.*limit|429|exceeded|limit") {
        Write-Host "❌ 结果: 速率限制" -ForegroundColor Red
        $status = "速率限制"
    } elseif ($testResult -match "402|credit|spend") {
        Write-Host "❌ 结果: 积分不足" -ForegroundColor Red
        $status = "积分不足"
    } elseif ($testResult -match "error|Error|failed") {
        Write-Host "❌ 结果: 其他错误" -ForegroundColor Red
        $status = "其他错误"
    } elseif ($testResult -match "测试成功|你好") {
        Write-Host "✅ 结果: 成功响应" -ForegroundColor Green
        $status = "成功"
    } else {
        Write-Host "⚠️ 结果: 未知响应" -ForegroundColor Yellow
        $status = "未知"
    }
    
    $results += [PSCustomObject]@{
        Model = $model
        Status = $status
        Detail = ($testResult -join "`n").Substring(0, [Math]::Min(200, ($testResult -join "`n").Length))
    }
    
    # 等待3秒避免速率限制
    Start-Sleep -Seconds 3
}

# 输出总结
Write-Host "`n`n========================================" -ForegroundColor Green
Write-Host "测试结果总结" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green

$results | Format-Table -AutoSize

# 找出成功的模型
$successful = $results | Where-Object { $_.Status -eq "成功" }
if ($successful) {
    Write-Host "`n✅ 可用模型:" -ForegroundColor Green
    $successful | ForEach-Object { Write-Host "  - $($_.Model)" -ForegroundColor Green }
} else {
    Write-Host "`n❌ 没有可用的免费模型" -ForegroundColor Red
}
