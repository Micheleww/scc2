// 简单测试桥接服务器 - 自动同步测试 (2026-02-10)
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
        content: '你是一个 helpful 的助手。你可以使用工具。工具格式：<tool_call>{"tool": "list_dir", "args": {"path": "."}}</tool_call>' 
      },
      { 
        role: 'user', 
        content: '请查看 C:\\scc\\scc-bd\\L1_code_layer 目录的内容，使用 list_dir 工具。' 
      }
    ]
  })
});

const data = await response.json();
console.log('=== 完整响应 ===');
console.log(JSON.stringify(data, null, 2));
console.log('\n=== AI 回复内容 ===');
console.log(data.choices?.[0]?.message?.content);
