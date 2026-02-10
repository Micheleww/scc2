
#!/usr/bin/env python3
"""
交易引擎API服务器
提供RESTful API接口，类似freqtrade webserver
"""

import json
import logging
from typing import Any, Dict, Optional

try:
    from flask import Flask, jsonify, request
except ImportError:
    Flask = None
    import logging
    logging.warning("Flask未安装，Web API功能不可用。请运行: pip install flask")

from src.quantsys.trading_engine.core.trading_bot import TradingBot
from src.quantsys.trading_engine.api.freqtrade_compat import FreqtradeAPICompat

logger = logging.getLogger(__name__)


class TradingAPIServer:
    """
    交易API服务器
    提供HTTP API接口
    """

    def __init__(self, trading_bot: TradingBot, config: Dict[str, Any] = None):
        """
        初始化API服务器

        Args:
            trading_bot: 交易机器人实例
            config: 配置字典
        """
        if Flask is None:
            raise ImportError("Flask未安装，无法启动Web API服务器。请运行: pip install flask")
        
        self.trading_bot = trading_bot
        self.config = config or {}
        self.host = self.config.get("host", "127.0.0.1")
        self.port = self.config.get("port", 8080)
        self.api_key = self.config.get("api_key", "")
        
        # 创建Flask应用
        self.app = Flask(__name__)
        
        # 设置Freqtrade兼容API
        self.freqtrade_compat = FreqtradeAPICompat(trading_bot)
        self.freqtrade_compat.setup_routes(self.app)
        
        # 设置原有路由（保持向后兼容）
        self._setup_routes()
        
        logger.info(f"API服务器初始化完成: {self.host}:{self.port}")

    def _setup_routes(self):
        """设置API路由"""
        
        # 只保留不与Freqtrade兼容层冲突的自定义路由
        @self.app.route("/api/v1/positions", methods=["GET"])
        def get_positions():
            """获取持仓"""
            if self.trading_bot.execution_manager:
                symbol = request.args.get("symbol")
                result = self.trading_bot.execution_manager.get_positions(symbol)
                return jsonify(result)
            return jsonify({"error": "执行管理器未配置"}), 400
        
        @self.app.route("/api/v1/process", methods=["POST"])
        def process():
            """处理交易对"""
            data = request.get_json()
            pair = data.get("pair")
            
            if not pair:
                return jsonify({"error": "缺少pair参数"}), 400
            
            try:
                result = self.trading_bot.process(pair)
                return jsonify(result)
            except Exception as e:
                return jsonify({"status": "error", "message": str(e)}), 500

    def run(self, debug: bool = False):
        """
        启动API服务器

        Args:
            debug: 是否开启调试模式
        """
        logger.info(f"启动API服务器: http://{self.host}:{self.port}")
        self.app.run(host=self.host, port=self.port, debug=debug)
