#!/usr/bin/env python3
"""
查询并测试更多免费模型，包括 Kimi K2.5
"""
import os
import json
import time
import urllib.request
import urllib.error

API_KEY = os.environ.get('OPENROUTER_API_KEY', '')

def fetch_all_models():
    """从 OpenRouter 获取所有模型"""
    try:
        req = urllib.request.Request(
            "https://openrouter.ai/api/v1/models",
            headers={"Authorization": f"Bearer {API_KEY}"},
            method='GET'
        )
        with urllib.request.urlopen(req, timeout=30) as response:
            data = json.loads(response.read().decode('utf-8'))
            return data.get('data', [])
    except Exception as e:
        print(f"获取模型列表失败: {e}")
        return []

def test_model(model_id):
    """测试模型是否可用"""
    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json"
    }
    data = {
        "model": model_id,
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

# 获取所有模型
print("=" * 70)
print("正在获取 OpenRouter 所有模型列表...")
print("=" * 70)
all_models = fetch_all_models()

# 筛选免费模型（通常免费模型有特定标记或价格）
free_models = []
for model in all_models:
    model_id = model.get('id', '')
    # 检查是否为免费模型（通过 pricing 或 id 判断）
    pricing = model.get('pricing', {})
    is_free = False
    
    # 如果 prompt 和 completion 价格都是 0，则是免费模型
    if pricing:
        prompt_price = pricing.get('prompt', 0)
        completion_price = pricing.get('completion', 0)
        if prompt_price == 0 and completion_price == 0:
            is_free = True
    
    # 或者模型ID包含免费标记
    if ':free' in model_id:
        is_free = True
    
    if is_free:
        free_models.append(model)

print(f"\n找到 {len(free_models)} 个免费模型:\n")

# 显示所有免费模型
for i, model in enumerate(free_models, 1):
    model_id = model.get('id', '')
    name = model.get('name', model_id)
    context = model.get('context_length', 'N/A')
    print(f"{i}. {model_id}")
    print(f"   名称: {name}")
    print(f"   上下文: {context}")
    
    # 测试模型
    print(f"   测试中...", end=" ")
    status, detail = test_model(model_id)
    
    if status == "SUCCESS":
        print(f"✅ 可用 - {detail}")
    elif "rate" in detail.lower() or "429" in status:
        print(f"⚠️  速率限制")
    elif "402" in status or "credit" in detail.lower():
        print(f"❌ 积分不足")
    elif "400" in status:
        print(f"❌ 无效模型")
    else:
        print(f"❌ {status}: {detail[:80]}")
    
    time.sleep(2)
    print()

# 特别查找 Kimi 模型
print("=" * 70)
print("查找 Kimi 相关模型...")
print("=" * 70)
kimi_models = [m for m in all_models if 'kimi' in m.get('id', '').lower() or 'moonshot' in m.get('id', '').lower()]
print(f"\n找到 {len(kimi_models)} 个 Kimi/Moonshot 模型:\n")

for model in kimi_models:
    model_id = model.get('id', '')
    name = model.get('name', model_id)
    pricing = model.get('pricing', {})
    prompt_price = pricing.get('prompt', 'N/A')
    completion_price = pricing.get('completion', 'N/A')
    
    print(f"模型: {model_id}")
    print(f"名称: {name}")
    print(f"价格: prompt={prompt_price}, completion={completion_price}")
    
    # 测试模型
    print(f"测试中...", end=" ")
    status, detail = test_model(model_id)
    
    if status == "SUCCESS":
        print(f"✅ 可用 - {detail}")
    elif "rate" in detail.lower() or "429" in status:
        print(f"⚠️  速率限制")
    elif "402" in status:
        print(f"❌ 积分不足")
    else:
        print(f"❌ {status}: {detail[:80]}")
    
    time.sleep(2)
    print()
