
"""测试所有Dashboard端点响应时间"""
import time
import requests

endpoints = [
    '/health',
    '/api/freqtrade/status',
    '/api/viewer/statistics',
    '/api/exchange/okx/status',
    '/api/validator/statistics',
    '/api/monitoring/status',
    '/api/exceptions/statistics',
    '/api/services',
]

print("="*60)
print("测试所有Dashboard端点响应时间")
print("="*60)

results = {}
for ep in endpoints:
    start = time.time()
    try:
        r = requests.get(f'http://127.0.0.1:18788/{ep}', timeout=5)
        elapsed = (time.time() - start) * 1000
        results[ep] = {'status': r.status_code, 'time': elapsed, 'ok': True}
    except Exception as e:
        elapsed = (time.time() - start) * 1000
        results[ep] = {'error': str(e)[:80], 'time': elapsed, 'ok': False}

print("\n结果:")
for ep, r in results.items():
    if r['ok']:
        print(f"  {ep:40} {r['status']:3} {r['time']:7.0f}ms")
    else:
        print(f"  {ep:40} ERROR {r['time']:7.0f}ms - {r['error']}")

print("\n" + "="*60)
total_time = sum(r['time'] for r in results.values())
print(f"总耗时: {total_time:.0f}ms")
print("="*60)
