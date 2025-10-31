# gemini_adapter/models/model_factory.py
from typing import Dict, Optional, Type
from .base_model import BaseModel
from .deepseek_chat import DeepSeekChatModel
from .deepseek_reasoner import DeepSeekReasonerModel
from .gemini_2_5_pro import Gemini25ProModel
from .gemini_2_5_flash import Gemini25FlashModel
from ..utils.config import config_manager

class ModelFactory:
    """模型工厂类，负责创建不同的AI模型实例"""
    
    # 存储模型类的字典
    _model_classes: Dict[str, Type[BaseModel]] = {
        "deepseek-chat": DeepSeekChatModel,
        "deepseek-reasoner": DeepSeekReasonerModel,
        "gemini-2.5-pro": Gemini25ProModel,
        "gemini-2.5-flash": Gemini25FlashModel
    }
    
    # 存储模型实例的缓存
    _model_instances: Dict[str, BaseModel] = {}
    
    @classmethod
    def create_model(cls, model_id: str) -> BaseModel:
        """创建并返回指定ID的模型实例
        
        Args:
            model_id: 模型ID，如 'gemini-2.5-pro', 'deepseek-chat' 等
            
        Returns:
            BaseModel: 模型实例
            
        Raises:
            ValueError: 如果模型ID无效
        """
        # 检查缓存中是否已有该模型实例
        if model_id in cls._model_instances:
            return cls._model_instances[model_id]
        
        # 检查模型ID是否有效
        if model_id not in cls._model_classes:
            raise ValueError(f"不支持的模型: {model_id}")
        
        # 从配置管理器获取模型配置
        api_keys = config_manager.get_value("model_config.json", "api_keys", default={})
        api_urls = config_manager.get_value("model_config.json", "api_urls", default={})
        proxies = config_manager.get_value("model_config.json", "proxies", default={})
        
        # 创建模型实例
        model_class = cls._model_classes[model_id]
        instance = model_class(
            model_id=model_id,
            api_key=api_keys.get(model_id, ""),
            base_url=api_urls.get(model_id, None),
            proxies=proxies.get(model_id, None)
        )
        
        # 缓存模型实例
        cls._model_instances[model_id] = instance
        
        return instance
    
    @classmethod
    def get_supported_models(cls) -> Dict[str, Type[BaseModel]]:
        """获取支持的所有模型
        
        Returns:
            Dict[str, Type[BaseModel]]: 模型ID到模型类的映射
        """
        return cls._model_classes.copy()