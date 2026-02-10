"""测试Freqtrade启动流程 - 完整测试"""
import asyncio
import logging
import os
import sys
import time
from pathlib import Path

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

# 添加项目根目录到路径
repo_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(repo_root))

# 加载环境变量
from dotenv import load_dotenv
load_dotenv(repo_root / "tools" / "mcp_bus" / ".env")

print("="*60)
print("Freqtrade 启动流程测试")
print("="*60)
print(f"REPO_ROOT: {repo_root}")
print(f"AUTO_START_FREQTRADE: {os.getenv('AUTO_START_FREQTRADE')}")

# 导入服务
from tools.mcp_bus.server.freqtrade_service import freqtrade_service
from tools.mcp_bus.server.main import startup_event

async def test_startup():
    """测试启动流程"""
    print("\n" + "="*60)
    print("步骤1: 停止现有的Freqtrade（如果运行）")
    print("="*60)
    
    status = freqtrade_service.get_status()
    print(f"当前状态: running={status['webserver']['running']}, pid={status['webserver'].get('pid')}")
    
    if status['webserver']['running']:
        print("停止Freqtrade...")
        freqtrade_service.stop_webserver()
        await asyncio.sleep(2)  # 等待进程停止
        status2 = freqtrade_service.get_status()
        print(f"停止后状态: running={status2['webserver']['running']}")
    
    print("\n" + "="*60)
    print("步骤2: 执行启动事件")
    print("="*60)
    
    # 执行启动事件
    await startup_event()
    
    # 等待任务执行
    print("\n等待启动任务执行...")
    await asyncio.sleep(5)
    
    print("\n" + "="*60)
    print("步骤3: 检查最终状态")
    print("="*60)
    
    status3 = freqtrade_service.get_status()
    print(f"最终状态: running={status3['webserver']['running']}, pid={status3['webserver'].get('pid')}")
    
    if status3['webserver']['running']:
        print("✅ Freqtrade 启动成功！")
    else:
        print("❌ Freqtrade 启动失败！")
    
    # 清理
    print("\n清理...")
    freqtrade_service.stop_webserver()

if __name__ == "__main__":
    asyncio.run(test_startup())
