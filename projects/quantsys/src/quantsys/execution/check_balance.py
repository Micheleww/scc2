#!/usr/bin/env python3
"""
查询OKX账户余额
"""

import base64
import hashlib
import hmac
import json
import logging
from datetime import datetime

import requests

# 配置日志
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class OKXBalanceChecker:
    """
    OKX账户余额查询类
    """

    def __init__(self, api_key, secret_key, passphrase):
        """
        初始化

        Args:
            api_key: API密钥
            secret_key: 密钥
            passphrase: 密码
        """
        self.api_key = api_key
        self.secret_key = secret_key
        self.passphrase = passphrase
        self.base_url = "https://www.okx.com"

    def _generate_signature(self, method, endpoint, body):
        """
        生成签名

        Args:
            method: HTTP方法
            endpoint: API端点
            body: 请求体

        Returns:
            headers: 请求头
        """
        # 获取当前时间戳
        timestamp = str(datetime.utcnow().isoformat()[:-3]) + "Z"

        # 构造签名字符串
        message = timestamp + method.upper() + endpoint + json.dumps(body)

        # 生成签名
        signature = base64.b64encode(
            hmac.new(
                self.secret_key.encode("utf-8"), message.encode("utf-8"), hashlib.sha256
            ).digest()
        ).decode("utf-8")

        # 构造请求头
        headers = {
            "OK-ACCESS-KEY": self.api_key,
            "OK-ACCESS-SIGN": signature,
            "OK-ACCESS-TIMESTAMP": timestamp,
            "OK-ACCESS-PASSPHRASE": self.passphrase,
            "Content-Type": "application/json",
        }

        return headers

    def get_balance(self):
        """
        查询账户余额

        Returns:
            balance_data: 余额数据
        """
        endpoint = "/api/v5/account/balance"
        method = "GET"
        body = {}

        headers = self._generate_signature(method, endpoint, body)

        try:
            response = requests.get(f"{self.base_url}{endpoint}", headers=headers)
            result = response.json()

            if result.get("code") == "0":
                return result["data"][0]
            else:
                logger.error(f"查询余额失败: {result.get('msg')}")
                return None
        except Exception as e:
            logger.error(f"查询余额时出错: {e}")
            return None

    def get_position(self):
        """
        查询持仓信息

        Returns:
            position_data: 持仓数据
        """
        endpoint = "/api/v5/account/positions"
        method = "GET"
        body = {}

        headers = self._generate_signature(method, endpoint, body)

        try:
            response = requests.get(f"{self.base_url}{endpoint}", headers=headers)
            result = response.json()

            if result.get("code") == "0":
                return result["data"]
            else:
                logger.error(f"查询持仓失败: {result.get('msg')}")
                return None
        except Exception as e:
            logger.error(f"查询持仓时出错: {e}")
            return None


def main():
    """
    主函数
    """
    logger.info("=== 查询OKX账户余额 ===")

    try:
        # 从密钥管理器获取交易所API凭证
        secret_manager = get_secret_manager()
        exchange_creds = secret_manager.get_exchange_credentials()

        # 配置API密钥
        api_key = exchange_creds.get("api_key", "")
        secret_key = exchange_creds.get("api_secret", "")
        passphrase = secret_manager.get_secret("exchange_passphrase", "")

        if not api_key or not secret_key:
            logger.error("交易所API凭证缺失，无法查询余额")
            return False

        logger.info("从密钥管理器获取交易所API凭证")
    except Exception as e:
        logger.error(f"获取交易所API凭证失败: {e}")
        return False

    # 创建余额查询实例
    balance_checker = OKXBalanceChecker(api_key, secret_key, passphrase)

    # 查询余额
    logger.info("查询账户余额...")
    balance = balance_checker.get_balance()

    if balance:
        logger.info("=== 账户余额信息 ===")
        logger.info(f"总权益: {balance.get('totalEq', '0')} USDT")
        logger.info(f"可用余额: {balance.get('availEq', '0')} USDT")
        logger.info(f"冻结余额: {balance.get('frozenEq', '0')} USDT")

        # 打印具体资产
        logger.info("\n=== 具体资产信息 ===")
        for coin in balance.get("details", []):
            logger.info(f"资产: {coin.get('ccy', '')}")
            logger.info(f"  可用: {coin.get('availBal', '0')} {coin.get('ccy', '')}")
            logger.info(f"  冻结: {coin.get('frozenBal', '0')} {coin.get('ccy', '')}")
            logger.info(f"  权益: {coin.get('eq', '0')} {coin.get('ccy', '')}")

    # 查询持仓
    logger.info("\n查询持仓信息...")
    position = balance_checker.get_position()

    if position:
        logger.info("=== 持仓信息 ===")
        if not position:
            logger.info("当前无持仓")
        else:
            for pos in position:
                logger.info(f"交易对: {pos.get('instId', '')}")
                logger.info(
                    f"  持仓方向: {'多头' if pos.get('posSide') == 'long' else '空头' if pos.get('posSide') == 'short' else pos.get('posSide')}"
                )
                logger.info(f"  持仓数量: {pos.get('pos', '0')}")
                logger.info(f"  可用数量: {pos.get('availPos', '0')}")
                logger.info(f"  持仓价值: {pos.get('notionalUsd', '0')} USDT")

    logger.info("\n=== 查询完成 ===")


if __name__ == "__main__":
    main()
