// 测试桥接服务器
const response = await fetch('http://localhost:3456/v1/chat/completions', {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json',
    'Authorization': 'Bearer sk-test'
  },
  body: JSON.stringify({
    model: 'opencode/kimi-k2.5-free',
    messages: [
      { role: 'user', content: 'Hello, who are you?' }
    ]
  })
});

const data = await response.json();
console.log('Response:', JSON.stringify(data, null, 2));
