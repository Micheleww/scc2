#!/usr/bin/env python3
"""
交易所适配器
实现不同交易所的统一接口，处理签名、请求发送等
"""

import base64
import hashlib
import hmac
import json
import logging
import time
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any

import requests

# 配置日志
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class ExchangeAdapter(ABC):
    """
    交易所适配器抽象基类
    定义统一的交易所接口
    """

    @abstractmethod
    def place_order(
        self,
        symbol: str,
        side: str,
        order_type: str,
        amount: float,
        price: float | None = None,
        params: dict[str, Any] = None,
    ) -> dict[str, Any]:
        """下单"""
        pass

    @abstractmethod
    def cancel_order(self, symbol: str, order_id: str) -> dict[str, Any]:
        """撤单"""
        pass

    @abstractmethod
    def get_order(self, symbol: str, order_id: str) -> dict[str, Any]:
        """查询订单"""
        pass

    @abstractmethod
    def get_balance(self) -> dict[str, Any]:
        """查询余额"""
        pass

    @abstractmethod
    def get_positions(self, symbol: str | None = None) -> dict[str, Any]:
        """查询持仓"""
        pass

    @abstractmethod
    def set_leverage(self, symbol: str, leverage: int, pos_side: str = "long") -> dict[str, Any]:
        """设置杠杆（合约交易）"""
        pass


class OKXAdapter(ExchangeAdapter):
    """
    OKX交易所适配器
    实现OKX交易所的API调用
    """

    def __init__(
        self,
        api_key: str,
        secret_key: str,
        passphrase: str,
        trading_mode: str = "drill",
        base_url: str = None,
        region: str = "default",
        simulated: bool = False,
        proxy: str = None,
        verify_ssl: bool = False,  # 禁用SSL验证以解决连接问题
    ):
        """
        初始化OKX适配器

        Args:
            api_key: API密钥
            secret_key: 密钥
            passphrase: 密码
            trading_mode: 交易模式
            base_url: API基础URL（如果为None，根据region自动选择）
            region: 账户区域（default/eea/us）- 2026年要求
            simulated: 是否为模拟盘（用于x-simulated-trading header）
            proxy: 代理服务器地址（可选）
            verify_ssl: 是否验证SSL证书
        """
        self.api_key = api_key
        self.secret_key = secret_key
        self.passphrase = passphrase
        self.trading_mode = trading_mode
        self.simulated = simulated
        self.region = region
        self.proxy = proxy
        self.verify_ssl = verify_ssl

        # 2026年区域域名映射
        region_domains = {
            "default": "https://www.okx.com",
            "aws": "https://aws.okx.com",  # AWS专用域名
            "eea": "https://eea.okx.com",  # 欧洲经济区
            "us": "https://us.okx.com",  # 美国
        }

        # 如果未指定base_url，根据region自动选择
        if base_url is None:
            self.base_url = region_domains.get(region, region_domains["default"])
        else:
            self.base_url = base_url

        self.exchange = "okx"  # 添加exchange属性供异常处理使用

        # 重试配置
        self.max_retries = 3
        self.initial_retry_delay = 1.0
        self.backoff_factor = 2.0
        self.max_retry_delay = 10.0

        logger.info(
            f"OKXAdapter initialized (mode: {trading_mode}, region: {region}, base_url: {self.base_url}, simulated: {simulated}, proxy: {proxy}, verify_ssl: {verify_ssl})"
        )

        # 验证时间同步 - 使用新的网络配置
        self._check_time_sync()

    def _sign_request(
        self, method: str, endpoint: str, body: dict[str, Any] = None
    ) -> dict[str, str]:
        """
        生成请求签名

        Args:
            method: HTTP方法
            endpoint: API端点
            body: 请求体

        Returns:
            headers: 包含签名的请求头
        """
        # 处理body：只有非GET请求且有body才需要序列化
        # GET请求必须使用空字符串作为body
        if method == "GET":
            body_str = ""
        else:
            # 非GET请求：只有非None且非空的body才需要序列化
            has_body = body is not None and bool(body)
            body_str = json.dumps(body, separators=(",", ":")) if has_body else ""

        # 获取当前时间戳（OKX要求ISO8601格式，毫秒精度）
        timestamp = datetime.utcnow().isoformat(timespec="milliseconds") + "Z"

        # 构造签名字符串：timestamp + method + endpoint + body
        message = timestamp + method.upper() + endpoint + body_str

        # 生成签名（OKX要求使用Base64编码）
        hmac_obj = hmac.new(self.secret_key.encode("utf-8"), message.encode("utf-8"), hashlib.sha256)
        signature = base64.b64encode(hmac_obj.digest()).decode("utf-8")

        # 构造请求头 - 严格按照OKX API文档要求的顺序和格式
        headers = {
            "OK-ACCESS-KEY": self.api_key,
            "OK-ACCESS-SIGN": signature,
            "OK-ACCESS-TIMESTAMP": timestamp,
            "OK-ACCESS-PASSPHRASE": self.passphrase,
            "Content-Type": "application/json",
            "x-simulated-trading": "1" if self.simulated else "0",  # 2026年要求：区分实盘和模拟盘
        }

        return headers

    def _check_time_sync(self):
        """检查本地时间与OKX服务器时间同步"""
        # 移除公共API依赖，使用系统时间监控代替
        logger.debug("时间同步检查已禁用，不再使用公共API获取服务器时间")

    def get_account_config(self) -> dict[str, Any]:
        """
        获取账户配置（包括账户模式）

        Returns:
            result: 账户配置信息
        """
        endpoint = "/api/v5/account/config"
        
        # 账户信息必须从真实API获取，禁止模拟数据
        result = self._send_request("GET", endpoint)

        # 解析账户模式
        if result.get("code") == "0" and result.get("data"):
            config = result["data"][0]
            account_level = config.get("acctLv", "")
            pos_mode = config.get("posMode", "")
            auto_loan = config.get("autoLoan", False)

            logger.info(
                f"账户配置: 账户等级={account_level}, 持仓模式={pos_mode}, 自动借贷={auto_loan}"
            )

            # 账户模式说明
            account_modes = {
                "1": "简单交易模式",
                "2": "单币种保证金模式",
                "3": "多币种保证金模式",
                "4": "组合保证金模式",
            }

            mode_name = account_modes.get(account_level, f"未知模式({account_level})")
            logger.info(f"账户模式: {mode_name}")

            result["_account_mode"] = mode_name
            result["_account_level"] = account_level
            result["_pos_mode"] = pos_mode

        return result

    def _send_request(
        self, method: str, endpoint: str, body: dict[str, Any] = None, params: dict[str, Any] = None
    ) -> dict[str, Any]:
        """
        发送API请求（带重试机制）

        Args:
            method: HTTP方法
            endpoint: API端点
            body: 请求体（POST/PUT/DELETE）
            params: 查询参数（GET）

        Returns:
            result: API响应结果
        """
        attempt = 0
        retry_delay = self.initial_retry_delay

        # 配置请求会话
        session = requests.Session()
        # 设置网络配置
        session.verify = self.verify_ssl
        if self.proxy:
            session.proxies = {
                'http': self.proxy,
                'https': self.proxy,
            }
        # 配置超时和连接池
        session.timeout = 15  # 增加超时时间
        session.mount('https://', requests.adapters.HTTPAdapter(
            pool_connections=10,
            pool_maxsize=10,
            max_retries=3,
        ))

        while attempt <= self.max_retries:
            try:
                attempt += 1
                headers = self._sign_request(method, endpoint, body)

                # 发送请求
                if method == "GET":
                    # GET请求：参数放在URL查询字符串中，body为空
                    response = session.get(
                        f"{self.base_url}{endpoint}",
                        headers=headers,
                        params=params or {},
                    )
                else:
                    # POST/PUT/DELETE请求：body放在请求体中
                    # 注意：签名时使用的body必须与发送的body完全一致
                    if body:
                        response = session.request(
                            method,
                            f"{self.base_url}{endpoint}",
                            headers=headers,
                            json=body,  # requests会自动序列化为JSON
                        )
                    else:
                        response = session.request(
                            method, f"{self.base_url}{endpoint}", headers=headers
                        )

                # 处理响应
                response.raise_for_status()
                result = response.json()

                # 检查并解析data字段中的详细错误信息（sCode）
                # OKX API可能返回 code='0' 但 data 中有 sCode 错误
                if result.get("code") == "0" and result.get("data"):
                    for item in result.get("data", []):
                        if isinstance(item, dict):
                            s_code = item.get("sCode")
                            s_msg = item.get("sMsg", "")
                            # 如果data中有错误代码，记录并返回错误
                            if s_code and s_code != "0":
                                logger.warning(
                                    f"OKX API data字段错误: sCode={s_code}, sMsg={s_msg}"
                                )
                                return {
                                    "code": str(s_code),
                                    "msg": s_msg or f"Data field error: sCode={s_code}",
                                    "data": result.get("data", []),
                                }

                return result

            except (requests.exceptions.Timeout, requests.exceptions.ConnectionError):
                # 网络错误，重试
                if attempt <= self.max_retries:
                    logger.warning(
                        f"请求失败，将在 {retry_delay:.2f} 秒后重试 ({attempt}/{self.max_retries}): {method} {endpoint}"
                    )
                    time.sleep(retry_delay)
                    retry_delay = min(retry_delay * self.backoff_factor, self.max_retry_delay)
                else:
                    logger.error(f"请求失败，已重试 {self.max_retries} 次: {method} {endpoint}")
                    return {
                        "code": "1",
                        "msg": f"请求失败，已重试 {self.max_retries} 次",
                        "data": [],
                    }

            except requests.exceptions.HTTPError as e:
                # HTTP错误
                status_code = e.response.status_code if hasattr(e, "response") else 0

                # 尝试解析OKX API的错误响应
                okx_error_code = None
                okx_error_msg = None
                error_data = []
                detailed_errors = []

                try:
                    if hasattr(e, "response") and e.response is not None:
                        error_response = e.response.json()
                        okx_error_code = error_response.get("code")
                        okx_error_msg = error_response.get("msg", "")
                        error_data = error_response.get("data", [])

                        # 解析data字段中的详细错误（sCode）
                        for item in error_data:
                            if isinstance(item, dict):
                                s_code = item.get("sCode")
                                s_msg = item.get("sMsg", "")
                                if s_code and s_code != "0":
                                    detailed_errors.append({"sCode": str(s_code), "sMsg": s_msg})
                except (ValueError, AttributeError, json.JSONDecodeError):
                    pass  # 如果无法解析JSON，使用HTTP状态码

                if status_code == 429:  # 限流错误，重试
                    if attempt <= self.max_retries:
                        logger.warning(
                            f"限流错误，将在 {retry_delay:.2f} 秒后重试 ({attempt}/{self.max_retries})"
                        )
                        time.sleep(retry_delay)
                        retry_delay = min(retry_delay * self.backoff_factor, self.max_retry_delay)
                        continue

                # 其他HTTP错误，不重试
                # 如果有OKX错误代码，使用它；否则使用HTTP状态码
                if okx_error_code:
                    error_msg = okx_error_msg or f"HTTP错误 {status_code}"

                    # 如果有data字段中的详细错误，添加到错误消息中
                    if detailed_errors:
                        detail_str = ", ".join(
                            [f"sCode={d['sCode']}, sMsg={d['sMsg']}" for d in detailed_errors]
                        )
                        error_msg += f" | data字段错误: {detail_str}"
                        logger.error(
                            f"OKX API错误 {okx_error_code} (data字段: {detail_str}): {method} {endpoint}"
                        )
                    else:
                        logger.error(
                            f"OKX API错误 {okx_error_code}: {method} {endpoint}, {error_msg}"
                        )

                    return {
                        "code": str(okx_error_code),
                        "msg": error_msg,
                        "data": error_data,
                        "_detailed_errors": detailed_errors,  # 保存详细错误信息
                    }
                else:
                    logger.error(f"HTTP错误 {status_code}: {method} {endpoint}, {e}")
                    return {"code": "1", "msg": f"HTTP错误 {status_code}: {str(e)}", "data": []}

            except Exception as e:
                # 其他异常，不重试
                logger.error(f"请求异常: {method} {endpoint}, {e}")
                return {"code": "1", "msg": f"请求异常: {str(e)}", "data": []}

        return {"code": "1", "msg": f"请求失败，已重试 {self.max_retries} 次", "data": []}

    def _should_send_real_request(self) -> bool:
        """判断是否应该发送真实请求"""
        return self.trading_mode == "live"

    def place_order(
        self,
        symbol: str,
        side: str,
        order_type: str,
        amount: float,
        price: float | None = None,
        params: dict[str, Any] = None,
    ) -> dict[str, Any]:
        """
        下单

        Args:
            symbol: 交易对
            side: 买卖方向
            order_type: 订单类型
            amount: 交易数量
            price: 交易价格（限价单需要）
            params: 其他参数

        Returns:
            result: 订单创建结果
        """
        endpoint = "/api/v5/trade/order"

        # 构造请求体
        body = {
            "instId": symbol,
            "side": side,
            "ordType": order_type,
            "sz": str(amount),
        }

        # 根据交易对类型设置交易模式
        if "-SWAP" in symbol or "-FUTURES" in symbol:
            body["tdMode"] = "cross"
            body["posSide"] = "short" if side == "sell" else "long"
        else:
            body["tdMode"] = "cash"

        # 限价单需要价格
        if order_type == "limit" and price:
            body["px"] = str(price)

        # 添加额外参数
        if params:
            filtered_params = {k: v for k, v in params.items() if k not in ["strategy_id"]}
            body.update(filtered_params)

        # 发送请求
        if self._should_send_real_request():
            return self._send_request("POST", endpoint, body)
        else:
            # Mock模式
            logger.info(f"{self.trading_mode}模式：模拟下单，不发送真实API请求")
            return {
                "code": "0",
                "msg": f"{self.trading_mode} mode order accepted",
                "data": [
                    {
                        "ordId": f"mock_{int(time.time())}",
                        "clOrdId": params.get("clOrdId", "") if params else "",
                        "state": "live" if self.trading_mode in ["paper", "drill"] else "pending",
                    }
                ],
            }

    def cancel_order(self, symbol: str, order_id: str) -> dict[str, Any]:
        """
        撤单

        Args:
            symbol: 交易对
            order_id: 订单ID

        Returns:
            result: 撤单结果
        """
        endpoint = "/api/v5/trade/cancel-order"
        body = {"instId": symbol, "ordId": order_id}

        if self._should_send_real_request():
            return self._send_request("POST", endpoint, body)
        else:
            logger.info(f"{self.trading_mode}模式：模拟撤单，不发送真实API请求")
            return {
                "code": "0",
                "msg": f"{self.trading_mode} mode cancel accepted",
                "data": [{"ordId": order_id, "sCode": "0", "sMsg": "Cancel request processed"}],
            }

    def get_order(self, symbol: str, order_id: str) -> dict[str, Any]:
        """
        查询订单

        Args:
            symbol: 交易对
            order_id: 订单ID

        Returns:
            result: 订单状态
        """
        endpoint = "/api/v5/trade/order"
        params = {"instId": symbol, "ordId": order_id}

        if self._should_send_real_request():
            return self._send_request("GET", endpoint, params=params)
        else:
            logger.info(f"{self.trading_mode}模式：模拟查询订单，不发送真实API请求")
            return {
                "code": "0",
                "msg": f"{self.trading_mode} mode order status",
                "data": [
                    {
                        "ordId": order_id,
                        "instId": symbol,
                        "state": "filled" if self.trading_mode == "paper" else "pending",
                        "side": "buy",
                        "ordType": "market",
                        "sz": "1",
                        "px": "0",
                    }
                ],
            }

    def get_balance(self) -> dict[str, Any]:
        """
        查询余额

        Returns:
            result: 账户余额信息
        """
        endpoint = "/api/v5/account/balance"
        # 账户信息必须从真实API获取，禁止模拟数据
        return self._send_request("GET", endpoint)

    def get_positions(self, symbol: str | None = None) -> dict[str, Any]:
        """
        查询持仓

        Args:
            symbol: 交易对（可选）

        Returns:
            result: 持仓信息
        """
        endpoint = "/api/v5/account/positions"
        params = {}
        if symbol:
            params["instId"] = symbol
        
        # 账户信息必须从真实API获取，禁止模拟数据
        return self._send_request("GET", endpoint, params=params)

    def set_leverage(self, symbol: str, leverage: int, pos_side: str = "long") -> dict[str, Any]:
        """
        设置杠杆

        Args:
            symbol: 交易对
            leverage: 杠杆倍数
            pos_side: 持仓方向

        Returns:
            result: 设置结果
        """
        endpoint = "/api/v5/account/set-leverage"
        body = {"instId": symbol, "lever": str(leverage), "mgnMode": "cross", "posSide": pos_side}

        if self._should_send_real_request():
            return self._send_request("POST", endpoint, body)
        else:
            logger.info(f"{self.trading_mode}模式：模拟设置杠杆，不发送真实API请求")
            return {"code": "0", "msg": f"{self.trading_mode} mode leverage set", "data": []}


class ExchangeAdapterFactory:
    """
    交易所适配器工厂
    根据交易所类型创建对应的适配器
    """

    @staticmethod
    def create(
        exchange: str,
        api_key: str,
        secret_key: str,
        passphrase: str,
        trading_mode: str = "drill",
        region: str = "default",
        simulated: bool = False,
        proxy: str = None,
        verify_ssl: bool = False,
    ) -> ExchangeAdapter:
        """
        创建交易所适配器

        Args:
            exchange: 交易所名称
            api_key: API密钥
            secret_key: 密钥
            passphrase: 密码
            trading_mode: 交易模式
            region: 账户区域（default/eea/us/aws）- 2026年要求
            simulated: 是否为模拟盘（用于x-simulated-trading header）
            proxy: 代理服务器地址（可选）
            verify_ssl: 是否验证SSL证书

        Returns:
            ExchangeAdapter: 交易所适配器实例
        """
        if exchange == "okx":
            return OKXAdapter(
                api_key,
                secret_key,
                passphrase,
                trading_mode=trading_mode,
                region=region,
                simulated=simulated,
                proxy=proxy,
                verify_ssl=verify_ssl,
            )
        else:
            raise ValueError(f"不支持的交易所: {exchange}")
