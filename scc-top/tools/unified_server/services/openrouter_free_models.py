"""
OpenRouter免费模型库

管理可用的免费模型列表，实现自动切换功能
按参数量排序：120B+ > 70B > 27B > 24B > 20B > 12B > 9B > 4B > 3B > 1B
"""

import json
import logging
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, asdict
from datetime import datetime

logger = logging.getLogger(__name__)


@dataclass
class FreeModel:
    """免费模型信息"""
    id: str
    name: str
    provider: str
    context_length: int
    supports_vision: bool
    params_b: int = 0  # 参数量（Billion）
    status: str = "available"  # available, rate_limited, exhausted, error
    last_used: Optional[str] = None
    use_count: int = 0
    error_count: int = 0
    priority: int = 0  # 优先级，数字越小优先级越高（按参数量排序）
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "FreeModel":
        return cls(**data)


class OpenRouterFreeModelLibrary:
    """
    OpenRouter免费模型库
    
    管理免费模型列表，自动切换模型
    按参数量排序：优先使用大参数模型
    """
    
    # 免费模型列表（按参数量排序，大模型优先）
    # 基于测试结果：共29个免费模型
    DEFAULT_MODELS = [
        # 120B+ 参数模型
        FreeModel(
            id="openrouter/openai/gpt-oss-120b",
            name="GPT-OSS-120B",
            provider="openai",
            context_length=131072,
            supports_vision=False,
            params_b=120,
            priority=1
        ),
        FreeModel(
            id="openrouter/nousresearch/hermes-3-llama-3.1-405b",
            name="Hermes-3-405B",
            provider="nousresearch",
            context_length=131072,
            supports_vision=False,
            params_b=405,
            priority=2
        ),
        # 80B 参数模型
        FreeModel(
            id="openrouter/qwen/qwen3-next-80b-a3b-instruct",
            name="Qwen3-Next-80B-A3B",
            provider="qwen",
            context_length=262144,
            supports_vision=False,
            params_b=80,
            priority=3
        ),
        # 70B 参数模型
        FreeModel(
            id="openrouter/meta-llama/llama-3.3-70b-instruct",
            name="Llama-3.3-70B",
            provider="meta",
            context_length=128000,
            supports_vision=False,
            params_b=70,
            priority=4
        ),
        # 30B 参数模型
        FreeModel(
            id="openrouter/nvidia/nemotron-3-nano-30b-a3b",
            name="Nemotron-3-Nano-30B",
            provider="nvidia",
            context_length=256000,
            supports_vision=False,
            params_b=30,
            priority=5
        ),
        # 27B 参数模型
        FreeModel(
            id="openrouter/google/gemma-3-27b-it",
            name="Gemma-3-27B-IT",
            provider="google",
            context_length=131072,
            supports_vision=True,
            params_b=27,
            priority=6
        ),
        # 24B 参数模型
        FreeModel(
            id="openrouter/mistralai/mistral-small-3.1-24b-instruct",
            name="Mistral-Small-3.1-24B",
            provider="mistral",
            context_length=128000,
            supports_vision=False,
            params_b=24,
            priority=7
        ),
        FreeModel(
            id="openrouter/cognitivecomputations/dolphin-mistral-24b-venice-edition",
            name="Dolphin-Mistral-24B-Venice",
            provider="cognitivecomputations",
            context_length=32768,
            supports_vision=False,
            params_b=24,
            priority=8
        ),
        # 20B 参数模型
        FreeModel(
            id="openrouter/openai/gpt-oss-20b",
            name="GPT-OSS-20B",
            provider="openai",
            context_length=131072,
            supports_vision=False,
            params_b=20,
            priority=9
        ),
        # 16B 参数模型（DeepSeek R1系列）
        FreeModel(
            id="openrouter/tngtech/tng-r1t-chimera",
            name="TNG-R1T-Chimera",
            provider="tngtech",
            context_length=163840,
            supports_vision=False,
            params_b=16,
            priority=10
        ),
        FreeModel(
            id="openrouter/tngtech/deepseek-r1t2-chimera",
            name="DeepSeek-R1T2-Chimera",
            provider="tngtech",
            context_length=163840,
            supports_vision=False,
            params_b=16,
            priority=11
        ),
        FreeModel(
            id="openrouter/tngtech/deepseek-r1t-chimera",
            name="DeepSeek-R1T-Chimera",
            provider="tngtech",
            context_length=163840,
            supports_vision=False,
            params_b=16,
            priority=12
        ),
        FreeModel(
            id="openrouter/deepseek/deepseek-r1-0528",
            name="DeepSeek-R1-0528",
            provider="deepseek",
            context_length=163840,
            supports_vision=False,
            params_b=16,
            priority=13
        ),
        # 14B 参数模型（GLM-4.5）
        FreeModel(
            id="openrouter/z-ai/glm-4.5-air",
            name="GLM-4.5-Air",
            provider="z-ai",
            context_length=131072,
            supports_vision=False,
            params_b=14,
            priority=14
        ),
        # 12B 参数模型
        FreeModel(
            id="openrouter/nvidia/nemotron-nano-12b-v2-vl",
            name="Nemotron-Nano-12B-V2-VL",
            provider="nvidia",
            context_length=128000,
            supports_vision=True,
            params_b=12,
            priority=15
        ),
        FreeModel(
            id="openrouter/google/gemma-3-12b-it",
            name="Gemma-3-12B-IT",
            provider="google",
            context_length=32768,
            supports_vision=True,
            params_b=12,
            priority=16
        ),
        # 9B 参数模型
        FreeModel(
            id="openrouter/nvidia/nemotron-nano-9b-v2",
            name="Nemotron-Nano-9B-V2",
            provider="nvidia",
            context_length=128000,
            supports_vision=False,
            params_b=9,
            priority=17
        ),
        # 4B 参数模型
        FreeModel(
            id="openrouter/google/gemma-3-4b-it",
            name="Gemma-3-4B-IT",
            provider="google",
            context_length=32768,
            supports_vision=True,
            params_b=4,
            priority=18
        ),
        FreeModel(
            id="openrouter/qwen/qwen3-4b",
            name="Qwen3-4B",
            provider="qwen",
            context_length=40960,
            supports_vision=False,
            params_b=4,
            priority=19
        ),
        # 3B 参数模型
        FreeModel(
            id="openrouter/meta-llama/llama-3.2-3b-instruct",
            name="Llama-3.2-3B",
            provider="meta",
            context_length=131072,
            supports_vision=False,
            params_b=3,
            priority=20
        ),
        # 2B 参数模型
        FreeModel(
            id="openrouter/google/gemma-3n-e4b-it",
            name="Gemma-3n-E4B",
            provider="google",
            context_length=8192,
            supports_vision=True,
            params_b=2,
            priority=21
        ),
        FreeModel(
            id="openrouter/google/gemma-3n-e2b-it",
            name="Gemma-3n-E2B",
            provider="google",
            context_length=8192,
            supports_vision=True,
            params_b=2,
            priority=22
        ),
        # 1.2B 参数模型
        FreeModel(
            id="openrouter/liquid/lfm-2.5-1.2b-thinking",
            name="LFM-2.5-1.2B-Thinking",
            provider="liquid",
            context_length=32768,
            supports_vision=False,
            params_b=1,
            priority=23
        ),
        FreeModel(
            id="openrouter/liquid/lfm-2.5-1.2b-instruct",
            name="LFM-2.5-1.2B-Instruct",
            provider="liquid",
            context_length=32768,
            supports_vision=False,
            params_b=1,
            priority=24
        ),
        # 其他模型（StepFun）
        FreeModel(
            id="openrouter/stepfun/step-3.5-flash",
            name="Step-3.5-Flash",
            provider="stepfun",
            context_length=256000,
            supports_vision=False,
            params_b=0,  # 未知参数量
            priority=25
        ),
        # Qwen3 Coder（480B A35B MoE）
        FreeModel(
            id="openrouter/qwen/qwen3-coder",
            name="Qwen3-Coder-480B-A35B",
            provider="qwen",
            context_length=262000,
            supports_vision=False,
            params_b=480,  # MoE模型
            priority=26
        ),
        # Trinity系列
        FreeModel(
            id="openrouter/arcee-ai/trinity-large-preview",
            name="Trinity-Large-Preview",
            provider="arcee-ai",
            context_length=131000,
            supports_vision=False,
            params_b=0,
            priority=27
        ),
        FreeModel(
            id="openrouter/arcee-ai/trinity-mini",
            name="Trinity-Mini",
            provider="arcee-ai",
            context_length=131072,
            supports_vision=False,
            params_b=0,
            priority=28
        ),
        # Upstage
        FreeModel(
            id="openrouter/upstage/solar-pro-3",
            name="Solar-Pro-3",
            provider="upstage",
            context_length=128000,
            supports_vision=False,
            params_b=0,
            priority=29
        ),
    ]
    
    def __init__(self, state_file: Optional[str] = None):
        self.models: List[FreeModel] = []
        self.current_index: int = 0
        self.state_file = state_file
        
        # 加载或初始化模型列表
        self._load_models()
        
        logger.info(f"OpenRouter免费模型库初始化完成，共 {len(self.models)} 个模型")
    
    def _load_models(self) -> None:
        """加载模型列表"""
        if self.state_file:
            try:
                with open(self.state_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.models = [FreeModel.from_dict(m) for m in data.get('models', [])]
                    self.current_index = data.get('current_index', 0)
                    logger.info(f"从文件加载了 {len(self.models)} 个模型")
                    return
            except Exception as e:
                logger.warning(f"无法加载模型状态文件: {e}，使用默认模型")
        
        # 使用默认模型
        self.models = [FreeModel(**asdict(m)) for m in self.DEFAULT_MODELS]
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
    
    def get_current_model(self) -> Optional[FreeModel]:
        """获取当前模型（按参数量排序，大模型优先）"""
        if not self.models:
            return None
        
        # 按优先级排序（参数量大的优先）
        available_models = [m for m in self.models if m.status == "available"]
        if not available_models:
            # 如果没有可用模型，重置所有非错误模型的状态
            for m in self.models:
                if m.status not in ["error"]:
                    m.status = "available"
            available_models = self.models
        
        # 按优先级排序（priority数字越小优先级越高）
        available_models.sort(key=lambda x: x.priority)
        
        if available_models:
            model = available_models[0]
            logger.info(f"当前使用模型: {model.name} ({model.params_b}B 参数)")
            return model
        
        return None
    
    def get_next_model(self) -> Optional[FreeModel]:
        """切换到下一个可用模型"""
        current = self.get_current_model()
        if current:
            # 标记当前模型为已用完
            current.status = "exhausted"
            current.last_used = datetime.now().isoformat()
            logger.info(f"模型 {current.name} 已标记为 exhausted")
        
        # 获取下一个可用模型
        next_model = self.get_current_model()
        if next_model:
            logger.info(f"已切换到模型: {next_model.name} ({next_model.params_b}B 参数)")
        
        self._save_models()
        return next_model
    
    def mark_model_rate_limited(self, model_id: str) -> None:
        """标记模型为速率限制"""
        for model in self.models:
            if model.id == model_id:
                model.status = "rate_limited"
                model.last_used = datetime.now().isoformat()
                logger.warning(f"模型 {model.name} 被标记为 rate_limited")
                self._save_models()
                break
    
    def mark_model_error(self, model_id: str) -> None:
        """标记模型为错误"""
        for model in self.models:
            if model.id == model_id:
                model.error_count += 1
                if model.error_count >= 3:
                    model.status = "error"
                    logger.error(f"模型 {model.name} 被标记为 error（错误次数: {model.error_count}）")
                else:
                    logger.warning(f"模型 {model.name} 错误次数: {model.error_count}")
                self._save_models()
                break
    
    def record_usage(self, model_id: str) -> None:
        """记录模型使用"""
        for model in self.models:
            if model.id == model_id:
                model.use_count += 1
                model.last_used = datetime.now().isoformat()
                self._save_models()
                break
    
    def reset_all_models(self) -> None:
        """重置所有模型状态"""
        for model in self.models:
            model.status = "available"
            model.error_count = 0
        self._save_models()
        logger.info("所有模型状态已重置")
    
    def get_all_models(self) -> List[FreeModel]:
        """获取所有模型"""
        return self.models
    
    def get_available_models(self) -> List[FreeModel]:
        """获取可用模型列表"""
        return [m for m in self.models if m.status == "available"]
    
    def get_models_by_size(self) -> Dict[str, List[FreeModel]]:
        """按参数量分组获取模型"""
        groups = {
            "120B+": [],
            "70B-119B": [],
            "30B-69B": [],
            "20B-29B": [],
            "10B-19B": [],
            "1B-9B": [],
            "<1B": [],
            "Unknown": []
        }
        
        for model in self.models:
            params = model.params_b
            if params >= 120:
                groups["120B+"].append(model)
            elif params >= 70:
                groups["70B-119B"].append(model)
            elif params >= 30:
                groups["30B-69B"].append(model)
            elif params >= 20:
                groups["20B-29B"].append(model)
            elif params >= 10:
                groups["10B-19B"].append(model)
            elif params >= 1:
                groups["1B-9B"].append(model)
            elif params > 0:
                groups["<1B"].append(model)
            else:
                groups["Unknown"].append(model)
        
        return groups


# 全局模型库实例
_model_library: Optional[OpenRouterFreeModelLibrary] = None


def get_model_library(state_file: Optional[str] = None) -> OpenRouterFreeModelLibrary:
    """获取全局模型库实例"""
    global _model_library
    if _model_library is None:
        _model_library = OpenRouterFreeModelLibrary(state_file)
    return _model_library
