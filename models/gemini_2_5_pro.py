# gemini_adapter/models/gemini_2_5_pro.py
from typing import Dict, Optional
from .base_model import BaseModel

class Gemini25ProModel(BaseModel):
    def __init__(self, api_key: str, proxies: Optional[Dict] = None):
        super().__init__(api_key, proxies)
        self.model_name = "gemini-2.5-pro"
        
    def prepare_request(self, user_msg: str, system_prompt: str = "") -> Dict:
        full_message = f"{system_prompt}\n\n用户消息：{user_msg}" if system_prompt else user_msg
        
        return {
            "contents": [{"role": "user", "parts": [{"text": full_message}]}],
            "generationConfig": {
                "maxOutputTokens": 2048,
                "temperature": 0.7,
                "topP": 0.95
            }
        }
        
    def parse_response(self, response_data: Dict) -> str:
        if "error" in response_data:
            error_msg = response_data["error"].get("message", "未知错误")
            return f"Gemini API错误：{error_msg[:30]}..."
        
        if "candidates" in response_data and response_data["candidates"]:
            candidate = response_data["candidates"][0]
            finish_reason = candidate.get("finishReason", "UNKNOWN")
            total_tokens = response_data.get("usageMetadata", {}).get("totalTokenCount", 0)
            
            if "content" in candidate and "parts" in candidate["content"]:
                parts = candidate["content"]["parts"]
                if parts and "text" in parts[0]:
                    return parts[0]["text"].strip()
            
            if finish_reason == "MAX_TOKENS" and total_tokens >= 2000:
                return "响应长度超出限制（已达2048令牌上限），请简化问题～"
        
        return "未获取到有效回复"
        
    @property
    def api_url(self) -> str:
        return f"https://generativelanguage.googleapis.com/v1/models/{self.model_name}:generateContent?key={self.api_key}"
        
    @property
    def headers(self) -> Dict[str, str]:
        return {"Content-Type": "application/json"}