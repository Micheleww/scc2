// 测试 Bridge V2 - 应该只返回工具调用意图，不执行工具
const response = await fetch('http://localhost:3457/v1/chat/completions', {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json',
    'Authorization': 'Bearer sk-test'
  },
  body: JSON.stringify({
    model: 'opencode/kimi-k2.5-free',
    messages: [
      { 
        role: 'user', 
        content: '请查看 C:\\scc\\scc-bd\\L1_code_layer 目录的内容。' 
      }
    ]
  })
});

const data = await response.json();
console.log('=== AI 回复内容 ===');
console.log(data.choices?.[0]?.message?.content);
console.log('\n=== 是否包含工具调用 ===');
const content = data.choices?.[0]?.message?.content || '';
console.log('包含 <tool_call>:', content.includes('<tool_call>'));
console.log('包含 <invoke>:', content.includes('<invoke>'));
