#!/usr/bin/env python3
"""
Windows服务安装脚本

将统一服务器安装为Windows服务，支持：
- 开机自启动
- 后台运行
- 独立运行（不依赖用户登录）
- 自动重启
"""

import os
import sys
import subprocess
from pathlib import Path

def check_admin():
    """检查是否以管理员权限运行"""
    try:
        import ctypes
        return ctypes.windll.shell32.IsUserAnAdmin() != 0
    except:
        return False

def install_service():
    """安装Windows服务"""
    if not check_admin():
        print("❌ 需要管理员权限！请以管理员身份运行此脚本。")
        sys.exit(1)
    
    # 获取脚本路径
    current_file = Path(__file__).resolve()
    unified_server_dir = current_file.parent
    repo_root = unified_server_dir.parent.parent
    
    # Python解释器路径
    python_exe = sys.executable
    
    # 服务脚本路径
    service_script = unified_server_dir / "main.py"
    
    # 使用NSSM (Non-Sucking Service Manager) 安装服务
    nssm_path = repo_root / "tools" / "unified_server" / "nssm.exe"
    
    if not nssm_path.exists():
        print("❌ 未找到 nssm.exe")
        print("请下载 NSSM 并放置到 tools/unified_server/ 目录")
        print("下载地址: https://nssm.cc/download")
        sys.exit(1)
    
    service_name = "QuantSysUnifiedServer"
    
    print(f"正在安装服务: {service_name}")
    print(f"Python: {python_exe}")
    print(f"脚本: {service_script}")
    
    # 安装服务
    install_cmd = [
        str(nssm_path),
        "install",
        service_name,
        python_exe,
        str(service_script)
    ]
    
    try:
        result = subprocess.run(install_cmd, check=True, capture_output=True, text=True)
        print("✅ 服务安装成功")
    except subprocess.CalledProcessError as e:
        print(f"❌ 服务安装失败: {e}")
        print(f"错误输出: {e.stderr}")
        sys.exit(1)
    
    # 配置服务
    print("正在配置服务...")
    
    # 设置工作目录
    subprocess.run([str(nssm_path), "set", service_name, "AppDirectory", str(unified_server_dir)], check=True)
    
    # 设置描述
    subprocess.run([str(nssm_path), "set", service_name, "Description", "QuantSys统一服务器 - 整合MCP总线、A2A Hub和Exchange Server"], check=True)
    
    # 设置启动类型为自动
    subprocess.run([str(nssm_path), "set", service_name, "Start", "SERVICE_AUTO_START"], check=True)
    
    # 设置失败时重启
    subprocess.run([str(nssm_path), "set", service_name, "AppRestartDelay", "5000"], check=True)
    subprocess.run([str(nssm_path), "set", service_name, "AppExit", "Default", "Restart"], check=True)
    
    # 设置环境变量
    env_vars = {
        "REPO_ROOT": str(repo_root),
        "UNIFIED_SERVER_HOST": "127.0.0.1",
        "UNIFIED_SERVER_PORT": "18788",
        "LOG_LEVEL": "info",
    }
    
    for key, value in env_vars.items():
        subprocess.run([str(nssm_path), "set", service_name, f"AppEnvironmentExtra", f"{key}={value}"], check=True)
    
    # 设置日志
    log_dir = unified_server_dir / "logs"
    log_dir.mkdir(exist_ok=True)
    
    subprocess.run([str(nssm_path), "set", service_name, "AppStdout", str(log_dir / "service_stdout.log")], check=True)
    subprocess.run([str(nssm_path), "set", service_name, "AppStderr", str(log_dir / "service_stderr.log")], check=True)
    
    print("✅ 服务配置完成")
    print(f"\n服务名称: {service_name}")
    print(f"日志目录: {log_dir}")
    print("\n可以使用以下命令管理服务:")
    print(f"  启动: net start {service_name}")
    print(f"  停止: net stop {service_name}")
    print(f"  删除: {nssm_path} remove {service_name} confirm")

def uninstall_service():
    """卸载Windows服务"""
    if not check_admin():
        print("❌ 需要管理员权限！请以管理员身份运行此脚本。")
        sys.exit(1)
    
    service_name = "QuantSysUnifiedServer"
    repo_root = Path(__file__).resolve().parent.parent.parent
    nssm_path = repo_root / "tools" / "unified_server" / "nssm.exe"
    
    if not nssm_path.exists():
        print("❌ 未找到 nssm.exe")
        sys.exit(1)
    
    print(f"正在卸载服务: {service_name}")
    
    try:
        subprocess.run([str(nssm_path), "remove", service_name, "confirm"], check=True)
        print("✅ 服务卸载成功")
    except subprocess.CalledProcessError as e:
        print(f"❌ 服务卸载失败: {e}")
        sys.exit(1)

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "uninstall":
        uninstall_service()
    else:
        install_service()
