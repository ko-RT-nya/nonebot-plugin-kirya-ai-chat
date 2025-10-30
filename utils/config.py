import os
import json
from typing import Dict, Any

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
CONFIG_FILE = os.path.join(DATA_DIR, "config.json")

# 默认配置（仅包含split和reply相关）
DEFAULT_CONFIG = {
    "split_enabled": False,
    "reply_status": {}  # 格式: {"user_123": True, "group_456": False}
}

def load_config() -> Dict[str, Any]:
    """加载split和reply的配置"""
    os.makedirs(DATA_DIR, exist_ok=True)
    if not os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(DEFAULT_CONFIG, f, ensure_ascii=False, indent=2)
        return DEFAULT_CONFIG
    
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            config = json.load(f)
            # 补全缺失的配置项
            for key, val in DEFAULT_CONFIG.items():
                if key not in config:
                    config[key] = val
            return config
    except (json.JSONDecodeError, Exception) as e:
        print(f"加载配置失败: {e}，使用默认配置")
        return DEFAULT_CONFIG

def save_config(config: Dict[str, Any]) -> bool:
    """保存split和reply的配置"""
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        print(f"保存配置失败: {e}")
        return False