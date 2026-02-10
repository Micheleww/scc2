#!/usr/bin/env python3
"""
Windows对话框Agent - 从对话框唤起AI执行任务

功能：
- 创建Windows系统对话框界面
- 支持搜索GitHub
- 支持发送任务到ATA系统执行
"""

import json
import os
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import messagebox, scrolledtext, ttk
from typing import Any

import httpx

# 项目根目录
REPO_ROOT = Path(__file__).resolve().parents[2]
MCP_BUS_URL = os.getenv("MCP_BUS_URL", "http://127.0.0.1:18788/")
AGENT_ID = "Windows助手"


class WindowsDialogAgent:
    """Windows对话框Agent主界面"""

    def __init__(self, root):
        self.root = root
        self.root.title("Windows助手 - AI任务执行")
        self.root.geometry("800x600")
        self.root.resizable(True, True)

        # 创建界面
        self.create_widgets()

    def create_widgets(self):
        """创建界面组件"""
        # 标题
        title_frame = ttk.Frame(self.root)
        title_frame.pack(fill=tk.X, padx=10, pady=10)

        title_label = ttk.Label(title_frame, text="🤖 Windows助手", font=("Arial", 16, "bold"))
        title_label.pack(side=tk.LEFT)

        status_label = ttk.Label(title_frame, text="Agent ID: Windows助手 #13", font=("Arial", 10))
        status_label.pack(side=tk.RIGHT)

        # 选项卡
        notebook = ttk.Notebook(self.root)
        notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        # GitHub搜索标签页
        github_frame = ttk.Frame(notebook)
        notebook.add(github_frame, text="GitHub搜索")
        self.create_github_tab(github_frame)

        # AI任务执行标签页
        task_frame = ttk.Frame(notebook)
        notebook.add(task_frame, text="AI任务执行")
        self.create_task_tab(task_frame)

    def create_github_tab(self, parent):
        """创建GitHub搜索标签页"""
        # 搜索框
        search_frame = ttk.Frame(parent)
        search_frame.pack(fill=tk.X, padx=10, pady=10)

        ttk.Label(search_frame, text="搜索查询:").pack(side=tk.LEFT, padx=5)
        self.github_query = ttk.Entry(search_frame, width=40)
        self.github_query.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)

        # 搜索类型
        type_frame = ttk.Frame(parent)
        type_frame.pack(fill=tk.X, padx=10, pady=5)

        ttk.Label(type_frame, text="搜索类型:").pack(side=tk.LEFT, padx=5)
        self.search_type = ttk.Combobox(
            type_frame, values=["repositories", "code", "issues"], state="readonly", width=15
        )
        self.search_type.set("repositories")
        self.search_type.pack(side=tk.LEFT, padx=5)

        # 搜索按钮
        search_btn = ttk.Button(type_frame, text="搜索GitHub", command=self.search_github)
        search_btn.pack(side=tk.LEFT, padx=10)

        # 结果区域
        result_frame = ttk.Frame(parent)
        result_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        ttk.Label(result_frame, text="搜索结果:").pack(anchor=tk.W)
        self.github_results = scrolledtext.ScrolledText(result_frame, height=20, wrap=tk.WORD)
        self.github_results.pack(fill=tk.BOTH, expand=True)

    def create_task_tab(self, parent):
        """创建AI任务执行标签页"""
        # 任务输入框
        task_frame = ttk.Frame(parent)
        task_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        ttk.Label(task_frame, text="任务描述:").pack(anchor=tk.W)
        self.task_input = scrolledtext.ScrolledText(task_frame, height=10, wrap=tk.WORD)
        self.task_input.pack(fill=tk.BOTH, expand=True, pady=5)

        # 目标Agent选择
        agent_frame = ttk.Frame(parent)
        agent_frame.pack(fill=tk.X, padx=10, pady=5)

        ttk.Label(agent_frame, text="目标Agent:").pack(side=tk.LEFT, padx=5)
        self.target_agent = ttk.Combobox(
            agent_frame,
            values=["ATA系统", "结构设计师", "CI完备", "交易模块", "Cursor-Auto"],
            state="readonly",
            width=20,
        )
        self.target_agent.set("ATA系统")
        self.target_agent.pack(side=tk.LEFT, padx=5)

        # 执行按钮
        exec_btn = ttk.Button(agent_frame, text="发送任务", command=self.send_task)
        exec_btn.pack(side=tk.LEFT, padx=10)

        # 结果区域
        result_frame = ttk.Frame(parent)
        result_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        ttk.Label(result_frame, text="执行结果:").pack(anchor=tk.W)
        self.task_results = scrolledtext.ScrolledText(result_frame, height=10, wrap=tk.WORD)
        self.task_results.pack(fill=tk.BOTH, expand=True)

    def _mcp_call(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        """调用MCP工具"""
        try:
            req = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {"name": name, "arguments": arguments},
            }
            response = httpx.post(f"{MCP_BUS_URL}/mcp", json=req, timeout=30.0)
            response.raise_for_status()
            data = response.json()
            if "result" in data and "content" in data["result"]:
                text = data["result"]["content"][0].get("text", "{}")
                return (
                    json.loads(text)
                    if isinstance(text, str) and text.strip().startswith("{")
                    else {"raw": text}
                )
            return {"success": False, "error": "Invalid response"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def search_github(self):
        """搜索GitHub"""
        query = self.github_query.get().strip()
        if not query:
            messagebox.showwarning("警告", "请输入搜索查询")
            return

        search_type = self.search_type.get()
        self.github_results.delete(1.0, tk.END)
        self.github_results.insert(tk.END, "正在搜索GitHub...\n")
        self.root.update()

        try:
            result = self._mcp_call(
                "github_search", {"query": query, "search_type": search_type, "limit": 10}
            )

            if result.get("success"):
                self.github_results.delete(1.0, tk.END)
                self.github_results.insert(tk.END, f"搜索查询: {query}\n")
                self.github_results.insert(tk.END, f"搜索类型: {search_type}\n")
                self.github_results.insert(
                    tk.END, f"找到 {result.get('total_count', 0)} 个结果\n\n"
                )

                for idx, item in enumerate(result.get("results", []), 1):
                    self.github_results.insert(
                        tk.END, f"{idx}. {json.dumps(item, ensure_ascii=False, indent=2)}\n\n"
                    )
            else:
                self.github_results.insert(tk.END, f"搜索失败: {result.get('error', '未知错误')}\n")
        except Exception as e:
            self.github_results.insert(tk.END, f"错误: {str(e)}\n")

    def send_task(self):
        """发送任务到ATA系统"""
        task_text = self.task_input.get(1.0, tk.END).strip()
        if not task_text:
            messagebox.showwarning("警告", "请输入任务描述")
            return

        target = self.target_agent.get()
        self.task_results.delete(1.0, tk.END)
        self.task_results.insert(tk.END, f"正在发送任务到 {target}...\n")
        self.root.update()

        try:
            taskcode = f"WIN-DIALOG-{datetime.now().strftime('%Y%m%d%H%M%S')}"
            result = self._mcp_call(
                "ata_send_request",
                {
                    "taskcode": taskcode,
                    "from_agent": AGENT_ID,
                    "to_agent": target,
                    "kind": "request",
                    "payload": {
                        "message": f"@{target}#{self._get_agent_code(target)} {task_text}",
                        "text": task_text,
                    },
                    "priority": "normal",
                    "requires_response": True,
                },
            )

            if result.get("success"):
                request_id = result.get("request_id")
                self.task_results.insert(tk.END, "任务已发送！\n")
                self.task_results.insert(tk.END, f"TaskCode: {taskcode}\n")
                self.task_results.insert(tk.END, f"Request ID: {request_id}\n")
                self.task_results.insert(tk.END, f"状态: {result.get('status', 'pending')}\n")
                self.task_results.insert(
                    tk.END, "\n注意: 任务已进入审核队列，需要管理员审核后才会发送。\n"
                )
            else:
                self.task_results.insert(tk.END, f"发送失败: {result.get('error', '未知错误')}\n")
        except Exception as e:
            self.task_results.insert(tk.END, f"错误: {str(e)}\n")

    def _get_agent_code(self, agent_id: str) -> str:
        """获取Agent编号"""
        codes = {
            "ATA系统": "01",
            "结构设计师": "08",
            "CI完备": "03",
            "交易模块": "02",
            "Cursor-Auto": "11",
        }
        return codes.get(agent_id, "--")


def main():
    """主函数"""
    root = tk.Tk()
    app = WindowsDialogAgent(root)
    root.mainloop()


if __name__ == "__main__":
    main()
