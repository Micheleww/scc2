#!/usr/bin/env python3
"""
策略管理API，整合本地策略库和Freqtrade策略
"""

import json
import logging
import os
from datetime import datetime
from typing import List, Dict, Any

import requests

logger = logging.getLogger(__name__)

class StrategyManager:
    """策略管理类，负责策略数据的获取和同步"""
    
    def __init__(self, config_path: str = None):
        """初始化策略管理器
        
        Args:
            config_path: 配置文件路径，默认为 None
        """
        self.config_path = config_path or os.path.join(
            os.path.dirname(__file__), 
            "..", "..", "..", "configs", "current", "strategies.json"
        )
        self.freqtrade_api_url = "http://127.0.0.1:18788/"
        
    def get_strategies(self) -> List[str]:
        """获取所有策略列表
        
        Returns:
            List[str]: 策略名称列表
        """
        try:
            # 1. 尝试从Freqtrade API获取策略列表
            freqtrade_strategies = self._get_freqtrade_strategies()
            
            # 2. 从本地配置获取策略列表
            local_strategies = self._get_local_strategies()
            
            # 3. 合并去重
            all_strategies = list(set(freqtrade_strategies + local_strategies))
            all_strategies.sort()
            
            return all_strategies
            
        except Exception as e:
            logger.error(f"获取策略列表失败: {e}")
            # 失败时返回本地策略列表
            return self._get_local_strategies()
    
    def get_strategy(self, strategy_name: str) -> Dict[str, Any]:
        """获取特定策略的详细信息
        
        Args:
            strategy_name: 策略名称
            
        Returns:
            Dict[str, Any]: 策略详细信息，包含strategy、code和timeframe字段
        """
        try:
            # 1. 尝试从Freqtrade API获取策略详情
            freqtrade_strategy = self._get_freqtrade_strategy(strategy_name)
            if freqtrade_strategy:
                return {
                    "strategy": strategy_name,
                    "code": freqtrade_strategy.get("code", ""),
                    "timeframe": freqtrade_strategy.get("timeframe", "")
                }
            
            # 2. 从本地配置获取策略详情
            local_strategy = self._get_local_strategy(strategy_name)
            return {
                "strategy": strategy_name,
                "code": local_strategy.get("code", ""),
                "timeframe": local_strategy.get("timeframe", "")
            }
            
        except Exception as e:
            logger.error(f"获取策略详情失败: {e}")
            # 失败时返回空字典
            return {
                "strategy": strategy_name,
                "code": "",
                "timeframe": ""
            }
    
    def _get_local_strategies(self) -> List[str]:
        """从本地配置文件获取策略列表
        
        Returns:
            List[str]: 本地策略名称列表
        """
        try:
            if os.path.exists(self.config_path):
                with open(self.config_path, "r", encoding="utf-8") as f:
                    strategies_data = json.load(f)
                # 支持两种格式：
                # 1. 新格式：{"strategies": [{"id": "...", "name": "...", ...}]}
                # 2. 旧格式：{"strategy_name": {...}}
                if isinstance(strategies_data, dict):
                    if "strategies" in strategies_data:
                        # 新格式
                        return [strategy["name"] for strategy in strategies_data["strategies"]]
                    else:
                        # 旧格式
                        return list(strategies_data.keys())
            return []
        except Exception as e:
            logger.error(f"读取本地策略文件失败: {e}")
            return []
    
    def _get_local_strategy(self, strategy_name: str) -> Dict[str, Any]:
        """从本地配置文件获取策略详情
        
        Args:
            strategy_name: 策略名称
            
        Returns:
            Dict[str, Any]: 本地策略详细信息
        """
        try:
            if os.path.exists(self.config_path):
                with open(self.config_path, "r", encoding="utf-8") as f:
                    strategies_data = json.load(f)
            
            if isinstance(strategies_data, dict):
                if "strategies" in strategies_data:
                    # 新格式：查找名称匹配的策略
                    for strategy in strategies_data["strategies"]:
                        if strategy["name"] == strategy_name:
                            return strategy
                    return {}
                else:
                    # 旧格式
                    return strategies_data.get(strategy_name, {})
            return {}
        except Exception as e:
            logger.error(f"读取本地策略详情失败: {e}")
            return {}
    
    def _get_freqtrade_strategies(self) -> List[str]:
        """从Freqtrade API获取策略列表
        
        Returns:
            List[str]: Freqtrade策略名称列表
        """
        try:
            url = f"{self.freqtrade_api_url}/api/v1/strategies"
            response = requests.get(url, timeout=5)
            if response.status_code == 200:
                data = response.json()
                return data.get("strategies", [])
            return []
        except Exception as e:
            logger.warning(f"从Freqtrade API获取策略列表失败: {e}")
            return []
    
    def _get_freqtrade_strategy(self, strategy_name: str) -> Dict[str, Any]:
        """从Freqtrade API获取策略详情
        
        Args:
            strategy_name: 策略名称
            
        Returns:
            Dict[str, Any]: Freqtrade策略详细信息
        """
        try:
            url = f"{self.freqtrade_api_url}/api/v1/strategy/{strategy_name}"
            response = requests.get(url, timeout=5)
            if response.status_code == 200:
                return response.json()
            return {}
        except Exception as e:
            logger.warning(f"从Freqtrade API获取策略详情失败: {e}")
            return {}
    
    def sync_strategies(self) -> bool:
        """同步策略数据，确保本地策略库与Freqtrade策略一致
        
        Returns:
            bool: 同步是否成功
        """
        try:
            # 1. 获取Freqtrade策略列表
            freqtrade_strategies = self._get_freqtrade_strategies()
            
            # 2. 获取本地策略列表
            local_strategies = self._get_local_strategies()
            
            # 3. 加载本地策略数据
            strategies_data = {"strategies": []}
            
            if os.path.exists(self.config_path):
                with open(self.config_path, "r", encoding="utf-8") as f:
                    existing_data = json.load(f)
                
                # 处理两种格式
                if isinstance(existing_data, dict):
                    if "strategies" in existing_data:
                        # 新格式
                        strategies_data = existing_data
                    else:
                        # 旧格式转换为新格式
                        strategies_data["strategies"] = []
                        for strategy_name, strategy_info in existing_data.items():
                            strategies_data["strategies"].append({
                                "id": strategy_name,
                                "name": strategy_info.get("name", strategy_name),
                                "description": strategy_info.get("description", ""),
                                "factors": strategy_info.get("factors", []),
                                "status": "active" if strategy_info.get("enabled", True) else "inactive",
                                "created": strategy_info.get("created", ""),
                                "category": strategy_info.get("category", "未分类"),
                                "code": strategy_info.get("code", ""),
                                "timeframe": strategy_info.get("timeframe", ""),
                                "type": strategy_info.get("type", "local"),
                                "source": strategy_info.get("source", "local")
                            })
            
            # 4. 合并Freqtrade策略到现有策略数据
            existing_strategy_names = {strategy["name"] for strategy in strategies_data["strategies"]}
            
            for strategy_name in freqtrade_strategies:
                if strategy_name not in existing_strategy_names:
                    # 添加新的Freqtrade策略
                    strategies_data["strategies"].append({
                        "id": f"freqtrade_{strategy_name}",
                        "name": strategy_name,
                        "description": "",
                        "factors": [],
                        "status": "active",
                        "created": datetime.now().isoformat() + "Z",
                        "category": "Freqtrade策略",
                        "code": "",
                        "timeframe": "",
                        "type": "freqtrade",
                        "source": "freqtrade"
                    })
            
            # 5. 保存更新后的策略数据
            with open(self.config_path, "w", encoding="utf-8") as f:
                json.dump(strategies_data, f, ensure_ascii=False, indent=2)
            
            logger.info(f"策略同步完成，共 {len(strategies_data['strategies'])} 个策略")
            return True
            
        except Exception as e:
            logger.error(f"策略同步失败: {e}")
            return False