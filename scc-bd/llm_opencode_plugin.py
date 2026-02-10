"""
LLM Plugin for OpenCode API
使用 OpenCode 的免费模型 API
"""

import llm
from llm.default_plugins.openai_models import Chat

class OpenCodeChat(Chat):
    """OpenCode Chat Model"""
    
    def __init__(self, model_id, **kwargs):
        # OpenCode API 配置
        self.api_base = "https://api.opencode.ai/v1"
        self.api_key = "sk-H631B8CDPPP9XQsc4RT5pHsMlyD4sNQiCYbot6pGg3QcnuPQyXrkGyEFY0iVjqoc"
        super().__init__(model_id=model_id, **kwargs)
    
    def __str__(self):
        return f"OpenCode: {self.model_id}"

@llm.hookimpl
def register_models(register):
