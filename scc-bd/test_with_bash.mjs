// 测试使用 bash 工具
const response = await fetch('http://localhost:3456/v1/chat/completions', {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json',
    'Authorization': 'Bearer sk-test'
  },
  body: JSON.stringify({
    model: 'opencode/kimi-k2.5-free',
    messages: [
      { 
        role: 'system', 
        content: '你是一个 helpful 的助手。' 
      },
      { 
        role: 'user', 
        content: '请使用 bash 工具执行 "ls C:\\scc\\scc-bd\\L1_code_layer" 命令查看目录内容。' 
      }
    ]
  })
});

const data = await response.json();
console.log('=== AI 回复内容 ===');
console.log(data.choices?.[0]?.message?.content);
