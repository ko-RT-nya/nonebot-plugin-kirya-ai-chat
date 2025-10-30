from typing import Dict, Callable, Awaitable, List, Union, Tuple
from nonebot.adapters.onebot.v11 import MessageEvent, MessageSegment
from nonebot import get_bot
import os
import json 

# ==================== 管理员配置加载（修改） ====================
DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
ADMIN_CONFIG_FILE = os.path.join(DATA_DIR, "admin_config.json")

# 确保数据目录存在
os.makedirs(DATA_DIR, exist_ok=True)

# 加载管理员配置
def load_admin_config() -> List[str]:
    """从外部文件加载管理员QQ列表"""
    try:
        if not os.path.exists(ADMIN_CONFIG_FILE):
            # 初始化默认配置
            default = {"admin_qq": ["757519749"]}
            with open(ADMIN_CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(default, f, ensure_ascii=False, indent=2)
            return default["admin_qq"]
        
        with open(ADMIN_CONFIG_FILE, "r", encoding="utf-8") as f:
            config = json.load(f)
            return config.get("admin_qq", [])
    except Exception as e:
        print(f"加载管理员配置失败：{str(e)}，使用空列表")
        return []

# 从配置文件加载管理员列表（替代硬编码）
ADMIN_QQ: List[str] = load_admin_config()
# ==============================================================

CommandMetadata = Dict[str, Union[List[str], Callable, str]]
COMMAND_METADATA: Dict[str, CommandMetadata] = {}
COMMAND_ALIASES: Dict[str, str] = {}

def is_admin(user_id: str) -> bool:
    return user_id in ADMIN_QQ

def register_command(
    command: Union[str, List[str]],
    description: str = "",
    usage: str = ""
):
    """注册指令装饰器（支持多别名、描述和用法）"""
    def wrapper(func):
        aliases = [command] if isinstance(command, str) else command
        primary_alias = aliases[0]  # 用第一个别名作为唯一标识
        
        # 存储元数据
        COMMAND_METADATA[primary_alias] = {
            "aliases": aliases,
            "handler": func,
            "description": description,
            "usage": usage
        }
        
        # 注册所有别名
        for alias in aliases:
            COMMAND_ALIASES[alias] = primary_alias
        return func
    return wrapper

async def handle_command(event: MessageEvent, command_text: str) -> bool:
    """解析并执行指令（支持多词指令）"""
    if not command_text.startswith("\\"):
        return False

    command_str = command_text[1:].strip()
    if not command_str:
        await get_bot().send(event, "指令格式错误！请使用 `\\指令名` 格式（如 \\关闭回复）")
        return True

    # 尝试匹配最长可能的指令名（支持多词指令）
    command_name = None
    parts = command_str.split()
    for i in range(len(parts), 0, -1):
        candidate = " ".join(parts[:i])
        if candidate in COMMAND_ALIASES:
            command_name = candidate
            break

    if not command_name:
        await get_bot().send(event, 
            f"指令不存在！可用指令：\n{', '.join(COMMAND_ALIASES.keys())}")
        return True

    # 权限检查
    user_id = str(event.user_id)
    if not is_admin(user_id):
        await get_bot().send(event, 
            MessageSegment.at(user_id) + f" 无权限执行指令 `{command_name}`（仅管理员可操作）")
        return True

    # 执行指令
    primary_alias = COMMAND_ALIASES[command_name]
    metadata = COMMAND_METADATA[primary_alias]
    return await metadata["handler"](event, command_text)

# 导入所有指令模块
from . import prompt, reply, help, model,memory
# 导出get_current_model函数供外部使用
from .model import get_current_model
from . import split