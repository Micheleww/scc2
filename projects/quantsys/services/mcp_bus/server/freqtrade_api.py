#!/usr/bin/env python3
"""
Freqtrade API 兼容层，实现前端期望的 API 端点
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Dict, Any

router = APIRouter(prefix="/api/v1", tags=["freqtrade_api"])


class AuthPayload(BaseModel):
    """登录请求体"""
    username: str
    password: str


class AuthResponse(BaseModel):
    """登录响应体"""
    access_token: str
    refresh_token: str


# 模拟的访问令牌和刷新令牌
MOCK_ACCESS_TOKEN = "mock_access_token_123"
MOCK_REFRESH_TOKEN = "mock_refresh_token_456"


@router.post("/token/login", response_model=AuthResponse)
async def login():
    """
    Freqtrade 兼容的登录端点
    返回模拟的访问令牌和刷新令牌
    """
    # 模拟登录成功，返回固定的令牌
    return AuthResponse(
        access_token=MOCK_ACCESS_TOKEN,
        refresh_token=MOCK_REFRESH_TOKEN
    )


@router.post("/token/refresh", response_model=AuthResponse)
async def refresh_token():
    """
    Freqtrade 兼容的刷新令牌端点
    返回新的模拟访问令牌
    """
    # 模拟刷新令牌成功，返回固定的令牌
    return AuthResponse(
        access_token=MOCK_ACCESS_TOKEN,
        refresh_token=MOCK_REFRESH_TOKEN
    )


@router.get("/ping")
async def ping():
    """
    Freqtrade 兼容的 ping 端点
    用于检查 API 服务是否正常运行
    """
    return {"status": "pong"}


@router.get("/status")
async def get_status():
    """
    Freqtrade 兼容的状态端点
    返回模拟的服务状态
    """
    return {
        "status": "running",
        "version": "1.0.0",
        "strategy_version": "1.0.0",
        "api_version": 1.0,
        "dry_run": True,
        "state": "running",
        "runmode": "webserver",
        "exchange": "binance",
        "max_open_trades": 10,
        "stake_currency": "USDT",
        "available_balance": 1000.0,
        "total_stake_amount": 1000.0,
        "unfilledtimeout": {
            "buy": 10,
            "sell": 30,
            "unit": "minutes"
        },
        "order_types": {
            "buy": "limit",
            "sell": "limit",
            "stoploss": "market",
            "stoploss_on_exchange": False
        },
        "pair_whitelist": ["BTC/USDT", "ETH/USDT", "BNB/USDT"],
        "pair_blacklist": [],
        "timeframe": "1h",
        "stake_amount": "unlimited",
        "tradable_balance": 1000.0,
        "min_stake_amount": 10.0,
        "max_stake_amount": 100.0,
        "stake_amount_step": 10.0
    }


@router.get("/strategies")
async def get_strategies():
    """
    Freqtrade 兼容的策略列表端点
    返回模拟的策略列表
    """
    return {"strategies": ["Strategy1", "Strategy2", "Strategy3"]}


@router.get("/strategy/{strategy_name}")
async def get_strategy(strategy_name: str):
    """
    Freqtrade 兼容的策略详情端点
    返回模拟的策略详情
    """
    return {
        "strategy": strategy_name,
        "code": f"# {strategy_name} 策略代码\nclass {strategy_name}(IStrategy):\n    pass",
        "timeframe": "1h"
    }


@router.get("/balance")
async def get_balance():
    """
    Freqtrade 兼容的余额端点
    返回模拟的余额信息
    """
    return {
        "USDT": {
            "total": 1000.0,
            "used": 0.0,
            "free": 1000.0
        }
    }


@router.get("/profit")
async def get_profit():
    """
    Freqtrade 兼容的利润端点
    返回模拟的利润信息
    """
    return {
        "profit_total": 0.0,
        "profit_total_abs": 0.0,
        "profit_close": 0.0,
        "profit_open": 0.0,
        "profit_manual": 0.0,
        "total_trades": 0,
        "open_trades": 0,
        "winrate": 0.0,
        "profit_factor": 0.0,
        "max_drawdown": 0.0,
        "cagr": 0.0
    }


@router.get("/trades")
async def get_trades():
    """
    Freqtrade 兼容的交易列表端点
    返回模拟的交易列表
    """
    return {
        "trades": [],
        "total_trades": 0
    }


@router.get("/status")
async def get_status():
    """
    Freqtrade 兼容的状态端点
    返回模拟的服务状态
    """
    return {
        "status": "running",
        "version": "1.0.0",
        "strategy_version": "1.0.0",
        "api_version": 1.0,
        "dry_run": True,
        "state": "running",
        "runmode": "webserver",
        "exchange": "binance",
        "max_open_trades": 10,
        "stake_currency": "USDT",
        "available_balance": 1000.0,
        "total_stake_amount": 1000.0,
        "unfilledtimeout": {
            "buy": 10,
            "sell": 30,
            "unit": "minutes"
        },
        "order_types": {
            "buy": "limit",
            "sell": "limit",
            "stoploss": "market",
            "stoploss_on_exchange": False
        },
        "pair_whitelist": ["BTC/USDT", "ETH/USDT", "BNB/USDT"],
        "pair_blacklist": [],
        "timeframe": "1h",
        "stake_amount": "unlimited",
        "tradable_balance": 1000.0,
        "min_stake_amount": 10.0,
        "max_stake_amount": 100.0,
        "stake_amount_step": 10.0
    }


@router.get("/whitelist")
async def get_whitelist():
    """
    Freqtrade 兼容的白名单端点
    返回模拟的交易对白名单
    """
    return {
        "whitelist": ["BTC/USDT", "ETH/USDT", "BNB/USDT"],
        "method": "StaticPairList"
    }


@router.get("/blacklist")
async def get_blacklist():
    """
    Freqtrade 兼容的黑名单端点
    返回模拟的交易对黑名单
    """
    return {"blacklist": []}


@router.get("/forcesell")
async def get_forcesell():
    """
    Freqtrade 兼容的强制卖出端点
    返回模拟的强制卖出信息
    """
    return {"result": "ok"}


@router.get("/forcebuy")
async def get_forcebuy():
    """
    Freqtrade 兼容的强制买入端点
    返回模拟的强制买入信息
    """
    return {"result": "ok"}


@router.get("/reload_config")
async def get_reload_config():
    """
    Freqtrade 兼容的重载配置端点
    返回模拟的重载配置信息
    """
    return {"status": "ok"}


@router.get("/stop")
async def get_stop():
    """
    Freqtrade 兼容的停止端点
    返回模拟的停止信息
    """
    return {"status": "ok"}


@router.get("/start")
async def get_start():
    """
    Freqtrade 兼容的启动端点
    返回模拟的启动信息
    """
    return {"status": "ok"}


@router.get("/stopbuy")
async def get_stopbuy():
    """
    Freqtrade 兼容的停止买入端点
    返回模拟的停止买入信息
    """
    return {"status": "ok"}


@router.get("/plot_config")
async def get_plot_config():
    """
    Freqtrade 兼容的图表配置端点
    返回模拟的图表配置信息
    """
    return {
        "main_plot": {},
        "subplots": {}
    }


@router.get("/freqaimodels")
async def get_freqaimodels():
    """
    Freqtrade 兼容的 FreqAI 模型列表端点
    返回模拟的 FreqAI 模型列表
    """
    return {"freqaimodels": []}


@router.get("/hyperopt-loss")
async def get_hyperopt_loss():
    """
    Freqtrade 兼容的超参数优化损失函数端点
    返回模拟的超参数优化损失函数列表
    """
    return {"loss_functions": []}


@router.get("/exchanges")
async def get_exchanges():
    """
    Freqtrade 兼容的交易所列表端点
    返回模拟的交易所列表
    """
    return {"exchanges": ["binance", "coinbasepro", "kraken"]}


@router.get("/performance")
async def get_performance():
    """
    Freqtrade 兼容的性能端点
    返回模拟的性能信息
    """
    return []


@router.get("/entries")
async def get_entries():
    """
    Freqtrade 兼容的入场统计端点
    返回模拟的入场统计信息
    """
    return []


@router.get("/exits")
async def get_exits():
    """
    Freqtrade 兼容的出场统计端点
    返回模拟的出场统计信息
    """
    return []


@router.get("/mix_tags")
async def get_mix_tags():
    """
    Freqtrade 兼容的混合标签统计端点
    返回模拟的混合标签统计信息
    """
    return []


@router.get("/balance")
async def get_balance():
    """
    Freqtrade 兼容的余额端点
    返回模拟的余额信息
    """
    return {
        "USDT": {
            "total": 1000.0,
            "used": 0.0,
            "free": 1000.0
        }
    }


@router.get("/sysinfo")
async def get_sysinfo():
    """
    Freqtrade 兼容的系统信息端点
    返回模拟的系统信息
    """
    return {
        "cpu_pct": [0.0],
        "ram_pct": 0.0
    }


@router.get("/backtest")
async def get_backtest():
    """
    Freqtrade 兼容的回测端点
    返回模拟的回测状态
    """
    return {
        "status": "not_running",
        "running": False,
        "status_msg": "",
        "step": "none",
        "progress": 0,
        "trade_count": 0,
        "backtest_result": None
    }


@router.get("/backtest/history")
async def get_backtest_history():
    """
    Freqtrade 兼容的回测历史端点
    返回模拟的回测历史记录
    """
    return []


@router.get("/backtest/history/result")
async def get_backtest_history_result():
    """
    Freqtrade 兼容的回测历史结果端点
    返回模拟的回测历史结果
    """
    return {
        "status": "not_running",
        "running": False,
        "status_msg": "",
        "step": "none",
        "progress": 0,
        "trade_count": 0,
        "backtest_result": None
    }


@router.get("/locks")
async def get_locks():
    """
    Freqtrade 兼容的锁端点
    返回模拟的锁信息
    """
    return {
        "locks": []
    }


@router.get("/logs")
async def get_logs():
    """
    Freqtrade 兼容的日志端点
    返回模拟的日志信息
    """
    return {
        "logs": [],
        "log_count": 0
    }


@router.get("/available_pairs")
async def get_available_pairs():
    """
    Freqtrade 兼容的可用交易对端点
    返回模拟的可用交易对信息
    """
    return {
        "pairs": ["BTC/USDT", "ETH/USDT", "BNB/USDT"],
        "pair_interval": []
    }


@router.get("/markets")
async def get_markets():
    """
    Freqtrade 兼容的市场端点
    返回模拟的市场信息
    """
    return {}


@router.get("/profit_all")
async def get_profit_all():
    """
    Freqtrade 兼容的所有利润端点
    返回模拟的所有利润信息
    """
    return {
        "all": {
            "profit_total": 0.0,
            "profit_total_abs": 0.0,
            "profit_close": 0.0,
            "profit_open": 0.0,
            "profit_manual": 0.0,
            "total_trades": 0,
            "open_trades": 0,
            "winrate": 0.0,
            "profit_factor": 0.0,
            "max_drawdown": 0.0,
            "cagr": 0.0
        }
    }


@router.get("/pair_candles")
async def get_pair_candles():
    """
    Freqtrade 兼容的交易对蜡烛图端点
    返回模拟的交易对蜡烛图信息
    """
    return {
        "candles": [],
        "columns": []
    }


@router.get("/pair_history")
async def get_pair_history():
    """
    Freqtrade 兼容的交易对历史端点
    返回模拟的交易对历史信息
    """
    return {
        "columns": [],
        "data": []
    }


@router.get("/show_config")
async def get_show_config():
    """
    Freqtrade 兼容的显示配置端点
    返回模拟的配置信息
    """
    return {
        "version": "1.0.0",
        "strategy_version": "1.0.0",
        "api_version": 1.0,
        "dry_run": True,
        "state": "running",
        "runmode": "webserver",
        "exchange": "binance",
        "max_open_trades": 10,
        "stake_currency": "USDT",
        "available_balance": 1000.0,
        "total_stake_amount": 1000.0,
        "unfilledtimeout": {
            "buy": 10,
            "sell": 30,
            "unit": "minutes"
        },
        "order_types": {
            "buy": "limit",
            "sell": "limit",
            "stoploss": "market",
            "stoploss_on_exchange": False
        },
        "pair_whitelist": ["BTC/USDT", "ETH/USDT", "BNB/USDT"],
        "pair_blacklist": [],
        "timeframe": "1h",
        "stake_amount": "unlimited",
        "tradable_balance": 1000.0,
        "min_stake_amount": 10.0,
        "max_stake_amount": 100.0,
        "stake_amount_step": 10.0
    }


@router.get("/download_data")
async def get_download_data():
    """
    Freqtrade 兼容的数据下载端点
    返回模拟的数据下载信息
    """
    return {
        "job_id": "mock_job_id",
        "status": "started"
    }


@router.get("/background/{job_id}")
async def get_background_job(job_id: str):
    """
    Freqtrade 兼容的后台任务端点
    返回模拟的后台任务状态
    """
    return {
        "status": "completed",
        "progress": 100,
        "result": None
    }


@router.get("/pairlists/available")
async def get_pairlists_available():
    """
    Freqtrade 兼容的交易对列表可用端点
    返回模拟的交易对列表可用信息
    """
    return {
        "pairlists": []
    }


@router.get("/pairlists/evaluate")
async def get_pairlists_evaluate():
    """
    Freqtrade 兼容的交易对列表评估端点
    返回模拟的交易对列表评估信息
    """
    return {
        "job_id": "mock_job_id",
        "status": "started"
    }


@router.get("/pairlists/evaluate/{job_id}")
async def get_pairlists_evaluate_job(job_id: str):
    """
    Freqtrade 兼容的交易对列表评估任务端点
    返回模拟的交易对列表评估任务结果
    """
    return {
        "result": [],
        "status": "completed",
        "progress": 100
    }


@router.post("/token/login")
async def post_token_login():
    """
    Freqtrade 兼容的登录端点（POST 方法）
    返回模拟的访问令牌和刷新令牌
    """
    return AuthResponse(
        access_token=MOCK_ACCESS_TOKEN,
        refresh_token=MOCK_REFRESH_TOKEN
    )


@router.post("/token/refresh")
async def post_token_refresh():
    """
    Freqtrade 兼容的刷新令牌端点（POST 方法）
    返回新的模拟访问令牌
    """
    return AuthResponse(
        access_token=MOCK_ACCESS_TOKEN,
        refresh_token=MOCK_REFRESH_TOKEN
    )


@router.post("/blacklist")
async def post_blacklist():
    """
    Freqtrade 兼容的黑名单端点（POST 方法）
    返回模拟的黑名单更新信息
    """
    return {
        "blacklist": [],
        "errors": {}
    }


@router.post("/forcebuy")
async def post_forcebuy():
    """
    Freqtrade 兼容的强制买入端点（POST 方法）
    返回模拟的强制买入结果
    """
    return {
        "status": "ok"
    }


@router.post("/forcesell")
async def post_forcesell():
    """
    Freqtrade 兼容的强制卖出端点（POST 方法）
    返回模拟的强制卖出结果
    """
    return {
        "status": "ok"
    }


@router.post("/reload_config")
async def post_reload_config():
    """
    Freqtrade 兼容的重载配置端点（POST 方法）
    返回模拟的重载配置结果
    """
    return {
        "status": "ok"
    }


@router.post("/stop")
async def post_stop():
    """
    Freqtrade 兼容的停止端点（POST 方法）
    返回模拟的停止结果
    """
    return {
        "status": "ok"
    }


@router.post("/start")
async def post_start():
    """
    Freqtrade 兼容的启动端点（POST 方法）
    返回模拟的启动结果
    """
    return {
        "status": "ok"
    }


@router.post("/stopbuy")
async def post_stopbuy():
    """
    Freqtrade 兼容的停止买入端点（POST 方法）
    返回模拟的停止买入结果
    """
    return {
        "status": "ok"
    }


@router.post("/backtest")
async def post_backtest():
    """
    Freqtrade 兼容的回测端点（POST 方法）
    返回模拟的回测启动结果
    """
    return {
        "status": "running",
        "running": True,
        "status_msg": "Backtest started",
        "step": "startup",
        "progress": 0,
        "trade_count": 0,
        "backtest_result": None
    }


@router.post("/download_data")
async def post_download_data():
    """
    Freqtrade 兼容的数据下载端点（POST 方法）
    返回模拟的数据下载启动结果
    """
    return {
        "job_id": "mock_job_id",
        "status": "started"
    }


@router.post("/pairlists/evaluate")
async def post_pairlists_evaluate():
    """
    Freqtrade 兼容的交易对列表评估端点（POST 方法）
    返回模拟的交易对列表评估启动结果
    """
    return {
        "job_id": "mock_job_id",
        "status": "started"
    }


@router.put("/trades/{trade_id}")
async def put_trades(trade_id: str):
    """
    Freqtrade 兼容的交易更新端点（PUT 方法）
    返回模拟的交易更新结果
    """
    return {
        "result": "ok"
    }


@router.delete("/trades/{trade_id}")
async def delete_trades(trade_id: str):
    """
    Freqtrade 兼容的交易删除端点（DELETE 方法）
    返回模拟的交易删除结果
    """
    return {
        "result": "ok",
        "result_msg": "Trade deleted"
    }


@router.delete("/locks/{lock_id}")
async def delete_locks(lock_id: str):
    """
    Freqtrade 兼容的锁删除端点（DELETE 方法）
    返回模拟的锁删除结果
    """
    return {
        "locks": []
    }


@router.delete("/backtest")
async def delete_backtest():
    """
    Freqtrade 兼容的回测重置端点（DELETE 方法）
    返回模拟的回测重置结果
    """
    return {
        "status": "not_running",
        "running": False,
        "status_msg": "Backtest reset",
        "step": "none",
        "progress": 0,
        "trade_count": 0,
        "backtest_result": None
    }


@router.delete("/backtest/history/{filename}")
async def delete_backtest_history(filename: str):
    """
    Freqtrade 兼容的回测历史删除端点（DELETE 方法）
    返回模拟的回测历史删除结果
    """
    return []


@router.patch("/backtest/history/{filename}")
async def patch_backtest_history(filename: str):
    """
    Freqtrade 兼容的回测历史更新端点（PATCH 方法）
    返回模拟的回测历史更新结果
    """
    return []
