# gemini_adapter/models/deepseek_chat.py
from typing import Dict, Optional
from .base_model import BaseModel
from ..utils.config import config_manager

class DeepSeekChatModel(BaseModel):
    def __init__(self, model_id: str = "deepseek-chat", api_key: str = "", base_url: Optional[str] = None, proxies: Optional[Dict] = None):
        # 如果没有提供API密钥，从配置管理器获取
        api_key = api_key or config_manager.get_value("core_config.json", "api_keys.deepseek", default="")
        # 如果没有提供代理，从配置管理器获取
        proxies = proxies or config_manager.get_value("core_config.json", "proxies", default={})
        super().__init__(api_key, proxies)
        self.model_name = model_id
        # 如果没有提供基础URL，从配置管理器获取或使用默认值
        self._base_url = base_url or config_manager.get_value("core_config.json", "urls.deepseek", default="https://api.deepseek.com/v1/chat/completions")
        
    def prepare_request(self, user_msg: str, system_prompt: str = "") -> Dict:
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": user_msg})
        
        return {
            "model": self.model_name,
            "messages": messages,
            "max_tokens": 2048,
            "temperature": 0.7,
            "top_p": 0.95
        }
        
    def parse_response(self, response_data: Dict) -> str:
        if "error" in response_data:
            error_msg = response_data["error"].get("message", "未知错误")
            return f"DeepSeek API错误：{error_msg[:30]}..."
        
        if "choices" in response_data and response_data["choices"]:
            choice = response_data["choices"][0]
            if "message" in choice and "content" in choice["message"]:
                return choice["message"]["content"].strip()
            
            finish_reason = choice.get("finish_reason", "unknown")
            if finish_reason == "length":
                return "响应长度超出限制，请简化问题～"
        
        return "未获取到有效回复"
        
    @property
    def api_url(self) -> str:
        return self._base_url
        
    @property
    def headers(self) -> Dict[str, str]:
        return {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}"
        }