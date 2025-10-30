# gemini_adapter/models/model_factory.py
from typing import Dict, Optional
from .base_model import BaseModel
from .deepseek_chat import DeepSeekChatModel
from .deepseek_reasoner import DeepSeekReasonerModel
from .gemini_2_5_pro import Gemini25ProModel
from .gemini_2_5_flash import Gemini25FlashModel

class ModelFactory:
    _model_classes = {
        "deepseek-chat": DeepSeekChatModel,
        "deepseek-reasoner": DeepSeekReasonerModel,
        "gemini-2.5-pro": Gemini25ProModel,
        "gemini-2.5-flash": Gemini25FlashModel
    }
    
    @classmethod
    def create_model(
        cls, 
        model_id: str, 
        api_keys: Dict[str, str],
        proxies: Optional[Dict] = None
    ) -> BaseModel:
        """
        创建模型实例
        :param model_id: 模型ID
        :param api_keys: 包含各模型API密钥的字典
        :param proxies: 代理配置
        :return: 模型实例
        """
        if model_id not in cls._model_classes:
            raise ValueError(f"不支持的模型: {model_id}")
            
        # 获取对应模型的API密钥
        api_key = api_keys.get(model_id)
        if not api_key:
            raise ValueError(f"未配置模型 {model_id} 的API密钥")
            
        return cls._model_classes[model_id](api_key, proxies)
    
    @classmethod
    def get_supported_models(cls) -> Dict[str, str]:
        """获取支持的模型列表"""
        return {
            # 直接访问类的__name__属性，无需实例化
            model_id: cls._model_classes[model_id].__name__
            for model_id in cls._model_classes
        }