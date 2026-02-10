// 测试 SCC Server API

const BASE_URL = 'http://localhost:3458';

console.log('=== 测试 SCC Server with OLT CLI ===\n');

// 1. 测试健康检查
console.log('1. 测试健康检查...');
const healthRes = await fetch(`${BASE_URL}/api/health`);
const health = await healthRes.json();
console.log('   状态:', health.status);
console.log('   服务:', health.services);

// 2. 测试模型列表
console.log('\n2. 测试模型列表...');
const modelsRes = await fetch(`${BASE_URL}/api/olt-cli/models`);
const models = await modelsRes.json();
console.log('   模型:', models.data.map(m => m.id));

// 3. 测试聊天完成
console.log('\n3. 测试聊天完成...');
const chatRes = await fetch(`${BASE_URL}/api/olt-cli/chat/completions`, {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    model: 'opencode/kimi-k2.5-free',
    messages: [
      { role: 'user', content: 'Hello, who are you?' }
    ]
  })
});
const chat = await chatRes.json();
console.log('   AI:', chat.choices?.[0]?.message?.content?.substring(0, 100) + '...');

// 4. 测试执行带工具的对话
console.log('\n4. 测试执行带工具的对话...');
const executeRes = await fetch(`${BASE_URL}/api/olt-cli/execute`, {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    task: '请查看 C:\\scc\\scc-bd\\L1_code_layer 目录的内容',
    maxRounds: 3
  })
});
const execute = await executeRes.json();
console.log('   成功:', execute.ok);
console.log('   轮数:', execute.rounds);
console.log('   结果:', execute.result?.substring(0, 150) + '...');

console.log('\n=== 所有测试完成 ===');
