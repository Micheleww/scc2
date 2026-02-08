#!/usr/bin/env python3
import os
import json
import time
import urllib.request
import urllib.error

API_KEY = os.environ.get('OPENROUTER_API_KEY', '')

# 正确的免费模型格式（不需要:free后缀，OpenRouter会自动路由到免费端点）
models = [
    "arcee-ai/trinity-mini",
    "google/gemma-3-27b-it",
    "nvidia/nemotron-nano-9b-v2",
    "openai/gpt-oss-20b",
    "qwen/qwen3-4b",
    "qwen/qwen3-coder",
    "stepfun/step-3.5-flash",
    "tngtech/tng-r1t-chimera",
    "upstage/solar-pro-3",
    "z-ai/glm-4.5-air"
]

def test_model(model_name):
    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json"
    }
    data = {
        "model": model_name,
        "messages": [{"role": "user", "content": "hi"}]
    }
    
    try:
        req = urllib.request.Request(
            url,
            data=json.dumps(data).encode('utf-8'),
            headers=headers,
            method='POST'
        )
        
        with urllib.request.urlopen(req, timeout=30) as response:
            result = json.loads(response.read().decode('utf-8'))
            if 'choices' in result and len(result['choices']) > 0:
                content = result['choices'][0].get('message', {}).get('content', '')
                return "SUCCESS", content[:50]
            else:
                return "NO_CONTENT", str(result)
    except urllib.error.HTTPError as e:
        error_body = e.read().decode('utf-8')
        return f"HTTP_{e.code}", error_body[:200]
    except Exception as e:
        return "ERROR", str(e)[:100]

print("=" * 70)
print("测试免费模型 (正确格式)")
print("=" * 70)

results = []
for i, model in enumerate(models, 1):
    print(f"\n{i}/{len(models)} 测试: {model}")
    status, detail = test_model(model)
    results.append({"model": model, "status": status, "detail": detail})
    
    if status == "SUCCESS":
        print(f"  ✅ 成功: {detail}")
    elif "rate" in detail.lower() or "429" in status:
        print(f"  ⚠️  速率限制 (429)")
    elif "402" in status or "credit" in detail.lower() or "limit" in detail.lower():
        print(f"  ❌ 积分不足 (402)")
    elif "400" in status:
        print(f"  ❌ 无效模型 (400)")
    else:
        print(f"  ❌ {status}: {detail[:80]}")
    
    time.sleep(2)

print("\n" + "=" * 70)
print("测试结果总结")
print("=" * 70)

success_models = [r for r in results if r['status'] == 'SUCCESS']
rate_limited = [r for r in results if 'rate' in r['detail'].lower() or '429' in r['status']]
no_credit = [r for r in results if '402' in r['status'] or 'credit' in r['detail'].lower()]
invalid = [r for r in results if '400' in r['status']]

print(f"\n✅ 可用模型 ({len(success_models)}):")
for r in success_models:
    print(f"  - {r['model']}")

print(f"\n⚠️  速率限制 ({len(rate_limited)}):")
for r in rate_limited:
    print(f"  - {r['model']}")

print(f"\n❌ 积分不足 ({len(no_credit)}):")
for r in no_credit:
    print(f"  - {r['model']}")
    
print(f"\n🚫 无效模型 ({len(invalid)}):")
for r in invalid:
    print(f"  - {r['model']}")
