import os
import json
from typing import Dict, Any, Optional

class ConfigManager:
    """统一的配置管理器"""
    
    def __init__(self):
        self.data_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
        self.configs: Dict[str, Dict[str, Any]] = {}
        self.default_configs = {
            "config.json": {
                "split_enabled": False,
                "reply_status": {}  # 格式: {"user_123": True, "group_456": False}
            },
            "core_config.json": {
                "api_keys": {
                    "gemini": "",
                    "deepseek": ""
                },
                "models": {
                    "gemini": "gemini-2.5-pro",
                    "deepseek": "deepseek-chat"
                },
                "urls": {
                    "gemini": "https://generativelanguage.googleapis.com/v1/models/{model}:generateContent?key={key}",
                    "deepseek": "https://api.deepseek.com/v1/chat/completions"
                },
                "proxies": {},
                "rate_limit": {
                    "gemini_cooldown": 15,
                    "deepseek_cooldown": 2,
                    "global_qps_limit": 2
                }
            },
            "model_config.json": {
                "current_model": "gemini-2.5-pro",
                "models": {
                    "gemini-2.5-pro": "Google Gemini 2.5 Pro",
                    "gemini-2.5-flash": "Google Gemini 2.5 Flash",
                    "deepseek-chat": "DeepSeek Chat",
                    "deepseek-reasoner": "DeepSeek Reasoner"
                },
                "api_keys": {
                    "gemini-2.5-pro": "",
                    "gemini-2.5-flash": "",
                    "deepseek-chat": "",
                    "deepseek-reasoner": ""
                },
                "cooldowns": {
                    "gemini-2.5-pro": 15,
                    "gemini-2.5-flash": 10,
                    "deepseek-chat": 2,
                    "deepseek-reasoner": 3
                },
                "urls": {
                    "gemini": "https://generativelanguage.googleapis.com/v1/models/{model}:generateContent?key={key}",
                    "deepseek": "https://api.deepseek.com/v1/chat/completions"
                },
                "proxies": {},
                "rate_limit": {
                    "global_qps_limit": 2
                }
            },
            "prompts_config.json": {
                "prompts": {},
                "status": {
                    "default": True
                }
            },
            "split_config.json": {
                "enabled": False,
                "prompt": "请将你的回答分成多条简短消息，每条消息控制在1-2句话内（一般不多于20字）。当需要分段时，请用【SPLIT】标记作为每条消息的结束。确保内容连贯自然，符合QQ聊天场景的交流习惯，避免过长段落。"
            },
            "admin_config.json": {
                "admin_qq": []
            }
        }
        
        # 确保数据目录存在
        os.makedirs(self.data_dir, exist_ok=True)
    
    def get_config_path(self, filename: str) -> str:
        """获取配置文件的完整路径"""
        return os.path.join(self.data_dir, filename)
    
    def load_config(self, filename: str) -> Dict[str, Any]:
        """加载指定的配置文件"""
        # 如果配置已加载，直接返回缓存的配置
        if filename in self.configs:
            return self.configs[filename]
        
        config_path = self.get_config_path(filename)
        default_config = self.default_configs.get(filename, {})
        
        # 如果文件不存在，创建默认配置文件
        if not os.path.exists(config_path):
            # 检查是否有对应的.example文件
            example_path = config_path + ".example"
            if os.path.exists(example_path):
                try:
                    with open(example_path, "r", encoding="utf-8") as f:
                        default_config = json.load(f)
                except Exception as e:
                    print(f"加载示例配置文件失败: {e}，使用内置默认配置")
            
            # 保存默认配置
            with open(config_path, "w", encoding="utf-8") as f:
                json.dump(default_config, f, ensure_ascii=False, indent=2)
            
            self.configs[filename] = default_config
            return default_config
        
        # 加载现有配置文件
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                config = json.load(f)
                
                # 补全缺失的配置项
                self._merge_defaults(config, default_config)
                
                # 缓存配置
                self.configs[filename] = config
                return config
        except (json.JSONDecodeError, Exception) as e:
            print(f"加载配置文件 {filename} 失败: {e}，使用默认配置")
            self.configs[filename] = default_config
            return default_config
    
    def save_config(self, filename: str, config: Dict[str, Any]) -> bool:
        """保存配置到指定文件"""
        try:
            config_path = self.get_config_path(filename)
            with open(config_path, "w", encoding="utf-8") as f:
                json.dump(config, f, ensure_ascii=False, indent=2)
            
            # 更新缓存
            self.configs[filename] = config
            return True
        except Exception as e:
            print(f"保存配置文件 {filename} 失败: {e}")
            return False
    
    def _merge_defaults(self, config: Dict[str, Any], defaults: Dict[str, Any]) -> None:
        """递归合并默认配置到现有配置中"""
        for key, val in defaults.items():
            if key not in config:
                config[key] = val
            elif isinstance(val, dict) and isinstance(config[key], dict):
                self._merge_defaults(config[key], val)
    
    def get_value(self, filename: str, keys: str, default: Any = None) -> Any:
        """获取嵌套配置值
        
        Args:
            filename: 配置文件名
            keys: 用点分隔的键路径，如 "api_keys.gemini"
            default: 默认值
        """
        config = self.load_config(filename)
        
        # 处理嵌套键
        parts = keys.split(".")
        value = config
        
        for part in parts:
            if isinstance(value, dict) and part in value:
                value = value[part]
            else:
                return default
        
        return value
    
    def set_value(self, filename: str, keys: str, value: Any) -> bool:
        """设置嵌套配置值
        
        Args:
            filename: 配置文件名
            keys: 用点分隔的键路径，如 "api_keys.gemini"
            value: 要设置的值
        """
        config = self.load_config(filename).copy()
        
        # 处理嵌套键
        parts = keys.split(".")
        last_key = parts[-1]
        
        # 导航到目标父级
        current = config
        for part in parts[:-1]:
            if part not in current or not isinstance(current[part], dict):
                current[part] = {}
            current = current[part]
        
        # 设置值
        current[last_key] = value
        
        # 保存配置
        return self.save_config(filename, config)
    
    def reload_config(self, filename: str) -> Dict[str, Any]:
        """重新加载指定配置文件，忽略缓存"""
        if filename in self.configs:
            del self.configs[filename]
        return self.load_config(filename)
    
    def reload_all(self) -> None:
        """重新加载所有配置文件"""
        self.configs.clear()
    
    def initialize(self) -> None:
        """初始化配置管理器，加载所有配置文件"""
        # 预加载所有默认配置文件以确保它们存在
        for filename in self.default_configs.keys():
            self.load_config(filename)
    
    def get_data_dir(self) -> str:
        """获取数据目录路径"""
        return self.data_dir

# 创建全局配置管理器实例
config_manager = ConfigManager()

# 提供向后兼容的函数
def load_config(filename: str = "config.json") -> Dict[str, Any]:
    """兼容旧接口的配置加载函数"""
    return config_manager.load_config(filename)

def save_config(config: Dict[str, Any], filename: str = "config.json") -> bool:
    """兼容旧接口的配置保存函数"""
    return config_manager.save_config(filename, config)

# 导出DATA_DIR供其他模块使用
DATA_DIR = config_manager.data_dir