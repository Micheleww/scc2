#!/usr/bin/env python3
"""
工具脚本集成模块
将系统中的工具脚本封装为FastAPI路由或后台任务
"""

import asyncio
import logging
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional, Any

from fastapi import APIRouter, HTTPException, BackgroundTasks, Query
from pydantic import BaseModel

logger = logging.getLogger(__name__)

# 创建API路由
tools_router = APIRouter(
    prefix="/api/tools",
    tags=["工具脚本"],
    responses={404: {"description": "Not found"}},
)

# 工具脚本配置
TOOLS_CONFIG: Dict[str, Dict[str, Any]] = {
    "cleanup_code": {
        "name": "代码清理",
        "description": "使用ruff和pre-commit进行代码格式化和检查",
        "script_path": "scripts/cleanup_code.py",
        "async_execution": True,
        "requires_sudo": False,
    },
    "verify_migration": {
        "name": "迁移验证",
        "description": "验证数据迁移的完整性和正确性",
        "script_path": "scripts/verify_migration.py",
        "async_execution": True,
        "requires_sudo": False,
    },
    "analyze_test_coverage": {
        "name": "测试覆盖率分析",
        "description": "分析测试覆盖率并生成报告",
        "script_path": "scripts/analyze_test_coverage.py",
        "async_execution": True,
        "requires_sudo": False,
    },
    "check_document_consistency": {
        "name": "文档一致性检查",
        "description": "检查文档之间的一致性",
        "script_path": "scripts/check_document_consistency.py",
        "async_execution": True,
        "requires_sudo": False,
    },
    "sync_documents_to_db": {
        "name": "文档同步到数据库",
        "description": "将文档内容同步到数据库",
        "script_path": "scripts/sync_documents_to_db.py",
        "async_execution": True,
        "requires_sudo": False,
    },
}

# 任务状态存储
task_status: Dict[str, Dict[str, Any]] = {}

class ToolExecutionRequest(BaseModel):
    """工具执行请求模型"""
    tool_name: str
    parameters: Optional[Dict[str, Any]] = None

class ToolExecutionResponse(BaseModel):
    """工具执行响应模型"""
    task_id: str
    tool_name: str
    status: str
    message: str

async def run_tool_script(tool_config: Dict[str, Any], parameters: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """异步运行工具脚本"""
    script_path = Path(tool_config["script_path"])
    if not script_path.is_absolute():
        script_path = Path.cwd() / script_path
    
    if not script_path.exists():
        return {
            "success": False,
            "message": f"脚本文件不存在: {script_path}",
            "stdout": "",
            "stderr": "",
            "returncode": -1
        }
    
    logger.info(f"执行工具脚本: {script_path}")
    
    # 构建命令
    cmd = [sys.executable, str(script_path)]
    
    # 添加参数
    if parameters:
        for key, value in parameters.items():
            cmd.append(f"--{key}")
            if value is not None and value is not False:
                cmd.append(str(value))
    
    try:
        # 异步运行命令
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=Path.cwd(),
            text=True,
            encoding="utf-8",
            errors="replace"
        )
        
        # 等待命令完成
        stdout, stderr = await process.communicate()
        
        return {
            "success": process.returncode == 0,
            "message": "工具脚本执行完成" if process.returncode == 0 else f"工具脚本执行失败，返回码: {process.returncode}",
            "stdout": stdout,
            "stderr": stderr,
            "returncode": process.returncode
        }
    except Exception as e:
        return {
            "success": False,
            "message": f"执行工具脚本时发生错误: {str(e)}",
            "stdout": "",
            "stderr": str(e),
            "returncode": -1
        }

async def run_tool_in_background(tool_name: str, parameters: Optional[Dict[str, Any]] = None, task_id: str = None):
    """在后台运行工具脚本"""
    if tool_name not in TOOLS_CONFIG:
        task_status[task_id] = {
            "status": "failed",
            "message": f"工具不存在: {tool_name}",
            "result": None
        }
        return
    
    task_status[task_id] = {
        "status": "running",
        "message": "工具脚本正在执行",
        "result": None
    }
    
    tool_config = TOOLS_CONFIG[tool_name]
    result = await run_tool_script(tool_config, parameters)
    
    task_status[task_id] = {
        "status": "completed" if result["success"] else "failed",
        "message": result["message"],
        "result": result
    }

@tools_router.get("/list")
async def list_tools():
    """列出所有可用工具"""
    tools = []
    for tool_name, config in TOOLS_CONFIG.items():
        tools.append({
            "name": tool_name,
            "display_name": config["name"],
            "description": config["description"],
            "async_execution": config["async_execution"],
            "requires_sudo": config["requires_sudo"],
        })
    
    return {
        "tools": tools,
        "total": len(tools)
    }

@tools_router.get("/{tool_name}/info")
async def get_tool_info(tool_name: str):
    """获取工具详细信息"""
    if tool_name not in TOOLS_CONFIG:
        raise HTTPException(status_code=404, detail=f"工具 {tool_name} 不存在")
    
    config = TOOLS_CONFIG[tool_name]
    return {
        "name": tool_name,
        "display_name": config["name"],
        "description": config["description"],
        "async_execution": config["async_execution"],
        "requires_sudo": config["requires_sudo"],
        "script_path": str(config["script_path"])
    }

@tools_router.post("/execute")
async def execute_tool(request: ToolExecutionRequest, background_tasks: BackgroundTasks):
    """执行工具脚本"""
    tool_name = request.tool_name
    parameters = request.parameters
    
    if tool_name not in TOOLS_CONFIG:
        raise HTTPException(status_code=404, detail=f"工具 {tool_name} 不存在")
    
    tool_config = TOOLS_CONFIG[tool_name]
    
    # 生成任务ID
    import uuid
    task_id = str(uuid.uuid4())
    
    if tool_config["async_execution"]:
        # 异步执行
        background_tasks.add_task(run_tool_in_background, tool_name, parameters, task_id)
        return ToolExecutionResponse(
            task_id=task_id,
            tool_name=tool_name,
            status="queued",
            message="工具脚本已提交到后台执行"
        )
    else:
        # 同步执行
        result = await run_tool_script(tool_config, parameters)
        return {
            "task_id": task_id,
            "tool_name": tool_name,
            "status": "completed" if result["success"] else "failed",
            "message": result["message"],
            "result": result
        }

@tools_router.get("/task/{task_id}/status")
async def get_task_status(task_id: str):
    """获取任务状态"""
    if task_id not in task_status:
        raise HTTPException(status_code=404, detail=f"任务 {task_id} 不存在")
    
    return {
        "task_id": task_id,
        **task_status[task_id]
    }

@tools_router.get("/task/{task_id}/result")
async def get_task_result(task_id: str):
    """获取任务结果"""
    if task_id not in task_status:
        raise HTTPException(status_code=404, detail=f"任务 {task_id} 不存在")
    
    status = task_status[task_id]
    if status["status"] == "running":
        return {
            "task_id": task_id,
            "status": "running",
            "message": "工具脚本正在执行，结果尚未可用"
        }
    
    return {
        "task_id": task_id,
        **status
    }

def include_tools_routes(app):
    """将工具路由添加到FastAPI应用"""
    app.include_router(tools_router)
    logger.info("✅ 工具脚本集成成功")
    return app