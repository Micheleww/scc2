
"""测试Freqtrade启动流程"""
import asyncio
import os
import sys
from pathlib import Path

# 添加项目根目录到路径
repo_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(repo_root))

# 加载环境变量
from dotenv import load_dotenv
load_dotenv(repo_root / "tools" / "mcp_bus" / ".env")

print(f"REPO_ROOT: {repo_root}")
print(f"AUTO_START_FREQTRADE: {os.getenv('AUTO_START_FREQTRADE')}")

# 导入服务
from tools.mcp_bus.server.freqtrade_service import freqtrade_service
from tools.mcp_bus.server.main import _start_freqtrade_async, _start_freqtrade_with_retry

async def test_startup():
    """测试启动流程"""
    print("\n" + "="*60)
    print("测试 Freqtrade 启动流程")
    print("="*60)
    
    # 检查当前状态
    print("\n1. 检查当前状态...")
    status = freqtrade_service.get_status()
    print(f"   当前状态: {status}")
    
    # 测试启动
    print("\n2. 测试启动...")
    try:
        result = await _start_freqtrade_with_retry(max_retries=3, retry_delay=1.0)
        print(f"   启动结果: {result}")
    except Exception as e:
        print(f"   启动异常: {e}")
        import traceback
        traceback.print_exc()
    
    # 检查最终状态
    print("\n3. 检查最终状态...")
    status = freqtrade_service.get_status()
    print(f"   最终状态: {status}")
    
    # 清理
    print("\n4. 清理...")
    freqtrade_service.stop_webserver()
    print("   已停止")

if __name__ == "__main__":
    asyncio.run(test_startup())
