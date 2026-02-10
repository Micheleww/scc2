"""
Agent 协调器 (Agent Coordinator)
管理 Agent 注册和状态，基于角色和能力匹配 Agent，智能路由消息
"""

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any


class AgentStatus(str, Enum):
    """Agent 状态"""

    AVAILABLE = "available"
    BUSY = "busy"
    UNAVAILABLE = "unavailable"
    ERROR = "error"


@dataclass
class Agent:
    """Agent 定义"""

    agent_id: str
    agent_type: str  # Cursor, GPT, TRAE
    role: str
    capabilities: list[str]
    current_load: int
    max_concurrent_tasks: int
    status: AgentStatus
    registered_at: str
    last_heartbeat: str
    numeric_code: int | None = None  # 数字编码（1-100，唯一）
    send_enabled: bool = True  # 是否允许发送ATA消息（硬权限）
    category: str = "user_ai"  # Agent类别：user_ai（用户AI）或 system_ai（系统AI）
    response_time_avg: float = 0.0  # 平均响应时间（秒）
    success_rate: float = 1.0  # 成功率
    total_tasks: int = 0
    completed_tasks: int = 0


class AgentRegistry:
    """Agent 注册表"""

    MAX_AGENTS = 100  # 最大Agent数量

    def __init__(self, repo_root: Path):
        self.repo_root = repo_root
        self.registry_file = self.repo_root / ".cursor" / "agent_registry.json"
        self.agents: dict[str, Agent] = {}
        self.load_registry()

    def _allocate_numeric_code(self) -> int | None:
        """分配唯一的数字编码（1-100）"""
        used_codes = {
            agent.numeric_code for agent in self.agents.values() if agent.numeric_code is not None
        }

        # 从1开始查找可用的编码
        for code in range(1, self.MAX_AGENTS + 1):
            if code not in used_codes:
                return code

        # 如果所有编码都被使用，返回None
        return None

    def load_registry(self):
        """加载注册表"""
        if self.registry_file.exists():
            try:
                with open(self.registry_file, encoding="utf-8") as f:
                    data = json.load(f)

                agents_data = data.get("agents", {})
                for agent_id, agent_data in agents_data.items():
                    # Default send_enabled (hard logic): Cursor-Auto cannot send
                    if "send_enabled" not in agent_data:
                        agent_data["send_enabled"] = not (
                            agent_id == "Cursor-Auto"
                            or agent_data.get("agent_type") == "Cursor-Auto"
                        )
                    # Default category: infer from numeric_code if not present (backward compatibility)
                    if "category" not in agent_data:
                        numeric_code = agent_data.get("numeric_code")
                        if numeric_code is not None and 1 <= numeric_code <= 10:
                            agent_data["category"] = "system_ai"
                        else:
                            agent_data["category"] = "user_ai"
                    # Normalize status field to AgentStatus enum
                    try:
                        status_val = agent_data.get("status", AgentStatus.AVAILABLE.value)
                        agent_data["status"] = AgentStatus(status_val)
                    except Exception:
                        agent_data["status"] = AgentStatus.AVAILABLE
                    self.agents[agent_id] = Agent(**agent_data)
            except Exception:
                pass

    def save_registry(self):
        """保存注册表"""
        data = {
            "agents": {agent_id: asdict(agent) for agent_id, agent in self.agents.items()},
            "roles": self._build_roles_index(),
        }

        self.registry_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.registry_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def register_agent(
        self,
        agent_id: str,
        agent_type: str,
        role: str,
        capabilities: list[str],
        max_concurrent_tasks: int = 5,
        numeric_code: int | None = None,
        send_enabled: bool | None = None,
        category: str | None = None,
    ) -> dict[str, Any]:
        """注册 Agent"""
        now = datetime.now().isoformat() + "Z"
        # Hard default: Cursor-Auto is read-only (can receive, cannot send)
        if send_enabled is None:
            send_enabled = not (agent_id == "Cursor-Auto" or agent_type == "Cursor-Auto")
        # Default category: infer from numeric_code if not provided
        if category is None:
            if numeric_code is not None and 1 <= numeric_code <= 10:
                category = "system_ai"
            else:
                category = "user_ai"
        # Validate category
        if category not in ["user_ai", "system_ai"]:
            return {
                "success": False,
                "error": f"Invalid category: {category} (must be 'user_ai' or 'system_ai')",
            }

        # Hard gate: numeric_code, when provided, must be valid and unused (fail-closed; never silently reassign)
        if numeric_code is not None:
            if not isinstance(numeric_code, int):
                return {"success": False, "error": "numeric_code must be an integer (1-100)"}
            if not (1 <= numeric_code <= self.MAX_AGENTS):
                return {
                    "success": False,
                    "error": f"numeric_code out of range: {numeric_code} (must be 1-{self.MAX_AGENTS})",
                }
            used_by_other = any(
                (a.numeric_code == numeric_code) and (a.agent_id != agent_id)
                for a in self.agents.values()
                if a.numeric_code is not None
            )
            if used_by_other:
                return {"success": False, "error": f"numeric_code already in use: {numeric_code}"}

        if agent_id in self.agents:
            # 更新现有 Agent
            agent = self.agents[agent_id]
            agent.agent_type = agent_type
            agent.role = role
            agent.capabilities = capabilities
            agent.max_concurrent_tasks = max_concurrent_tasks
            agent.last_heartbeat = now
            agent.status = AgentStatus.AVAILABLE
            agent.send_enabled = bool(send_enabled)
            agent.category = category
            # 如果指定了数字编码且与现有不同，检查是否可用
            if numeric_code is not None and numeric_code != agent.numeric_code:
                # 已在上方硬门校验唯一性/范围，这里直接更新
                agent.numeric_code = numeric_code
        else:
            # 创建新 Agent
            # 分配数字编码
            if numeric_code is None:
                numeric_code = self._allocate_numeric_code()

            if numeric_code is None:
                return {"success": False, "error": f"已达到最大Agent数量限制（{self.MAX_AGENTS}）"}

            agent = Agent(
                agent_id=agent_id,
                agent_type=agent_type,
                role=role,
                capabilities=capabilities,
                current_load=0,
                max_concurrent_tasks=max_concurrent_tasks,
                status=AgentStatus.AVAILABLE,
                registered_at=now,
                last_heartbeat=now,
                numeric_code=numeric_code,
                send_enabled=bool(send_enabled),
                category=category,
            )
            self.agents[agent_id] = agent

        self.save_registry()

        return {
            "success": True,
            "agent_id": agent_id,
            "numeric_code": agent.numeric_code,
            "send_enabled": agent.send_enabled,
            "role": role,
            "status": agent.status.value,
        }

    def unregister_agent(self, agent_id: str) -> dict[str, Any]:
        """注销 Agent"""
        if agent_id not in self.agents:
            return {"success": False, "error": f"Agent {agent_id} not found"}

        del self.agents[agent_id]
        self.save_registry()

        return {"success": True, "agent_id": agent_id}

    def update_agent_status(
        self, agent_id: str, status: str, current_load: int | None = None
    ) -> dict[str, Any]:
        """更新 Agent 状态"""
        if agent_id not in self.agents:
            return {"success": False, "error": f"Agent {agent_id} not found"}

        agent = self.agents[agent_id]
        agent.status = AgentStatus(status)
        agent.last_heartbeat = datetime.now().isoformat() + "Z"

        if current_load is not None:
            agent.current_load = current_load
            # 自动更新状态
            if current_load >= agent.max_concurrent_tasks:
                agent.status = AgentStatus.BUSY
            elif current_load == 0:
                agent.status = AgentStatus.AVAILABLE

        self.save_registry()

        return {"success": True, "agent_id": agent_id, "status": agent.status.value}

    def find_agents(
        self,
        role: str | None = None,
        capabilities: list[str] | None = None,
        available_only: bool = True,
    ) -> list[Agent]:
        """查找匹配的 Agent"""
        candidates = []

        for agent in self.agents.values():
            # 检查可用性
            if available_only:
                if agent.status not in [AgentStatus.AVAILABLE, AgentStatus.BUSY]:
                    continue
                if agent.current_load >= agent.max_concurrent_tasks:
                    continue

            # 检查角色匹配
            if role and agent.role != role:
                continue

            # 检查能力匹配
            if capabilities:
                if not all(cap in agent.capabilities for cap in capabilities):
                    continue

            candidates.append(agent)

        return candidates

    def get_agent(self, agent_id: str) -> Agent | None:
        """获取 Agent"""
        return self.agents.get(agent_id)

    def _build_roles_index(self) -> dict[str, dict[str, Any]]:
        """构建角色索引"""
        roles = {}

        for agent in self.agents.values():
            if agent.role not in roles:
                roles[agent.role] = {"agents": [], "total_capacity": 0, "available_capacity": 0}

            roles[agent.role]["agents"].append(agent.agent_id)
            roles[agent.role]["total_capacity"] += agent.max_concurrent_tasks
            available = max(0, agent.max_concurrent_tasks - agent.current_load)
            roles[agent.role]["available_capacity"] += available

        return roles

    def get_all_agents(self) -> list[dict[str, Any]]:
        """获取所有Agent的列表"""

        def _format_code(n: int | None) -> str:
            if n is None:
                return "--"
            try:
                return f"{int(n):02d}"
            except Exception:
                return "--"

        agents_list = []
        for agent in self.agents.values():
            display_name = f"{agent.agent_id}#{_format_code(agent.numeric_code)}"
            agent_dict = {
                "agent_id": agent.agent_id,
                "numeric_code": agent.numeric_code,
                "display_name": display_name,
                "agent_type": agent.agent_type,
                "role": agent.role,
                "capabilities": agent.capabilities,
                "current_load": agent.current_load,
                "max_concurrent_tasks": agent.max_concurrent_tasks,
                "status": agent.status.value,
                "send_enabled": agent.send_enabled,
                "category": agent.category,
                "registered_at": agent.registered_at,
                "last_heartbeat": agent.last_heartbeat,
                "response_time_avg": agent.response_time_avg,
                "success_rate": agent.success_rate,
                "total_tasks": agent.total_tasks,
                "completed_tasks": agent.completed_tasks,
            }
            agents_list.append(agent_dict)
        return agents_list

    def get_agent_by_code(self, numeric_code: int) -> Agent | None:
        """根据数字编码获取Agent"""
        for agent in self.agents.values():
            if agent.numeric_code == numeric_code:
                return agent
        return None


class SmartRouter:
    """智能路由器"""

    def __init__(self, registry: AgentRegistry):
        self.registry = registry

    def route_message(self, message: dict[str, Any], available_agents: list[Agent]) -> Agent | None:
        """智能路由消息到合适的 Agent"""
        if not available_agents:
            return None

        # 如果只有一个 Agent，直接返回
        if len(available_agents) == 1:
            return available_agents[0]

        # 评分排序
        scored_agents = []
        for agent in available_agents:
            score = self._calculate_agent_score(agent, message)
            scored_agents.append((score, agent))

        # 按分数降序排序
        scored_agents.sort(key=lambda x: x[0], reverse=True)

        # 返回得分最高的 Agent
        return scored_agents[0][1] if scored_agents else None

    def _calculate_agent_score(self, agent: Agent, message: dict[str, Any]) -> float:
        """计算 Agent 得分"""
        score = 100.0

        # 负载分数（负载越低分数越高）
        load_ratio = (
            agent.current_load / agent.max_concurrent_tasks if agent.max_concurrent_tasks > 0 else 0
        )
        score -= load_ratio * 30  # 最多扣30分

        # 响应时间分数（响应时间越短分数越高）
        if agent.response_time_avg > 0:
            # 假设理想响应时间是30秒，超过60秒开始扣分
            if agent.response_time_avg > 60:
                score -= (agent.response_time_avg - 60) / 10  # 每10秒扣1分

        # 成功率分数
        score += agent.success_rate * 20  # 最多加20分

        # 状态分数
        if agent.status == AgentStatus.AVAILABLE:
            score += 10
        elif agent.status == AgentStatus.BUSY:
            score -= 5

        return max(0, score)


class LoadBalancer:
    """负载均衡器"""

    def __init__(self, registry: AgentRegistry):
        self.registry = registry

    def select_agent(self, agents: list[Agent]) -> Agent | None:
        """选择 Agent（基于负载）"""
        if not agents:
            return None

        # 过滤可用 Agent
        available = [
            a
            for a in agents
            if a.current_load < a.max_concurrent_tasks
            and a.status in [AgentStatus.AVAILABLE, AgentStatus.BUSY]
        ]

        if not available:
            return None

        # 选择负载最低的 Agent
        return min(
            available,
            key=lambda a: a.current_load / a.max_concurrent_tasks
            if a.max_concurrent_tasks > 0
            else 1.0,
        )


class AgentCoordinator:
    """Agent 协调器"""

    def __init__(self, repo_root: Path):
        self.repo_root = repo_root
        self.registry = AgentRegistry(repo_root)
        self.router = SmartRouter(self.registry)
        self.load_balancer = LoadBalancer(self.registry)

        # 心跳超时（秒）
        self.heartbeat_timeout = 300  # 5分钟

    def register_agent(
        self,
        agent_id: str,
        agent_type: str,
        role: str,
        capabilities: list[str],
        max_concurrent_tasks: int = 5,
        numeric_code: int | None = None,
        send_enabled: bool | None = None,
        category: str | None = None,
    ) -> dict[str, Any]:
        """注册 Agent"""
        return self.registry.register_agent(
            agent_id=agent_id,
            agent_type=agent_type,
            role=role,
            capabilities=capabilities,
            max_concurrent_tasks=max_concurrent_tasks,
            numeric_code=numeric_code,
            send_enabled=send_enabled,
            category=category,
        )

    def find_agent_for_role(
        self, role: str, capabilities: list[str] | None = None, use_load_balancing: bool = True
    ) -> Agent | None:
        """为角色查找 Agent"""
        agents = self.registry.find_agents(
            role=role, capabilities=capabilities, available_only=True
        )

        if not agents:
            return None

        if use_load_balancing:
            return self.load_balancer.select_agent(agents)
        else:
            return self.router.route_message({}, agents)

    def update_agent_heartbeat(
        self, agent_id: str, current_load: int | None = None
    ) -> dict[str, Any]:
        """更新 Agent 心跳"""
        return self.registry.update_agent_status(
            agent_id, AgentStatus.AVAILABLE.value, current_load
        )

    def get_all_agents(self) -> list[dict[str, Any]]:
        """获取所有Agent列表"""
        return self.registry.get_all_agents()

    def cleanup_stale_agents(self) -> dict[str, Any]:
        """清理过期的 Agent"""
        now = datetime.now()
        stale_agents = []

        for agent_id, agent in self.registry.agents.items():
            last_heartbeat = datetime.fromisoformat(agent.last_heartbeat.replace("Z", "+00:00"))
            # 转换为本地时间比较
            if (now - last_heartbeat.replace(tzinfo=None)) > timedelta(
                seconds=self.heartbeat_timeout
            ):
                stale_agents.append(agent_id)

        for agent_id in stale_agents:
            self.registry.agents[agent_id].status = AgentStatus.UNAVAILABLE
            self.registry.save_registry()

        return {"success": True, "stale_count": len(stale_agents), "stale_agents": stale_agents}
