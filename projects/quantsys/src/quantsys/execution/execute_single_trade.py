#!/usr/bin/env python3
"""
执行单笔交易脚本
用于执行用户请求的具体交易
"""

import logging

from order_execution import OrderExecution
from risk_manager import RiskManager

# 配置日志
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def execute_eth_short_order():
    """
    执行ETH空单交易
    """
    logger.info("=== 执行ETH空单交易 ===")

    try:
        # 从密钥管理器获取交易所API凭证
        secret_manager = get_secret_manager()
        exchange_creds = secret_manager.get_exchange_credentials()

        # 1. 配置交易所API密钥
        exchange_config = {
            "exchange": "okx",
            "api_key": exchange_creds.get("api_key", ""),
            "secret_key": exchange_creds.get("api_secret", ""),
            "passphrase": secret_manager.get_secret("exchange_passphrase", ""),
        }

        if not exchange_config["api_key"] or not exchange_config["secret_key"]:
            logger.error("交易所API凭证缺失，无法执行交易")
            return False

        logger.info("从密钥管理器获取交易所API凭证")
    except Exception as e:
        logger.error(f"获取交易所API凭证失败: {e}")
        return False

    # 2. 配置风险参数
    risk_config = {
        "max_single_order_amount": 5.0,  # 单笔订单最大金额（USDT）
        "min_order_amount": 1.0,  # 最小订单金额（USDT）
        "max_slippage": 0.01,  # 最大滑点容忍度（1%）
    }

    # 3. 初始化订单执行和风险控制模块
    order_executor = OrderExecution(exchange_config)
    risk_manager = RiskManager(risk_config)

    # 4. 交易参数
    symbol = "ETH-USDT-SWAP"  # OKX永续合约交易对格式
    side = "sell"  # 空单
    order_type = "market"  # 市价单
    amount_usdt = 5.0  # 5 USDT
    leverage = 10  # 10倍杠杆

    try:
        # 5. 获取当前ETH价格（用于计算数量）
        # 调用OKX API获取当前价格

        import requests

        # OKX API获取当前价格
        def get_current_price(symbol):
            url = f"https://www.okx.com/api/v5/market/ticker?instId={symbol}"
            response = requests.get(url)
            if response.status_code == 200:
                data = response.json()
                if data.get("code") == "0":
                    return float(data["data"][0]["last"])
            logger.error(f"获取当前价格失败: {response.text}")
            return None

        # 获取当前ETH价格
        current_eth_price = get_current_price(symbol)
        if current_eth_price is None:
            logger.error("无法获取当前价格，无法执行交易")
            return False

        # 6. 计算交易数量
        # 合约交易中，数量通常是合约张数，这里简化处理
        # 使用USDT金额计算合约张数：张数 = 金额 * 杠杆 / 价格
        # ETH-USDT-SWAP的最小交易单位是0.01张
        amount = (amount_usdt * leverage) / current_eth_price

        # 确保数量是最小交易单位（0.01张）的倍数
        min_lot_size = 0.01
        amount = round(amount / min_lot_size) * min_lot_size

        # 7. 设置杠杆（OKX合约需要先设置杠杆）
        logger.info(f"设置 {symbol} 杠杆为 {leverage} 倍")

        # 调用API设置杠杆，需要为多空方向都设置
        for pos_side in ["long", "short"]:
            set_leverage_result = order_executor.set_leverage(symbol, leverage, pos_side)
            if set_leverage_result.get("code") != "0":
                logger.error(f"设置 {pos_side} 方向杠杆失败: {set_leverage_result.get('msg')}")
                return False

        # 8. 检查风险
        # 使用合理的总余额（例如100 USDT）进行风险检查
        total_balance = 100.0  # 假设总余额为100 USDT

        # 检查是否为合约交易
        is_contract = "-SWAP" in symbol or "-FUTURES" in symbol

        if not risk_manager.check_order_risk(
            symbol,
            side,
            amount,
            current_eth_price,
            balance=total_balance,
            current_position=0.0,
            total_position=0.0,
            is_contract=is_contract,
            contract_amount=amount_usdt,  # 传递合约交易参数
        ):
            logger.error("风险检查未通过，无法执行交易")
            return False

        # 9. 执行交易
        logger.info(f"执行 {amount_usdt} USDT 的 {symbol} 空单，10倍杠杆")
        logger.info(f"当前价格: {current_eth_price} USDT, 交易数量: {amount:.6f} 张")

        # 实际执行交易
        # 对于合约交易，需要添加额外参数
        params = {
            "tdMode": "cross",  # 全仓模式
            "posSide": "short",  # 空头
            "lever": str(leverage),  # 杠杆
        }

        result = order_executor.place_order(
            symbol=symbol, side=side, order_type=order_type, amount=amount, params=params
        )

        # 9. 处理交易结果
        if result.get("code") == "0":
            order_id = result["data"][0]["ordId"]
            logger.info(f"交易执行成功！订单ID: {order_id}")
            logger.info(f"交易详情: {result['data'][0]}")
            return True
        else:
            logger.error(f"交易执行失败: {result.get('msg')}")
            return False

    except Exception as e:
        logger.error(f"执行交易时发生错误: {e}")
        return False


if __name__ == "__main__":
    logger.info("启动单笔交易执行脚本")
    logger.info("注意：当前脚本使用模拟数据，实际交易需要配置API密钥并取消相应注释")

    execute_eth_short_order()

    logger.info("单笔交易执行脚本结束")
