"""测试Dashboard页面各项数据"""
import json
import requests
import time

base_url = 'http://127.0.0.1:18788/'

endpoints = {
    '消息总数': '/api/viewer/statistics',
    '服务健康': '/health',
    'Freqtrade状态': '/api/freqtrade/status',
    '交易所状态': '/api/exchange/okx/status',
    '校验器统计': '/api/validator/statistics',
    '服务列表': '/api/services',
}

print("="*60)
print("Dashboard页面数据测试")
print("="*60)

results = {}
for name, endpoint in endpoints.items():
    start_time = time.time()
    try:
        r = requests.get(f'{base_url}{endpoint}', timeout=3)
        elapsed = (time.time() - start_time) * 1000
        
        if r.status_code == 200:
            data = r.json()
            results[name] = {
                'status': 'OK',
                'time': f'{elapsed:.0f}ms',
                'data': data
            }
        else:
            results[name] = {
                'status': f'HTTP {r.status_code}',
                'time': f'{elapsed:.0f}ms',
                'data': None
            }
    except Exception as e:
        elapsed = (time.time() - start_time) * 1000
        results[name] = {
            'status': 'ERROR',
            'time': f'{elapsed:.0f}ms',
            'error': str(e)[:80]
        }

print("\n测试结果:")
print("-"*60)

for name, result in results.items():
    print(f"\n【{name}】")
    print(f"  状态: {result['status']}")
    print(f"  耗时: {result['time']}")
    
    if 'data' in result and result['data']:
        data = result['data']
        
        # 根据不同的端点提取关键信息
        if name == '消息总数':
            total = data.get('total_messages', 'N/A')
            print(f"  消息总数: {total}")
            by_agent = data.get('by_agent', {})
            if by_agent:
                print(f"  按智能体分布: {len(by_agent)}个智能体")
        
        elif name == '服务健康':
            ok = data.get('ok', False)
            status = data.get('status', 'unknown')
            version = data.get('version', 'N/A')
            print(f"  健康状态: {'正常' if ok else '异常'}")
            print(f"  状态: {status}")
            print(f"  版本: {version}")
        
        elif name == 'Freqtrade状态':
            webserver = data.get('webserver', {})
            running = webserver.get('running', False)
            pid = webserver.get('pid', 'N/A')
            print(f"  Web服务: {'运行中' if running else '未运行'}")
            print(f"  PID: {pid}")
            trade = data.get('trade', {})
            trade_running = trade.get('running', False)
            print(f"  交易进程: {'运行中' if trade_running else '未运行'}")
        
        elif name == '交易所状态':
            success = data.get('success', False)
            status = data.get('status', 'N/A')
            exchange = data.get('exchange', 'N/A')
            print(f"  连接状态: {'成功' if success else '失败'}")
            print(f"  状态: {status}")
            print(f"  交易所: {exchange}")
        
        elif name == '校验器统计':
            success = data.get('success', False)
            stats = data.get('statistics', {})
            total = stats.get('total_validations', 0)
            passed = stats.get('passed', 0)
            failed = stats.get('failed', 0)
            pass_rate = stats.get('pass_rate', 0.0)
            print(f"  总校验: {total}")
            print(f"  通过: {passed}")
            print(f"  失败: {failed}")
            print(f"  通过率: {pass_rate:.1%}")
        
        elif name == '服务列表':
            services = data.get('services', {})
            print(f"  服务数量: {len(services)}")
            for svc_name, svc_data in list(services.items())[:5]:
                enabled = svc_data.get('enabled', False)
                checked = svc_data.get('checked', False)
                print(f"    {svc_name}: {'启用' if enabled else '禁用'} ({'已检查' if checked else '未检查'})")
    
    elif 'error' in result:
        print(f"  错误: {result['error']}")

print("\n" + "="*60)
print("测试完成")
print("="*60)
