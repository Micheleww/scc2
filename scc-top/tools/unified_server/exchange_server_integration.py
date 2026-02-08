"""
Exchange Server服务集成模块

将aiohttp Exchange Server服务转换为FastAPI并集成到统一服务器中
"""

import os
import sys
from pathlib import Path
from fastapi import FastAPI, Request, Response, Header
from fastapi.responses import StreamingResponse, JSONResponse
import asyncio
import json
from typing import Optional

# 添加Exchange Server路径
current_file = os.path.abspath(__file__)
unified_server_dir = os.path.dirname(current_file)
tools_dir = os.path.dirname(unified_server_dir)
repo_root = os.path.dirname(tools_dir)
exchange_server_dir = os.path.join(tools_dir, "exchange_server")

# 添加路径
if repo_root not in sys.path:
    sys.path.insert(0, repo_root)
if exchange_server_dir not in sys.path:
    sys.path.insert(0, exchange_server_dir)

# 导入Exchange Server
import importlib.util
spec = importlib.util.spec_from_file_location(
    "exchange_main",
    os.path.join(exchange_server_dir, "main.py")
)
exchange_main = importlib.util.module_from_spec(spec)
sys.modules["exchange_main"] = exchange_main
spec.loader.exec_module(exchange_main)
ExchangeServer = exchange_main.ExchangeServer
TOOLSET_VERSION = exchange_main.TOOLSET_VERSION

# 全局Exchange Server实例
_exchange_server = None


class AiohttpRequestAdapter:
    """将FastAPI Request适配为类似aiohttp Request的对象"""
    
    def __init__(self, fastapi_request: Request):
        self._request = fastapi_request
        self.method = fastapi_request.method
        self.path = fastapi_request.url.path
        self.headers = fastapi_request.headers
        self.remote = fastapi_request.client.host if fastapi_request.client else "unknown"
        self._json_data = None
    
    async def json(self):
        """获取JSON数据"""
        if self._json_data is None:
            self._json_data = await self._request.json()
        return self._json_data
    
    def get(self, key, default=None):
        """获取header值"""
        return self.headers.get(key, default)


async def convert_aiohttp_response_to_fastapi(aiohttp_response):
    """将aiohttp Response转换为FastAPI Response"""
    # 读取响应内容
    if hasattr(aiohttp_response, 'text'):
        # 如果是文本响应
        content = aiohttp_response.text
        if isinstance(content, str):
            body = content.encode('utf-8')
        else:
            body = content
    elif hasattr(aiohttp_response, 'body'):
        body = aiohttp_response.body
    else:
        body = b""
    
    # 获取状态码
    status_code = aiohttp_response.status if hasattr(aiohttp_response, 'status') else 200
    
    # 获取headers
    headers = dict(aiohttp_response.headers) if hasattr(aiohttp_response, 'headers') else {}
    
    # 获取content_type
    content_type = headers.get('Content-Type', 'application/json')
    
    return Response(
        content=body,
        status_code=status_code,
        headers=headers,
        media_type=content_type
    )


def create_exchange_server_app() -> FastAPI:
    """
    创建Exchange Server FastAPI应用
    
    将aiohttp应用转换为FastAPI应用
    """
    global _exchange_server
    
    # 创建Exchange Server实例
    auth_mode = os.getenv("EXCHANGE_AUTH_MODE", "none")
    _exchange_server = ExchangeServer(auth_mode=auth_mode)
    
    # 创建FastAPI应用
    app = FastAPI(title="Exchange Server", version="1.0.0")
    
    # 转换JSON-RPC端点
    @app.post("/mcp")
    async def jsonrpc_endpoint(
        request: Request,
        authorization: Optional[str] = Header(None, alias="Authorization"),
        x_trace_id: Optional[str] = Header(None, alias="X-Trace-ID"),
        x_request_nonce: Optional[str] = Header(None, alias="X-Request-Nonce"),
        x_request_ts: Optional[str] = Header(None, alias="X-Request-Ts"),
    ):
        """JSON-RPC端点"""
        try:
            # 创建适配的请求对象
            aiohttp_req = AiohttpRequestAdapter(request)
            
            # 调用Exchange Server的JSON-RPC处理
            aiohttp_response = await _exchange_server.handle_jsonrpc(aiohttp_req)
            
            # 转换为FastAPI响应
            return await convert_aiohttp_response_to_fastapi(aiohttp_response)
        except Exception as e:
            return JSONResponse(
                status_code=500,
                content={
                    "jsonrpc": "2.0",
                    "error": {
                        "code": -32603,
                        "message": f"Internal error: {str(e)}"
                    }
                }
            )
    
    # SSE端点
    @app.get("/sse")
    async def sse_endpoint(
        request: Request,
        authorization: Optional[str] = Header(None, alias="Authorization"),
        x_trace_id: Optional[str] = Header(None, alias="X-Trace-ID"),
    ):
        """Server-Sent Events端点"""
        try:
            # 创建适配的请求对象
            aiohttp_req = AiohttpRequestAdapter(request)
            
            # 调用Exchange Server的SSE处理
            aiohttp_response = await _exchange_server.handle_sse(aiohttp_req)
            
            # 检查是否是StreamResponse
            from aiohttp import web
            if isinstance(aiohttp_response, web.StreamResponse):
                # 创建一个流式响应生成器
                async def event_generator():
                    try:
                        # 从StreamResponse中读取数据
                        # 注意：这需要aiohttp的StreamResponse支持
                        # 由于架构差异，我们可能需要使用不同的方法
                        # 暂时返回一个占位，实际实现需要更深入的集成
                        yield f"data: {json.dumps({'message': 'SSE integration - streaming not fully implemented yet'})}\n\n"
                    except Exception as e:
                        yield f"data: {json.dumps({'error': str(e)})}\n\n"
                
                return StreamingResponse(
                    event_generator(),
                    media_type="text/event-stream",
                    headers={
                        "Cache-Control": "no-cache",
                        "Connection": "keep-alive",
                        "X-Accel-Buffering": "no",
                    }
                )
            else:
                # 普通响应
                return await convert_aiohttp_response_to_fastapi(aiohttp_response)
        except Exception as e:
            import traceback
            return JSONResponse(
                status_code=500,
                content={"error": f"SSE error: {str(e)}", "traceback": traceback.format_exc()}
            )
    
    # ChatGPT兼容的SSE端点
    @app.get("/mcp/messages")
    async def sse_messages_endpoint(
        request: Request,
        authorization: Optional[str] = Header(None, alias="Authorization"),
        x_trace_id: Optional[str] = Header(None, alias="X-Trace-ID"),
    ):
        """ChatGPT兼容的SSE端点"""
        # 与/sse端点相同
        return await sse_endpoint(request, authorization, x_trace_id)
    
    # 版本端点
    @app.get("/version")
    async def version_endpoint():
        """版本信息端点"""
        if _exchange_server:
            return {
                "git_sha": "unknown",
                "build_time": "unknown",
                "toolset_version": TOOLSET_VERSION,
                "RULESET_SHA256": _exchange_server.RULESET_SHA256,
            }
        return {"error": "Exchange Server not initialized"}
    
    # 指标端点
    @app.get("/metrics")
    async def metrics_endpoint(request: Request):
        """Prometheus格式的指标端点"""
        try:
            aiohttp_req = AiohttpRequestAdapter(request)
            aiohttp_response = await _exchange_server.handle_metrics(aiohttp_req)
            return await convert_aiohttp_response_to_fastapi(aiohttp_response)
        except Exception as e:
            return Response(
                status_code=500,
                content=f"Metrics error: {str(e)}",
                media_type="text/plain"
            )
    
    # 状态端点
    @app.get("/status")
    async def status_endpoint(request: Request):
        """状态端点"""
        try:
            aiohttp_req = AiohttpRequestAdapter(request)
            aiohttp_response = await _exchange_server.handle_status(aiohttp_req)
            return await convert_aiohttp_response_to_fastapi(aiohttp_response)
        except Exception as e:
            return JSONResponse(
                status_code=500,
                content={"error": f"Status error: {str(e)}"}
            )
    
    return app
