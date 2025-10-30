# gemini_adapter/models/base_model.py
from abc import ABC, abstractmethod
from typing import Dict, Optional

class BaseModel(ABC):
    @abstractmethod
    def __init__(self, api_key: str, proxies: Optional[Dict] = None):
        self.api_key = api_key
        self.proxies = proxies or {}
        
    @abstractmethod
    def prepare_request(self, user_msg: str, system_prompt: str = "") -> Dict:
        """准备API请求数据"""
        pass
        
    @abstractmethod
    def parse_response(self, response_data: Dict) -> str:
        """解析API响应数据"""
        pass
        
    @property
    @abstractmethod
    def api_url(self) -> str:
        """API请求地址"""
        pass
        
    @property
    @abstractmethod
    def headers(self) -> Dict[str, str]:
        """请求头信息"""
        pass