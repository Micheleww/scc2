"""测试状态端点响应时间"""
import time
import requests
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

print("="*60)
print("测试 /api/freqtrade/status 端点")
print("="*60)

# 测试1: 直接调用端点
print("\n1. 测试端点响应时间...")
start = time.time()
try:
    r = requests.get('http://127.0.0.1:18788/api/freqtrade/status', timeout=10)
    elapsed = (time.time() - start) * 1000
    print(f"   状态码: {r.status_code}")
    print(f"   响应时间: {elapsed:.0f}ms")
    if r.status_code == 200:
        data = r.json()
        print(f"   数据: {data}")
except Exception as e:
    elapsed = (time.time() - start) * 1000
    print(f"   错误 (耗时 {elapsed:.0f}ms): {type(e).__name__}: {e}")

# 测试2: 直接调用get_status方法
print("\n2. 测试get_status方法...")
from tools.mcp_bus.server.freqtrade_service import freqtrade_service
start = time.time()
try:
    status = freqtrade_service.get_status()
    elapsed = (time.time() - start) * 1000
    print(f"   方法执行时间: {elapsed:.0f}ms")
    print(f"   WebServer运行: {status['webserver']['running']}")
    print(f"   PID: {status['webserver'].get('pid')}")
except Exception as e:
    elapsed = (time.time() - start) * 1000
    print(f"   错误 (耗时 {elapsed:.0f}ms): {type(e).__name__}: {e}")

print("\n" + "="*60)
