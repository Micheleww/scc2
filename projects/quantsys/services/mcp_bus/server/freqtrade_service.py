
"""
Freqtrade服务管理模块 - 集成freqtrade启动和管理到总服务器
"""

import logging
import os
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class FreqtradeService:
    """Freqtrade服务管理器"""

    def __init__(self, repo_root: str | None = None):
        self.repo_root = Path(repo_root) if repo_root else Path(os.getenv("REPO_ROOT", "."))
        self.webserver_proc: subprocess.Popen | None = None
        self.trade_proc: subprocess.Popen | None = None
        self.proc_lock = threading.Lock()

        # 配置路径
        self.config_path = self.repo_root / "configs" / "current" / "freqtrade_config.json"
        if not self.config_path.exists():
            # 回退到旧路径
            self.config_path = (
                self.repo_root / "user_data" / "configs" / "freqtrade_live_config.json"
            )

        # 日志路径
        self.log_dir = self.repo_root / "logs"
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.webserver_log = self.log_dir / "freqtrade_webserver.log"
        self.trade_log = self.log_dir / "freqtrade_trade.log"

        # 状态信息
        self.webserver_start_time: float | None = None
        self.trade_start_time: float | None = None
        self.last_error: str = ""

        # API配置
        self.api_port = int(os.getenv("FREQTRADE_API_PORT", "8080"))
        self.api_url = f"http://127.0.0.1:{self.api_port}"

    # 优化：缓存freqtrade命令，避免重复查找（最快速度）
    _freqtrade_command_cache: str | None = None
    
    def _find_freqtrade_command(self) -> str | None:
        """查找freqtrade命令（带缓存优化）"""
        # 如果已缓存，直接返回（最快）
        if FreqtradeService._freqtrade_command_cache is not None:
            return FreqtradeService._freqtrade_command_cache
        
        # 尝试多种方式找到freqtrade（按优先级）
        # 优先尝试 python -m freqtrade（更可靠）
        test_commands = [
            (["python", "-m", "freqtrade", "--version"], "python -m freqtrade"),
            (["freqtrade", "--version"], "freqtrade"),
        ]

        for cmd_args, cmd_name in test_commands:
            try:
                # 优化：缩短超时时间从5秒到2秒，快速失败
                logger.debug(f"Testing freqtrade command: {cmd_name}")
                # subprocess.run() 不支持 windowsHide，需要使用 Popen 的 creationflags
                run_kwargs = {
                    "capture_output": True,
                    "timeout": 2,  # 从5秒减少到2秒
                }
                if os.name == "nt":  # Windows
                    # 使用 CREATE_NO_WINDOW 标志隐藏控制台
                    run_kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
                
                result = subprocess.run(cmd_args, **run_kwargs)
                logger.debug(f"Command {cmd_name} result: returncode={result.returncode}, stdout length={len(result.stdout)}, stderr length={len(result.stderr)}")
                if result.returncode == 0:
                    # 缓存结果（存储命令名称，用于后续构建命令）
                    # 注意：返回 "python -m freqtrade" 用于后续判断，但实际使用时需要拆分
                    cached_cmd = "python -m freqtrade" if "python -m" in cmd_name else "freqtrade"
                    FreqtradeService._freqtrade_command_cache = cached_cmd
                    logger.info(f"✅ Found freqtrade command: {cached_cmd}")
                    return cached_cmd
                else:
                    logger.debug(f"Command {cmd_name} returned non-zero exit code: {result.returncode}")
            except subprocess.TimeoutExpired:
                logger.debug(f"Command {cmd_name} test timed out")
                continue
            except Exception as e:
                logger.debug(f"Command {cmd_name} test failed: {e}", exc_info=True)
                continue

        logger.warning("❌ Freqtrade command not found in PATH or as Python module")
        return None

    def start_webserver(self) -> tuple[bool, str]:
        """启动Freqtrade WebServer（API服务器）"""
        with self.proc_lock:
            if self.webserver_proc and self.webserver_proc.poll() is None:
                return False, "WebServer already running"

            # 优化：记录查找命令的开始时间
            find_cmd_start = time.time()
            freqtrade_cmd = self._find_freqtrade_command()
            find_cmd_duration = (time.time() - find_cmd_start) * 1000
            if find_cmd_duration > 500:
                logger.warning(f"[Performance] _find_freqtrade_command() took {find_cmd_duration:.0f}ms (slow, consider caching)")
            else:
                logger.debug(f"[Performance] _find_freqtrade_command() took {find_cmd_duration:.0f}ms")
            
            if not freqtrade_cmd:
                error_msg = (
                    "Freqtrade command not found. Please install freqtrade or add it to PATH."
                )
                self.last_error = error_msg
                logger.error(error_msg)
                return False, error_msg

            try:
                # 构建命令
                # 注意：freqtrade webserver的端口在配置文件中设置（api_server.listen_port）
                # 不支持--port命令行参数
                if freqtrade_cmd == "freqtrade":
                    cmd = [
                        "freqtrade",
                        "webserver",
                        "--config",
                        str(self.config_path),
                    ]
                else:
                    cmd = [
                        "python",
                        "-m",
                        "freqtrade",
                        "webserver",
                        "--config",
                        str(self.config_path),
                    ]

                # 打开日志文件
                log_handle = self.webserver_log.open("a", encoding="utf-8")

                # 准备环境变量（确保关键变量被传递）
                env = os.environ.copy()
                env["REPO_ROOT"] = str(self.repo_root)
                env["PYTHONUNBUFFERED"] = "1"  # 确保Python输出不被缓冲

                # 启动进程（后台运行，不等待）
                # Windows上使用CREATE_NEW_PROCESS_GROUP创建独立进程组，避免父进程关闭时子进程也被关闭
                # 使用CREATE_NO_WINDOW确保不显示控制台窗口（静默启动）
                import subprocess

                creation_flags = 0
                if os.name == "nt":  # Windows
                    # CREATE_NEW_PROCESS_GROUP: 创建新的进程组
                    # CREATE_NO_WINDOW: 不创建控制台窗口（静默启动，无弹窗）
                    creation_flags = (
                        subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW
                    )

                logger.info(f"Starting Freqtrade with command: {' '.join(cmd)}")
                logger.info(f"Working directory: {self.repo_root}")
                logger.info(f"Config path: {self.config_path}")

                self.webserver_proc = subprocess.Popen(
                    cmd,
                    cwd=str(self.repo_root),
                    stdout=log_handle,
                    stderr=subprocess.STDOUT,
                    env=env,
                    creationflags=creation_flags if os.name == "nt" else 0,
                    start_new_session=True if os.name != "nt" else False,
                    close_fds=True if os.name != "nt" else False,  # Unix上关闭文件描述符
                )

                # 优化：减少等待时间，从0.5秒减少到0.1秒（最快速度）
                time.sleep(0.1)  # 只等待0.1秒让进程启动
                if self.webserver_proc.poll() is not None:
                    # 进程立即退出了
                    exit_code = self.webserver_proc.returncode
                    error_msg = f"Freqtrade process exited immediately with code {exit_code}. Check logs: {self.webserver_log}"
                    self.last_error = error_msg
                    logger.error(error_msg)
                    # 读取日志的最后几行
                    try:
                        if self.webserver_log.exists():
                            with open(self.webserver_log, encoding="utf-8", errors="ignore") as f:
                                log_lines = f.readlines()
                                if log_lines:
                                    last_lines = "".join(log_lines[-10:])
                                    logger.error(f"Last log lines:\n{last_lines}")
                    except Exception:
                        pass
                    self.webserver_proc = None
                    self.webserver_start_time = None
                    return False, error_msg

                # 进程启动成功，记录启动时间
                self.webserver_start_time = time.time()
                self.last_error = ""

                logger.info(f"Freqtrade WebServer started (PID: {self.webserver_proc.pid})")
                logger.info(f"Log file: {self.webserver_log}")
                return True, f"WebServer started (PID: {self.webserver_proc.pid})"

            except Exception as e:
                error_msg = f"Failed to start WebServer: {str(e)}"
                self.last_error = error_msg
                logger.error(error_msg, exc_info=True)
                # 确保清理状态
                if self.webserver_proc:
                    try:
                        self.webserver_proc.terminate()
                    except:
                        pass
                    self.webserver_proc = None
                self.webserver_start_time = None
                return False, error_msg

    def start_trade(
        self, strategy: str | None = None, dry_run: bool = True, passphrase: str | None = None
    ) -> tuple[bool, str]:
        """启动Freqtrade交易进程"""
        with self.proc_lock:
            if self.trade_proc and self.trade_proc.poll() is None:
                return False, "Trade process already running"

            freqtrade_cmd = self._find_freqtrade_command()
            if not freqtrade_cmd:
                error_msg = (
                    "Freqtrade command not found. Please install freqtrade or add it to PATH."
                )
                self.last_error = error_msg
                logger.error(error_msg)
                return False, error_msg

            try:
                # 构建命令
                if freqtrade_cmd == "freqtrade":
                    cmd = [
                        "freqtrade",
                        "trade",
                        "--config",
                        str(self.config_path),
                    ]
                else:
                    cmd = [
                        "python",
                        "-m",
                        "freqtrade",
                        "trade",
                        "--config",
                        str(self.config_path),
                    ]

                if strategy:
                    cmd.extend(["--strategy", strategy])

                if dry_run:
                    cmd.append("--dry-run")

                # 环境变量
                env = os.environ.copy()
                if passphrase:
                    env["FT_PASSPHRASE"] = passphrase

                # 打开日志文件
                log_handle = self.trade_log.open("a", encoding="utf-8")

                # Windows上使用CREATE_NO_WINDOW确保不显示控制台窗口（静默启动）
                creation_flags = 0
                if os.name == "nt":  # Windows
                    creation_flags = (
                        subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW
                    )

                # 启动进程
                self.trade_proc = subprocess.Popen(
                    cmd,
                    cwd=str(self.repo_root),
                    stdout=log_handle,
                    stderr=subprocess.STDOUT,
                    env=env,
                    creationflags=creation_flags if os.name == "nt" else 0,
                    start_new_session=True if os.name != "nt" else False,
                    close_fds=True if os.name != "nt" else False,
                )

                self.trade_start_time = time.time()
                self.last_error = ""

                logger.info(
                    f"Freqtrade trade process started (PID: {self.trade_proc.pid}, dry_run={dry_run})"
                )
                return True, f"Trade process started (PID: {self.trade_proc.pid})"

            except Exception as e:
                error_msg = f"Failed to start trade process: {str(e)}"
                self.last_error = error_msg
                logger.error(error_msg, exc_info=True)
                return False, error_msg

    def stop_webserver(self) -> tuple[bool, str]:
        """停止WebServer（包括外部启动的进程）"""
        with self.proc_lock:
            stopped = False
            
            # 首先尝试停止由我们管理的进程
            if self.webserver_proc:
                try:
                    self.webserver_proc.terminate()
                    try:
                        self.webserver_proc.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        self.webserver_proc.kill()
                        self.webserver_proc.wait()
                    stopped = True
                    self.webserver_proc = None
                    self.webserver_start_time = None
                    logger.info("Freqtrade WebServer stopped (managed process)")
                except Exception as e:
                    logger.warning(f"Failed to stop managed process: {e}")
            
            # 如果还有外部进程在运行（通过API检测），尝试通过端口查找并停止
            try:
                import urllib.request
                urllib.request.urlopen(self.api_url + "/api/v1/ping", timeout=0.5)
                # API可访问，说明还有进程在运行
                logger.info("Detected external Freqtrade process, attempting to stop...")
                
                # 通过端口查找进程（Windows）
                if sys.platform == "win32":
                    import subprocess as sp
                    result = sp.run(
                        ["netstat", "-ano"], capture_output=True, text=True, timeout=5
                    )
                    for line in result.stdout.split("\n"):
                        if f":{self.api_port}" in line and "LISTENING" in line:
                            parts = line.split()
                            if len(parts) >= 5:
                                pid = int(parts[-1])
                                try:
                                    import psutil
                                    proc = psutil.Process(pid)
                                    if "freqtrade" in " ".join(proc.cmdline()).lower():
                                        logger.info(f"Stopping external Freqtrade process (PID: {pid})...")
                                        proc.terminate()
                                        try:
                                            proc.wait(timeout=5)
                                        except psutil.TimeoutExpired:
                                            proc.kill()
                                        stopped = True
                                        logger.info(f"External Freqtrade process (PID: {pid}) stopped")
                                except (psutil.NoSuchProcess, psutil.AccessDenied, ImportError) as e:
                                    logger.warning(f"Could not stop external process {pid}: {e}")
            except Exception:
                # API不可访问，说明进程已停止
                pass
            
            if stopped:
                return True, "WebServer stopped"
            else:
                return False, "WebServer not running or could not be stopped"

    def stop_trade(self) -> tuple[bool, str]:
        """停止交易进程"""
        with self.proc_lock:
            if not self.trade_proc:
                return False, "Trade process not running"

            try:
                self.trade_proc.terminate()
                try:
                    self.trade_proc.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    self.trade_proc.kill()
                    self.trade_proc.wait()

                self.trade_proc = None
                self.trade_start_time = None
                logger.info("Freqtrade trade process stopped")
                return True, "Trade process stopped"
            except Exception as e:
                error_msg = f"Failed to stop trade process: {str(e)}"
                self.last_error = error_msg
                logger.error(error_msg)
                return False, error_msg

    def get_status(self) -> dict[str, Any]:
        """获取Freqtrade状态"""
        with self.proc_lock:
            # 检查进程是否还在运行，如果已退出则清理
            if self.webserver_proc is not None:
                poll_result = self.webserver_proc.poll()
                if poll_result is not None:
                    # 进程已退出，清理状态
                    logger.warning(
                        f"Freqtrade WebServer process (PID: {self.webserver_proc.pid}) has exited with code {poll_result}"
                    )
                    self.webserver_proc = None
                    self.webserver_start_time = None

            if self.trade_proc is not None:
                poll_result = self.trade_proc.poll()
                if poll_result is not None:
                    # 进程已退出，清理状态
                    logger.warning(
                        f"Freqtrade trade process (PID: {self.trade_proc.pid}) has exited with code {poll_result}"
                    )
                    self.trade_proc = None
                    self.trade_start_time = None

            # 优化：优先检查进程存在，不等待API就绪（最快速度）
            # 检查WebServer是否在运行（通过进程对象）
            webserver_running = (
                self.webserver_proc is not None and self.webserver_proc.poll() is None
            )

            # 如果进程对象不存在，尝试通过API检查（但使用更短的超时）
            if not webserver_running:
                try:
                    import urllib.request

                    # 优化：缩短超时时间到0.5秒，快速失败
                    urllib.request.urlopen(self.api_url + "/api/v1/ping", timeout=0.5)
                    # API可访问，说明服务实际在运行（可能是外部启动的）
                    webserver_running = True
                    # 清除旧的错误信息
                    if self.last_error and "cannot access local variable 'time'" in self.last_error:
                        self.last_error = ""
                except Exception:
                    # API不可访问，但进程可能正在启动中，不立即判定为失败
                    # 优化：如果进程刚启动（启动时间<5秒），认为可能还在启动中
                    if self.webserver_start_time and (time.time() - self.webserver_start_time) < 5:
                        webserver_running = True  # 认为可能还在启动中
                    else:
                        webserver_running = False

            trade_running = self.trade_proc is not None and self.trade_proc.poll() is None

            # 如果API可访问但进程对象不存在，尝试通过端口查找进程
            detected_pid = None
            if webserver_running and self.webserver_proc is None:
                try:
                    # 通过端口查找进程（Windows）
                    if sys.platform == "win32":
                        import subprocess as sp

                        result = sp.run(
                            ["netstat", "-ano"], capture_output=True, text=True, timeout=5
                        )
                        for line in result.stdout.split("\n"):
                            if f":{self.api_port}" in line and "LISTENING" in line:
                                parts = line.split()
                                if len(parts) > 0:
                                    try:
                                        detected_pid = int(parts[-1])
                                        break
                                    except ValueError:
                                        pass
                except Exception:
                    pass

            status = {
                "webserver": {
                    "running": webserver_running,
                    "pid": self.webserver_proc.pid if self.webserver_proc else detected_pid,
                    "start_time": self.webserver_start_time,
                    "uptime_seconds": (
                        time.time() - self.webserver_start_time
                        if self.webserver_start_time and webserver_running
                        else None
                    ),
                    "log_path": str(self.webserver_log),
                    "api_url": self.api_url if webserver_running else None,
                },
                "trade": {
                    "running": trade_running,
                    "pid": self.trade_proc.pid if self.trade_proc else None,
                    "start_time": self.trade_start_time,
                    "uptime_seconds": (
                        time.time() - self.trade_start_time if self.trade_start_time else None
                    ),
                    "log_path": str(self.trade_log),
                },
                "config_path": str(self.config_path),
                "last_error": self.last_error,
            }

            return status

    def get_logs(self, log_type: str = "webserver", lines: int = 100) -> str:
        """获取日志内容"""
        log_file = self.webserver_log if log_type == "webserver" else self.trade_log

        if not log_file.exists():
            return ""

        try:
            with open(log_file, encoding="utf-8", errors="ignore") as f:
                all_lines = f.readlines()
                return "".join(all_lines[-lines:])
        except Exception as e:
            logger.error(f"Failed to read log: {e}")
            return ""


# 全局Freqtrade服务实例
freqtrade_service = FreqtradeService()
