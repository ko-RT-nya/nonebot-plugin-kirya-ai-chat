# gemini_adapter/commands/model.py
import os
import json
from typing import Dict, Optional
from nonebot import get_bot
from nonebot.adapters.onebot.v11 import MessageEvent
from . import register_command, is_admin
from ..models.model_factory import ModelFactory

# 模型配置存储路径
DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
MODEL_CONFIG_FILE = os.path.join(DATA_DIR, "model_config.json")

# 确保数据目录存在
os.makedirs(DATA_DIR, exist_ok=True)

# 默认模型配置
DEFAULT_MODEL_CONFIG = {
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
    }
}

def load_model_config() -> Dict[str, any]:
    """加载模型配置（支持完全自定义模型列表）"""
    try:
        if not os.path.exists(MODEL_CONFIG_FILE):
            # 初始化默认配置（仅首次运行时）
            with open(MODEL_CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(DEFAULT_MODEL_CONFIG, f, ensure_ascii=False, indent=2)
            return DEFAULT_MODEL_CONFIG
            
        with open(MODEL_CONFIG_FILE, "r", encoding="utf-8") as f:
            config = json.load(f)
            # 兼容旧配置：如果缺少必要字段，补充默认值
            if "models" not in config:
                config["models"] = DEFAULT_MODEL_CONFIG["models"]
            if "current_model" not in config:
                config["current_model"] = next(iter(config["models"].keys()))  # 默认第一个模型
            if "api_keys" not in config:
                config["api_keys"] = {}
            if "cooldowns" not in config:
                config["cooldowns"] = {}
            return config
    except (json.JSONDecodeError, Exception) as e:
        print(f"加载模型配置失败：{str(e)}，使用默认配置")
        return DEFAULT_MODEL_CONFIG

def save_model_config(config: Dict[str, any]) -> bool:
    """保存模型配置"""
    try:
        with open(MODEL_CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        print(f"保存模型配置失败：{str(e)}")
        return False

@register_command(
    command=["切换模型", "model switch"],
    description="切换使用的AI模型（仅管理员）",
    usage="\\切换模型 模型ID 或 \\model switch 模型ID（如：\\切换模型 gemini-2.5-flash）"
)
async def handle_switch_model(event: MessageEvent, command_text: str) -> bool:
    """处理切换模型指令"""
    user_id = str(event.user_id)
    if not is_admin(user_id):
        await get_bot().send(event, "无权限执行此操作（仅管理员可切换模型）")
        return True

    try:
        # 修复：使用split()分割所有空格（支持多个空格/全角空格），取第三个元素作为模型ID
        parts = command_text.split()
        if len(parts) < 2:
            raise ValueError("缺少模型ID")
        model_id = parts[2].strip()  # 指令格式：\切换模型 模型ID → parts[0]是'\切换模型', parts[1]是模型ID
        
        config = load_model_config()
        if model_id not in config["models"]:
            models_list = "\n".join([f"- {k}: {v}" for k, v in config["models"].items()])
            await get_bot().send(event, f"模型ID不存在！可用模型：\n{models_list}")
            return True
        
        config["current_model"] = model_id
        if save_model_config(config):
            await get_bot().send(event, 
                f"已切换模型为：{model_id}（{config['models'][model_id]}）")
        else:
            await get_bot().send(event, "切换模型失败（存储错误）")
        return True
    except ValueError as e:
        await get_bot().send(event, 
            f"格式错误！正确格式：\\切换模型 模型ID（如 \\切换模型 gemini-2.5-flash）\n错误：{str(e)}")
        return True

@register_command(
    command=["查看当前模型", "model current"],
    description="查看当前使用的AI模型",
    usage="\\查看当前模型 或 \\model current"
)
async def handle_show_current_model(event: MessageEvent, _: str) -> bool:
    """查看当前模型指令"""
    config = load_model_config()
    current = config["current_model"]
    models_list = "\n".join([f"- {k}: {v}" for k, v in config["models"].items()])
    await get_bot().send(event, 
        f"当前使用模型：{current}（{config['models'][current]}）\n\n可用模型列表：\n{models_list}")
    return True

@register_command(
    command=["设置模型密钥", "model setkey"],
    description="设置模型API密钥（仅管理员）",
    usage="\\设置模型密钥 模型ID 密钥 或 \\model setkey 模型ID 密钥"
)
async def handle_set_api_key(event: MessageEvent, command_text: str) -> bool:
    """设置模型API密钥"""
    user_id = str(event.user_id)
    if not is_admin(user_id):
        await get_bot().send(event, "无权限执行此操作（仅管理员可设置密钥）")
        return True

    try:
        _, model_id, api_key = command_text.split(" ", 2)
        model_id = model_id.strip()
        api_key = api_key.strip()
        
        if not model_id or not api_key:
            raise ValueError
        
        config = load_model_config()
        supported_models = ModelFactory.get_supported_models()
        if model_id not in supported_models:
            await get_bot().send(event, f"模型ID不存在！支持的模型：{', '.join(supported_models.keys())}")
            return True
        
        if "api_keys" not in config:
            config["api_keys"] = {}
        config["api_keys"][model_id] = api_key
        
        if save_model_config(config):
            await get_bot().send(event, f"已设置 {model_id} 的API密钥")
        else:
            await get_bot().send(event, "设置密钥失败（存储错误）")
        return True
    except ValueError:
        await get_bot().send(event, "格式错误！正确格式：\\设置模型密钥 模型ID 密钥")
        return True

@register_command(
    command=["设置模型冷却时间", "model cooldown"],
    description="设置模型冷却时间(秒)（仅管理员）",
    usage="\\设置模型冷却时间 模型ID 秒数 或 \\model cooldown 模型ID 秒数"
)
async def handle_set_cooldown(event: MessageEvent, command_text: str) -> bool:
    """设置模型冷却时间"""
    user_id = str(event.user_id)
    if not is_admin(user_id):
        await get_bot().send(event, "无权限执行此操作（仅管理员可设置冷却时间）")
        return True

    try:
        _, model_id, seconds_str = command_text.split(" ", 2)
        model_id = model_id.strip()
        seconds = int(seconds_str.strip())
        
        if seconds < 1:
            raise ValueError("冷却时间必须为正整数")
        
        config = load_model_config()
        supported_models = ModelFactory.get_supported_models()
        if model_id not in supported_models:
            await get_bot().send(event, f"模型ID不存在！支持的模型：{', '.join(supported_models.keys())}")
            return True
        
        if "cooldowns" not in config:
            config["cooldowns"] = {}
        config["cooldowns"][model_id] = seconds
        
        if save_model_config(config):
            await get_bot().send(event, f"已设置 {model_id} 的冷却时间为 {seconds} 秒")
        else:
            await get_bot().send(event, "设置冷却时间失败（存储错误）")
        return True
    except ValueError as e:
        await get_bot().send(event, f"格式错误！正确格式：\\设置模型冷却时间 模型ID 秒数（正整数）\n错误：{str(e)}")
        return True

def get_current_model() -> str:
    """获取当前模型ID（供主程序调用）"""
    config = load_model_config()
    return config["current_model"]