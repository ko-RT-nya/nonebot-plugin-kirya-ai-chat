import os
import json
import re
from typing import Dict, List
from nonebot import get_bot
from nonebot.adapters.onebot.v11 import MessageEvent, MessageSegment
from . import register_command, is_admin
from ..utils.config import load_config, save_config

# 文本分割配置存储路径
DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
SPLIT_CONFIG_FILE = os.path.join(DATA_DIR, "split_config.json")

# 确保数据目录存在
os.makedirs(DATA_DIR, exist_ok=True)

# 默认分割配置
DEFAULT_SPLIT_CONFIG = {
    "enabled": False,  # 默认关闭
    "prompt": "请将你的回答分成多条简短消息，每条消息控制在1-2句话内（一般不多于20字）。"
              "当需要分段时，请用【SPLIT】标记作为每条消息的结束。"
              "确保内容连贯自然，符合QQ聊天场景的交流习惯，避免过长段落。"
}

def is_split_enabled() -> bool:
    """检查文本分割功能是否启用"""
    config = load_config()
    return config.get("split_enabled", False)

# 保留split提示词的独立配置（从split_config.json读取）
def get_split_prompt() -> str:
    """获取文本分割提示词（仍从原文件读取）"""
    DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
    SPLIT_CONFIG_FILE = os.path.join(DATA_DIR, "split_config.json")
    DEFAULT_PROMPT = "请将你的回答分成多条简短消息，每条消息控制在1-2句话内（一般不多于20字）。当需要分段时，请用【SPLIT】标记作为每条消息的结束。确保内容连贯自然，符合QQ聊天场景的交流习惯，避免过长段落。"
    
    try:
        with open(SPLIT_CONFIG_FILE, "r", encoding="utf-8") as f:
            config = json.load(f)
            return config.get("prompt", DEFAULT_PROMPT)
    except Exception:
        return DEFAULT_PROMPT

def split_text(text: str) -> List[str]:
    """根据【SPLIT】标记分割文本（移除标记并处理句尾情况）"""
    if not text:
        return []
    
    # 按标记分割并移除所有残留的标记，同时过滤空内容
    parts = [
        part.replace("【SPLIT】", "").strip()  # 彻底移除标记
        for part in text.split("【SPLIT】") 
        if part.replace("【SPLIT】", "").strip()  # 确保内容非空
    ]
    
    # 如果没有分割标记，作为备选方案自动分割
    if len(parts) == 1:
        auto_split_parts = []
        current_part = ""
        # 按原文本中的标点/空格分割成短句（保留原句标点）
        sentences = re.split(r'([。，,；;！!？?\s])', text)  # 分割并保留分隔符
        sentences = [s for s in sentences if s.strip()]  # 过滤空内容
        
        for sent in sentences:
            # 检查当前段落加上新句子后的长度
            if len(current_part) + len(sent) > 150:  # 超过150字则分割
                if current_part:
                    auto_split_parts.append(current_part)
                current_part = sent
            else:
                current_part += sent
        
        # 添加最后一段
        if current_part:
            auto_split_parts.append(current_part)
        
        return auto_split_parts if auto_split_parts else [text]
    
    return parts

@register_command(
    command=["启用文本分割", "split on"],
    description="启用AI回复文本分割功能（仅管理员）",
    usage="\\启用文本分割 或 \\split on"
)
async def handle_enable_split(event: MessageEvent, _: str) -> bool:
    user_id = str(event.user_id)
    if not is_admin(user_id):
        await get_bot().send(event, "无权限执行此操作（仅管理员可启用文本分割）")
        return True

    config = load_config()
    config["split_enabled"] = True
    if save_config(config):
        await get_bot().send(event, "已启用文本分割功能")
    else:
        await get_bot().send(event, "启用文本分割功能失败（存储错误）")
    return True

@register_command(
    command=["禁用文本分割", "split off"],
    description="禁用AI回复文本分割功能（仅管理员）",
    usage="\\禁用文本分割 或 \\split off"
)
async def handle_disable_split(event: MessageEvent, _: str) -> bool:
    user_id = str(event.user_id)
    if not is_admin(user_id):
        await get_bot().send(event, "无权限执行此操作（仅管理员可禁用文本分割）")
        return True

    config = load_config()
    config["split_enabled"] = False
    if save_config(config):
        await get_bot().send(event, "已禁用文本分割功能")
    else:
        await get_bot().send(event, "禁用文本分割功能失败（存储错误）")
    return True

@register_command(
    command=["查看分割状态", "split status"],
    description="查看文本分割功能当前状态",
    usage="\\查看分割状态 或 \\split status"
)
async def handle_show_split_status(event: MessageEvent, _: str) -> bool:
    config = load_split_config()
    status = "启用" if config.get("enabled", False) else "禁用"
    await get_bot().send(event, f"文本分割功能当前状态：{status}")
    return True

@register_command(
    command=["设置分割提示词", "split setprompt"],
    description="设置文本分割的AI提示词（仅管理员）",
    usage="\\设置分割提示词 提示词内容 或 \\split setprompt 提示词内容"
)
async def handle_set_split_prompt(event: MessageEvent, command_text: str) -> bool:
    user_id = str(event.user_id)
    if not is_admin(user_id):
        await get_bot().send(event, "无权限执行此操作（仅管理员可设置分割提示词）")
        return True

    try:
        _, prompt_content = command_text.split(" ", 1)
        prompt_content = prompt_content.strip()
        
        if not prompt_content:
            raise ValueError("提示词内容不能为空")
        
        config = load_split_config()
        config["prompt"] = prompt_content
        
        if save_split_config(config):
            await get_bot().send(event, "已更新文本分割提示词")
        else:
            await get_bot().send(event, "更新文本分割提示词失败（存储错误）")
        return True
    except ValueError as e:
        await get_bot().send(event, f"格式错误！正确格式：\\设置分割提示词 提示词内容\n错误：{str(e)}")
        return True

@register_command(
    command=["查看分割提示词", "split showprompt"],
    description="查看当前文本分割的AI提示词",
    usage="\\查看分割提示词 或 \\split showprompt"
)
async def handle_show_split_prompt(event: MessageEvent, _: str) -> bool:
    config = load_split_config()
    prompt = config.get("prompt", DEFAULT_SPLIT_CONFIG["prompt"])
    await get_bot().send(event, f"当前文本分割提示词：\n{prompt}")
    return True

@register_command(
    command=["重置分割提示词", "split resetprompt"],
    description="重置文本分割提示词为默认值（仅管理员）",
    usage="\\重置分割提示词 或 \\split resetprompt"
)
async def handle_reset_split_prompt(event: MessageEvent, _: str) -> bool:
    user_id = str(event.user_id)
    if not is_admin(user_id):
        await get_bot().send(event, "无权限执行此操作（仅管理员可重置分割提示词）")
        return True

    config = load_split_config()
    config["prompt"] = DEFAULT_SPLIT_CONFIG["prompt"]
    
    if save_split_config(config):
        await get_bot().send(event, "已重置文本分割提示词为默认值")
    else:
        await get_bot().send(event, "重置文本分割提示词失败（存储错误）")
    return True