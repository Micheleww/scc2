// 测试完整的多轮对话流程

const BRIDGE_URL = 'http://localhost:3457/v1/chat/completions';

async function callAI(messages) {
  const response = await fetch(BRIDGE_URL, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Authorization': 'Bearer sk-test'
    },
    body: JSON.stringify({
      model: 'opencode/kimi-k2.5-free',
      messages
    })
  });
  
  const data = await response.json();
  return data.choices[0].message.content;
}

console.log('=== 测试多轮对话流程 ===\n');

// 第一轮：用户请求
const messages = [
  { 
    role: 'system', 
    content: '你是AI助手。可用工具：list_dir(列目录), read_file(读文件)。需要工具时输出：<tool_call>{"tool": "工具名", "args": {...}}</tool_call>' 
  },
  { 
    role: 'user', 
    content: '请查看 C:\\scc\\scc-bd\\L1_code_layer 目录' 
  }
];

console.log('用户: 请查看 C:\scc\scc-bd\L1_code_layer 目录');

// 调用 AI
const aiResponse = await callAI(messages);
console.log('\nAI:', aiResponse);

// 检查是否包含工具调用
if (aiResponse.includes('<tool_call>')) {
  console.log('\n✅ 检测到工具调用标记！');
  
  // 模拟工具执行结果
  const toolResult = {
    success: true,
    path: 'C:\\scc\\scc-bd\\L1_code_layer',
    directories: ['config', 'docker', 'factory_policy', 'gateway', 'ui'],
    files: ['package.json', 'package-lock.json', 'README.md']
  };
  
  // 第二轮：将工具结果返回给 AI
  messages.push({ role: 'assistant', content: aiResponse });
  messages.push({ 
    role: 'user', 
    content: `工具执行结果：\n${JSON.stringify(toolResult, null, 2)}\n\n请总结目录内容。` 
  });
  
  console.log('\n--- 第二轮 ---');
  console.log('用户: [工具执行结果]');
  
  const aiResponse2 = await callAI(messages);
  console.log('\nAI:', aiResponse2);
  
  console.log('\n✅ 多轮对话完成！');
} else {
  console.log('\n❌ 未检测到工具调用标记');
}
