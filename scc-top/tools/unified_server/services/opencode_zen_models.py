"""
OpenCode Zen 免费模型库

OpenCode Zen 提供的免费模型，与 OpenRouter 互补
包含 Kimi K2.5 Free 等独家免费模型
"""

import json
import logging
import os
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, asdict
from datetime import datetime

logger = logging.getLogger(__name__)


@dataclass
class OpenCodeZenModel:
    """OpenCode Zen 模型信息"""
    id: str
    name: str
    provider: str
    context_length: int
    supports_vision: bool
    description: str = ""
    status: str = "available"  # available, rate_limited, exhausted, error
    last_used: Optional[str] = None
    use_count: int = 0
    error_count: int = 0
    priority: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "OpenCodeZenModel":
        return cls(**data)


class OpenCodeZenModelLibrary:
    """
    OpenCode Zen 免费模型库
    
    OpenCode Zen 提供的免费模型：
    - Big Pickle (隐身模型)
    - MiniMax M2.1 Free
    - GLM 4.7 Free
    - Kimi K2.5 Free (重点！)
    - GPT 5 Nano (永久免费)
    """
    
    # OpenCode Zen API 配置
    API_BASE_URL = "https://api.opencode.ai/v1"
    
    # 免费模型列表
    DEFAULT_MODELS = [
        # Kimi K2.5 Free - 最期待的模型！
        OpenCodeZenModel(
            id="kimi-k2.5-free",
            name="Kimi K2.5 Free",
            provider="moonshot",
            context_length=256000,
            supports_vision=True,
            description="月之暗面 Kimi K2.5，限时免费，支持长文本和视觉",
            priority=1
        ),
        # GLM 4.7 Free
        OpenCodeZenModel(
            id="glm-4.7-free",
            name="GLM 4.7 Free",
            provider="zhipu",
            context_length=131072,
            supports_vision=True,
            description="智谱 GLM 4.7，限时免费",
            priority=2
        ),
        # GPT 5 Nano (永久免费)
        OpenCodeZenModel(
            id="gpt-5-nano",
            name="GPT 5 Nano",
            provider="openai",
            context_length=128000,
            supports_vision=False,
            description="OpenAI GPT-5 Nano，永久免费",
            priority=3
        ),
        # MiniMax M2.1 Free
        OpenCodeZenModel(
            id="minimax-m2.1-free",
            name="MiniMax M2.1 Free",
            provider="minimax",
            context_length=100000,
            supports_vision=False,
            description="MiniMax M2.1，限时免费",
            priority=4
        ),
        # Big Pickle (隐身模型)
        OpenCodeZenModel(
            id="big-pickle",
            name="Big Pickle",
            provider="opencode",
            context_length=128000,
            supports_vision=False,
            description="OpenCode 隐身模型，免费",
            priority=5
        ),
    ]
    
    def __init__(self, state_file: Optional[str] = None, api_key: Optional[str] = None):
        self.models: List[OpenCodeZenModel] = []
        self.current_index: int = 0
        self.state_file = state_file
        self.api_key = api_key or os.getenv("OPENCODE_ZEN_API_KEY")
        
        # 加载或初始化模型列表
        self._load_models()
        
        logger.info(f"OpenCode Zen 模型库初始化完成，共 {len(self.models)} 个模型")
    
    def _load_models(self) -> None:
        """加载模型列表"""
        if self.state_file:
            try:
                with open(self.state_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.models = [OpenCodeZenModel.from_dict(m) for m in data.get('models', [])]
                    self.current_index = data.get('current_index', 0)
                    logger.info(f"从文件加载了 {len(self.models)} 个 OpenCode Zen 模型")
                    return
            except Exception as e:
                logger.warning(f"无法加载模型状态文件: {e}，使用默认模型")
        
        # 使用默认模型
        self.models = [OpenCodeZenModel(**asdict(m)) for m in self.DEFAULT_MODELS]
        self._save_models()
    
    def _save_models(self) -> None:
        """保存模型状态"""
        if self.state_file:
            try:
                data = {
                    'models': [m.to_dict() for m in self.models],
                    'current_index': self.current_index,
                    'updated_at': datetime.now().isoformat()
                }
                with open(self.state_file, 'w', encoding='utf-8') as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)
            except Exception as e:
                logger.warning(f"无法保存模型状态文件: {e}")
    
    def get_current_model(self) -> Optional[OpenCodeZenModel]:
        """获取当前可用模型"""
        if not self.models:
            return None
        
        # 按优先级排序
        available_models = [m for m in self.models if m.status == "available"]
        if not available_models:
            # 如果没有可用模型，重置所有非错误模型的状态
            for m in self.models:
                if m.status not in ["error"]:
                    m.status = "available"
            available_models = self.models
        
        # 按优先级排序
        available_models.sort(key=lambda x: x.priority)
        
        if available_models:
            model = available_models[0]
            logger.info(f"当前使用 OpenCode Zen 模型: {model.name}")
            return model
        
        return None
    
    def get_next_model(self) -> Optional[OpenCodeZenModel]:
        """切换到下一个可用模型"""
        current = self.get_current_model()
        if current:
            # 标记当前模型为已用完
            current.status = "rate_limited"
            current.last_used = datetime.now().isoformat()
            self._save_models()
            logger.info(f"模型 {current.name} 已标记为限流，切换到下一个")
        
        return self.get_current_model()
    
    def mark_model_error(self, model_id: str) -> None:
        """标记模型为错误状态"""
        for model in self.models:
            if model.id == model_id:
                model.error_count += 1
                if model.error_count >= 3:
                    model.status = "error"
                    logger.warning(f"模型 {model.name} 已被标记为错误状态")
                self._save_models()
                break
    
    def reset_model_status(self, model_id: Optional[str] = None) -> None:
        """重置模型状态"""
        if model_id:
            for model in self.models:
                if model.id == model_id:
                    model.status = "available"
                    model.error_count = 0
                    logger.info(f"模型 {model.name} 状态已重置")
        else:
            for model in self.models:
                model.status = "available"
                model.error_count = 0
            logger.info("所有模型状态已重置")
        
        self._save_models()
    
    def get_api_config(self) -> Dict[str, str]:
        """获取 API 配置"""
        return {
            "base_url": self.API_BASE_URL,
            "api_key": self.api_key or "",
            "provider": "opencode-zen"
        }


# 全局模型库实例
_opencode_zen_library: Optional[OpenCodeZenModelLibrary] = None


def get_opencode_zen_library(api_key: Optional[str] = None) -> OpenCodeZenModelLibrary:
    """获取 OpenCode Zen 模型库实例"""
    global _opencode_zen_library
    if _opencode_zen_library is None:
        state_file = os.path.join(os.path.dirname(__file__), '..', '..', '..', '.opencode_zen_models_state.json')
        _opencode_zen_library = OpenCodeZenModelLibrary(
            state_file=state_file,
            api_key=api_key
        )
    return _opencode_zen_library


if __name__ == "__main__":
    # 测试
    logging.basicConfig(level=logging.INFO)
    lib = get_opencode_zen_library()
    print(f"\nOpenCode Zen 免费模型库 ({len(lib.models)} 个模型):")
    for i, m in enumerate(lib.models, 1):
        print(f"{i}. {m.name} ({m.id}) - {m.description}")
    
    current = lib.get_current_model()
    if current:
        print(f"\n当前优先使用: {current.name}")
