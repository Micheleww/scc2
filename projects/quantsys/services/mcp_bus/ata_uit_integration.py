#!/usr/bin/env python3
"""
ATA与UI-TARS集成服务
当user_ai收到ATA消息时，自动触发UI-TARS发送提醒

功能：
1. 定期检查ATA系统中user_ai的未读消息
2. 当检测到新消息时，通过UI-TARS底层代码层发送提醒
3. 一一对应，保证每个user_ai收到消息都有UIT提醒
"""

import json
import logging
import os
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path

# 确保输出使用UTF-8编码
if sys.platform == "win32":
    import io

    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("ata_uit_integration.log", encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)


class ATAUITIntegration:
    """ATA与UI-TARS集成服务"""

    def __init__(self, repo_root: Path, mcp_bus_config: dict | None = None):
        """
        初始化集成服务

        Args:
            repo_root: 项目根目录
            mcp_bus_config: MCP Bus配置（可选，用于直接调用工具）
        """
        self.repo_root = Path(repo_root)
        self.mcp_bus_config = mcp_bus_config

        # UI-TARS IPC文件目录
        self.ipc_dir = Path(tempfile.gettempdir()) / "ui-tars-ipc"
        self.ipc_dir.mkdir(parents=True, exist_ok=True)

        # 已处理的消息ID集合（避免重复提醒）
        self.processed_message_ids: set[str] = set()

        # Agent注册表路径
        self.registry_file = self.repo_root / ".cursor" / "agent_registry.json"

        logger.info("初始化ATA-UI-TARS集成服务")
        logger.info(f"  - 项目根目录: {self.repo_root}")
        logger.info(f"  - IPC目录: {self.ipc_dir}")
        logger.info(f"  - 注册表文件: {self.registry_file}")

    def load_agent_registry(self) -> dict:
        """加载Agent注册表"""
        if not self.registry_file.exists():
            logger.warning(f"注册表文件不存在: {self.registry_file}")
            return {}

        try:
            with open(self.registry_file, encoding="utf-8") as f:
                data = json.load(f)
            return data.get("agents", {})
        except Exception as e:
            logger.error(f"加载注册表失败: {e}")
            return {}

    def get_user_ai_agents(self) -> list[dict]:
        """获取所有user_ai类型的agent"""
        agents = self.load_agent_registry()
        user_ais = []

        for agent_id, agent_data in agents.items():
            # 检查category是否为user_ai
            category = agent_data.get("category", "user_ai")
            # 如果没有category字段，根据numeric_code推断（1-10为system_ai，其他为user_ai）
            if "category" not in agent_data:
                numeric_code = agent_data.get("numeric_code")
                if numeric_code is not None and 1 <= numeric_code <= 10:
                    category = "system_ai"
                else:
                    category = "user_ai"

            if category == "user_ai":
                user_ais.append(
                    {
                        "agent_id": agent_id,
                        "numeric_code": agent_data.get("numeric_code"),
                        "category": category,
                        **agent_data,
                    }
                )

        logger.info(f"找到 {len(user_ais)} 个user_ai agent")
        return user_ais

    def call_ata_receive(self, to_agent: str, unread_only: bool = True) -> dict:
        """
        调用ATA receive工具获取消息

        Args:
            to_agent: 目标agent ID
            unread_only: 是否只获取未读消息

        Returns:
            消息列表
        """
        try:
            # 直接从ATA消息目录读取（与tools.py中的ata_receive逻辑一致）
            ata_messages_dir = self.repo_root / "mvm" / "ata" / "messages"
            if not ata_messages_dir.exists():
                return {"success": True, "messages": [], "count": 0}

            messages = []

            # 遍历所有任务目录
            for task_dir in ata_messages_dir.iterdir():
                if not task_dir.is_dir():
                    continue

                # 遍历所有消息文件
                for msg_file in task_dir.glob("*.json"):
                    try:
                        with open(msg_file, encoding="utf-8") as f:
                            message = json.load(f)

                        # 过滤目标agent
                        if message.get("to_agent") != to_agent:
                            continue

                        # 过滤未读消息
                        if unread_only:
                            status = message.get("status", "pending")
                            if status in ["read", "acked"]:
                                continue

                        # 添加文件路径和消息ID
                        message["file_path"] = str(msg_file.relative_to(self.repo_root))
                        if "msg_id" not in message:
                            # 生成唯一消息ID（使用文件路径作为唯一标识）
                            message["msg_id"] = f"{task_dir.name}/{msg_file.name}"

                        messages.append(message)
                    except Exception as e:
                        logger.warning(f"读取消息文件失败 {msg_file}: {e}")
                        continue

            # 按优先级和创建时间排序（与tools.py一致）
            priority_order = {"urgent": 4, "high": 3, "normal": 2, "low": 1}
            messages.sort(
                key=lambda x: (
                    priority_order.get(x.get("priority", "normal"), 2),
                    x.get("created_at", ""),
                ),
                reverse=True,
            )

            return {"success": True, "messages": messages, "count": len(messages)}
        except Exception as e:
            logger.error(f"调用ata_receive失败: {e}")
            return {"success": False, "error": str(e), "messages": [], "count": 0}

    def send_uit_message(self, message: str) -> bool:
        """
        通过UI-TARS底层代码层发送消息

        Args:
            message: 要发送的消息内容

        Returns:
            是否成功
        """
        try:
            # 创建IPC触发文件
            timestamp = int(time.time() * 1000)
            trigger_file = self.ipc_dir / f"send_message_{timestamp}.json"

            payload = {"action": "sendMessage", "message": message, "timestamp": timestamp}

            trigger_file.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
            )

            logger.info(f"已创建UI-TARS触发文件: {trigger_file.name}")
            logger.debug(f"消息内容: {message}")
            return True
        except Exception as e:
            logger.error(f"发送UI-TARS消息失败: {e}")
            return False

    def check_and_notify(self) -> dict:
        """
        检查所有user_ai的未读消息，并发送UI-TARS提醒

        Returns:
            处理结果统计
        """
        stats = {"checked_agents": 0, "new_messages": 0, "notifications_sent": 0, "errors": 0}

        # 获取所有user_ai
        user_ais = self.get_user_ai_agents()
        stats["checked_agents"] = len(user_ais)

        for agent in user_ais:
            agent_id = agent["agent_id"]
            numeric_code = agent.get("numeric_code")

            try:
                # 检查该agent的未读消息
                result = self.call_ata_receive(to_agent=agent_id, unread_only=True)

                if not result.get("success"):
                    logger.warning(f"检查 {agent_id} 的消息失败: {result.get('error')}")
                    stats["errors"] += 1
                    continue

                messages = result.get("messages", [])
                new_messages = [
                    msg for msg in messages if msg.get("msg_id") not in self.processed_message_ids
                ]

                if new_messages:
                    stats["new_messages"] += len(new_messages)

                    # 标记为已处理
                    for msg in new_messages:
                        msg_id = msg.get("msg_id")
                        if msg_id:
                            self.processed_message_ids.add(msg_id)

                    # 发送UI-TARS提醒
                    reminder_message = f"请查看ATA收件箱。您有 {len(new_messages)} 条新消息。"

                    if self.send_uit_message(reminder_message):
                        stats["notifications_sent"] += 1
                        logger.info(
                            f"✅ 已为 {agent_id} 发送UI-TARS提醒 (新消息: {len(new_messages)}条)"
                        )
                    else:
                        stats["errors"] += 1
                        logger.error(f"❌ 为 {agent_id} 发送UI-TARS提醒失败")
                else:
                    logger.debug(f"  {agent_id}: 无新消息")

            except Exception as e:
                logger.error(f"处理 {agent_id} 时出错: {e}")
                stats["errors"] += 1

        return stats

    def run_continuous(self, check_interval: int = 30):
        """
        持续运行，定期检查并发送提醒

        Args:
            check_interval: 检查间隔（秒）
        """
        logger.info(f"开始持续运行，检查间隔: {check_interval}秒")
        logger.info("按 Ctrl+C 停止")

        try:
            while True:
                logger.info("=" * 60)
                logger.info(f"开始检查 [{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}]")

                stats = self.check_and_notify()

                logger.info("检查完成:")
                logger.info(f"  - 检查agent数: {stats['checked_agents']}")
                logger.info(f"  - 新消息数: {stats['new_messages']}")
                logger.info(f"  - 发送提醒数: {stats['notifications_sent']}")
                logger.info(f"  - 错误数: {stats['errors']}")

                logger.info(f"等待 {check_interval} 秒后继续...")
                time.sleep(check_interval)

        except KeyboardInterrupt:
            logger.info("收到停止信号，正在退出...")
        except Exception as e:
            logger.error(f"运行出错: {e}")
            import traceback

            traceback.print_exc()


def main():
    """主函数"""
    import argparse

    parser = argparse.ArgumentParser(description="ATA与UI-TARS集成服务")
    parser.add_argument(
        "--repo-root", type=str, default=os.getcwd(), help="项目根目录（默认: 当前目录）"
    )
    parser.add_argument("--check-interval", type=int, default=30, help="检查间隔（秒，默认: 30）")
    parser.add_argument("--once", action="store_true", help="只检查一次，不持续运行")

    args = parser.parse_args()

    # 初始化服务
    repo_root = Path(args.repo_root).resolve()
    service = ATAUITIntegration(repo_root)

    if args.once:
        # 只检查一次
        logger.info("执行单次检查...")
        stats = service.check_and_notify()
        logger.info("=" * 60)
        logger.info("检查结果:")
        logger.info(f"  - 检查agent数: {stats['checked_agents']}")
        logger.info(f"  - 新消息数: {stats['new_messages']}")
        logger.info(f"  - 发送提醒数: {stats['notifications_sent']}")
        logger.info(f"  - 错误数: {stats['errors']}")
    else:
        # 持续运行
        service.run_continuous(check_interval=args.check_interval)


if __name__ == "__main__":
    main()
