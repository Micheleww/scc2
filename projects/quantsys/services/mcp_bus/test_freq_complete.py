
"""完整测试Freqtrade启动流程"""
import time
import requests
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from tools.mcp_bus.server.freqtrade_service import freqtrade_service

print("="*60)
print("Freqtrade 完整启动测试")
print("="*60)

# 1. 检查当前状态
print("\n1. 检查当前状态...")
status = freqtrade_service.get_status()
print(f"   运行状态: {status['webserver']['running']}")
print(f"   PID: {status['webserver'].get('pid', 'None')}")

# 2. 检查API
print("\n2. 检查Freqtrade API...")
try:
    r = requests.get('http://127.0.0.1:18788/api/v1/ping', timeout=2)
    if r.status_code == 200:
        print("   ✅ Freqtrade API可访问")
    else:
        print(f"   ⚠️ API返回状态码: {r.status_code}")
except Exception as e:
    print(f"   ❌ API不可访问: {e}")

# 3. 检查总服务器状态
print("\n3. 检查总服务器Freqtrade状态...")
try:
    r = requests.get('http://127.0.0.1:18788/api/freqtrade/status', timeout=2)
    if r.status_code == 200:
        data = r.json()
        print(f"   运行状态: {data['webserver']['running']}")
        print(f"   PID: {data['webserver'].get('pid', 'None')}")
        if data['webserver']['running']:
            print("   ✅ 总服务器检测到Freqtrade运行")
        else:
            print("   ⚠️ 总服务器未检测到Freqtrade运行")
    else:
        print(f"   ❌ 总服务器错误: {r.status_code}")
except Exception as e:
    print(f"   ❌ 总服务器不可访问: {e}")

# 4. 检查进程
print("\n4. 检查Freqtrade进程...")
try:
    import psutil
    procs = []
    for p in psutil.process_iter(['pid', 'name', 'cmdline']):
        try:
            cmdline = ' '.join(p.info['cmdline'] or [])
            if 'freqtrade' in cmdline.lower() and 'webserver' in cmdline.lower():
                procs.append(p)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    
    print(f"   找到 {len(procs)} 个Freqtrade WebServer进程")
    for p in procs[:3]:
        print(f"     PID {p.info['pid']}: {p.info['name']}")
except ImportError:
    print("   ⚠️ psutil未安装，跳过进程检查")
except Exception as e:
    print(f"   ❌ 进程检查失败: {e}")

print("\n" + "="*60)
print("测试完成")
print("="*60)
